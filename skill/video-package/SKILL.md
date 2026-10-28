---
name: video-package
description: 根据最终成片和字幕制作20组标题与封面候选、通用发布说明，支持筛选、混搭与多轮修改，用户最终选定后将五类发布材料复制到upload；不执行平台上传。
---

# 发布包装：从20组候选到待上传材料

适用于已完成剪辑的视频，或对既有候选继续筛选、修改、选定。先读总工作流；尺寸与平台入口见 [平台参考](references/platforms.md)，具体输入见 [输入与状态](references/input-formats.md)。共用代码、字体和依赖在 scripts，任务资料在 package，输出到 upload。

## 恢复与素材依据

- 从process的manifest定位已完成成片与最终字幕；从对应package的发布包.json、发布选择.json、events和实际图片恢复包装进度。剪辑的completed与包装的upload_ready分别记录。
- 用最终字幕和成片文字稿理解实际保留内容，不根据原片删掉的内容写标题。文字稿只整理标点、分段，与最终字幕的文字核对一致；原片逐字稿继续留在process。
- package/完整拍摄时间_视频名/保存本阶段全部资料，materials放输入、抽帧、素材和处理记录，候选及历轮修订保留原文件。final保留剪辑成片，upload只收最终确定的发布材料。目录名沿用稳定视频标识，发布标题单独存文件，不因换标题改变原片归档名。
- 若遇到旧process/publishing，用package-migrate迁入package/materials；先核验文件，历史快照保留原路径，并保存迁移映射。不要手工合并或覆盖历史。

## 第一轮：20个真实可选组合

```powershell
python -X utf8 scripts/video.py package-prepare --job "process/完整时间_视频名"
```

查看抽帧总览，选眼睛睁开、表情自然、人物清晰的照片。工具按本条实际保留时间线映射到无烧录字幕原片画面，适用于不同时长；不能照抄样例抽帧秒数。

agent在package/materials编写package_spec.json：20个不同切入角度的标题，每个配封面短句、画面、版式及依据；另有一版通用说明、可选话题和与成片一致的分段文字稿。标题与封面短字可以不同，但应互相补充。表达必须忠于成片，不添加虚构成果、经历、数字或权威背书。平台标签只是创意参考，不是算法结论。

默认从**未抠图的原始静帧**制作首轮20组，保留实际拍摄背景，直接叠加大主字；尝试黑字配紧贴文字的黄底或白黄大字。避免整块banner和多余副标题，检查缩略图可读性与人脸遮挡。不要因为上一条视频最终用了纯色，就在下一条首轮自动抠图或换成纯色。用户明确需要更换纯色背景时，再单独抠图制作新版本；本条有明确背景要求时按该要求执行。

原始静帧始终作为各背景分支的共同起点。实际背景直接取原图，不把已抠出的人物重新贴回房间背景；虚化也从原始完整照片处理环境，保留人物区域和原有发丝边缘，避免复用旧抠图带来的白边、缺发和接缝。横版优先以完整原帧裁切或重新布局；若需要扩图或场景延展，从未抠图原图另做适配并注明补绘，不默认调用带matte_asset的人像合成模式。纯色分支的抠图与处理记录独立保留，不作为后续恢复实际背景的底图。

```powershell
python -X utf8 scripts/video.py package-build --job "process/完整时间_视频名" --spec "package/完整时间_视频名/materials/package_spec.json"
python -X utf8 scripts/video.py package-check --job "process/完整时间_视频名"
```

交付能直接看到图片的候选总览，不能只列20个标题或封面提示词。每组附同一设计的尺寸适配版，第一轮说明共用一版；除非用户另有要求，不为四个平台分别改写整组内容。首次生成后等待用户筛选，不自行认定推荐编号为最终选择。

## 筛选、混搭与修订

- 用户缩小范围：记录narrow反馈及候选编号，只围绕该范围深化，不必每轮重做20组。
- 用户提出修改：记录revise反馈，编制新修订输入，package-refine生成新目录；保留上一轮，输出实际预览再收集反馈。
- 用户直接选定或混搭：可以标题选某组、封面选另一组，也可以选旧版本。确认精确版本、目录和实际文件，不用最新版本替代用户选择。
- 浏览页收藏、短名单、推荐和导出的本机偏好文件都不是最终确认。用户明确选定后才执行package-select。

```powershell
python -X utf8 scripts/video.py package-feedback --job "process/完整时间_视频名" --spec "package/完整时间_视频名/materials/feedback.json"
python -X utf8 scripts/video.py package-refine --job "process/完整时间_视频名" --spec "package/完整时间_视频名/materials/cover_revision.json"
```

共用排版器支持直接叠字、黑字黄底及四种比例。若需修改照片、移除背景或生成图像素材，使用当前会话可用的内置imagegen并遵循其skill；生成资产、提示词、来源及处理记录保存到本任务package/materials。不要为普通排版擅自重绘用户人物。可以只用生成抠图的透明度，人物颜色仍取原片；实际检查发丝边缘及身份一致性。

## 最终选择与upload交付

实际查看所选图片：字形与文字正确、缩小可读、无人脸遮挡、无越界，各比例不丢字。最终选择输入包含发布标题、封面文案、精确封面目录、真实视觉检查说明；发布说明默认沿用通用版本，可在最终选择中明确修改。

```powershell
python -X utf8 scripts/video.py package-select --job "process/完整时间_视频名" --spec "package/完整时间_视频名/materials/final_selection.json" --message "用户明确选定的原话"
python -X utf8 scripts/video.py upload-ready --job "process/完整时间_视频名"
python -X utf8 scripts/video.py upload-check --job "process/完整时间_视频名"
```

upload-ready核对选择后的封面、成片和文字稿，复制到upload/完整拍摄时间_视频名/：标题.txt、视频说明.txt、视频文字稿.md、最终成片.mp4、封面目录中的四种尺寸。选择依据、复制清单与哈希核验留在package。final和package归档均保留；已经选定的封面按原文件复制，不重新渲染导致版本变化。

没有明确选择、选择后文件变动、字幕与文字稿不符时停止导出并定位对应记录；不要绕过校验补写完成状态。已有upload不覆盖，用户需再改时保留旧交付，建立新版本后重新选定和检查。进入upload仅表示材料就绪，不表示已对外发布，也不授予登录或上传平台的权限。

重新选定后的新交付使用 `upload-ready --revision v2` 等明确后缀，生成同一视频标识加版本后缀的目录；旧目录保留，历次交付清单随events归档。

向用户提供upload目录和选定标题、封面版本，简述验证结果。新视频重新做内容判断和选择流程，不继承上一条标题、说明、剪辑批准或最终选择。
