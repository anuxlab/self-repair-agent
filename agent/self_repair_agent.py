# agent/self_repair_agent.py
import os
import subprocess
import sys
import json
import logging
from pathlib import Path
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_community.chat_models import ChatOpenAI  # Qwen via DashScope compatible API

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("qwen-selfrepair")

# ---------------------------------------------------------------- Qwen model
# Use Qwen3-4B or Qwen3-8B through an OpenAI-compatible endpoint.
# Replace with your own base_url / key (e.g., DashScope, Ollama, vLLM).
llm = ChatOpenAI(
    model="qwen3-4b",          # or "qwen3-8b"
    openai_api_base=os.environ["QWEN_API_BASE"],   # e.g. https://dashscope.aliyuncs.com/compatible-mode/v1
    openai_api_key=os.environ["QWEN_API_KEY"],
    temperature=0.2,
)

# ---------------------------------------------------------------- tools
@tool
def write_code(code: str, filename: str = "solution.py") -> str:
    """Write generated or repaired code to a file."""
    Path(filename).write_text(code)
    return f"Wrote {len(code)} chars to {filename}"

@tool
def execute_code(filename: str = "solution.py", timeout: int = 10) -> str:
    """Run the Python file and return stdout / stderr."""
    try:
        result = subprocess.run(
            [sys.executable, filename],
            capture_output=True, text=True, timeout=timeout,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        return f"EXIT={result.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
    except subprocess.TimeoutExpired:
        return "EXIT=TIMEOUT"

# ---------------------------------------------------------------- prompt
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a senior Python engineer. You write clean, correct code. "
     "When you receive an execution error, you diagnose the root cause and "
     "rewrite only the necessary parts. Always call the write_code tool "
     "with the full file content, then call execute_code to verify."),
    ("human",
     "Problem statement:\n{problem}\n\n"
     "Current code (if any):\n```python\n{current_code}\n```\n\n"
     "Last execution output:\n{last_output}\n\n"
     "Write or repair the code so that it passes all tests. "
     "If it already passes, reply DONE."),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, [write_code, execute_code], prompt)
executor = AgentExecutor(agent=agent, tools=[write_code, execute_code], verbose=True)

# ---------------------------------------------------------------- self-repair loop
def solve_problem(problem_path: Path, max_rounds: int = 5) -> dict:
    problem = problem_path.read_text()
    current_code = ""
    last_output = "No execution yet."
    history = []

    for round_idx in range(1, max_rounds + 1):
        logger.info("🔁 Round %d / %d for %s", round_idx, max_rounds, problem_path.name)
        result = executor.invoke({
            "problem": problem,
            "current_code": current_code,
            "last_output": last_output,
        })
        agent_text = result["output"]
        logger.info("Agent response: %s", agent_text[:500])

        # Read whatever the agent wrote to disk
        code_file = Path("solution.py")
        if code_file.exists():
            current_code = code_file.read_text()

        # Re-execute to get a fresh, structured result for the next round
        exec_out = execute_code.invoke({"filename": "solution.py"})
        last_output = exec_out
        history.append({
            "round": round_idx,
            "agent_output": agent_text,
            "execution": exec_out,
            "code_snapshot": current_code,
        })

        if "EXIT=0" in exec_out and "STDERR:\n\n" in exec_out:   # crude success check
            logger.info("✅ Solution converged on round %d", round_idx)
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
        "final_code": current_code,
        "history": history,
        "last_output": last_output,
    }

if __name__ == "__main__":
    problem_dir = Path("problems")
    results = []
    for prob_file in sorted(problem_dir.glob("*.py")):
        logger.info("=== Processing %s ===", prob_file.name)
        results.append(solve_problem(prob_file))

    # Save full log as artifact
    Path("selfrepair_log.json").write_text(json.dumps(results, indent=2))
    logger.info("All results written to selfrepair_log.json")