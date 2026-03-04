import os
import subprocess
import time
import sys
import datetime
import re
import signal
import threading
from pathlib import Path

# --- Configuration ---
AGENT_EXECUTOR = os.getenv("MONKEY_EXECUTOR", "claude")
AGENT_REVIEWER = os.getenv("MONKEY_REVIEWER", "gemini")

BASE_DIR = Path(__file__).resolve().parent
SESSIONS_ROOT = BASE_DIR / "sessions"
CURRENT_PROJECT_ROOT = BASE_DIR

def monitor_sentinels(process, session_dir, stop_event):
    """Background monitor: Kills the process if marker files appear."""
    markers = ["STOP.md", "HANDOVER.md", "CONTINUE.md"]
    while not stop_event.is_set():
        if process.poll() is not None:
            break
        for m in markers:
            if (session_dir / m).exists():
                print(f"\n[Monkey] {m} detected. Turn complete. Ending process...")
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except:
                    process.terminate()
                return
        time.sleep(1)

def run_agent_interactive(cmd_list, session_dir):
    """Runs the agent in the foreground with full TTY transparency."""
    print(f"\n[EXEC]: {' '.join(cmd_list)}\n" + "="*60)
    for s in ["STOP.md", "HANDOVER.md", "CONTINUE.md"]:
        if (session_dir / s).exists(): (session_dir / s).unlink()

    process = subprocess.Popen(
        cmd_list,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        preexec_fn=os.setsid 
    )

    stop_event = threading.Event()
    monitor_thread = threading.Thread(target=monitor_sentinels, args=(process, session_dir, stop_event))
    monitor_thread.start()

    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n[User Abort]")
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    finally:
        stop_event.set()
        monitor_thread.join(timeout=1)
    print("="*60 + "\n")

def setup_session(instruction=None, resume_path=None):
    if not SESSIONS_ROOT.exists():
        SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    if resume_path:
        session_path = Path(resume_path)
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = re.sub(r'[/]', '_', instruction[:50]).strip()
        session_path = SESSIONS_ROOT / f"{timestamp}_{clean_name}"
    session_path.mkdir(parents=True, exist_ok=True)
    (session_path / "logs").mkdir(parents=True, exist_ok=True)
    task_file = session_path / "TASK.md"
    if instruction:
        task_file.write_text(instruction, encoding="utf-8")
    return session_path

def get_status_content(session_path, name, truncate=None):
    p = session_path / f"{name}.md"
    if p.exists():
        content = p.read_text(encoding="utf-8").strip()
        if truncate and len(content) > truncate:
            return content[:truncate] + "\n\n...(Truncated for brevity, please audit the actual files)..."
        return content
    return None

def orchestrate(session_path):
    session_abs = session_path.absolute()
    executor = AGENT_EXECUTOR
    reviewer = AGENT_REVIEWER
    iteration = 1
    
    while True:
        task_file = session_path / "TASK.md"
        if not task_file.exists(): break
        task_desc = task_file.read_text(encoding="utf-8")
        
        # --- [HUMAN VIEW] ---
        print(f"\n🚀 [Iteration {iteration}] Alpha Monkey (Executor): {executor}")
        
        last_feedback = get_status_content(session_path, "CONTINUE")
        
        # --- [AI PROMPT: PROFESSIONAL EXECUTOR] ---
        prompt = (
            f"### ROLE ###\n"
            f"You are a Lead Software Engineer. Your goal is to implement the requested features or fixes. "
            f"Be surgical, follow best practices, and work autonomously.\n\n"
            f"### MISSION OBJECTIVE ###\n{task_desc}\n\n"
        )
        if last_feedback:
            prompt += f"### REVISION REQUIREMENTS (From Architect) ###\n{last_feedback}\n\n"
        
        prompt += (
            f"### OPERATIONAL PROTOCOL ###\n"
            f"1. Project Root: {CURRENT_PROJECT_ROOT}\n"
            f"2. SUCCESS: Once complete, write a professional summary of changes to: {session_abs}/STOP.md\n"
            f"3. STUCK: If you encounter an unresolvable blocker, write the technical reason to: {session_abs}/HANDOVER.md\n"
            f"IMPORTANT: Your turn ends immediately upon writing either file. Do not wait for user input."
        )

        if executor == "claude":
            cmd = ["claude", "--dangerously-skip-permissions", prompt]
        elif executor == "gemini":
            cmd = ["gemini", "--yolo", prompt]
        else:
            cmd = [executor, prompt]
            
        run_agent_interactive(cmd, session_path)

        if (session_abs / "HANDOVER.md").exists():
            print(f"\n[Monkey] Alpha Monkey requested handoff.")
            executor, reviewer = reviewer, executor
            continue

        if (session_abs / "STOP.md").exists():
            summary_snippet = get_status_content(session_path, "STOP", truncate=1200)
            
            # --- [HUMAN VIEW] ---
            print(f"\n🔍 [Iteration {iteration}] Wise Monkey (Reviewer): {reviewer}")
            
            # --- [AI PROMPT: PROFESSIONAL REVIEWER] ---
            review_prompt = (
                f"### ROLE ###\n"
                f"You are a Senior Software Architect and Auditor. Your goal is to verify the work performed by the implementation engineer. "
                f"Do not take their word for granted; inspect the codebase directly for correctness, performance, and adherence to requirements.\n\n"
                f"### ORIGINAL MISSION ###\n{task_desc}\n\n"
                f"### IMPLEMENTATION SUMMARY (Snippet) ###\n{summary_snippet}\n\n"
                f"### AUDIT INSTRUCTIONS ###\n"
                f"1. Audit the codebase at: {CURRENT_PROJECT_ROOT}\n"
                f"2. REJECT: If requirements are missing or code is flawed, write specific feedback to: {session_abs}/CONTINUE.md\n"
                f"3. TAKE OVER: If you need to perform the fix yourself, write your intent to: {session_abs}/HANDOVER.md\n"
                f"4. PASS: If everything is perfect, simply exit/abort without writing any marker files."
            )
            
            if (session_path / "CONTINUE.md").exists(): (session_path / "CONTINUE.md").unlink()
            
            if reviewer == "gemini":
                cmd_rev = ["gemini", "--yolo", review_prompt]
            elif reviewer == "claude":
                cmd_rev = ["claude", "--dangerously-skip-permissions", review_prompt]
            else:
                cmd_rev = [reviewer, review_prompt]
            
            run_agent_interactive(cmd_rev, session_path)
            
            if (session_path / "CONTINUE.md").exists():
                print(f"\n❌ [Audit] Wise Monkey rejected the work. Sending back for revisions.")
                iteration += 1
                continue
            elif (session_path / "HANDOVER.md").exists():
                executor, reviewer = reviewer, executor
                continue
            else:
                print(f"\n✅ [Success] Wise Monkey approved the work. Mission Accomplished!")
                break

        print(f"\n⚠️ Agent exited without status update.")
        choice = input("[r]etry, [h]andover, [f]eedback, [q]uit: ").lower()
        if choice == 'r': iteration += 1; continue
        elif choice == 'h': executor, reviewer = reviewer, executor; continue
        elif choice == 'f':
            f_text = input("Enter manual feedback: ")
            (session_path / "CONTINUE.md").write_text(f_text, encoding="utf-8")
            continue
        else: break

def main():
    print("=== MONKEY'S MULTIAGENT: Just Files. No Magic. ===")
    while True:
        if not SESSIONS_ROOT.exists(): SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
        try:
            sessions = sorted([d for d in SESSIONS_ROOT.iterdir() if d.is_dir()], reverse=True)
        except:
            sessions = []
            
        print(f"\nSession History:")
        print(f"0. [CREATE NEW MISSION]")
        for i, s in enumerate(sessions, 1):
            print(f"{i}. {s.name}")
            
        choice = input("\nSelect Index (q to quit): ")
        if choice.lower() == 'q': break
        if choice == '0':
            task = input("Enter Objective: ")
            if not task: continue
            orchestrate(setup_session(instruction=task))
        elif choice.isdigit() and 0 < int(choice) <= len(sessions):
            orchestrate(sessions[int(choice)-1])

if __name__ == "__main__":
    main()
