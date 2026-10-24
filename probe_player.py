# -*- coding: utf-8 -*-
"""
探查某个视频的播放器配置与进度上报接口

  1) out/videos.json 里按 objectid 定位所属 sectionId
  2) /mooc-ans/knowledge/cards 取回该小节 HTML，解析内嵌的 mArg 配置
  3) 打印：播放器页地址 / 进度上报地址 / 防拖拽-防切窗-倍速开关 / 时长核对

用法：
  python probe_player.py --list
  python probe_player.py 1142259eb4d4a5c9ddbbcbb2899592d3
  python probe_player.py --section 100000004
"""
import argparse
import html
import json
import re
import sys
import time

import requests

import config

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "https://mooc1.chaoxing.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
NO_PROXY = {"http": None, "https": None}


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    for k, v in config.COOKIES.items():
        if v:
            s.cookies.set(k, v, domain=".chaoxing.com")
    return s


def study_referer(knowledge_id):
    return (f"{BASE}/mycourse/studentstudy?chapterId={knowledge_id}"
            f"&courseId={config.COURSE_ID}&clazzid={config.CLAZZ_ID}"
            f"&cpi={config.CPI}&enc={config.ENC}&mooc2=1&hidetype=0"
            + (f"&openc={config.OPENC}" if config.OPENC else ""))


def fetch_cards_html(s, knowledge_id):
    params = {
        "clazzid": config.CLAZZ_ID, "courseid": config.COURSE_ID,
        "knowledgeid": knowledge_id, "num": 0, "ut": "s", "cpi": config.CPI,
        "v": time.strftime("%Y-%m%d-%H%M"), "mooc2": 1,
        "isMicroCourse": "false", "editorPreview": 0,
    }
    r = s.get(f"{BASE}/mooc-ans/knowledge/cards", params=params,
              headers={"Referer": study_referer(knowledge_id)},
              timeout=30, proxies=NO_PROXY)
    r.raise_for_status()
    return r.text


def parse_marg(page):
    """从 cards 页面里取出 uParse 的第三个参数 mArg"""
    page = html.unescape(page)
    m = re.search(r"mArg\s*=\s*(\{.*?\})\s*;\s*\n?\s*\}\s*catch", page, re.S)
    if not m:
        m = re.search(r"mArg\s*=\s*(\{.*?\"attachments\".*?\})\s*;", page, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def player_url(oid, jobid):
    return (f"{BASE}/ananas/modules/video/index.html"
            f"?objectid={oid}&jobid={jobid}")


def report(s, oid, known_duration=""):
    videos = []
    try:
        with open("out/videos.json", encoding="utf-8") as f:
            videos = json.load(f).get("videos", [])
    except OSError:
        pass
    row = next((v for v in videos if v["objectid"] == oid), None)
    if not row:
        print(f"! out/videos.json 里没有 objectid={oid}，先跑 fetch_videos.py")
        return 1
    kid = row["sectionId"]
    print(f"视频      : {row['video_name']}")
    print(f"objectid  : {oid}")
    print(f"小节      : {row['section']}  (sectionId={kid})")
    print(f"已抓时长  : {row['duration']}   {row['size']}")

    arg = parse_marg(fetch_cards_html(s, kid))
    if not arg:
        print("! 没解析到 mArg，页面结构可能变了")
        return 1
    d = arg.get("defaults", {})
    att = next((a for a in arg.get("attachments", [])
                if a.get("objectId") == oid), (arg.get("attachments") or [{}])[0])
    prop = att.get("property", {})

    print("\n--- 播放器 ---")
    print(f"页面地址  : {player_url(oid, prop.get('jobid', row.get('jobid', '')))}")

    print("\n--- 进度上报接口 ---")
    print(f"reportUrl : {d.get('reportUrl')}")
    print(f"上报间隔  : {d.get('reportTimeInterval')} 秒")
    print(f"初始化    : {d.get('initdataUrl')}")
    print(f"字幕      : {d.get('subtitleUrl')}")

    print("\n--- 平台限制开关 ---")
    for k in ("fastforward", "switchwindow", "doublespeed"):
        print(f"{k:12}: {prop.get(k, d.get(k, '-'))}")
    print(f"{'playingCapture':12}: {d.get('playingCapture')}  "
          f"captureInterval={d.get('captureInterval')}  "
          f"videoAutoPlay={d.get('videoAutoPlay')}")

    print("\n--- 校验 ---")
    att_dur = att.get("attDuration")
    if att_dur and row.get("duration", "").count(":") == 1:
        mm, ss = row["duration"].split(":")
        mine = int(mm) * 60 + int(ss)
        print(f"attDuration={att_dur}s  已抓表={mine}s  → "
              f"{'一致' if att_dur == mine else f'差 {att_dur - mine}s'}")
    print(f"签名参数  : ktoken={d.get('ktoken')}  "
          f"mtEnc={d.get('mtEnc')}  defenc={d.get('defenc')}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("objectid", nargs="?", default="", help="要探查的视频 objectid")
    ap.add_argument("--list", action="store_true", help="列出全部 objectid")
    ap.add_argument("--section", default="", help="直接给 sectionId 看该小节配置")
    args = ap.parse_args()

    if args.list:
        with open("out/videos.json", encoding="utf-8") as f:
            for i, v in enumerate(json.load(f).get("videos", []), 1):
                print(f"{i:>3}. {v['objectid']}  {v['duration']:>6}  {v['video_name'][:50]}")
        return 0

    s = make_session()
    if args.section:
        arg = parse_marg(fetch_cards_html(s, args.section))
        if not arg:
            print("! 没解析到 mArg")
            return 1
        print(json.dumps(arg, ensure_ascii=False, indent=2))
        return 0

    if not args.objectid:
        ap.print_help()
        return 2
    return report(s, args.objectid)


if __name__ == "__main__":
    sys.exit(main())
