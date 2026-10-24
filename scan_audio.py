# -*- coding: utf-8 -*-
"""扫描全课，找出所有音频资源：insertaudio iframe、mp3/m4a/aac 附件、以及作业里的音频。"""
import re, sys, json, time, collections, requests
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import config, fetch_videos as F

s = F.make_session()
catalog = F.get_catalog(s)
audio = []          # 音频条目
mods = collections.Counter()
ext_hits = collections.Counter()

for c in catalog:
    for sec in c["sections"]:
        kid = sec["knowledgeId"]
        r = s.get(f"{F.BASE}/mooc-ans/knowledge/cards",
                  params={"clazzid": config.CLAZZ_ID, "courseid": config.COURSE_ID,
                          "knowledgeid": kid, "num": 0, "ut": "s", "cpi": config.CPI,
                          "v": time.strftime("%Y-%m%d-%H%M"), "mooc2": 1,
                          "isMicroCourse": "false", "editorPreview": 0},
                  headers={"Referer": F.study_referer(kid)}, timeout=30)
        if F.is_login(r.text):
            raise SystemExit("Cookie 失效")
        t = r.text
        soup = BeautifulSoup(t, "html.parser")
        for ifr in soup.find_all("iframe"):
            mods[ifr.get("module") or "(none)"] += 1
        # 任意位置的音频扩展名
        for m in re.finditer(r'[\w\-\.\u4e00-\u9fff%]+\.(mp3|m4a|aac|wav|ogg|flac)', t, re.I):
            ext_hits[m.group(1).lower()] += 1
        # insertaudio / 附件 data
        for tag in soup.find_all(attrs={"data": True}):
            try:
                d = json.loads(tag["data"])
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            nm = (d.get("name") or d.get("type") or "")
            if re.search(r'\.(mp3|m4a|aac|wav|ogg)$', str(nm), re.I) or tag.get("module") == "insertaudio":
                audio.append({"chapter": c["chapter"], "section": sec["title"], "sectionId": kid,
                              "module": tag.get("module"), "name": nm,
                              "objectid": d.get("objectid", ""), "jobid": d.get("jobid") or d.get("_jobid", ""),
                              "duration": d.get("duration", ""), "hsize": d.get("hsize", "")})
        # a 标签附件
        for a in soup.find_all("a", href=True):
            if re.search(r'\.(mp3|m4a|aac|wav|ogg)(\?|$)', a["href"], re.I):
                audio.append({"chapter": c["chapter"], "section": sec["title"], "sectionId": kid,
                              "module": "attachment-link", "name": a.get_text(" ", strip=True),
                              "objectid": "", "href": a["href"], "jobid": "", "duration": "", "hsize": ""})
        time.sleep(0.12)

print("=== iframe module 统计 ===")
for k, v in mods.most_common():
    print(f"  {v:>4}  {k}")
print("\n=== 音频扩展名出现次数 ===", dict(ext_hits))
print(f"\n=== 音频条目 {len(audio)} ===")
for a in audio:
    print(f"  {a['chapter'].strip():<12} | {a['section'][:24]:<24} | {a['module']:<16} | {str(a['name'])[:44]}")
json.dump(audio, open("out/audio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
