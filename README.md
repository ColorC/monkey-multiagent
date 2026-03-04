# Monkey's Multiagent 🐒

> **"Just Files. No Magic. Banana-driven Development."**

Monkey's Multiagent is an ultra-minimalist, file-driven orchestrator. It treats the file system as a playground where agents play "catch" with Markdown files. It doesn't care if your agent is a super-intelligence or a simple bash script—if it can write a file, it's part of the troop.

## New: Monkey-in-the-Cage Mode 🎡
You can now run Monkey's Multiagent as a "black box" plugin for other agent frameworks or CLI tools. Just pass your objective as a command-line argument:

```bash
python3 orchestrator.py "Refactor the project to use async/await"
```

The "Cage" (Orchestrator) will keep the monkeys working (Execute-Audit cycle) until the mission is accomplished, with built-in **Stuck Detection** that automatically swaps monkeys if they get into a loop.

## The Monkey Philosophy

Agent frameworks are too smart for their own good. They hide states in complex databases. **Monkey** returns to the trees: **Everything is a file.**

1. **The Monkey (Agent)** does the work.
2. **The Banana (Sentinel File)** marks the end of a turn.
3. **The Troop (Orchestrator)** swaps or retries the monkeys based on their physical output.

## The Protocol

Monkeys talk by throwing files at each other:

- `STOP.md`: "I'm done. Here's my banana." (Reviewer wakes up)
- `CONTINUE.md`: "This banana is rotten. Fix it." (Executor wakes up)
- `HANDOVER.md`: "Too heavy for me. You take it." (Roles swap)

## Features

- **Stuck Detection**: Uses MD5 hashing of agent logs to detect if a monkey is repeating itself. If output stops changing, it automatically swaps to a different monkey.
- **Auto-Retry**: If an agent process crashes or silences, the troop automatically re-runs it before giving up.
- **Configurable Troop**: Customize your lead executor and senior reviewer via `monkey_config.json`.
- **Transparent Interaction**: Full TTY transparency. You see the colors, the progress bars, and the "Thinking..." states in real-time.

## Configuration (`monkey_config.json`)

```json
{
    "executor": "claude",
    "reviewer": "gemini",
    "inactivity_timeout": 60,
    "max_auto_retries": 3
}
```

## Why use this?

- **Zero Context Noise**: Injects only relevant mission data and truncated summaries to keep the "Wise Monkey" focused on the actual files.
- **Physical Resume**: Kill the orchestrator anytime. It remembers everything by looking at the files in the session folder.
- **Agent-Agnostic**: Works with `claude`, `gemini`, or any CLI that accepts a prompt as an argument.

---

*“Even a monkey can code, but it takes a troop of monkeys to build an empire.”*

## License
MIT
