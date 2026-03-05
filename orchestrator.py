import os
import subprocess
import time
import sys
import datetime
import re
import signal
import json
import pty
import select
import hashlib
import fcntl
import termios
import struct
from pathlib import Path

# --- Configuration & Paths ---
BASE_DIR = Path(__file__).resolve().parent
SESSIONS_ROOT = BASE_DIR / "sessions"
CURRENT_PROJECT_ROOT = BASE_DIR
CONFIG_FILE = BASE_DIR / "monkey_config.json"

def load_config():
    defaults = {
        "executor": "claude",
        "reviewer": "gemini",
        "inactivity_timeout": 60,
        "max_auto_retries": 3
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                defaults.update(data)
        except: pass
    return defaults

def set_pty_size(fd, rows=40, cols=120): # 稍微放宽点宽度
    size = struct.pack('HHHH', rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, size)

def run_agent_autonomous(cmd_list, session_dir, timeout):
    """
    运行 Agent，透传 TTY，但不主动录制 log。
    返回 (Success_Flag, Data_Hash)
    """
    print(f"\n[EXEC]: {' '.join(cmd_list)}\n" + "-"*60)
    
    markers = ["STOP.md", "HANDOVER.md", "CONTINUE.md"]
    for m in ["STOP.md", "HANDOVER.md"]:
        if (session_dir / m).exists(): (session_dir / m).unlink()

    last_output_time = time.time()
    master_fd, slave_fd = pty.openpty()
    set_pty_size(slave_fd)
    
    # 继承所有环境变量，确保 Auth 状态 (如 CLAUDE_CONFIG_DIR 等)
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["PYTHONUNBUFFERED"] = "1"
    
    process = subprocess.Popen(
        cmd_list,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=os.setsid, env=env
    )
    os.close(slave_fd)

    # 内存中维护一个缓冲区用于计算哈希（不写文件）
    hash_accumulator = hashlib.md5()

    try:
        while True:
            # 1. 哨兵检测
            for m in markers:
                if (session_dir / m).exists():
                    print(f"\n[Monkey] Marker {m} found. Turn complete.")
                    return True, hash_accumulator.hexdigest()

            # 2. 输出透传与哈希计算
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if master_fd in r:
                try:
                    data = os.read(master_fd, 8192)
                    if data:
                        # 实时透传到屏幕
                        os.write(sys.stdout.fileno(), data)
                        # 累加哈希用于死循环检测
                        hash_accumulator.update(data)
                        last_output_time = time.time()
                except OSError: pass

            # 3. 进程退出检查
            retcode = process.poll()
            if retcode is not None:
                # 扫尾读取
                try:
                    remaining = os.read(master_fd, 8192)
                    os.write(sys.stdout.fileno(), remaining)
                    hash_accumulator.update(remaining)
                except: pass
                print(f"\n[System] Process exited ({retcode}).")
                return False, hash_accumulator.hexdigest()

            # 4. 超时检测
            if time.time() - last_output_time > timeout:
                print(f"\n[System] Silence for {timeout}s. Harvesting...")
                return False, hash_accumulator.hexdigest()

    finally:
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.2)
            if process.poll() is None: os.killpg(pgid, signal.SIGKILL)
        except: pass
        try: os.close(master_fd)
        except: pass

def setup_session(instruction):
    if not SESSIONS_ROOT.exists(): SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # 支持中文和空格
    clean_name = re.sub(r'[/]', '_', instruction[:50]).strip()
    session_path = SESSIONS_ROOT / f"{timestamp}_{clean_name}"
    session_path.mkdir(parents=True, exist_ok=True)
    (session_path / "logs").mkdir(parents=True, exist_ok=True)
    (session_path / "TASK.md").write_text(instruction, encoding="utf-8")
    return session_path

def orchestrate(session_path):
    config = load_config()
    executor, reviewer = config["executor"], config["reviewer"]
    timeout, max_retries = config["inactivity_timeout"], config["max_auto_retries"]
    session_abs = session_path.absolute()
    logs_abs = (session_path / "logs").absolute()
    
    last_exec_hash = ""
    retry_count = 0
    iteration = 1
    
    while True:
        task_desc = (session_path / "TASK.md").read_text(encoding="utf-8")
        last_feedback = (session_path / "CONTINUE.md").read_text(encoding="utf-8") if (session_path / "CONTINUE.md").exists() else None
        
        print(f"\n🚀 [Round {iteration}] Alpha Monkey: {executor} (Try {retry_count+1})")
        
        # 强化 Prompt：明确 logs 目录权限
        prompt = (
            f"### MISSION ###\n{task_desc}\n\n"
            f"### PROTOCOL ###\n"
            f"1. Working Dir: {CURRENT_PROJECT_ROOT}\n"
            f"2. Logs Dir: {logs_abs} (Output any detailed logs/reports here)\n"
            f"3. SUCCESS: Write summary to {session_abs}/STOP.md\n"
            f"4. STUCK: Write reason to {session_abs}/HANDOVER.md\n"
            f"Your turn ends once a marker file is created."
        )
        if last_feedback: prompt += f"\n\n### REVISION REQ ###\n{last_feedback}"

        cmd = ["claude", "--dangerously-skip-permissions", prompt] if executor == "claude" else \
              (["gemini", "--yolo", prompt] if executor == "gemini" else [executor, prompt])
            
        success, current_hash = run_agent_autonomous(cmd, session_path, timeout)

        if (session_path / "HANDOVER.md").exists():
            executor, reviewer = reviewer, executor
            retry_count = 0; iteration += 1; continue

        if not (session_path / "STOP.md").exists():
            if current_hash == last_exec_hash and retry_count >= max_retries:
                print("\n[System] Persistent failure. Swapping...")
                executor, reviewer = reviewer, executor
                retry_count = 0; last_exec_hash = ""
            else:
                last_exec_hash = current_hash
                retry_count += 1
            iteration += 1; continue

        # Reviewer Turn
        retry_count = 0
        summary = (session_path / "STOP.md").read_text(encoding="utf-8")[:1200]
        print(f"\n🔍 [Round {iteration}] Wise Monkey: {reviewer}")
        
        rev_prompt = (
            f"### MISSION ###\n{task_desc}\n\n"
            f"### SUMMARY ###\n{summary}\n\n"
            f"### AUDIT PROTOCOL ###\n"
            f"1. Audit: {CURRENT_PROJECT_ROOT}\n"
            f"2. Logs: {logs_abs}\n"
            f"3. REJECT? -> {session_abs}/CONTINUE.md\n"
            f"4. PASS? -> Do nothing."
        )
        
        if (session_path / "CONTINUE.md").exists(): (session_path / "CONTINUE.md").unlink()
        cmd_rev = ["gemini", "--yolo", rev_prompt] if reviewer == "gemini" else \
                  (["claude", "--dangerously-skip-permissions", rev_prompt] if reviewer == "claude" else [reviewer, rev_prompt])
        
        run_agent_autonomous(cmd_rev, session_path, timeout)
        
        if (session_path / "CONTINUE.md").exists():
            print("\n❌ [Audit] REJECTED."); iteration += 1; continue
        elif (session_path / "HANDOVER.md").exists():
            executor, reviewer = reviewer, executor; iteration += 1; continue
        else:
            print("\n✅ [Success] Mission accomplished!"); break

def main():
    if len(sys.argv) > 1:
        orchestrate(setup_session(" ".join(sys.argv[1:])))
    else:
        print("=== MONKEY'S MULTIAGENT v15 (Freedom Edition) ===")
        while True:
            if not SESSIONS_ROOT.exists(): SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
            try:
                sessions = sorted([d for d in SESSIONS_ROOT.iterdir() if d.is_dir()], reverse=True)
            except: sessions = []
            print(f"\nHistory:\n0. [NEW MISSION]")
            for i, s in enumerate(sessions, 1): print(f"{i}. {s.name}")
            choice = input("\nSelect Index (q to quit): ")
            if choice.lower() == 'q': break
            if choice == '0':
                task = input("Objective: ")
                if task: orchestrate(setup_session(task))
            elif choice.isdigit() and 0 < int(choice) <= len(sessions):
                orchestrate(sessions[int(choice)-1])

if __name__ == "__main__": main()
