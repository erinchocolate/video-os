---
name: video-edit-plan
description: 结合逐字稿、词级时间点及停顿记录，为单条口播视频编制可审核的删段方案；记录用户针对该版本剪辑稿的确认。
---

# 编制剪辑稿与记录审核

输入：已归档任务的转写、词级时间点、silences.json 和复核标记。读 [输入格式](../文件与接口约定.md)。入口 `scripts/video.py review`、approve；实现 `scripts/video_pipeline/intake.py`。

## 内容判断

- 先说明主线、结论、必要条件和必须保留的例子。
- 优先精简无意义口头语、重复、重新起句和长停顿，不机械删除每个“就是”“然后”，不删除有意义的犹豫、强调或条件。
- 用词级时间点定位每段，写出原话、起止秒数和具体理由，避免密集短切。不能复制样片的删段到新视频。
- 可能改变立场、因果或有效信息的删改，先列出供用户判断。机器边界不等于精确发音边界。

## 提案

agent 将判断写入本任务 edit_spec.json，再执行：

```powershell
python -X utf8 scripts/video.py review --job "process/完整时间_标题" --spec "process/完整时间_标题/edit_spec.json" --trim-pauses
```

--trim-pauses 可选，仅把候选停顿加入提案，不会剪视频。阅读生成的 edit_plan.json 和剪辑稿，核对逻辑、删段和时长，向用户提供链接和主要删改。**在此等待用户确认具体稿件。**

## 收到确认后

引用用户实际确认原话和 review 返回的 SHA256：

```powershell
python -X utf8 scripts/video.py approve --job "process/完整时间_标题" --plan-hash "当前提案SHA256" --message "用户实际确认原话"
```

产出 approval.json 与审核快照。不能把“先做样片”“沿用字幕”或上一条视频的认可当作新稿批准。初始化、edit、转写、render 不得自动制造确认。

提案更改后旧确认失效；重新展示并确认。验收：记录匹配当前原片和提案哈希，确认依据可追溯。

下一环节：[执行剪辑](../video-edit/SKILL.md)。
