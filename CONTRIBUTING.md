# Contributing

欢迎提交小而明确的改进。

1. 从 `main` 创建一个描述单一改动的短分支。
2. 修改行为时，新增或更新一个能证明该行为的聚焦测试。
3. 运行完整单测：

   ```powershell
   python -B -m unittest discover -s tests/fps-highlight-editor -p "test_*.py" -v
   ```

4. 修改 Skill 指令或资源后，运行本地 Skill 校验，并确认 `fps-highlight-editor/` 仍是可独立安装的目录。
5. 若改动影响 FFmpeg 命令、帧率、音轨或清理，补做相应的真实媒体验证。
6. 提交 Pull Request，说明问题、最小解决方案、验证命令和结果。

请勿提交游戏录像、音乐、生成视频、FFmpeg 二进制、访问令牌或机器专用路径。新依赖必须有当前标准库或现有工具无法满足的明确理由。
