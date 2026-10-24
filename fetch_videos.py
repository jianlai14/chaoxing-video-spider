# -*- coding: utf-8 -*-
"""
学习通（超星）课程视频地址抓取

  1) /mycourse/studentstudycourselist  -> 整门课目录（章 -> 小节 knowledgeId）
  2) /mooc-ans/knowledge/cards         -> 小节内容 HTML，含 <iframe module="insertvideo" data="{...objectid...}">
  3) /ananas/status/<objectid>         -> 真实播放地址（sd.mp4 / download / duration / filename）

输出：out/videos.csv  out/videos.json  out/videos.txt

用法：
  python fetch_videos.py            # 抓整门课
  python fetch_videos.py --only-chapter 100000004   # 只抓某一章/小节
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

import config

try:  # 控制台可能是 GBK，强制 UTF-8 输出避免符号报错
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "https://mooc1.chaoxing.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    for k, v in config.COOKIES.items():
        if v:
            s.cookies.set(k, v, domain=".chaoxing.com")
    return s


def study_referer(knowledge_id):
    return (f"{BASE}/mycourse/studentstudy?chapterId={knowledge_id}"
            f"&courseId={config.COURSE_ID}&clazzid={config.CLAZZ_ID}"
            f"&cpi={config.CPI}&enc={config.ENC}&mooc2=1&hidetype=0&fanyaVersion=0"
            + (f"&openc={config.OPENC}" if config.OPENC else ""))


def is_login(text):
    head = text[:3000]
    return "用户登录" in head or 'id="loginForm"' in head or "loginBtn" in head


def get_catalog(s):
    """返回 [{chapter, chapterId, sections:[{title, code, knowledgeId}]}]"""
    r = s.get(f"{BASE}/mycourse/studentstudycourselist",
              params={"courseId": config.COURSE_ID, "clazzid": config.CLAZZ_ID,
                      "cpi": config.CPI, "enc": config.ENC, "s": "", "mooc2": 1},
              headers={"Referer": study_referer(config.CHAPTER_ID)}, timeout=30)
    r.raise_for_status()
    if is_login(r.text):
        raise RuntimeError("Cookie 已失效：目录接口返回登录页")

    soup = BeautifulSoup(r.text, "html.parser")
    chapters, current = [], None
    # 一级：div.posCatalog_select.firstLayer ；二级：div.posCatalog_select#curXXXX 内含 getTeacherAjax
    for div in soup.find_all("div", class_="posCatalog_select"):
        classes = div.get("class") or []
        onclick = None
        node_title = None
        name_span = div.find("span", class_="posCatalog_name")
        title_span = div.find("span", class_="posCatalog_title")
        span = name_span or title_span
        if span:
            onclick = span.get("onclick") or ""
            node_title = (span.get("title") or span.get_text(" ", strip=True))
        m = re.search(r"getTeacherAjax\('(\d+)','(\d+)','(\d+)'\)", str(onclick))
        if "firstLayer" in classes and not m:
            current = {"chapterId": div.get("id", ""), "chapter": node_title or "", "sections": []}
            chapters.append(current)
            continue
        if m:
            sec = {"knowledgeId": m.group(3), "title": node_title or ""}
            if current is None:
                current = {"chapterId": "", "chapter": "(未分组)", "sections": []}
                chapters.append(current)
            current["sections"].append(sec)
    # 若目录里没有一级标题，退化成扁平列表
    if not chapters:
        chapters = [{"chapterId": "", "chapter": "", "sections": []}]
    total = sum(len(c["sections"]) for c in chapters)
    if total == 0:
        raise RuntimeError("目录解析为空，页面结构可能已变化，请检查 courselist 输出")
    return chapters


def get_videos_of_section(s, knowledge_id):
    """小节 cards -> 视频条目 [{name, objectid, jobid, size, type}]"""
    params = {
        "clazzid": config.CLAZZ_ID, "courseid": config.COURSE_ID,
        "knowledgeid": knowledge_id, "num": 0, "ut": "s", "cpi": config.CPI,
        "v": time.strftime("%Y-%m%d-%H%M"), "mooc2": 1,
        "isMicroCourse": "false", "editorPreview": 0,
    }
    r = s.get(f"{BASE}/mooc-ans/knowledge/cards", params=params,
              headers={"Referer": study_referer(knowledge_id)}, timeout=30)
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}"
    if is_login(r.text):
        raise RuntimeError(f"Cookie 已失效（小节 {knowledge_id} 返回登录页）")

    vids = []
    soup = BeautifulSoup(r.text, "html.parser")
    for ifr in soup.find_all("iframe"):
        module = (ifr.get("module") or "").lower()
        typ = (ifr.get("type") or "").lower()
        data = ifr.get("data")
        if module == "insertvideo" or typ == "online":
            d = {}
            if data:
                try:
                    d = json.loads(data)
                except (ValueError, TypeError):
                    d = {}
            oid = d.get("objectid") or ifr.get("objectid") or ""
            if oid:
                vids.append({
                    "name": d.get("name") or "",
                    "objectid": oid,
                    "jobid": d.get("jobid") or d.get("_jobid") or "",
                    "size": d.get("size") or "",
                    "hsize": d.get("hsize") or "",
                    "type": d.get("type") or "",
                    "isPassed": d.get("isPassed", ""),
                })
    # 兜底：正则扫 attachmentHtml / 内嵌 json
    if not vids:
        for m in re.finditer(r'objectid["\'\s:&=]{1,8}([0-9a-f]{32})', r.text):
            vids.append({"name": "", "objectid": m.group(1), "jobid": "",
                         "size": "", "hsize": "", "type": ""})
    return vids, ""


def ananas_status(s, objectid):
    url = f"{BASE}/ananas/status/{objectid}"
    params = {"flag": "mooc2-ans", "k": objectid[:8], "_": str(int(time.time() * 1000))}
    ref = f"{BASE}/mooc-ans/knowledge/cards?clazzid={config.CLAZZ_ID}"
    r = s.get(url, params=params,
              headers={"Referer": ref, "Accept": "application/json, text/javascript, */*; q=0.01"},
              timeout=30)
    ct = r.headers.get("Content-Type", "")
    if r.status_code == 200 and ("json" in ct or r.text.strip().startswith("{")):
        try:
            return r.json(), None
        except ValueError as e:
            return None, f"JSON 解析失败 {e}"
    return None, f"HTTP {r.status_code} ct={ct} {r.text[:150]}"


def fmt_len(sec):
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return ""
    return f"{sec // 60}:{sec % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-chapter", default="", help="只抓指定 chapterId/小节ID")
    ap.add_argument("--delay", type=float, default=0.35, help="请求间隔秒")
    args = ap.parse_args()

    s = make_session()
    print("[1] 拉取课程目录 ...")
    chapters = get_catalog(s)
    tot = sum(len(c["sections"]) for c in chapters)
    print(f"    {len(chapters)} 个章 / {tot} 个小节")
    for c in chapters:
        print(f"    · {c['chapter'][:40]:<40} ({len(c['sections'])} 小节)")

    rows, seen_oid, errors = [], set(), []
    n_sec = 0
    for c in chapters:
        for sec in c["sections"]:
            kid = sec["knowledgeId"]
            if args.only_chapter and args.only_chapter not in (kid, c["chapterId"]):
                continue
            n_sec += 1
            print(f"[2.{n_sec}] 小节 {kid}  {sec['title'][:50]}")
            try:
                vids, err = get_videos_of_section(s, kid)
            except RuntimeError as e:
                print("    !!", e)
                errors.append({"knowledgeId": kid, "error": str(e)})
                continue
            if err:
                print(f"    cards 异常: {err}")
                errors.append({"knowledgeId": kid, "error": err})
                continue
            print(f"    视频 {len(vids)} 个")
            for v in vids:
                oid = v["objectid"]
                if oid in seen_oid:
                    print(f"      - {v['name'][:40]} (重复 objectid，跳过)")
                    continue
                seen_oid.add(oid)
                data, serr = ananas_status(s, oid)
                row = {
                    "chapter": c["chapter"], "chapterId": c["chapterId"],
                    "section": sec["title"], "sectionId": kid,
                    "video_name": v["name"] or (data or {}).get("filename", ""),
                    "objectid": oid, "jobid": v["jobid"],
                    "size": v["hsize"] or "", "duration": "",
                    "mp4_sd": "", "mp4_fl": "", "download": "",
                    "screenshot": "", "mp3": "", "status": "", "error": serr or "",
                    "isPassed": v.get("isPassed", ""),
                }
                if data:
                    row.update({
                        "duration": fmt_len(data.get("duration")),
                        "mp4_sd": data.get("http", "") or data.get("h264", ""),
                        "mp4_fl": data.get("m3u8", "") or data.get("h265", ""),
                        "download": data.get("download", ""),
                        "screenshot": data.get("screenshot", ""),
                        "mp3": data.get("mp3", ""),
                        "status": data.get("status", ""),
                    })
                    print(f"      ✓ {row['video_name'][:40]} [{row['duration']}] -> "
                          f"{(row['mp4_sd'] or row['download'])[:70]}")
                else:
                    print(f"      ✗ {v['name'][:40]} status 失败: {serr}")
                    errors.append({"objectid": oid, "error": serr})
                rows.append(row)
                time.sleep(args.delay)
            time.sleep(args.delay)

    os.makedirs("out", exist_ok=True)
    with open("out/videos.json", "w", encoding="utf-8") as f:
        json.dump({"course": config.COURSE_ID, "clazz": config.CLAZZ_ID,
                   "cpi": config.CPI, "total_sections": n_sec,
                   "videos": rows, "errors": errors}, f, ensure_ascii=False, indent=2)

    import csv
    cols = ["chapter", "section", "video_name", "duration", "size",
            "mp4_sd", "mp4_fl", "download", "mp3", "screenshot",
            "objectid", "jobid", "sectionId", "chapterId", "status", "error"]
    with open("out/videos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    with open("out/videos.txt", "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            f.write(f"{i:>3}. {r['chapter']} / {r['section']} / {r['video_name']}"
                    f"  [{r['duration']} {r['size']}]\n")
            link = r["mp4_sd"] or r["download"]
            f.write(f"      播放: {link}\n")
            if r["download"]:
                f.write(f"      下载: {r['download']}\n")
            f.write("\n")

    ok = sum(1 for r in rows if r["mp4_sd"] or r["download"])
    print(f"\n[3] 完成：小节 {n_sec} 个，视频 {len(rows)} 个，成功拿到地址 {ok} 个")
    print("    out/videos.csv   out/videos.json   out/videos.txt")
    if errors:
        print(f"    失败/异常 {len(errors)} 条，见 videos.json 的 errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
