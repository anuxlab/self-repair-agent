# agent/self_repair_agent.py
import os
import subprocess
import sys
import json
import logging
from pathlib import Path

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("qwen-selfrepair")

# --- Local Ollama endpoint: no API key required ---
# Ollama accepts any non-empty api_key when running locally.
llm = ChatOpenAI(
    model=os.environ.get("QWEN_MODEL", "qwen3:4b"),   # qwen3:4b, qwen3:8b, qwen3:1.7b, etc.
    base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),  # placeholder; Ollama does not validate it
    temperature=0.2,
)

@tool
def write_code(code: str, filename: str = "solution.py") -> str:
    """Write generated or repaired Python code to a file."""
    Path(filename).write_text(code)
    return f"Wrote {len(code)} chars to {filename}"

@tool
def execute_code(filename: str = "solution.py", timeout: int = 10) -> str:
    """Execute a Python file and return its exit code, stdout, and stderr."""
    try:
        result = subprocess.run(
            [sys.executable, filename],
            capture_output=True, text=True, timeout=timeout,
        )
        return (
            f"EXIT={result.returncode}\n"
            f"STDOUT:\n{result.stdout.strip()}\n"
            f"STDERR:\n{result.stderr.strip()}"
        )
    except subprocess.TimeoutExpired:
        return "EXIT=TIMEOUT"

agent = create_agent(
    model=llm,
    tools=[write_code, execute_code],
    system_prompt=(
        "You are a senior Python engineer. Write clean, correct code. "
        "When you receive an execution error, diagnose the root cause and "
        "rewrite only the necessary parts. Always call write_code with the "
        "full file content, then call execute_code to verify. "
        "If the code already passes, reply DONE."
    ),
)

def solve_problem(problem_path: Path, max_rounds: int = 3) -> dict:
    problem = problem_path.read_text()
    history = []
    last_output = "No execution yet."

    for round_idx in range(1, max_rounds + 1):
        logger.info("🔁 Round %d / %d for %s", round_idx, max_rounds, problem_path.name)

        result = agent.invoke({
            "messages": [
                ("user",
                 f"Problem statement:\n{problem}\n\n"
                 f"Last execution output:\n{last_output}\n\n"
                 "Write or repair the code so that it passes all tests. "
                 "If it already passes, reply DONE.")
            ]
        })

        agent_text = result["messages"][-1].content
        logger.info("Agent response: %s", agent_text[:500])

        code_file = Path("solution.py")
        current_code = code_file.read_text() if code_file.exists() else ""

        exec_out = execute_code.invoke({"filename": "solution.py"})
        last_output = exec_out

        history.append({
            "round": round_idx,
            "agent_output": agent_text,
            "execution": exec_out,
            "code_snapshot": current_code,
        })

        if "EXIT=0" in exec_out and "STDERR:\n\n" in exec_out:
            logger.info("✅ Converged on round %d", round_idx)
            break
        if agent_text.strip().upper() == "DONE":
            logger.info("Agent signalled DONE on round %d", round_idx)
            break
    else:
        logger.warning("❌ Did not converge within %d rounds", max_rounds)

    return {
        "problem": problem_path.name,
        "rounds": len(history),
        "converged": "EXIT=0" in last_output,
        "final_code": Path("solution.py").read_text() if Path("solution.py").exists() else "",
        "history": history,
        "last_output": last_output,
    }

if __name__ == "__main__":
    problem_dir = Path("problems")
    results = []
    for prob_file in sorted(problem_dir.glob("*.py")):
        logger.info("=== Processing %s ===", prob_file.name)
        results.append(solve_problem(prob_file))

    Path("selfrepair_log.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    logger.info("All results written to selfrepair_log.json")