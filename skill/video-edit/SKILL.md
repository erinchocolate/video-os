---
name: video-edit
description: 按已获用户确认的剪辑稿构建实际帧时间线、生成剪后音频，并通过重新转写和切点复核交接给字幕环节。
---

# 执行已确认的剪辑

输入：manifest、当前 edit_plan、匹配该版本的 approval。入口 `scripts/video.py edit`、transcribe --edited；实现 `scripts/video_pipeline/editing.py`、asr.py。

```powershell
python -X utf8 scripts/video.py edit --job "process/完整时间_标题"
python -X utf8 scripts/video.py transcribe --job "process/完整时间_标题" --edited
```

## 执行与产出

- 校验审核哈希和原片哈希，读取实际帧率及尺寸，不套用样片的固定 59.94 fps。
- 切点就近对齐源帧，音频先统一为 48 kHz 再按对应时间裁切；连接处约 4 ms 去点击淡化，结尾约 0.3 秒末帧和静音缓冲。
- 生成 edited_audio.wav、edited/audio.wav 和 render_plan.json；视频在字幕就绪后一次性渲染，原片保留完整。
- HDR 素材需要确认色彩处理，脚本会停止，不直接套 SDR 转换造成失真。

## 复核与修订

阅读剪后逐字稿，对照审核稿核查目标重复已删、观点和条件保留、没有新残句，尤其检查短词、重新起句和结尾。必要时使用 transcribe --edited --start 秒 --end 秒 做局部识别。

实际试听或观看切点时记录依据；识别结果只能作为内容线索，不能冒称已完整听看。发生吞字或短切不自然时保留证据，修订具体提案；明显改变删改内容时重新确认。

重剪前将旧 edited/、字幕、时间线和渲染输入保存到本任务 history/修订标识，再按当前审核版本重建，避免旧转写和新剪辑混用。

验收：实际时间线匹配审核版本，剪后转写覆盖有效内容，音频样本数与帧时间线一致。向字幕环节交接剪后转写，不能直接用原片 SRT。

下一环节：[字幕与渲染](../video-subtitles/SKILL.md)。
