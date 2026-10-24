# -*- coding: utf-8 -*-
"""把课程 31 个视频的音轨转成文字。
   每个视频：现取签名地址 -> ffmpeg 抽 16k 单声道 wav -> faster-whisper(GPU) -> txt + srt
   输出：out/transcripts/NN_章_节_视频名.txt / .srt，外加 _ALL.md 合并全文
"""
import os, sys, csv, re, time, json, subprocess, shutil
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 让 ctranslate2 找到 GPU（cuBLAS 在 torch 自带库里）
import torch
os.add_dll_directory(os.path.join(os.path.dirname(torch.__file__), "lib"))
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import config, fetch_videos as F
from faster_whisper import WhisperModel
import numpy as np
import wave

def load_pcm16k(path):
    """标准库解 16k 单声道 s16le wav -> float32。
       绕开 PyAV：本机 av 19 与 faster-whisper 1.2.1 不兼容，
       内部 decode_audio 会因 metadata_errors 参数直接抛错。"""
    with wave.open(path, "rb") as w:
        if (w.getnchannels(), w.getframerate(), w.getsampwidth()) != (1, 16000, 2):
            raise RuntimeError(f"wav 格式不符: {w.getnchannels()},{w.getframerate()},{w.getsampwidth()}")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

OUT = "out/transcripts"
os.makedirs(OUT, exist_ok=True)
AUD = os.path.join(OUT, "_audio"); os.makedirs(AUD, exist_ok=True)

# 复用 fetch_videos 的登录态
s = F.make_session()

def fresh_mp4(objectid):
    """重新取一个带签名的可下载 mp4 地址"""
    r = s.get(f"{F.BASE}/ananas/status/{objectid}",
              params={"flag": "mooc2-ans", "k": objectid[:8], "_": str(int(time.time()*1000))},
              headers={"Referer": f"{F.BASE}/mooc-ans/knowledge/cards"})
    d = r.json()
    return d.get("http") or d.get("h264") or "", d.get("filename") or ""

def safe(name):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name)[:60] or "video"

def extract_audio(url, wav):
    if not url:
        raise RuntimeError("没有签名地址")
    # ffmpeg 直接从 URL 抽音频，不落 mp4。Referer/UA 必带，否则 403
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    headers = f"Referer: {F.BASE}/mooc-ans/knowledge/cards\r\nUser-Agent: {F.UA}\r\n"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-headers", headers, "-i", url,
           "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(wav) or os.path.getsize(wav) < 4096:
        raise RuntimeError(f"ffmpeg 抽音频失败 rc={p.returncode} {p.stderr[:300]}")

def fmt_ts(t):
    h = int(t//3600); m = int(t%3600//60); sec = t%60
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

def main():
    rows = list(csv.DictReader(open("out/videos.csv", encoding="utf-8-sig")))
    print(f"[i] 待转 {len(rows)} 个视频")

    t0 = time.time()
    model = WhisperModel("small", device="cuda", compute_type="float16")
    print(f"[i] 模型就绪 ({time.time()-t0:.0f}s, device=cuda)")

    combined = []
    fail = []
    for i, r in enumerate(rows, 1):
        oid = r["objectid"]
        base = f"{i:02d}_{safe(r['chapter'])}_{safe(r['video_name'])}"
        wav = os.path.join(AUD, base + ".wav")
        txt = os.path.join(OUT, base + ".txt")
        srt = os.path.join(OUT, base + ".srt")
        title = f"{r['chapter'].strip()} / {r['section'].strip()} / {r['video_name']}"
        print(f"\n[{i}/{len(rows)}] {title}")
        try:
            url, fn = fresh_mp4(oid)
            if not os.path.exists(wav) or os.path.getsize(wav) < 4096:
                t = time.time(); extract_audio(url, wav)
                print(f"    音频抽取 {time.time()-t:.0f}s  {os.path.getsize(wav)//1024}KB")
            t = time.time()
            audio = load_pcm16k(wav)
            segs, info = model.transcribe(
                audio, language=None, vad_filter=True, beam_size=1,
                initial_prompt="以下是大学英语课程内容，中英混合。")
            segs = list(segs)
            lines = [seg.text.strip() for seg in segs if seg.text.strip()]
            open(txt, "w", encoding="utf-8").write("\n".join(lines))
            with open(srt, "w", encoding="utf-8") as f:
                for n, seg in enumerate(segs, 1):
                    f.write(f"{n}\n{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}\n{seg.text.strip()}\n\n")
            word = "".join(lines)
            combined.append((title, r["duration"], word))
            print(f"    转录 {time.time()-t:.0f}s  [{info.language}] {len(lines)}段 {len(word)}字")
            try: os.remove(wav)
            except OSError: pass
        except Exception as e:
            print(f"    !! 失败: {e}")
            fail.append({"i": i, "title": title, "error": str(e)})

    with open(os.path.join(OUT, "_ALL.md"), "w", encoding="utf-8") as f:
        f.write(f"# 课程视频文字稿（{len(combined)} 个 / 共约 4.3 小时）\n\n")
        for title, dur, word in combined:
            f.write(f"## {title}  `[{dur}]`\n\n{word}\n\n")
    json.dump({"done": len(combined), "fail": fail},
              open(os.path.join(OUT, "_status.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"\n[✓] 完成 {len(combined)}/{len(rows)}  用时 {(time.time()-t0)/60:.1f} 分  失败 {len(fail)}")
    print(f"    全文合集: {OUT}/_ALL.md   逐条: {OUT}/NN_*.txt 和 .srt")

if __name__ == "__main__":
    main()
