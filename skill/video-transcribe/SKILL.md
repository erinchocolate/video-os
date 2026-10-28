---
name: video-transcribe
description: 接收本工作区 Inbox 中的口播视频，使用本地模型生成带词级时间点的逐字稿和待复核项；也用于剪后重新转写和局部识别复核。
---

# 接收视频与生成逐字稿

输入：待处理视频或已有任务。先读 [文件约定](../文件与接口约定.md)。执行入口 `scripts/video.py`；实现为 `scripts/video_pipeline/asr.py`、`intake.py`。

## 操作

1. 执行 `python -X utf8 scripts/video.py doctor`。模型在 `scripts/models/large-v3-turbo/`，依赖在 `scripts/vendor/`，配置在 `scripts/config/environment.json`。本机处理，不上传素材。
2. 接收新视频：

```powershell
python -X utf8 scripts/video.py ingest --input "Inbox/原始视频.mp4"
```

完整拍摄时间优先来自原文件名；没有时使用用户提供或确认的 `--timestamp YYYYMMDDHHMMSS`，不要用修改日期冒充拍摄时间。脚本建立 `process/完整时间_未命名/`，写 manifest、媒体信息、16 kHz 单声道 WAV、停顿记录和原片静帧。

3. 使用命令返回的真实目录转写：

```powershell
python -X utf8 scripts/video.py transcribe --job "process/完整时间_未命名"
```

剪后转写增加 `--edited`。局部复核增加 `--start 秒数 --end 秒数`，也可同时用 --edited，结果独立保存为 spot_*.json。

4. 阅读逐字稿、原始词级 JSON 和 review_flags。对低置信度、乱码、专有名词和语义异常做局部复核，保留校正依据。此时保留重复、口头语和重新起句，不提前改写为精简稿。

有依据的校正可用 correct-transcript --job 实际目录 --spec 校正JSON（剪后加 --edited）。JSON 为 from/to/basis 列表，也可直接使用 edit_spec.json 的 corrections。from 使用可唯一定位的完整短语；命令只更新可读稿，保存初稿与校对记录，不改原始 ASR。

## 产出与验收

原始 ASR JSON、TXT、SRT、可读逐字稿、词级时间点、复核标记和日志均留在该任务；剪后产物在该任务的 edited/。核对有效声音覆盖，特别检查首尾。机器时间码仅用于定位，不能宣称已逐句人工听校。

## 故障处理

- 不重复下载已有模型；doctor --deep 校验模型哈希。缺资源时使用 `scripts/setup_resources.py --help`，依赖恢复到 scripts/vendor，不修改全局 Python。
- PyAV 与转写库的文件解码接口曾不兼容；现脚本直接读取已提取的 PCM WAV，不改回未经验证的解码路径。
- Windows 使用 python -X utf8。中断时保留 JSONL 进度，完整结果缺失可重跑；音频已改而旧结果仍在时，先将旧结果保存到该任务 history。

下一环节：[命名归档](../video-archive/SKILL.md)。
