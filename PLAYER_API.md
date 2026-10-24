# 播放器与进度上报接口

`samples/` 里存了播放器页壳（`player.html`）和前端脚本（`video_index.js`、
`videojs_ext.min.js`），本文是从这两份脚本 + `knowledge/cards` 返回的 `mArg`
配置里还原出来的接口全景。用 `python probe_player.py <objectid>` 可对任意视频
复查。

## 1. 数据核对

`out/videos.json` 抓到的字段与页面实际下发完全一致：

| 字段 | 已抓表 | cards 里的 mArg | 结果 |
|---|---|---|---|
| objectid | `00000000000000000000000000000001` | `attachments[0].objectId` 相同 | 一致 |
| 文件名 | `Listening to news reports（教师A）_x264.mp4` | `property.name` 相同 | 一致 |
| 时长 | `7:39` = 459s | `attDuration` = 459 | 一致 |
| 大小 | `38.43 MB` | `property.hsize` 相同、`size`=40295199 | 一致 |

31 条 objectid 无重复，全部拿到播放地址，总时长 15423 秒（约 4h17m）。

## 2. 三层接口

```
① knowledge/cards            -> HTML，内嵌 mArg 配置（含 reportUrl、限制开关、签名参数）
② ananas/status/<objectid>   -> 真实视频地址 sd.mp4 / download / mp3
③ ananas/modules/video/index.html?objectid=&jobid=   -> video.js 播放器页（iframe 内容）
```

① 是 ②③ 的上游：`reportUrl`、`ktoken`、`mtEnc`、`fastforward` 这些**只出现在 ①**，
`ananas/status` 里没有。之前只抓 ② 是够用的（要的是 mp4 地址），但要分析播放行为
必须回到 ①。

## 3. 播放器页

```
https://mooc1.chaoxing.com/ananas/modules/video/index.html?objectid=<objectid>&jobid=<jobid>
```

直接用抓到的 cookie + 章节页 Referer 请求返回 200（约 25KB）。这个页面本身
**不含 `<video>` 标签**，video 元素和 `vjs-big-play-button` 都是
`/ananas/modules/video/index.js` 运行时创建的，所以静态解析拿不到播放器实例。

`jobid` 取自 cards 里 `property.jobid`（与 `videos.json` 的 `jobid` 相同）。

### 视频地址的播放条件（实测）

`out/videos.json` 里的 `mp4_sd` 不是裸链接，缺 Referer 会被拒：

| 请求头 | 结果 |
|---|---|
| 无 Referer | `403` / `text/html` |
| `Referer: .../ananas/modules/video/index.html?objectid=…&jobid=…` | `206` / `video/mp4`，`Content-Range: bytes 0-1023/31933739` |

返回 206 说明支持 Range，可边下边播、任意 seek。`size` 字段是原片体积，
`mp4_sd` 是转码后的标清版，两者数值不同属正常现象。

## 4. 进度上报

| 项 | 值 |
|---|---|
| 地址 | `https://mooc1.chaoxing.com/mooc-ans/multimedia/log/a/<cpi>` |
| cpi | `100000003`（即 `config.CPI`） |
| 间隔 | 60 秒（`reportTimeInterval`） |
| 方法 | GET，参数挂在 query 上 |

`videojs_ext.min.js` 里拼出的参数集：

| 参数 | 来源 |
|---|---|
| `clazzId` / `courseid` / `chapterId` | `config.CLAZZ_ID` / `COURSE_ID` / 小节 |
| `objectId` / `jobid` / `mid` | cards 的 attachments |
| `playingTime` | 当前播放位置（秒） |
| `duration` / `attDuration` | 视频总时长（`attDuration` 来自 attachments） |
| `clipTime` | 本次上报覆盖的片段时长 |
| `isdrag` | 是否拖拽过（0/1/2/3） |
| `view` | 固定 `pc` |
| `dtype` | `Video` / `Audio` |
| `userid` / `uid` | `config.COOKIES["_uid"]` |
| `otherInfo` | attachments 里同名字段，含 `nodeId_/cpi_/rt_d/ds_0/ff_1/be_0_0/vt_1/v_6/enc_` 编码 |
| `enc` | **前端算的签名**，`md5(...)` 结果，混入 `ktoken` / `mtEnc` |
| `rt` | 上报时刻毫秒时间戳 |

`enc` 的输入包含 `ktoken`（每次拉 cards 会变，本次 `9a2e7785...`），不是纯时间
函数，因此不能脱离页面自行构造。这一步是平台判断"真人观看"的核心，不作为
自动化的实现目标。

另外两个读接口：

- `GET /mooc-ans/richvideo/initdatawithviewer?objectid=&clazzid=&report=true`
  → 上次的播放进度、弹题点。实测新视频返回 `[]`。
- `GET /mooc-ans/richvideo/subtitle` → 字幕。

## 5. 限制开关

cards 里 `attachments[0].property` 携带的播放限制，由播放器读取后拦截：

| 开关 | 本课取值 | 含义 |
|---|---|---|
| `fastforward` | `true` | 启用防拖拽检测（`isdrag` 上报异常会作废进度） |
| `switchwindow` | `true` | 启用切窗检测，切换标签页/失焦时暂停计时 |
| `doublespeed` | `0` | 禁用倍速（`ratechange` 会被拦截或标记） |
| `videoAutoPlay` | `0` | 不自动播放，必须点 `vjs-big-play-button` |
| `playingCapture` | `1` | 播放中抓拍（配合 `captureInterval=10`） |

所以"点按钮"这一步是必需的：`videoAutoPlay=0` + 浏览器 autoplay 策略，两者
叠加导致不点不播。要点：

```js
// 播放按钮只是转发 player.play()，直接操作实例等价
const btn = document.querySelector('.vjs-big-play-button');
const player = videojs.getPlayer(btn.closest('.video-js'));
player.muted(true);        // 绕过 autoplay 策略
player.play();
```

## 6. 用法

```bash
python probe_player.py --list                      # 列全部 objectid
python probe_player.py <objectid>                  # 查单个视频的接口与开关
python probe_player.py --section 100000004        # 打印该小节的完整 mArg
```

## 7. 浏览器自动化（Playwright + Edge）

`browser_click.py` 用 Playwright 驱动本机 Edge，点一次播放按钮并读状态：

```bash
python browser_click.py            # 注入 cookie -> 打开章节页 -> 点一次 -> 报结论
python browser_click.py --keep     # 验证完不关浏览器
python browser_click.py --autoplay # 附带 --autoplay-policy=no-user-gesture-required
```

要点：

- `channel="msedge"` 直接用系统 Edge（155.0.4283.62），不需要 `playwright install`
- `launch_persistent_context(user_data_dir=~/.chaoxing_edge_profile)` 持久化，
  配合 `ctx.add_cookies(config.COOKIES)` 通常免登录（实测 17 条 cookie 直接进课程）
- 播放器在 iframe 里，不要写死选择器，遍历 `page.frames` 找含
  `.vjs-big-play-button` 的那个更稳
- Playwright 的 `click()` 触发的是真实用户手势（`isTrusted=true`），
  **不会**被 autoplay 策略拦，不需要预先静音

实测输出：

```
命中 frame: https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2026-0920-1154
初始状态: {'t': 55, 'paused': True, 'readyState': 0, 'duration': nan}
点击后  : {'t': 56.97, 'paused': False, 'readyState': 4, 'duration': 459.264}
2.5秒后 : {'t': 59.48, 'paused': False, 'readyState': 4, 'duration': 459.264}
时间轴 56.97s -> 59.48s  在走      → 可播放
```

`duration=459.264` 与 cards 里的 `attDuration=459` 吻合，初始 `t=55` 是断点续播位置。
