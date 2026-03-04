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

def strip_ansi(text):
    """剔除 ANSI 转义序列（颜色、光标移动等）"""
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

def set_pty_size(fd, rows=40, cols=80):
    """固定 PTY 窗口大小，防止 Agent 疯狂重绘"""
    size = struct.pack('HHHH', rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, size)

def get_content_hash(log_path):
    if not os.path.exists(log_path): return ""
    with open(log_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def run_agent_autonomous(cmd_list, session_dir, timeout, log_name):
    """
    带窗口锁定和日志清洗的 Agent 运行器
    """
    log_path = session_dir / "logs" / log_name
    print(f"\n[EXEC]: {' '.join(cmd_list)}\n" + "-"*60)
    
    markers = ["STOP.md", "HANDOVER.md", "CONTINUE.md"]
    for m in ["STOP.md", "HANDOVER.md"]:
        if (session_dir / m).exists(): (session_dir / m).unlink()

    last_output_time = time.time()
    master_fd, slave_fd = pty.openpty()
    
    # 核心：锁定窗口大小
    set_pty_size(slave_fd)
    
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["PYTHONUNBUFFERED"] = "1"
    
    process = subprocess.Popen(
        cmd_list,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=os.setsid, env=env
    )
    os.close(slave_fd)

    # 日志写入器：负责清洗噪音
    with open(log_path, "w", encoding="utf-8") as log_f:
        try:
            partial_line = ""
            while True:
                # 1. 检查标志文件
                for m in markers:
                    if (session_dir / m).exists():
                        print(f"\n[Monkey] Marker {m} found.")
                        return True, get_content_hash(log_path)

                # 2. 监控输出
                r, _, _ = select.select([master_fd], [], [], 0.5)
                if master_fd in r:
                    try:
                        data = os.read(master_fd, 8192)
                        if data:
                            # 原始数据直通屏幕（保留颜色和进度条，给人类看）
                            os.write(sys.stdout.fileno(), data)
                            
                            # 清洗后的数据写入日志（剔除 ANSI，折叠回车）
                            chunk = data.decode('utf-8', errors='ignore')
                            clean_chunk = strip_ansi(chunk)
                            
                            # 简单的回车处理：如果包含 \r，只记录这块输出的最后部分，减少冗余
                            if '\r' in clean_chunk:
                                parts = clean_chunk.split('\r')
                                clean_chunk = parts[-1] 
                            
                            log_f.write(clean_chunk)
                            log_f.flush()
                            last_output_time = time.time()
                    except OSError: pass

                # 3. 进程退出检查
                retcode = process.poll()
                if retcode is not None:
                    print(f"\n[System] Process exited ({retcode}).")
                    return False, get_content_hash(log_path)

                # 4. 超时检测
                if time.time() - last_output_time > timeout:
                    print(f"\n[System] Silence for {timeout}s. Harvesting...")
                    return False, get_content_hash(log_path)

        finally:
            try:
                pgid = os.setsid(os.getpgid(process.pid)) # 获取进程组
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.2)
                if process.poll() is None: os.killpg(pgid, signal.SIGKILL)
            except: pass
            try: os.close(master_fd)
            except: pass

def setup_session(instruction):
    if not SESSIONS_ROOT.exists(): SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
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
    
    last_exec_hash = ""
    retry_count = 0
    iteration = 1
    
    while True:
        task_desc = (session_path / "TASK.md").read_text(encoding="utf-8")
        last_feedback = (session_path / "CONTINUE.md").read_text(encoding="utf-8") if (session_path / "CONTINUE.md").exists() else None
        
        print(f"\n🚀 [Round {iteration}] Alpha Monkey: {executor} (Try {retry_count+1})")
        
        prompt = (
            f"### MISSION ###\n{task_desc}\n\n"
        )
        if last_feedback: prompt += f"### REVISION REQ ###\n{last_feedback}\n\n"
        prompt += f"### PROTOCOL ###\nSUCCESS? -> {session_path.absolute()}/STOP.md\nSTUCK? -> {session_path.absolute()}/HANDOVER.md"

        cmd = ["claude", "--dangerously-skip-permissions", prompt] if executor == "claude" else \
              (["gemini", "--yolo", prompt] if executor == "gemini" else [executor, prompt])
            
        log_name = f"it_{iteration}_exec_{executor}_try_{retry_count}.log"
        success, current_hash = run_agent_autonomous(cmd, session_path, timeout, log_name)

        if (session_path / "HANDOVER.md").exists():
            executor, reviewer = reviewer, executor
            retry_count = 0; iteration += 1; continue

        if not (session_path / "STOP.md").exists():
            if current_hash == last_exec_hash and retry_count >= max_retries:
                print("\n[System] Persistent failure. Swapping monkeys...")
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
            f"### AUDIT ###\nREJECT? -> {session_path.absolute()}/CONTINUE.md\nPASS? -> Do nothing."
        )
        
        if (session_path / "CONTINUE.md").exists(): (session_path / "CONTINUE.md").unlink()
        cmd_rev = ["gemini", "--yolo", rev_prompt] if reviewer == "gemini" else \
                  (["claude", "--dangerously-skip-permissions", rev_prompt] if reviewer == "claude" else [reviewer, rev_prompt])
        
        run_agent_autonomous(cmd_rev, session_path, timeout, f"it_{iteration}_rev_{reviewer}.log")
        
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
        print("=== MONKEY'S MULTIAGENT v14 (Clean Log Edition) ===")
        while True:
            if not SESSIONS_ROOT.exists(): SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
            sessions = sorted([d for d in SESSIONS_ROOT.iterdir() if d.is_dir()], reverse=True)
            print(f"\nSession History:\n0. [CREATE NEW MISSION]")
            for i, s in enumerate(sessions, 1): print(f"{i}. {s.name}")
            choice = input("\nSelect Index (q to quit): ")
            if choice.lower() == 'q': break
            if choice == '0':
                task = input("Objective: ")
                if task: orchestrate(setup_session(task))
            elif choice.isdigit() and 0 < int(choice) <= len(sessions):
                orchestrate(sessions[int(choice)-1])

if __name__ == "__main__": main()
