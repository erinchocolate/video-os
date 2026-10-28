---
name: video-archive
description: 根据已生成的逐字稿拟定内容标题，校验并归档完整原片，同时将每条视频的过程目录统一为完整拍摄时间加标题。
---

# 命名与原片归档

输入：已转写任务的 manifest、逐字稿及原文件名。工具为 `scripts/video.py archive`，实现为 `scripts/video_pipeline/intake.py`。

1. 阅读整份逐字稿，拟定简洁、准确的初始标题，概括核心内容，不添加原片未表达的承诺或观点。
2. 过程目录使用原始完整拍摄时间；原片沿用 YYYY-MM-DD_标题.mp4。同名时追加时分秒，仍冲突则停止，不覆盖文件。
3. 执行：

```powershell
python -X utf8 scripts/video.py archive --job "process/完整时间_未命名" --title "内容标题"
```

4. **后续使用返回的新 job 路径。**脚本将完整原片移入 raw，过程目录改为 process/YYYY-MM-DD_HH-mm-ss_标题，更新活动引用，移动前后核对 SHA256。

验收：原片字节未改变；过程物料在新目录；manifest 指向真实 raw 文件；Inbox 只移走本次素材。已完成视频不重新命名或重做。

中断时保留 manifest 中 archive_intent，核对原路径、目标路径及哈希后恢复，不重复移动、不覆盖同名文件或删除判断不明的副本。

下一环节：[剪辑稿](../video-edit-plan/SKILL.md)。
