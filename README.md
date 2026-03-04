# Monkey's Multiagent 🐒

> **"Just Files. No Magic. Banana-driven Development."**

Monkey's Multiagent is an ultra-minimalist, file-driven orchestrator. It treats the file system as a playground where agents play "catch" with Markdown files. It doesn't care if your agent is a super-intelligence or a simple bash script—if it can write a file, it's part of the troop.

## The Monkey Philosophy

Agent frameworks are too smart for their own good. They hide states in complex databases. **Monkey** returns to the trees: **Everything is a file.**

1. **The Monkey (Agent)** does the work.
2. **The Banana (Sentinel File)** marks the end of a turn.
3. **The Troop (Orchestrator)** swaps the monkeys once a banana is found.

## The Protocol

Monkeys talk by throwing files at each other:

- `STOP.md`: "I'm done. Here's my banana." (Reviewer wakes up)
- `CONTINUE.md`: "This banana is rotten. Fix it." (Executor wakes up)
- `HANDOVER.md`: "Too heavy for me. You take it." (Roles swap)

Once a marker file is detected, the Orchestrator stops the current monkey and brings in the next one.

## Quick Start

### 1. Installation
Zero dependencies. Just Python 3.
```bash
git clone https://github.com/your-repo/monkey-multiagent.git
cd monkey-multiagent
```

### 2. Run
Ensure your agents (like `claude` or `gemini`) are in your PATH.
```bash
python3 orchestrator.py
```

### 3. Usage
- Select `[0] CREATE NEW MISSION`.
- Input your objective.
- Watch the monkeys play.

## Why use this?

- **Transparent Interaction**: You see what the monkey sees. You can even hand it a real banana (type into the terminal) if it gets stuck.
- **Physical Resume**: Kill the orchestrator anytime. Restart it, select the session, and the troop remembers everything by looking at the files.
- **True Peer-to-Peer**: Monkeys can tap out. No hierarchy, just coordination.

---

*“Even a monkey can code, but it takes a troop of monkeys to build an empire.”*

## License
MIT
