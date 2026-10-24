# -*- coding: utf-8 -*-
"""审计：遍历所有小节 cards，统计 insertvideo / insertaudio / attachment /
其它 ans-module 类型，找出漏抓的资源。"""
import sys, time, json, collections, requests
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import config, fetch_videos as F

s = F.make_session()
catalog = F.get_catalog(s)
mods = collections.Counter()
unk = []
audio = []
for c in catalog:
    for sec in c["sections"]:
        kid = sec["knowledgeId"]
        try:
            r = s.get(f"{F.BASE}/mooc-ans/knowledge/cards",
                      params={"clazzid": config.CLAZZ_ID, "courseid": config.COURSE_ID,
                              "knowledgeid": kid, "num": 0, "ut": "s", "cpi": config.CPI,
                              "v": time.strftime("%Y-%m%d-%H%M"), "mooc2": 1,
                              "isMicroCourse": "false", "editorPreview": 0},
                      headers={"Referer": F.study_referer(kid)}, timeout=30)
        except Exception as e:
            unk.append((kid, "请求失败 " + str(e))); continue
        soup = BeautifulSoup(r.text, "html.parser")
        for ifr in soup.find_all("iframe"):
            mods[ifr.get("module") or "(无module)"] += 1
        for a in soup.find_all("a", href=True):
            if "download" in a["href"] or "attachment" in a["href"]:
                mods["(链接)" + ("download" if "download" in a["href"] else "attachment")] += 1
        if (kid == "1000000000"):
            print("!! 1000000000 Video Watching 原文 3000 字:")
            print(r.text[:3000])
        time.sleep(0.15)
print("\n=== module 统计 ===")
for k, v in mods.most_common():
    print(f"{v:>4}  {k}")
print("小节请求异常:", unk[:10])
