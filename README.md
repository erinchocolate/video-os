# Video OS

可迁移的视频剪辑与发布包装工作流。供 AI agent 依照 SOP 完成转写、原片归档、剪辑稿审核、剪辑、字幕、成片检查、标题封面筛选及待上传材料整理。

先读 [AGENTS.md](AGENTS.md)，再读 [工作流说明](工作流说明.md) 和当前环节的 [skill](skill/)。脚本不会替 agent 作内容判断，也不会替用户确认剪辑稿、字幕或发布选择。

## 仓库保存什么

- 工作流说明、各环节 skill、共享配置、脚本、模板及合成测试。
- `scripts/requirements.txt`：直接依赖；`scripts/requirements.lock.txt`：当前环境的固定版本清单，安装入口使用后者。
- 空目录占位文件：Git 不记录空目录，因此使用 `.gitkeep` 保留目录名。

视频、音频、转写、字幕、剪辑稿、审核记录、图片、标题封面候选及发布材料均不入库。已安装 Python 包、模型、字体及缓存也不入库。GitHub 仅同步流程和工具，不同步任务进度或素材；更换电脑后若要继续旧任务，需另外传输原片和完整任务目录。

## 在另一台电脑安装

当前已验收环境是 **Windows、Python 3.12、FFmpeg/FFprobe**。其他操作系统尚未验收；固定版本依赖需由目标平台提供兼容的安装包。

1. 安装 Git、Python 3.12（含 pip）和 FFmpeg，将 `python`、`git`、`ffmpeg`、`ffprobe` 加入 PATH。FFmpeg 需要支持 `ass`（libass）、`libx264` 和 AAC。Windows 概览小字使用系统微软雅黑字体。
2. 克隆仓库，在仓库根目录执行：

```powershell
git clone https://github.com/erinchocolate/video-os.git
cd video-os
python -X utf8 scripts/setup_resources.py --init
python -X utf8 scripts/setup_resources.py --packages --model --font "D:\字体\xinqingnian.ttf"
python -X utf8 scripts/video.py doctor --deep
python -X utf8 scripts/video.py status
```

第二条安装命令会联网把固定版本依赖安装到 `scripts/vendor/`，把转写模型下载到 `scripts/models/large-v3-turbo/`，并复制指定字体到 `scripts/fonts/xinqingnian.ttf`；不修改全局 Python 包。它不上传视频。字体需自行从有权使用的来源准备：字幕配置要求 **文悦新青年体 / WenYue XinQingNianTi (Non-Commercial Use) W8**，字体授权需与实际用途匹配。仓库不分发字体。模型来源和 SHA256 记录在 [环境配置](scripts/config/environment.json)，恢复和深度检查会核对模型哈希。

如果暂时没有字体，可先执行 `--packages --model` 下载依赖和模型；最后的检查会提示字体缺失，补齐后重跑 `doctor --deep`。`--init` 单独执行时只建目录，不需要第三方 Python 包。已有同名字体或模型不一致时停止，不覆盖本地资源。`requirements.lock.txt` 是版本清单，不是跨平台哈希锁；安装失败时保留错误记录，确认目标 Python/系统兼容性后再调整版本并重新验收。

## 目录

```text
Inbox/          待处理视频（本地）
raw/            完整原片（本地）
process/        每条视频的转写、剪辑及字幕过程（本地）
final/          检查通过的成片（本地）
package/        标题封面候选、修订及筛选记录（本地）
upload/         最终选定的五类发布材料（本地，不代表已发布）
  published/    已发布材料的本地归档目录
skill/          分环节 SOP 和共享参考
scripts/        共享脚本、配置、模板和测试
  vendor/       安装后的 Python 依赖（本地）
  models/       下载后的模型（本地）
  fonts/        自行准备的字体（本地）
  cache/        缓存及合成测试物料（本地）
```

`package/` 是发布包装物料目录，和 Python 依赖包不是同一个概念；两者都排除实际内容，仅保留目录或依赖清单。

## 使用与验证

把新视频放入 `Inbox/`，让 agent 按工作流处理。每条新视频必须先展示具体剪辑稿并获得针对该稿的确认；若要求字幕审核，则先审核当前版本再烧录。发布包装先给 20 组实际标题封面，用户最终选择后才导出 `upload/`。

```powershell
python -X utf8 scripts/video.py --help
python -X utf8 scripts/tests/test_setup_resources.py
python -X utf8 scripts/tools/check_workspace.py
python -X utf8 scripts/tests/test_packaging.py
```

最后一条同时运行剪辑工作流测试，使用 `scripts/cache/selftest/` 下的隔离合成素材，不处理原片。测试需要已安装依赖、字体及 FFmpeg。日常修改脚本或 skill 后，可用 `git status` 检查，再提交和推送；不要使用 `git add -f` 强行加入被排除的物料。
