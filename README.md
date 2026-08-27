# FPS Highlight Editor

一个面向 Valorant（无畏契约）和 PUBG 素材的 Codex Skill：先让 AI 与你一起找高光、确认剪辑方案，再用 FFmpeg 输出可复查、可迭代的版本。支持横屏 60 fps、保留游戏原声、BGM 卡点、转场、变速、质量验证，以及最终确认后的安全清理。

> An agent-guided Codex Skill for reviewable, versioned Valorant and PUBG highlight edits using FFmpeg. It supports music, effects, validation, and exact-plan cleanup.

## 它适合什么

本项目是“AI 辅助剪辑工作流”，不是承诺自动识别所有击杀的黑盒模型。Agent 会检查素材、提出候选片段和剪辑理由；你确认后，它才渲染新版本。Valorant 与 PUBG 的 UI、淘汰提示和节奏不同，因此具体高光仍需要视觉判断和用户反馈。

主要模式：

- `inspect`：读取素材信息并创建 `edit-project.json`。
- `draft`：把已批准的片段剪成初版。
- `music`：使用有授权依据的本地音乐副本进行混音和卡点。
- `enhance`：在批准范围内加入转场、强调和变速。
- `verify`：检查 MP4、分辨率、帧率、音频、响度、完整解码和 QC 画面。
- `cleanup`：先生成精确删除计划，再用一次明确确认执行；原始素材永不属于普通清理范围。

## 环境要求

- Codex
- Python 3.10 或更高版本
- [FFmpeg 与 ffprobe](https://ffmpeg.org/download.html)

脚本只使用 Python 标准库；仓库不捆绑 FFmpeg、游戏素材或音乐。

## 安装

```powershell
git clone https://github.com/zouyuetao-lgtm/fps-highlight-editor.git
cd fps-highlight-editor
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -LiteralPath ".\fps-highlight-editor" -Destination "$env:USERPROFILE\.codex\skills\fps-highlight-editor"
```

如果目标 Skill 已存在，请先保留现有副本并确认内容，再自行更新。仓库级的测试、文档和 GitHub 配置不需要复制。

## 最小工作流

1. 在 Codex 中说明素材目录、游戏、横竖屏、目标帧率和成片用途。
2. Agent 检查素材并创建项目记录，例如：

   ```powershell
   python scripts/inspect_media.py ".\game-footage" --output-dir ".\video-output\project-name" --game valorant --target-fps 60
   ```

3. Agent 提出候选高光、片段顺序和节奏方案；你批准或调整。
4. Agent 把已批准片段渲染为新版本：

   ```powershell
   python scripts/render_project.py ".\video-output\project-name\edit-project.json" draft
   ```

5. 需要 BGM 或效果时，先批准音乐授权记录、卡点方案或效果范围，再运行 `music` / `enhance` 模式。
6. 用 `validate_output.py` 验证候选 MP4；你拍板后才把版本标记为最终版。
7. 如需腾出空间，先运行 `cleanup_project.py plan` 展示完整路径和摘要；只有你确认该摘要后才运行 `execute`。

完整规则见 [Skill 入口](fps-highlight-editor/SKILL.md) 及其 `references/` 文档。各脚本参数可用 `python scripts/<name>.py --help` 查看。

## 安全与音乐版权

- 源素材只读；渲染使用新版本文件且不覆盖旧版本。
- 清理只能删除 manifest 可分类、精确列出且摘要已确认的派生文件；预检失败时零删除。
- 最终版、批准版、报告、授权证据和复现最终版所需的音乐副本受保护。
- “标注原创者”不等于取得使用授权。BGM 渲染必须绑定与实际本地音乐副本匹配的授权证据。
- 使用用户提供的商业音乐仍可能触发平台版权声明、静音、限流或收益限制。

## 当前限制

- 没有内置的端到端击杀识别模型；候选片段由 Agent 结合画面、音频和游戏规则提出。
- 自动测试覆盖安全规则与命令生成；真实 FFmpeg 全流程作为本地发布检查，不在 CI 下载大型二进制。
- 成片质量仍依赖素材清晰度、HUD、音轨、录制帧率和用户对节奏的反馈。

## 路线图

- 根据真实 Valorant / PUBG 项目继续改进高光候选规则。
- 增加更多可批准的转场、变速与强调模板。
- 在有稳定样本后评估可选的自动事件检测，而不是提前引入重型模型。
- 有实际版本管理需求后再加入发行包和 changelog。

## 相关项目与规范

这些链接用于理解生态和设计取舍；本仓库没有复制它们的代码或素材。

- [Agent Skills / SKILL.md](https://github.com/Open-Dot-Agents/SKILL.md)
- [FFmpeg](https://ffmpeg.org/)
- [Auto-Editor](https://github.com/WyattBlue/auto-editor)
- [PySceneDetect](https://github.com/Breakthrough/PySceneDetect)
- [GameVideoEdit](https://github.com/Friend-Xu/GameVideoEdit)

## 许可

[MIT License](LICENSE) © 2026 fps-highlight-editor contributors
