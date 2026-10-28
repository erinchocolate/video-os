---
name: video-deliver
description: 对渲染视频执行全片解码、帧率、音视频时长、字体、字幕及原片完整性检查，实际查看预览后交付到 final。
---

# 成片检查与交付

输入：任务内 rendered.mp4、字幕、render_plan 和审核记录。入口 `scripts/video.py frames`、verify、publish；实现 `scripts/video_pipeline/editing.py`。

```powershell
python -X utf8 scripts/video.py frames --job "process/完整时间_标题"
python -X utf8 scripts/video.py verify --job "process/完整时间_标题"
```

## 验收

脚本核查尺寸和帧率、准确帧数、音视频总时长差 <50 ms、字幕范围及无重叠、实际字体、剪后音频样本数和数字削波、全片解码、完整原片哈希，以及渲染输入是否变动。

agent 实际打开九宫格和成片画面，检查字形、字号、黄白配色、描边、遮挡、边界及画面颜色；有条件时查看切点和首尾播放，核查听感与口型。总时长一致不能单独证明每个切点同步。

有错则依据对应日志修复，失败输出留在 process。不要把技术检查或抽帧描述成已全片人工听看。

## 发布到本地 final

技术检查通过并实际复核画面后，记录真实检查内容：

```powershell
python -X utf8 scripts/video.py publish --job "process/完整时间_标题" --visual-note "填写实际查看的画面、切点和结果"
```

脚本将已检查的视频移入 final/YYYY-MM-DD_标题_成片.mp4，更新 manifest、verification 与成片说明。目标存在时追加拍摄时分秒，仍冲突则停止，不覆盖。

验收：成片存在可打开，raw 完整原片哈希一致，过程物料保留，其他待处理视频仍在 Inbox。向用户提供成片链接、时长和必要的检查限制，等待评价后再决定其余素材的处理。
