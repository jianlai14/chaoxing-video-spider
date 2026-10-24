# -*- coding: utf-8 -*-
"""
视频信息结构体（struct）定义。

对应 out/videos_array.json：一个由 VideoInfo 组成的数组，
字段顺序固定，可直接按位取用。等价于 C 里的：

    typedef struct {
        int   no;                 // 序号
        char *chapter;            // 章名
        char *chapter_id;
        char *section;            // 小节名
        char *section_id;
        char *name;               // 视频文件名
        char *duration;           // "9:16"
        int   duration_sec;       // 556
        char *size_text;          // "54.15 MB"
        long  size_bytes;
        char *objectid;
        char *jobid;
        bool  is_passed;          // 观看完成（平台 isPassed，抓取时刻快照）
        char *mid;
        char *player_url;         // 播放器页
        char *play_url;           // mp4 直链
        char *download_url;
        char *mp3_url;
        char *screenshot_url;
        char *report_url;         // 进度上报接口
        int   report_interval;    // 秒
        bool  fastforward;        // 防拖拽
        bool  switchwindow;       // 防切窗
        bool  doublespeed;        // 是否允许倍速
        char *transcript_txt;
        char *transcript_srt;
    } VideoInfo;

用法：
    from video_schema import load_array, to_numpy

    rows = load_array()                       # list[VideoInfo]
    for v in rows:
        print(v.no, v.name, v.duration, v.play_url)

    arr = to_numpy(rows)                      # numpy 结构化数组
    arr["duration_sec"].sum()
"""
import json
from dataclasses import dataclass, asdict, fields
from typing import List

import numpy as np

DEFAULT_PATH = "out/videos_array.json"


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _bool(v):
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes")


def _str(v):
    return "" if v is None else str(v)


@dataclass(slots=True)
class VideoInfo:
    no: int                 # 序号，与 out/transcripts 的 NN_ 前缀一致
    chapter: str            # 章名
    chapter_id: str
    section: str            # 小节名
    section_id: str
    name: str               # 视频文件名
    duration: str           # "9:16"
    duration_sec: int       # 556
    size_text: str          # "54.15 MB"
    size_bytes: int
    objectid: str
    jobid: str
    is_passed: bool         # 观看完成（平台 isPassed，抓取时刻快照）
    mid: str
    player_url: str         # 播放器页 index.html?objectid=&jobid=
    play_url: str           # sd.mp4 直链（带签名，需 Referer）
    download_url: str
    mp3_url: str
    screenshot_url: str
    report_url: str         # 进度上报 /multimedia/log/a/<cpi>
    report_interval: int    # 上报间隔秒
    fastforward: bool       # 防拖拽开关
    switchwindow: bool      # 防切窗开关
    doublespeed: bool       # 是否允许倍速
    transcript_txt: str
    transcript_srt: str

    # ---------- 构造 ----------
    @classmethod
    def from_dict(cls, d: dict) -> "VideoInfo":
        return cls(
            no=_int(d.get("no")),
            chapter=_str(d.get("chapter")),
            chapter_id=_str(d.get("chapter_id")),
            section=_str(d.get("section")),
            section_id=_str(d.get("section_id")),
            name=_str(d.get("name")),
            duration=_str(d.get("duration")),
            duration_sec=_int(d.get("duration_sec")),
            size_text=_str(d.get("size_text")),
            size_bytes=_int(d.get("size_bytes")),
            objectid=_str(d.get("objectid")),
            jobid=_str(d.get("jobid")),
            is_passed=_bool(d.get("is_passed", d.get("isPassed"))),
            mid=_str(d.get("mid")),
            player_url=_str(d.get("player_url")),
            play_url=_str(d.get("play_url")),
            download_url=_str(d.get("download_url")),
            mp3_url=_str(d.get("mp3_url")),
            screenshot_url=_str(d.get("screenshot_url")),
            report_url=_str(d.get("report_url")),
            report_interval=_int(d.get("report_interval")),
            fastforward=_bool(d.get("fastforward")),
            switchwindow=_bool(d.get("switchwindow")),
            doublespeed=_bool(d.get("doublespeed")),
            transcript_txt=_str(d.get("transcript_txt")),
            transcript_srt=_str(d.get("transcript_srt")),
        )

    # ---------- 导出 ----------
    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def referer(self) -> str:
        """访问 play_url 时必须带的 Referer"""
        return self.player_url

    def __str__(self):
        return f"[{self.no:02d}] {self.name}  {self.duration}  {self.size_text}"


FIELDS = [f.name for f in fields(VideoInfo)]


def load_array(path: str = DEFAULT_PATH) -> List[VideoInfo]:
    with open(path, encoding="utf-8") as f:
        return [VideoInfo.from_dict(d) for d in json.load(f)]


def save_array(rows: List[VideoInfo], path: str = DEFAULT_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in rows], f, ensure_ascii=False, indent=2)


def to_numpy(rows: List[VideoInfo]) -> np.ndarray:
    """转 numpy 结构化数组，按字段名取列：arr["duration_sec"].sum()"""
    dtype = [
        ("no", "i4"), ("chapter", "O"), ("chapter_id", "O"),
        ("section", "O"), ("section_id", "O"), ("name", "O"),
        ("duration", "O"), ("duration_sec", "i4"),
        ("size_text", "O"), ("size_bytes", "i8"),
        ("objectid", "O"), ("jobid", "O"), ("is_passed", "?"), ("mid", "O"),
        ("player_url", "O"), ("play_url", "O"), ("download_url", "O"),
        ("mp3_url", "O"), ("screenshot_url", "O"),
        ("report_url", "O"), ("report_interval", "i4"),
        ("fastforward", "?"), ("switchwindow", "?"), ("doublespeed", "?"),
        ("transcript_txt", "O"), ("transcript_srt", "O"),
    ]
    arr = np.empty(len(rows), dtype=dtype)
    for i, r in enumerate(rows):
        for k in arr.dtype.names:
            arr[k][i] = getattr(r, k)
    return arr


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    data = load_array()
    print(f"共 {len(data)} 条，字段 {len(FIELDS)} 个\n")
    for v in data[:5]:
        print(v)
    print("...")

    arr = to_numpy(data)
    print(f"\nnumpy 结构化数组: shape={arr.shape}  dtype={len(arr.dtype.names)} 字段")
    print(f"总时长 {int(arr['duration_sec'].sum())} 秒 "
          f"({int(arr['duration_sec'].sum()) // 3600}h"
          f"{int(arr['duration_sec'].sum()) % 3600 // 60}m)")
    print(f"原片合计 {arr['size_bytes'].sum() / 1024 ** 3:.2f} GB")
