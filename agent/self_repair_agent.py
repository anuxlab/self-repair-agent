\
#!/usr/bin/env python3
"""Local-model code-generation and test-driven repair benchmark.

All generated code runs in a separate, time-limited subprocess. This is a CI
benchmark, not a hardened security sandbox; never run untrusted code with secrets.
"""
from __future__ import annotations
import ast, json, logging, os, re, subprocess, sys, time
from pathlib import Path
from typing import Any
from langchain_openai import ChatOpenAI

ROOT = Path(__file__).resolve().parents[1]
PROBLEM_DIR = ROOT / "problems"
OUTPUT_DIR = ROOT / "artifacts"
SOLUTIONS_DIR = OUTPUT_DIR / "solutions"
LOG_PATH = OUTPUT_DIR / "selfrepair_log.json"
MODEL = os.getenv("QWEN_MODEL", "qwen3:4b")
MAX_ROUNDS = max(1, int(os.getenv("MAX_REPAIR_ROUNDS", "3")))
EXEC_TIMEOUT = max(1, int(os.getenv("EXEC_TIMEOUT_SECONDS", "5")))
MAX_OUTPUT_CHARS = 6000
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("self-repair")

llm = ChatOpenAI(
    model=MODEL,
    base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
    api_key="ollama",  # required by OpenAI-compatible client; local Ollama ignores it
    temperature=0.2,
    timeout=int(os.getenv("LLM_TIMEOUT_SECONDS", "300")),
    max_retries=1,
)

SYSTEM_PROMPT = """You are an expert Python programmer working in a test-driven code-repair benchmark.
Return ONLY the complete Python source code for the requested function, optionally inside one python code fence.
Do not include a main block, test runner, explanation, markdown outside the code fence, file writes, imports from local files, or network access.
Think carefully through edge cases and complexity before answering, but do not print your private reasoning. Implement the exact function signature/name in the task. Never hard-code the listed examples; solve the general problem."""

def extract_code(content: Any) -> str:
    if isinstance(content, list):
        content = "\n".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in content)
    text = str(content).strip()
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S | re.I)
    if match:
        return match.group(1).strip() + "\n"
    # Avoid saving conversational prose as Python. ast.parse below will reject it.
    return text + "\n"

def validate_syntax(code: str) -> str | None:
    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        return f"SyntaxError at line {exc.lineno}, column {exc.offset}: {exc.msg}"

def run_tests(code_path: Path, spec_path: Path) -> dict:
    """Run isolated function-level tests in a subprocess; never trust model self-report."""
    runner = ROOT / "tests" / "run_cases.py"
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(runner), str(code_path), str(spec_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=EXEC_TIMEOUT,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
        )
        stdout, stderr = proc.stdout[-MAX_OUTPUT_CHARS:], proc.stderr[-MAX_OUTPUT_CHARS:]
        try:
            payload = json.loads(stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            payload = {"passed": False, "passed_tests": 0, "total_tests": 0, "failures": ["Test runner returned invalid JSON."], "error": stdout[-1000:]}
        payload.update({"exit_code": proc.returncode, "stdout": stdout, "stderr": stderr, "timed_out": False})
        if proc.returncode != 0:
            payload["passed"] = False
        return payload
    except subprocess.TimeoutExpired as exc:
        return {"passed": False, "passed_tests": 0, "total_tests": 0, "failures": [f"Execution timed out after {EXEC_TIMEOUT}s"], "exit_code": None, "stdout": str(exc.stdout or "")[-1000:], "stderr": str(exc.stderr or "")[-1000:], "timed_out": True}

def invoke_model(spec: dict, previous_code: str, test_result: dict, round_no: int) -> tuple[str, float, str]:
    if round_no == 1:
        task = f"Task: {spec['statement']}\nRequired function name: {spec['name']}\n"
    else:
        failures = "\n".join(test_result.get("failures", [])[:10]) or test_result.get("error", "Tests did not pass.")
        task = (f"Repair the previous implementation for this task: {spec['statement']}\n"
                f"Required function name: {spec['name']}\nPrevious code:\n```python\n{previous_code}\n```\n"
                f"Independent test report ({test_result.get('passed_tests', 0)}/{test_result.get('total_tests', 0)} passed):\n{failures}\n"
                "Return the complete corrected source file, not a patch.")
    started = time.perf_counter()
    response = llm.invoke([("system", SYSTEM_PROMPT), ("user", task)])
    elapsed = time.perf_counter() - started
    content = getattr(response, "content", response)
    usage = getattr(response, "usage_metadata", None) or {}
    code = extract_code(content)
    return code, elapsed, json.dumps(usage, ensure_ascii=False) if usage else ""

def solve(spec_path: Path) -> dict:
    spec = json.loads(spec_path.read_text())
    slug = spec_path.stem
    solution_path = SOLUTIONS_DIR / f"{slug}.py"
    history, code = [], ""
    started_problem = time.perf_counter()
    last_test = {"passed": False, "passed_tests": 0, "total_tests": len(spec["tests"]), "failures": ["No attempt yet"]}
    for round_no in range(1, MAX_ROUNDS + 1):
        log.info("%s: round %d/%d with %s", slug, round_no, MAX_ROUNDS, MODEL)
        try:
            code, llm_seconds, token_usage = invoke_model(spec, code, last_test, round_no)
        except Exception as exc:
            history.append({"round": round_no, "model_error": f"{type(exc).__name__}: {exc}", "passed": False})
            log.exception("Model invocation failed for %s", slug)
            break
        syntax_error = validate_syntax(code)
        solution_path.write_text(code)
        if syntax_error:
            last_test = {"passed": False, "passed_tests": 0, "total_tests": len(spec["tests"]), "failures": [syntax_error], "exit_code": None, "timed_out": False, "stdout": "", "stderr": ""}
        else:
            last_test = run_tests(solution_path, spec_path)
        entry = {"round": round_no, "llm_seconds": round(llm_seconds, 4), "token_usage": token_usage or None,
                 "syntax_error": syntax_error, "passed": bool(last_test.get("passed")),
                 "passed_tests": last_test.get("passed_tests", 0), "total_tests": last_test.get("total_tests", len(spec["tests"])),
                 "test_report": last_test, "code_snapshot": code}
        history.append(entry)
        if last_test.get("passed"):
            break
    converged = bool(last_test.get("passed"))
    return {"problem": spec_path.name, "function": spec["name"], "difficulty": spec["difficulty"], "model": MODEL,
            "rounds": len(history), "rounds_to_converge": len(history) if converged else None,
            "converged": converged, "passed_tests": last_test.get("passed_tests", 0),
            "total_tests": last_test.get("total_tests", len(spec["tests"])),
            "problem_seconds": round(time.perf_counter() - started_problem, 4),
            "final_code_path": str(solution_path.relative_to(ROOT)), "final_code": code,
            "last_test_report": last_test, "history": history}

def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)
    specs = sorted(PROBLEM_DIR.glob("*.json"))
    if not specs:
        log.error("No JSON problem specs found in %s", PROBLEM_DIR)
        return 2
    results = [solve(path) for path in specs]
    report = {"schema_version": 2, "model": MODEL, "max_repair_rounds": MAX_ROUNDS,
              "problem_count": len(results), "solved_count": sum(r["converged"] for r in results),
              "pass_rate": round(sum(r["converged"] for r in results) / len(results), 4), "results": results}
    LOG_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    log.info("Results: %d/%d solved. Report: %s", report["solved_count"], len(results), LOG_PATH)
    # Keep CI green to upload evidence even if the model fails; the report makes failures explicit.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
