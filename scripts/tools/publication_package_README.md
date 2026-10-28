# 发布包装工具入口

正式 SOP：[video-package](../../skill/video-package/SKILL.md)。平台尺寸、输入格式与选择规则均由该 skill 维护。

所有操作优先经 python -X utf8 scripts/video.py --help：package-prepare、package-build、package-feedback、package-refine、package-select、package-check、package-migrate、upload-ready、upload-check。

两个排版实现保留为可直接运行的工具，输入位置统一为 package/materials。字体和本地排版依赖在 scripts，照片编辑使用会话图像工具；不要嵌入某条视频的文案、抽帧时间或用户选择。
