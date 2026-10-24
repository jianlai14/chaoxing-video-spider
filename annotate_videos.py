# -*- coding: utf-8 -*-
"""
把 out/videos.json 里只有地址的粗表，补成一份完整可查的视频清单。

  1) 按 sectionId 分组，每个小节回 /knowledge/cards 取一次 mArg
  2) 从 mArg 里补出：播放器页地址、进度上报地址、attDuration、限制开关
  3) 合并出 out/videos_full.json + out/VIDEO_INDEX.md

用法：
  python annotate_videos.py
  python annotate_videos.py --delay 0.5
"""
import argparse
import glob
import json
import os
import sys
import time
import warnings
from collections import OrderedDict

import config
from probe_player import (make_session, fetch_cards_html, parse_marg,
                          player_url)

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def hms(sec):
    if not sec:
        return ""
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def human_size(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


def switches(prop, d):
    """把三个限制开关翻译成人话"""
    def on(v):
        return str(v).lower() in ("true", "1")

    ff = "开" if on(prop.get("fastforward", True)) else "关"
    sw = "开" if on(prop.get("switchwindow", True)) else "关"
    ds = "允许" if on(prop.get("doublespeed", 0)) else "禁"
    return f"防拖拽={ff}　防切窗={sw}　倍速={ds}"


def collect(session, videos, delay):
    """按小节拉 mArg，返回 {sectionId: (defaults, {objectid: attachment})}"""
    kids = list(OrderedDict.fromkeys(v["sectionId"] for v in videos))
    info = {}
    for i, kid in enumerate(kids, 1):
        try:
            arg = parse_marg(fetch_cards_html(session, kid))
        except Exception as e:
            print(f"  [{i}/{len(kids)}] {kid} 失败: {type(e).__name__} {e}")
            continue
        if not arg:
            print(f"  [{i}/{len(kids)}] {kid} 未解析到 mArg")
            continue
        atts = {a.get("objectId") or a.get("objectid"): a
                for a in arg.get("attachments", []) if a}
        info[kid] = (arg.get("defaults", {}), atts)
        print(f"  [{i}/{len(kids)}] {kid} ok  attachments={len(atts)}")
        time.sleep(delay)
    return info


def parse_size(s):
    """'54.15 MB' -> 56770560"""
    try:
        num, unit = str(s).split()
        return int(float(num) * {"B": 1, "KB": 1024, "MB": 1024 ** 2,
                                 "GB": 1024 ** 3}[unit.upper()])
    except Exception:
        return 0


def to_bool(v):
    return str(v).lower() in ("true", "1")


def build(videos, info):
    rows = []
    for i, v in enumerate(videos, 1):
        d, atts = info.get(v["sectionId"], ({}, {}))
        att = atts.get(v["objectid"], {})
        prop = att.get("property", {})
        dur = att.get("attDuration") or 0
        tx = glob.glob(f"out/transcripts/{i:02d}_*.txt")
        sr = glob.glob(f"out/transcripts/{i:02d}_*.srt")
        rows.append({
            **v,
            "no": i,
            "duration_sec": dur,
            "duration_hms": hms(dur),
            "size_bytes": parse_size(v.get("size")),
            "isPassed": att.get("isPassed", v.get("isPassed", "")),
            "player_url": player_url(v["objectid"], prop.get("jobid", v.get("jobid", ""))),
            "report_url": d.get("reportUrl", ""),
            "report_interval": d.get("reportTimeInterval", ""),
            "init_url": d.get("initdataUrl", ""),
            "subtitle_url": d.get("subtitleUrl", ""),
            "mid": att.get("mid", ""),
            "aid": att.get("aid", ""),
            "switches": switches(prop, d),
            "fastforward": to_bool(prop.get("fastforward", True)),
            "switchwindow": to_bool(prop.get("switchwindow", True)),
            "doublespeed": to_bool(prop.get("doublespeed", 0)),
            "attDurationEnc": att.get("attDurationEnc", ""),
            "otherInfo": att.get("otherInfo", ""),
            "transcript_txt": tx[0].replace(os.sep, "/") if tx else "",
            "transcript_srt": sr[0].replace(os.sep, "/") if sr else "",
        })
    return rows


def to_markdown(rows):
    total_sec = sum(r["duration_sec"] for r in rows)
    total_size = 0
    for r in rows:
        try:
            total_size += float(str(r.get("size", "")).split()[0]) * (
                1024 ** 3 if "GB" in str(r.get("size", "")) else 1024 ** 2)
        except Exception:
            pass

    out = []
    out.append("# 课程视频清单\n")
    out.append(f"- 课程：courseId `{config.COURSE_ID}`　"
               f"clazzId `{config.CLAZZ_ID}`　cpi `{config.CPI}`")
    out.append(f"- 视频数：**{len(rows)}**　"
               f"总时长：**{hms(total_sec)}**（{total_sec} 秒）　"
               f"原片合计：约 **{human_size(total_size)}**")
    out.append(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M')}")
    out.append("\n> mp4 / mp3 / 下载 地址均带签名（`at_`/`ak_`/`ad_`），有时效。"
               "过期后重跑 `fetch_videos.py` 换新。\n")
    out.append("> 所有地址都必须带 Referer 访问："
               "`Referer: https://mooc1.chaoxing.com/ananas/modules/video/index.html"
               "?objectid=<objectid>&jobid=<jobid>`\n")

    cur_ch, cur_sec = None, None
    n = 0
    for r in rows:
        n += 1
        ch = (r["chapter"] or "(未分组)").strip()
        sec = (r["section"] or "(未命名小节)").strip()
        if ch != cur_ch:
            cur_ch, cur_sec = ch, None
            out.append(f"\n## {ch}\n")
        if sec != cur_sec:
            cur_sec = sec
            out.append(f"\n### {sec}\n")

        out.append(f"#### {n}. {r['video_name'].strip()}\n")
        out.append("| 项 | 内容 |")
        out.append("|---|---|")
        dur_txt = f"{r['duration']}（{r['duration_sec']} 秒）" \
            if r["duration_sec"] else r["duration"]
        if r["duration_sec"] and r["duration_sec"] >= 3600:
            dur_txt = f"{r['duration']}（{r['duration_sec']} 秒 / {r['duration_hms']}）"
        out.append(f"| 时长 | {dur_txt} |")
        out.append(f"| 大小 | {r['size']}（原片） |")
        out.append(f"| objectid | `{r['objectid']}` |")
        out.append(f"| jobid | `{r['jobid']}` |")
        if r["mid"]:
            out.append(f"| mid | `{r['mid']}` |")
        out.append(f"| 播放器页 | `{r['player_url']}` |")
        out.append(f"| 播放地址 | `{r['mp4_sd'] or '—'}` |")
        out.append(f"| 下载地址 | `{r['download'] or '—'}` |")
        out.append(f"| 音频(mp3) | `{r['mp3'] or '—'}` |")
        out.append(f"| 视频截图 | `{r['screenshot'] or '—'}` |")
        out.append(f"| 上报接口 | `{r['report_url'] or '—'}`　"
                   f"（每 {r['report_interval'] or '?'} 秒一次） |")
        out.append(f"| 限制开关 | {r['switches'] or '—'} |")
        tx = r.get("transcript_txt", "")
        sr = r.get("transcript_srt", "")
        if tx:
            out.append(f"| 文字稿 | `{tx}` |")
        if sr:
            out.append(f"| 字幕 | `{sr}` |")
        out.append("")
    return "\n".join(out)


# 结构体数组的字段定义：输出名 -> 内部字段名
ARRAY_MAP = OrderedDict([
    ("no", "no"),
    ("chapter", "chapter"),
    ("chapter_id", "chapterId"),
    ("section", "section"),
    ("section_id", "sectionId"),
    ("name", "video_name"),
    ("duration", "duration"),
    ("duration_sec", "duration_sec"),
    ("size_text", "size"),
    ("size_bytes", "size_bytes"),
    ("objectid", "objectid"),
    ("jobid", "jobid"),
    ("is_passed", "isPassed"),
    ("mid", "mid"),
    ("player_url", "player_url"),
    ("play_url", "mp4_sd"),
    ("download_url", "download"),
    ("mp3_url", "mp3"),
    ("screenshot_url", "screenshot"),
    ("report_url", "report_url"),
    ("report_interval", "report_interval"),
    ("fastforward", "fastforward"),
    ("switchwindow", "switchwindow"),
    ("doublespeed", "doublespeed"),
    ("transcript_txt", "transcript_txt"),
    ("transcript_srt", "transcript_srt"),
])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.4, help="每个小节的请求间隔")
    ap.add_argument("--from-cache", action="store_true",
                    help="复用 out/videos_full.json，不重新请求 cards")
    args = ap.parse_args()

    with open("out/videos.json", encoding="utf-8") as f:
        data = json.load(f)
    videos = data.get("videos", [])
    if not videos:
        print("out/videos.json 里没有视频，先跑 fetch_videos.py")
        return 1

    if args.from_cache and os.path.exists("out/videos_full.json"):
        print("[1] 命中缓存 out/videos_full.json，跳过网络请求")
        with open("out/videos_full.json", encoding="utf-8") as f:
            rows = json.load(f).get("videos", [])
    else:
        print(f"[1] 读取 {len(videos)} 条视频，开始补齐 cards 配置 ...")
        session = make_session()
        info = collect(session, videos, args.delay)
        print("\n[2] 合并字段 ...")
        rows = build(videos, info)

    os.makedirs("out", exist_ok=True)
    # 目录里部分名称带前导空格，统一去掉（缓存路径也走这里）
    for r in rows:
        for k in ("chapter", "section", "video_name"):
            if isinstance(r.get(k), str):
                r[k] = r[k].strip()
    payload = {
        "course": data.get("course"), "clazz": data.get("clazz"),
        "cpi": data.get("cpi"),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_videos": len(rows),
        "total_duration_sec": sum(r["duration_sec"] for r in rows),
        "videos": rows,
    }
    with open("out/videos_full.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 结构体数组：纯数组，元素字段与顺序固定
    struct_arr = [{k: r.get(src, "") for k, src in ARRAY_MAP.items()} for r in rows]
    with open("out/videos_array.json", "w", encoding="utf-8") as f:
        json.dump(struct_arr, f, ensure_ascii=False, indent=2)

    md = to_markdown(rows)
    with open("out/VIDEO_INDEX.md", "w", encoding="utf-8") as f:
        f.write(md)

    # 顺手出一份 Excel 友好表
    import csv
    cols = [("chapter", "章"), ("chapterId", "章ID"), ("section", "小节"),
            ("sectionId", "小节ID"), ("video_name", "视频名"),
            ("duration", "时长"), ("duration_sec", "时长(秒)"), ("size", "大小"),
            ("objectid", "objectid"), ("jobid", "jobid"), ("mid", "mid"),
            ("player_url", "播放器页"), ("mp4_sd", "播放地址"),
            ("download", "下载地址"), ("mp3", "音频"), ("screenshot", "截图"),
            ("report_url", "上报接口"), ("report_interval", "上报间隔(秒)"),
            ("switches", "限制开关")]
    with open("out/videos_full.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["序号"] + [c[1] for c in cols])
        for i, r in enumerate(rows, 1):
            w.writerow([i] + [r.get(k, "") for k, _ in cols])

    miss = [r["objectid"] for r in rows if not r["report_url"]]
    print(f"    out/videos_full.json   {len(rows)} 条")
    print(f"    out/videos_array.json  {len(struct_arr)} 条 × {len(ARRAY_MAP)} 字段")
    print(f"    out/VIDEO_INDEX.md     {len(md)} 字符")
    if miss:
        print(f"    ! {len(miss)} 条没补到 mArg：{miss[:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
