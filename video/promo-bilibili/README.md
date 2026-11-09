# dsh-logo-golden · B站宣传片制作与投稿记录

## 最终投稿（目标账号）

- 账号：**Lamedh**（uid **11119522**）
- 稿件：**BV1XrWs69Edp** / aid **117583772650373** / cid **43449713325**
- 公开页：https://www.bilibili.com/video/BV1XrWs69Edp
- 状态（2026-11-09 09:13:40 CST 复查）：**开放浏览**（member archive `state=0`；公开 view API `code=0`；公开页 HTTP 200）
- 发布时刻：2026-11-09 09:13:35 CST
- 标题于 2026-11-09 更新：参考同类 DSH 插件视频，将 DSH、DeepSeek Harness、美化插件、HDR 和扫光等关键词放入标题；已核对公开页生效。参考视频及旧标题见 `publish/publish-record.json` 的 `title_update`。
- B站时长：68 s（母版 67.000 s，平台向上取整）
- 分区：科技 / 软件应用（tid 230）
- 标题：`【DSH插件】DeepSeek Harness 金色Logo美化｜HDR扫光实机演示`
- 标签：DeepSeek Harness, dsh-logo-golden, 桌面端, 插件, UI, 金色, 扫光, 开源, 软件应用, 科技
- 类型：自制（`copyright=1`）
- 封面：`cover/dsh-logo-golden-cover-1146x717.png`（1146×717，16:10，与 B站 CDN 返回图 SHA-256 一致）
- HDR 档位：`playurl qn=127` 返回 **quality 125「真彩 HDR」**，编码 `hvc1.2.4.L120.90`、1920×1080、30 fps；同时存在 SDR AVC 1080P+ / 1080P / 720P / 480P / 360P 档
- 发布数据：`publish/publish-record.json`；最终状态快照：`publish/records/target-11119522/status.json`

## 早期投稿（已不可公开访问）

- 账号：rainstopp_（uid 368976229）
- 稿件：**BV1CvWH6wEaj** / aid 117581189024789
- 链接：https://www.bilibili.com/video/BV1CvWH6wEaj
- 本任务最初完成并替换为 HDR 的稿件；用户后改为发布到 uid 11119522，并在原 DeepSeek 会话中要求撤回旧账号稿件。
- 2026-11-09 收尾复查：旧账号后台返回 `state=-50`，匿名公开接口返回 `code=62012`；旧稿已不可公开访问。该结果不等同于永久删除。

## 成片与技术核验

- HDR 母版：`build/dsh-logo-golden-promo-1080p-hdr.mp4`
  - 41,111,147 bytes；67.000 s；1920×1080；30/1
  - HEVC Main10 `yuv420p10le`；`smpte2084` / `bt2020` / `bt2020nc`；HDR10 静态元数据
  - 音轨：AAC 48 kHz 立体声；EBU R128 集成 **-15.2 LUFS**，LRA 4.6，True Peak -3.1 dBFS
  - `ffmpeg -v error -i ... -f null -` 全片解码无错误
  - SHA-256：`9117cdac1909e13913227dc8e2154b7eedacffd27a632095487f00335dbe1786`
- SDR 备用母版：`build/dsh-logo-golden-promo-1080p.mp4`
  - 224,576,451 bytes；67.000 s；H.264 1920×1080 30 fps；AAC 48 kHz
  - 未用于本次目标账号投稿；保留作为兼容/预览备份。
- 字幕：`publish/dsh-logo-golden-promo-zh.srt`，11 条，0–58.0 s，已烧录；58–67 s 为结尾信息卡，无字幕。
- 封面：1146×717 PNG；2× 母版 `cover/cover-master-2x.png`。
- 素材来源：dsh-logo-golden v0.4.16 在真实 DeepSeek Harness 桌面端中的运行录屏；仅使用侧栏品牌与顶部界面裁切，不含聊天内容、密钥或内部地址。
- 扫光周期：源码 `SWEEP_PARAMS.periodMs = 3000`；真实录屏静止低谷间隔均值约 3.036 s（24 s 录屏的采样误差）；片中 0.5× 慢放完整展示至少一个周期。
- 配乐：`scripts/make_music.py` 程序化生成，48 kHz，无外部采样。
- HDR 说明：本片是 HDR10 母版，但**未做 HDR 显示器实测**；B站档位存在不等于每台设备都能正确呈现，简介与片尾均不宣称实测 HDR 观感。

## 真实 HDR 素材与核验

- 品牌高光来自真实宿主的 ScreenCaptureKit HDR 采集，采集源见 `hdr/tools/HDRRecorder.swift`；使用保留 SDR 参考白的 HDR10 录制预设，输出 Main10 / PQ / BT.2020。文字、背景和版式从 SDR 设计转换到线性 BT.2020，品牌区域再叠加真实 HDR 采集数据。
- 本地源 `hdr/capture/brand-hdr-24.mov` 为 400×66、24.141667 秒；线性缓存 `brand-hdr-linear.npy` 含 971 帧，最大线性通道值 20.53125，2,628,890 个通道采样超过参考白 1.0。
- 直接解码原始采集文件第一帧并逆变换 PQ 后，峰值约为参考白的 19.446 倍，与缓存第一帧的相关系数约 0.9999。该检查用于确认采集中的扩展高光确实保留；解码及色度重建会产生数值差异。
- 数值中的 100 nit 是合成与编码采用的参考白，**不是显示器亮度测量结果**。实际观看请使用支持 HDR 的屏幕和客户端，并选择 B站「真彩 HDR」档位。
- 可运行 `.venv/bin/python scripts/verify_hdr_source.py` 复查本地采集与成片，结果保存到 `publish/hdr-verification.json`；平台、账号及旧稿最终复查见 `publish/final-recheck.json`。
- 原始采集、线性缓存、帧序列和渲染结果保留在本地，目录中的 `.gitignore` 只允许制作源文件与公开交付记录进入 Git。完整重新渲染需要这些本地素材；重新采集时需按当前宿主所在屏幕及品牌区域调整采集坐标。

## 文案与声明

- 标题/简介/标签/分区：`publish/metadata.json`
- 简介已说明：真实宿主录屏、3.000 秒周期、安装命令、仓库、v0.4.16、Apache-2.0、原创程序化配乐、脚本/剪辑/封面 AI 辅助、画面非 AI 生成、HDR10 母版未做显示器实测。
- B站本次投稿页面未提供独立的 AI 声明字段；创作声明按平台默认标注为**自制**（未经作者允许，禁止转载）。AI 辅助情况已在简介中披露，不把真实录屏说成 AI 生成画面。

## 复现

```bash
cd video/promo-bilibili

# 1) 原创配乐
.venv/bin/python scripts/make_music.py

# 2) HDR 无音轨母版（2010 帧 / 67 s）
.venv/bin/python scripts/make_video_hdr.py --render --from 0 --to 67 \
  --video build/dsh-logo-golden-promo-1080p-hdr-video.mp4

# 3) 混流为最终 HDR 母版
ffmpeg -y -i build/dsh-logo-golden-promo-1080p-hdr-video.mp4 -i build/music.wav \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 320k -ar 48000 -shortest \
  -movflags +faststart \
  -metadata title='dsh-logo-golden · 侧栏里的金色' \
  build/dsh-logo-golden-promo-1080p-hdr.mp4

# 4) 封面
.venv/bin/python scripts/make_cover.py

# 5) 投稿前检查（HDR 与目标 uid 校验）
/tmp/biliup-venv/bin/python scripts/publish_bilibili.py --preflight \
  --credential /path/to/target-credential.json --proxy ""

# 6) 正式投稿（只执行一次；脚本会先按标题查重）
/tmp/biliup-venv/bin/python scripts/publish_bilibili.py --submit \
  --credential /path/to/target-credential.json --proxy ""

# 7) 状态与 HDR 档位复查
/tmp/biliup-venv/bin/python scripts/check_bvid_status.py --bvid BV1XrWs69Edp \
  --credential /path/to/target-credential.json \
  --out publish/records/target-11119522/status.json
```

投稿环境：`/tmp/biliup-venv`，Python 3.11，bilibili-api-python 17.4.2，aiohttp 3.14.5。脚本不打印 cookie；凭证文件不进入仓库。

## 文件

| 用途 | 路径 |
| --- | --- |
| HDR 成片 | `build/dsh-logo-golden-promo-1080p-hdr.mp4` |
| SDR 备用成片 | `build/dsh-logo-golden-promo-1080p.mp4` |
| HDR 无音轨母版 | `build/dsh-logo-golden-promo-1080p-hdr-video.mp4` |
| 配乐 | `build/music.wav` |
| B站封面 | `cover/dsh-logo-golden-cover-1146x717.png` |
| 封面 2× 母版 | `cover/cover-master-2x.png` |
| 字幕 | `publish/dsh-logo-golden-promo-zh.srt` |
| 标题/简介/标签/分区 | `publish/metadata.json` |
| 最终投稿数据 | `publish/publish-record.json` |
| 平台状态快照 | `publish/records/target-11119522/status.json` |
| 原始真实录屏 | `raw/live-20261108-193208.mp4`（含品牌裁切以外的宿主界面；不要公开/提交） |

## 关于 Git

- 适合纳入 Git：`scripts/`、`publish/metadata.json`、`publish/*.srt`、`publish/publish-record.json`、`publish/upload-result.json`、`publish/records/` 下的 JSON、封面 PNG（<1 MB）、本 README。
- 不建议直接纳入普通 Git：`build/dsh-logo-golden-promo-1080p-hdr.mp4`（41 MB，虽低于 GitHub 单文件限制，但对插件仓库偏大；建议 Release/LFS/外部制品）、`build/dsh-logo-golden-promo-1080p.mp4`（约 214 MB，超过 GitHub 单文件限制）、`build/video-noaudio-v2.mp4`、`build/music.wav`、`.venv/`、`raw/` 原始录屏与中间帧。
- 本次只新增 `video/` 下的宣传制作文件；未修改产品逻辑，未提交/推送。
