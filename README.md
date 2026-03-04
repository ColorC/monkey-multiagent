# 极简多Agent框架 (Minimal Multi-Agent Framework)

这是一个基于文件系统状态机的极简编排工具，利用 `Claude Code` 和 `Gemini CLI` 的 Session 机制实现持续工作与代码审计。

## 核心机制
- **Executor (执行者)**: 负责写代码和执行任务。完成后创建 `status/STOP`。
- **Reviewer (审核者)**: 负责检查结果。不满意则创建 `status/CONTINUE`。
- **Handover (移交)**: 任何一方觉得搞不定，创建 `status/HANDOVER` 换人。
- **To-Human (求助)**: 陷入死循环或双方都放弃，请求人类介入。

## 快速开始
1. 进入目录：`cd /home/zhouhaowen/projects/minimal-agent-framework/`
2. 初始化 Git (可选但推荐): `git init`
3. 编辑任务：`nano TASK.md` (填入你的需求)
4. 运行编排脚本：`python3 orchestrator.py`

## 注意事项
- 脚本默认使用了 `--dangerously-skip-permissions` (Claude) 和 `--yolo` (Gemini) 标志，请确保在受信任的环境中运行。
- Agent 的上下文（Session）由各自的 CLI 自动管理。
