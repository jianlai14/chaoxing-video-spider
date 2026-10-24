# 学习通（超星）课程视频抓取 + 语音转文字

抓取 mooc1.chaoxing.com 课程目录里的全部视频，换取真实播放地址，并把音轨转成文字稿。

## 快速开始

```bash
pip install requests beautifulsoup4 faster-whisper

# 1. 填 Cookie（浏览器 F12 -> Network -> 任一请求 -> cookie 整行）
cp config.example.py config.py

# 2. 抓全课视频地址 -> out/videos.csv, videos.json, videos.txt
python fetch_videos.py

# 3. 音轨转文字（GPU，RTX 4060 + faster-whisper small，31 个视频约 24 分钟）
python transcribe.py

# 可选：补全每条视频的信息 -> out/VIDEO_INDEX.md, videos_full.json/.csv
python annotate_videos.py

# 可选：查某个视频的播放器配置与上报接口
python probe_player.py <objectid>

# 可选：用 Playwright 驱动 Edge 点一次播放按钮，验证能否播放
python browser_click.py
```

播放器与进度上报接口的完整梳理见 [PLAYER_API.md](PLAYER_API.md)。

## 按结构体取用

`out/videos_array.json` 是一个 31 元素、26 字段的数组，配合 `video_schema.py`：

```python
from video_schema import load_array, to_numpy, VideoInfo

rows = load_array()                 # list[VideoInfo]
for v in rows:
    print(v.no, v.name, v.duration, v.play_url)

arr = to_numpy(rows)                # numpy 结构化数组
arr["duration_sec"].sum()           # 15423
arr[arr["chapter"] == "Listening"]["name"]
```

## 数据与隐私

本仓库**不含任何真实学习数据**：

- `config.py`（真实 Cookie）与 `out/` 下的抓取产物（视频清单、签名地址、
  转写文本等，含课程 ID 与教师姓名）均已加入 `.gitignore`，只在本地生成；
- `out/videos_array.example.json` 是视频清单的结构样例（通用占位内容），
  字段说明见代码内注释与 [USAGE.md](USAGE.md)；
- 文档与样本中出现的 ID、地址均为占位符（如 `000...001`、`100000001`）。

## 抓取原理

三层接口，都在 `fetch_videos.py` 里：

| 步骤 | 接口 | 拿到什么 |
|---|---|---|
| 1 | `/mycourse/studentstudycourselist` | 全课目录：章 -> 小节 knowledgeId（藏在 `getTeacherAjax('cid','clazzid','kid')` 里） |
| 2 | `/mooc-ans/knowledge/cards` | 小节内容 HTML，视频是 `<iframe module="insertvideo" data='{"objectid":"..."}'>` |
| 3 | `/ananas/status/<objectid>` | 真实播放地址 `http`(sd.mp4)、`download`、`duration`、`mp3` |

要点：

- 第 3 步**必须带 `Referer`**，否则 403。
- 返回的 `at_ / ak_ / ad_` 签名地址**有时效**（几十分钟），过期重跑第 3 步即可。
- `ananas/status` 的 `_` 参数要用真实毫秒时间戳。
- 视频是客户端渲染的，直接抓章节页 HTML 拿不到视频，必须走 `knowledge/cards`。

## 转录

`transcribe.py` 不下载完整 mp4，用 ffmpeg 直接从签名地址抽 16k 单声道 wav：

```
签名地址 -> ffmpeg -vn -ac 1 -ar 16000 -> faster-whisper(cuda, float16) -> txt + srt
```

> **踩坑记录**：PyAV 19 与 faster-whisper 1.2.1 不兼容，内部 `decode_audio`
> 会因 `metadata_errors` 参数直接抛错。这里用标准库 `wave` 解码成 numpy 数组
> 再喂给模型，绕开 PyAV。
> 另外本机 `huggingface.co` 不通，需 `HF_ENDPOINT=https://hf-mirror.com`；
> ctranslate2 找不到 cuBLAS，需把 torch 自带 `lib` 目录加进 DLL 搜索路径。

## 产物

```
out/
  videos.csv / videos.json / videos.txt   # 31 个视频地址表（粗表）
  videos_array.json                       # 结构体数组：31 元素 × 26 字段，配 video_schema.py
  VIDEO_INDEX.md                          # 完整清单：时长/五类网址/限制开关/转写稿索引
  videos_full.json / videos_full.csv      # 同上，结构化
  transcripts/
    _ALL.md                # 全部文字稿合并
    NN_<章>_<视频名>.txt    # 纯文字
    NN_<章>_<视频名>.srt    # 带时间轴字幕
samples/                   # 各接口的原始响应，便于分析结构
```

## 注意

- `config.py` 含真实登录态，已在 `.gitignore` 里排除，不要提交。
- Cookie 约一周过期（看 `p_auth_token` JWT 的 `exp`），失效时脚本会明确报"返回登录页"。
- 仅限个人学习用途，请遵守学校与平台规则。
