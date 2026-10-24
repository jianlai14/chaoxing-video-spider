# 学习通课程视频助手 · 运行命令

## 环境要求

- Python 3.12+
- 依赖：`requests`、`beautifulsoup4`、`playwright`（首次装完执行 `playwright install` 不必须，
  脚本直接用系统 Edge：`channel="msedge"`）
- 系统装有 Microsoft Edge

## 首次准备

Cookie 存在 `config.py` 里（来自浏览器抓包，会过期）。过期后脚本会停在登录页等你扫码，
或重新从浏览器 DevTools 复制 cookie 更新 `config.COOKIES`。

首次运行会创建独立浏览器 profile（`~/.chaoxing_edge_profile`），无登录态时在窗口里手动登录一次即可记住。

## 常用命令

```bash
cd /d/爬虫/学习通

# 1. 抓取课程目录和全部视频信息 -> out/videos_array.json 等
python fetch_videos.py

# 2. 单发验证：打开章节页 -> 点一次播放 -> 打印是否可播放（点完即关）
python browser_click.py

# 3. 单发验证 + 挂机：验证完一直播，被暂停自动续播，Ctrl+C 结束
python browser_click.py --stay

# 4. 验证完保持浏览器打开（等回车再关）
python browser_click.py --keep

# 5. 清单模式：按 JSON 逐个观看（一次只看一个），每集等 时长+15秒
python browser_click.py --playlist out/videos_array.json

# 6. 清单模式 + 自定义余量（每集多等 30 秒）
python browser_click.py --playlist out/videos_array.json --margin 30

# 6b. 清单模式 + 跳过已看完的视频（isPassed=true 的直接跳过）
python browser_click.py --playlist out/videos_array.json --skip-passed

# 7. 无界面挂机（profile 里已有登录态时才能用，否则无法手动扫码）
python browser_click.py --playlist out/videos_array.json --headless

# 8. 等待手动登录的时间调长（默认 180 秒）
python browser_click.py --playlist out/videos_array.json --login-wait 300
```

## 可用清单文件

| 文件 | 格式 | 说明 |
|---|---|---|
| `out/videos_array.json` | 平铺数组 | 字段：`section_id`、`duration_sec`、`is_passed`、`name`、`player_url` 等 |
| `out/videos_full.json` | `{"videos": [...]}` | 字段为驼峰（`sectionId`、`isPassed`），脚本自动兼容 |

`is_passed` 是**抓取时刻**的观看完成快照；看完新视频后重跑 `python fetch_videos.py`
和 `python annotate_videos.py` 可刷新。

## 常用参数速查

| 参数 | 作用 |
|---|---|
| `--playlist PATH` | 按 JSON 清单逐个观看 |
| `--margin N` | 每集在时长基础上多等的秒数（默认 15） |
| `--skip-passed` | 跳过清单里 `is_passed=true` 的已完成视频 |
| `--stay` | 验证完挂机：保持播放、被暂停自动续播 |
| `--keep` | 结束后不关浏览器，等回车 |
| `--headless` | 无界面模式（无法手动登录） |
| `--login-wait N` | 等手动登录的秒数（默认 180） |
| `--no-cookies` | 不注入 config.py 的 cookie，纯靠 profile 登录态 |
| `--autoplay` | 加浏览器参数放行无手势自动播放 |

## 常见问题

- **浏览器窗口看着像"另一个浏览器"**：脚本用系统 Edge + 独立空白 profile
  （`~/.chaoxing_edge_profile`），没有你的书签和日常登录态，属正常设计。
- **几秒就关**：不带 `--playlist` 是单发验证模式，点完就关是预期；清单模式正常会跑数小时。
- **同一时间点反复"被暂停→续播"**：视频里插了弹题，脚本只续播不答题，需手动去答。
- **提示 Cookie 失效 / 停在登录页**：重新抓 cookie 更新 `config.py`，或在窗口里扫码。
- **进度没有增长**：确认打开的是小节页（清单模式走 `section_id`），而不是直接开
  `player_url`——后者缺少进度上报所需的参数。
- **隐私说明**：`out/` 的真实数据文件（清单、转写）含个人学习数据，已加入
  `.gitignore` 不入库；仓库只保留结构样例 `out/videos_array.example.json`。
