# 输入、产物与状态

命令从工作区根目录执行。--job指向process里的剪辑任务，脚本据任务名找到package；包装输入与图像资产在package/materials。路径使用工作区相对路径。

## 首轮package_spec.json

结构示意（实际candidates须包含01至20共20组，不重复标题）：

```json
{
  "description": "根据成片编写的一版通用发布说明",
  "topics": ["与内容相关的话题"],
  "recommended": ["01", "07", "17"],
  "transcript_paragraphs": ["与最终字幕逐字对应的内容，只整理标点和分段"],
  "platform_notes": [{"text": "需要随本视频说明的尺寸或入口事项"}],
  "candidates": [
    {"id":"01", "group":"某个创意切入方向", "title":"本条内容的标题", "cover_lines":["主字第一行","主字第二行"], "design":"highlight", "frame_id":"01", "evidence":"对应成片的时间范围与内容", "rationale":"标题和封面为什么这样搭配"}
  ]
}
```

cover_lines两行，每行最多9字；按实际边界缩放后仍检查缩略图可读性。推荐design为direct或highlight；旧模板为历史兼容保留，不默认使用banner或副标题。frame_id来自materials/frames.json。文本、抽帧和成片必须属于同一视频。首轮依据SKILL.md保留未抠图原帧的实际背景，不从旧示例复制solid或matte_asset；下面的换底与抠图模式用于用户明确要求的修订，不代表首轮默认。

## feedback.json

```json
{"action":"narrow","candidate_ids":["04","11"],"message":"用户实际筛选原话"}
```

继续修改时action改为revise，message记录实际建议，candidate_ids可为空。narrow仅缩小范围，不触发交付。对已选方案提出新修改，使当前选择失效，但保留已导出的旧upload版本。

## cover_revision.json

包含publication_title、cover_lines、frame_id、唯一revision_name、feedback及variants。variants为本轮少量方案，每项含id、style（direct/highlight）、label、description，可选background。生成新目录，保留旧版。

旧background模式属于兼容输入，不作为新批次的默认制作路径。新批次按SKILL.md先用本条完整原帧制作无字、连贯的强虚化底图，再原生排版。不要使用uncut_photo_left把完整原图矩形贴回底图；这会重新引入接缝。修订候选JSON保留原candidates结构，images指向package内精确修订文件；发布包.json的review_revision_manifest指向该文件，供批次页稳定恢复。

## final_selection.json

```json
{
  "publication_title": "用户最终选定的发布标题",
  "cover_text": "用户选定的封面短句",
  "cover_directory": "package/完整时间_视频名/某一轮/所选版式",
  "visual_note": "实际查看所选图片后的真实检查内容"
}
```

cover_directory指向本视频package内实际图片目录，含封面_9x16.jpg、封面_3x4.jpg、封面_16x9.jpg、封面_4x3.jpg。可增加description覆盖通用说明，否则沿用通用发布说明。package-select的--message写用户明确选定原话，不以推荐、收藏或“先看看”作为选定。

选择按精确目录与四张图哈希保存，标题可与封面来自不同候选。发布选择.json是当前选择，events保留历次反馈与选择；upload_manifest.json记录复制清单，upload_verification.json记录核验。浏览器偏好不自动改这些文件。

## 状态与导出

包装独立于剪辑：首轮awaiting_user_selection；缩小范围shortlisted；继续修改awaiting_revision；明确选定selected；复制验证后upload_ready。新反馈使此前选择变为superseded_by_feedback。渲染完成不是用户确认。

upload含五类材料：标题.txt、视频说明.txt、视频文字稿.md、最终成片.mp4、封面目录。多个尺寸是同一设计的适配，复制时不改图，无用户确认不能导出。已有交付目录不覆盖，核验和历史留在package。

同一视频需要新交付时，重新选定后用 `upload-ready --revision v2`，写入新的带后缀upload目录；不覆盖旧交付。
