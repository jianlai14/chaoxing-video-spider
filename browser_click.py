# -*- coding: utf-8 -*-
"""
用 Playwright 驱动 Edge 打开章节页，点一次播放按钮，验证视频是否真的开始播放。

默认只做单次点击与状态读取，不改进度、不动上报；--stay 时进入挂机保持播放。

首次运行会创建独立 profile（默认 ~/.chaoxing_edge_profile），
因为没有登录态，会停在登录页等你手动扫码；登录一次后 profile 记住，后续免登录。

用法：
  python browser_click.py                  # 打开章节页 -> 点一次 -> 打印结论
  python browser_click.py --keep           # 验证完不关浏览器
  python browser_click.py --stay           # 验证完挂机：保持播放+自动续播，Ctrl+C 结束
  python browser_click.py --playlist out/videos_array.json
                                           # 按 JSON 清单逐个观看（一次只看一个），
                                           # 每集等 时长+余量 秒再进下一集
  python browser_click.py --playlist out/videos_array.json --margin 30
                                           # 余量改为 30 秒（默认 15）
  python browser_click.py --headless       # 无界面（无登录态时无法手动登录）
  python browser_click.py --login-wait 120 # 等登录的秒数，默认 180
"""
import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import config
from fetch_videos import study_referer

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROFILE = Path.home() / ".chaoxing_edge_profile"
IS_LOGIN = ("用户登录", "loginForm", "passport2")


def wait_player_frame(page, timeout=60):
    """在所有 frame 里找含播放按钮的那个（视频在 insertvideo iframe 内）"""
    end = time.time() + timeout
    while time.time() < end:
        for f in page.frames:
            try:
                if f.locator(".vjs-big-play-button").count() > 0:
                    return f
            except Exception:
                continue
        page.wait_for_timeout(800)
    return None


def read_state(frame):
    return frame.evaluate("""() => {
        const v = document.querySelector('video');
        if (!v) return null;
        return {
            t: +v.currentTime.toFixed(2),
            paused: v.paused,
            ended: v.ended,
            readyState: v.readyState,
            muted: v.muted,
            duration: v.duration,
            error: v.error ? v.error.code : 0
        };
    }""")


def click_play(page, frame):
    """点一次播放按钮；若仍暂停则静音重试。返回 (点击后的状态, 是否动用了静音)"""
    btn = frame.locator(".vjs-big-play-button")
    try:
        btn.wait_for(state="visible", timeout=15000)
        btn.click()
    except PWTimeout:
        print("    常规点击超时，改用强制点击")
        btn.click(force=True)

    page.wait_for_timeout(2500)
    s1 = read_state(frame)

    need_mute = False
    if s1 and s1["paused"]:
        need_mute = True
        print("    仍在暂停，静音后重试")
        frame.evaluate("""() => {
            const v = document.querySelector('video');
            if (v) v.muted = true;
        }""")
        try:
            btn.click(force=True)
        except Exception:
            frame.evaluate("document.querySelector('video').play()")
        page.wait_for_timeout(2500)
        s1 = read_state(frame)
    return s1, need_mute


def stay_playing(frame, page):
    """挂机：视频保持播放，被暂停（弹题/播放策略等）就自动续播，Ctrl+C 结束"""
    print("\n[4] 挂机中：每 5 秒检查一次，被暂停就自动续播，Ctrl+C 结束")
    ticks = 0
    ended_reported = False
    try:
        while True:
            page.wait_for_timeout(5000)
            try:
                s = read_state(frame)
            except Exception:
                nf = wait_player_frame(page, timeout=10)
                if nf is None:
                    print("[x] 播放器 frame 已失效（页面可能跳转了），停止挂机")
                    return
                frame, ended_reported = nf, False
                print("[i] 重新定位到播放器 frame，继续挂机")
                continue
            if not s:
                continue
            if s["ended"]:
                if not ended_reported:
                    print(f"[✓] 本视频已播完（{s['duration']:.0f}s），进程继续挂着，Ctrl+C 退出")
                    ended_reported = True
                continue
            if s["paused"]:
                try:
                    frame.evaluate("document.querySelector('video').play()")
                    print(f"    {s['t']:.0f}s 处被暂停 -> 已自动续播")
                except Exception:
                    pass
                continue
            ticks += 1
            if ticks % 12 == 0:
                print(f"    进度 {s['t']:.0f}s / {s['duration']:.0f}s")
    except KeyboardInterrupt:
        print("\n手动中断，退出挂机")


def watch_to_deadline(frame, page, wait_sec):
    """挂机等待一集：被暂停就续播，播完提前结束。返回 '播完'/'等待期满'/'丢失'"""
    deadline = time.time() + wait_sec
    last_log = 0.0
    while time.time() < deadline:
        page.wait_for_timeout(5000)
        try:
            s = read_state(frame)
        except Exception:
            nf = wait_player_frame(page, timeout=10)
            if nf is None:
                return "丢失"
            frame = nf
            continue
        if not s:
            continue
        if s["ended"]:
            print(f"    [✓] 已播完（{s['t']:.0f}s），提前进入下一个")
            return "播完"
        if s["paused"]:
            try:
                frame.evaluate("document.querySelector('video').play()")
                print(f"    {s['t']:.0f}s 处被暂停 -> 已自动续播")
            except Exception:
                pass
            continue
        now = time.time()
        if now - last_log >= 60:
            print(f"    播放中 {s['t']:.0f}s / {s['duration']:.0f}s")
            last_log = now
    return "等待期满"


def run_playlist(page, vids, margin, skip_passed=False):
    """按清单逐个观看：一次只开一个，点击后等 时长+margin 秒"""
    results = []
    try:
        for i, v in enumerate(vids, 1):
            kid = v.get("section_id") or ""
            name = v.get("name") or "(未命名)"
            dur = int(v.get("duration_sec") or 0)
            print(f"\n=== [{i}/{len(vids)}] {name[:56]}  时长 {v.get('duration', '?')} ===")
            if not kid:
                print(f"    [x] 缺 section_id，跳过（该条目字段: {sorted(v.keys())}）")
                results.append((name, "跳过"))
                continue
            if skip_passed and v.get("is_passed"):
                print("    已完成（isPassed=true），跳过")
                results.append((name, "已完成"))
                continue
            page.goto(study_referer(kid), wait_until="domcontentloaded", timeout=60000)
            frame = wait_player_frame(page, timeout=60)
            if not frame:
                print("    [x] 没找到播放器，跳过")
                results.append((name, "无播放器"))
                continue
            click_play(page, frame)
            wait_sec = dur + margin
            print(f"    点击完成，挂机 {wait_sec}s（时长 {dur}s + 余量 {margin}s）")
            status = watch_to_deadline(frame, page, wait_sec)
            print(f"    本集结束: {status}")
            results.append((name, status))
    except KeyboardInterrupt:
        print("\n手动中断，收尾 ...")

    print("\n===== 汇总 =====")
    ok = sum(1 for _, st in results if st in ("播完", "等待期满", "已完成"))
    for i, (name, st) in enumerate(results, 1):
        print(f"  {i:>2}. [{st}] {name[:60]}")
    print(f"\n处理 {len(results)} 集：正常 {ok}，异常 {len(results) - ok}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="验证完保持浏览器打开")
    ap.add_argument("--stay", action="store_true",
                    help="验证完挂机：保持播放、被暂停自动续播，Ctrl+C 结束")
    ap.add_argument("--playlist", default="",
                    help="JSON 清单路径（如 out/videos_array.json），逐个观看")
    ap.add_argument("--margin", type=int, default=15,
                    help="清单模式下每集在时长基础上多等的秒数（默认 15）")
    ap.add_argument("--skip-passed", action="store_true",
                    help="跳过清单里 isPassed=true 的已完成视频")
    ap.add_argument("--headless", action="store_true", help="无界面模式")
    ap.add_argument("--login-wait", type=int, default=180, help="等待手动登录的秒数")
    ap.add_argument("--autoplay", action="store_true",
                    help="给浏览器加 --autoplay-policy=no-user-gesture-required")
    ap.add_argument("--no-cookies", action="store_true",
                    help="不注入 config.py 的 cookie，纯靠 profile 里的登录态")
    args = ap.parse_args()

    PROFILE.mkdir(parents=True, exist_ok=True)

    vids = []
    if args.playlist:
        with open(args.playlist, encoding="utf-8") as f:
            vids = json.load(f)
        if isinstance(vids, dict):          # 兼容 videos_full.json 的 {"videos": [...]}
            vids = vids.get("videos", [])
        # 兼容两份 JSON 的字段命名（section_id/sectionId、name/video_name 等）
        vids = [{"section_id": v.get("section_id") or v.get("sectionId") or "",
                 "name": v.get("name") or v.get("video_name") or "(未命名)",
                 "duration_sec": int(v.get("duration_sec") or 0),
                 "duration": v.get("duration") or v.get("duration_hms") or "?",
                 "is_passed": str(v.get("isPassed", v.get("is_passed", ""))).lower()
                              in ("true", "1")}
                for v in vids]
        if not vids:
            print(f"[x] 清单 {args.playlist} 为空或格式不对")
            return 1
        total_min = sum(int(v.get("duration_sec") or 0) for v in vids) // 60
        print(f"清单    : {args.playlist}（{len(vids)} 个视频，约 {total_min} 分钟）")
        url = study_referer(vids[0].get("section_id") or config.CHAPTER_ID)
    else:
        url = study_referer(config.CHAPTER_ID)
    print(f"profile : {PROFILE}")
    print(f"目标页  : {url[:110]}...")

    with sync_playwright() as p:
        launch_args = ["--disable-blink-features=AutomationControlled"]
        if args.autoplay:
            launch_args.append("--autoplay-policy=no-user-gesture-required")

        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            channel="msedge",                     # 直接用系统装的 Edge，不用另下浏览器
            headless=args.headless,
            args=launch_args,
            viewport={"width": 1600, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 先把 config.py 里的 cookie 灌进去，通常就不用手动登录了
        if not args.no_cookies:
            jar = [{"name": k, "value": v, "domain": ".chaoxing.com", "path": "/"}
                   for k, v in config.COOKIES.items() if v]
            try:
                ctx.add_cookies(jar)
                print(f"    已注入 {len(jar)} 条 cookie")
            except Exception as e:
                print(f"    cookie 注入失败: {e}")

        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # 1) 登录态检查
        body = page.content()[:5000]
        if any(k in body for k in IS_LOGIN):
            print(f"\n[!] 当前 profile 没有登录态。请在打开的窗口里手动登录，")
            print(f"    最多等 {args.login_wait} 秒 ...")
            end = time.time() + args.login_wait
            while time.time() < end:
                page.wait_for_timeout(2000)
                if not any(k in page.content()[:5000] for k in IS_LOGIN):
                    print("[+] 登录完成")
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    break
            else:
                print("[x] 等待超时，退出")
                if not args.keep:
                    ctx.close()
                return 1

        # 清单模式：逐个观看，不走下面的单发验证
        if args.playlist:
            results = run_playlist(page, vids, args.margin, args.skip_passed)
            if results and all(st not in ("播完", "等待期满", "已完成")
                               for _, st in results) \
                    and not args.headless:
                input("\n[!] 没有一集正常观看，看完上面的输出后按回车关闭浏览器 ...")
            if args.keep:
                print("\n浏览器保持打开，手动关闭窗口即可结束。")
                input("按回车退出 ...")
            ctx.close()
            return 0

        # 2) 找播放器 frame
        print("\n[1] 定位播放器 ...")
        frame = wait_player_frame(page, timeout=60)
        if not frame:
            print("[x] 没找到播放按钮。确认本章节确实有视频、且页面已加载完。")
            if not args.keep:
                ctx.close()
            return 1
        print(f"    命中 frame: {frame.url[:100]}")

        s0 = read_state(frame)
        print(f"    初始状态: {s0}")

        # 3) 点一次播放按钮
        print("\n[2] 点击 .vjs-big-play-button")
        s1, need_mute = click_play(page, frame)

        # 4) 再观察 2.5 秒，确认时间轴真的在走
        page.wait_for_timeout(2500)
        s2 = read_state(frame)

        if not s1 or not s2:
            print("[x] 读不到 video 状态")
            if not args.keep:
                ctx.close()
            return 1

        advancing = (s2["t"] - s1["t"]) > 0.5
        print(f"\n[3] 结果  第一次点击后 {s1}")
        print(f"          2.5 秒后   {s2}")
        print(f"          时间轴 {s1['t']}s -> {s2['t']}s   {'在走' if advancing else '没走'}")
        print(f"          是否需静音: {'是' if need_mute else '否'}")

        if advancing:
            print("\n[✓] 结论：可播放")
        elif s2["paused"]:
            print(f"\n[✗] 结论：点不动（error={s2['error']}）")
        else:
            print("\n[✗] 结论：已解除暂停但时间不走（缓冲或源失效）")

        if args.keep:
            print("\n浏览器保持打开，手动关闭窗口即可结束。")
            input("按回车退出 ...")
        elif args.stay:
            stay_playing(frame, page)
        ctx.close()
        return 0 if advancing else 1


if __name__ == "__main__":
    sys.exit(main())
