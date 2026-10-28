---
name: video-subtitles
description: 根据剪后转写制作按语义分句、重点词黄白双色的新青年体字幕，生成准确字体的外观预览并烧录进视频。
---

# 字幕制作、预览与渲染

输入：审核记录、render_plan 和剪后词级转写。读 [caption_spec 格式](../文件与接口约定.md)。入口 `scripts/video.py subtitles`、preview、render；实现 `scripts/video_pipeline/captions.py`、editing.py。

## 资源与默认样式

- 字体：scripts/fonts/xinqingnian.ttf；实际家族和 PostScript 名称见 scripts/config/subtitle_style.json。
- 公共配置复制到每条任务的 subtitle_style.json。1920×1080 下 84 号，新青年体自身字重、不额外伪粗体；白字、#FFD700 黄色重点词、4 像素深色描边、底边距 230 像素。
- 保留比例，字号以画面短边 1080 像素为基准缩放：横屏默认 84 号，竖屏依据手机可读性反馈增大到 100 号，由 portrait_font_size_at_1080p 单独配置；描边按短边、底边距按高度缩放。横屏最多 16 字，1080×1920 竖屏每行最多 8 字。先检查预览，避免挡脸、遮重要内容或越界。
- 已确认例句“你觉得怎么样？”只将“怎么样”设为黄色，其余白色。其他句子的重点依内容选择，不整段染黄。

## agent 编写分句与重点

阅读剪后逐字稿和复核标记，写本任务的 caption_spec.json。每行最多 16 字，按语义断开，避免割裂词组和闪字。每句少量重点通过 emphasis 指定。

全部字幕须与剪后识别对应；错字需局部复核或明确语境依据，并记录 corrections。不能编造校正来掩盖删字或改写。保留原始 ASR。

```powershell
python -X utf8 scripts/video.py subtitles --job "process/完整时间_标题" --spec "process/完整时间_标题/caption_spec.json"
python -X utf8 scripts/video.py preview --job "process/完整时间_标题" --text "从该视频实际选取的一句" --emphasis "一句" --at 10
```

preview 的 at 是原片秒数，文字与时间要换成真实内容。实际查看字幕外观预览.jpg。脚本确认字体实际加载，不能把替代字体当成用户确认的样式。

## 渲染

若用户要求先审核字幕，在本任务写入 subtitle_review_request.json（required=true及用户原话）。生成字幕后执行 subtitle-review，提供可播放的字幕审核.html、带编号时间码的字幕审核稿.md及SRT；在用户审核前不执行render、publish或后续发布包装。该审核是按用户要求启用，不自动增加到所有任务。

```powershell
python -X utf8 scripts/video.py subtitle-review --job "process/完整时间_标题"
```

审核页使用相同剪辑时间线的无字视频，字幕由网页动态显示，尚未烧录。先整理低置信度、错字和漏字，列明有依据的校正，保留原始ASR。用户按编号或时间码提出修改时，更新分句、校正和字幕文件，再重新提供审核版；无字视频按剪辑哈希复用。不要把字幕改写当作已经修改了音频。

用户明确确认当前字幕后，以 subtitle-review 返回的字幕哈希执行：

```powershell
python -X utf8 scripts/video.py subtitle-approve --job "process/完整时间_标题" --subtitle-hash "当前字幕SHA256" --message "用户实际字幕确认原话"
```

确认绑定JSON、SRT、ASS、样式与实际剪辑时间线；后续任何这些文件变化均需重新审核。render与publish会拦截缺少确认或版本不匹配的任务。批准剪辑不代替字幕确认。

```powershell
python -X utf8 scripts/video.py render --job "process/完整时间_标题"
```

产出 ASS、SRT、JSON、可读字幕稿和本任务 rendered.mp4。H.264、CRF 18、AAC 256 kbps、yuv420p，按实际源帧率输出。进度和日志留在任务目录，此时不进入 final。

文字对不上时查错误位置、分句与识别差异，不跳过校验。样式变化需重新生成字幕和预览；剪辑变化需重建剪后转写与字幕时间轴。

下一环节：[检查交付](../video-deliver/SKILL.md)。
