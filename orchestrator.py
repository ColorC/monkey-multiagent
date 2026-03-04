import os
import subprocess
import time
import sys

# --- Configuration ---
# You can customize these commands based on your PATH and flags
AGENT_EXECUTOR = "claude"
AGENT_REVIEWER = "gemini"
STATUS_DIR = "status"
LOGS_DIR = "logs"
TASK_FILE = "TASK.md"

# Specific flags for non-interactive / autonomous mode
# Claude Code: --dangerously-skip-permissions for full shell access
# Gemini CLI: --yolo for autonomous mode
CMD_CLAUDE = "claude "{prompt}" --dangerously-skip-permissions"
CMD_GEMINI = "gemini "{prompt}" --yolo"

def run_command(cmd):
    print(f"
[Running]: {cmd}")
    # Stream output to console
    process = subprocess.Popen(cmd, shell=True, stdout=sys.stdout, stderr=sys.stderr)
    process.wait()

def setup():
    for d in [STATUS_DIR, LOGS_DIR]:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
    if not os.path.exists(TASK_FILE):
        with open(TASK_FILE, "w") as f:
            f.write("# Mission Objective
Write your requirements here...")
        print(f"Please fill in your requirements in {TASK_FILE} and run again.")
        sys.exit(0)

def clear_status():
    for f in ["STOP", "CONTINUE", "HANDOVER", "TO_HUMAN"]:
        p = os.path.join(STATUS_DIR, f)
        if os.path.exists(p):
            os.remove(p)

def get_status_content(filename):
    p = os.path.join(STATUS_DIR, filename)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

def git_checkpoint(message):
    if os.path.exists(".git"):
        print(f"
[Git]: Creating checkpoint - {message}")
        subprocess.run("git add .", shell=True)
        subprocess.run(f'git commit -m "{message}" --allow-empty', shell=True)

def main():
    setup()
    
    executor = AGENT_EXECUTOR
    reviewer = AGENT_REVIEWER
    iteration = 1

    print("=== Minimal Multi-Agent Orchestrator Starting ===")

    while True:
        print(f"
--- Round {iteration} ---")
        
        last_feedback = get_status_content("CONTINUE")
        task_desc = open(TASK_FILE, "r", encoding="utf-8").read()
        
        # 1. Prepare Executor Prompt
        prompt = f"### TASK OBJECTIVE ###
{task_desc}

"
        if last_feedback:
            prompt += f"### REVIEWER FEEDBACK ###
{last_feedback}

"
        
        prompt += (
            "### INSTRUCTION ###
"
            "You are the EXECUTOR. Execute the task. Use bash as needed.
"
            "1. If you believe you are DONE, you MUST create 'status/STOP' and write a summary of your work inside it.
"
            "2. If you find the task IMPOSSIBLE or too complex, you MUST create 'status/HANDOVER' and explain why.
"
            "Do NOT ask for confirmation. Work autonomously."
        )

        # 2. Run Executor
        clear_status()
        exec_cmd = CMD_CLAUDE if executor == "claude" else CMD_GEMINI
        run_command(exec_cmd.format(prompt=prompt))

        # 3. Check for Handover
        if os.path.exists(os.path.join(STATUS_DIR, "HANDOVER")):
            reason = get_status_content("HANDOVER")
            print(f"
[Handoff]: {executor} requested handover. Reason: {reason}")
            executor, reviewer = reviewer, executor # Swap roles
            continue

        # 4. Check for Stop/Review
        if os.path.exists(os.path.join(STATUS_DIR, "STOP")):
            summary = get_status_content("STOP")
            print(f"
[Review]: {executor} completed work. Invoking Reviewer ({reviewer})...")
            
            review_prompt = (
                f"### TASK OBJECTIVE ###
{task_desc}

"
                f"### EXECUTOR SUMMARY ###
{summary}

"
                "### INSTRUCTION ###
"
                "You are the REVIEWER. Check the work performed by the executor.
"
                "1. If it's CORRECT and COMPLETE, do NOTHING (the orchestrator will finish).
"
                "2. If it's WRONG or INCOMPLETE, you MUST create 'status/CONTINUE' with specific feedback.
"
                "3. If you can't review or think you should take over, create 'status/HANDOVER'.
"
                "Do NOT ask for confirmation."
            )

            review_cmd = CMD_GEMINI if reviewer == "gemini" else CMD_CLAUDE
            run_command(review_cmd.format(prompt=review_prompt))

            # Handle Reviewer Outcome
            if os.path.exists(os.path.join(STATUS_DIR, "CONTINUE")):
                print(f"
[Result]: Review failed. Retrying...")
                git_checkpoint(f"Round {iteration}: Review failed, moving to fix.")
                iteration += 1
                continue
            elif os.path.exists(os.path.join(STATUS_DIR, "HANDOVER")):
                if executor == AGENT_REVIEWER: # Both tried
                     with open(os.path.join(STATUS_DIR, "TO_HUMAN"), "w") as f:
                         f.write("Both agents requested handover.")
                else:
                    executor, reviewer = reviewer, executor
                    continue
            else:
                print(f"
[Success]: Task completed successfully!")
                git_checkpoint(f"Round {iteration}: Task completed.")
                break

        # 5. Help/Human Intervention
        if os.path.exists(os.path.join(STATUS_DIR, "TO_HUMAN")):
            print(f"
[HELP REQUIRED]: Agents have stalled.")
            human_input = input("Enter instruction for the Executor (or 'exit'): ")
            if human_input.lower() == 'exit':
                break
            with open(os.path.join(STATUS_DIR, "CONTINUE"), "w") as f:
                f.write(f"Human intervention: {human_input}")
            # Reset to original executor if needed or keep current
            continue

        # Fallback if no file created
        print("
[Warning]: Agent exited without creating any status file.")
        human_input = input("Continue anyway? (y/n) or 'handover': ")
        if human_input.lower() == 'y':
            iteration += 1
            continue
        elif human_input.lower() == 'handover':
            executor, reviewer = reviewer, executor
        else:
            break

        time.sleep(1)

if __name__ == "__main__":
    main()
