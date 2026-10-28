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

background为uniform_blur时指定已准备的plate与matte_asset；solid时指定color和matte_asset。资产位于package且列入顶层assets以记录哈希。图像素材由agent调用会话图像工具处理，脚本负责现有原生排版。

background为original_scene时，竖版直接保留原片照片；横版使用plate中的同场景清晰背景延展图，并以matte_asset叠加原片人物。横版生成或修复过的环境必须注明“原场景延展”，不将补绘区域宣称为原始实拍。比较虚化时，uniform_blur的plate须已由图像工具做全背景虚化，两版保留相同人物、文案与排版。

首轮需适配横版且不抠图时，可用background.mode=uncut_photo及landscape_plate（同场景清晰延展资产）。竖版直接用原帧；横版按画高1.35倍缩放完整原帧、上移0.15倍画高并贴右，其矩形区域包含原始人物和真实环境，不读取matte_asset。图像工具仅负责横版画布其余场景的延展，素材需留在本条materials并注明补绘；先检查原图矩形边界的环境衔接，再批量排版。若原帧本身适合直接横向裁切，也可另做原帧构图，不必使用此模式。

虚化背景可另指定portrait_plate，使用原竖版照片只虚化环境的素材，保持与实际背景版一致的构图；plate继续用于横版。两张素材都需列入assets。排版器不重绘人物，叠加的RGB仍来自原帧。

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
