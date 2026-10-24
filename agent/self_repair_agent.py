#!/usr/bin/env python3
"""Local-model code-generation and test-driven repair benchmark.

All generated code runs in a separate, time-limited subprocess. This is a CI
benchmark, not a hardened security sandbox; never run untrusted code with secrets.
"""
from __future__ import annotations
import ast, json, logging, os, re, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any
from langchain_openai import ChatOpenAI

ROOT = Path(__file__).resolve().parents[1]
PROBLEM_DIR = ROOT / "problems"
OUTPUT_DIR = ROOT / "artifacts"
SOLUTIONS_DIR = OUTPUT_DIR / "solutions"
LOG_PATH = OUTPUT_DIR / "selfrepair_log.json"
MODEL = os.getenv("QWEN_MODEL", "qwen3:1.7b")
MAX_ROUNDS = max(1, int(os.getenv("MAX_REPAIR_ROUNDS", "3")))
EXEC_TIMEOUT = max(1, int(os.getenv("EXEC_TIMEOUT_SECONDS", "5")))
MAX_OUTPUT_CHARS = 6000
ISSUE_REPORTING = os.getenv("REPORT_GITHUB_ISSUES", "1") == "1"

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("self-repair")

llm = ChatOpenAI(
    model=MODEL,
    base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
    api_key="ollama",  # required by OpenAI-compatible client; local Ollama ignores it
    temperature=0.2,
    timeout=int(os.getenv("LLM_TIMEOUT_SECONDS", "240")),
    max_retries=0,
    max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
)

SYSTEM_PROMPT = """You are an expert Python programmer working in a test-driven code-repair benchmark.
Return ONLY the complete Python source code for the requested function, optionally inside one python code fence.
Do not include a main block, test runner, explanation, markdown outside the code fence, file writes, imports from local files, or network access.
Think carefully through edge cases and complexity before answering, but do not print your private reasoning. Implement the exact function signature/name in the task. Never hard-code the listed examples; solve the general problem."""

def extract_code(content: Any) -> str:
    if isinstance(content, list):
        content = "\n".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in content)
    text = str(content).strip()
    # Qwen3 may emit its thinking trace in tagged form on some Ollama endpoints.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
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

def cleanup_python_caches() -> None:
    """Remove Python bytecode caches created during each problem evaluation."""
    for base in (ROOT / "artifacts", ROOT / "problems", ROOT / "tests", ROOT / "agent", ROOT / "scripts"):
        if not base.exists():
            continue
        for cache_dir in base.rglob("__pycache__"):
            shutil.rmtree(cache_dir, ignore_errors=True)
        for pyc in base.rglob("*.pyc"):
            try:
                pyc.unlink()
            except OSError:
                pass

def report_invocation_issue(problem: str, error: str) -> None:
    """Create/update an issue immediately for model invocation failures."""
    if not ISSUE_REPORTING or not os.getenv("GH_TOKEN") or not os.getenv("GITHUB_REPOSITORY"):
        return
    repo = os.environ["GITHUB_REPOSITORY"]
    model_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", MODEL).strip("-")
    title = f"SLM invocation failure: {model_slug} / {problem}"
    run_url = os.getenv("GITHUB_RUN_URL") or (
        f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{repo}/actions/runs/{os.getenv('GITHUB_RUN_ID', 'unknown')}"
    )
    body = (
        "## Model invocation failure detected during benchmark\n\n"
        f"- **Model:** `{MODEL}`\n- **Problem:** `{problem}`\n"
        f"- **Run:** {run_url}\n- **Failure:** `{error[:500]}`\n\n"
        "The invocation failed before independent tests could assess generated code. "
        "This is tracked separately from ordinary wrong-answer outcomes.\n\n"
        "### Suggested checks\n"
        "1. Inspect Ollama server logs and runner memory pressure.\n"
        "2. Check the configured model-call timeout and output-token budget.\n"
        "3. Confirm the model endpoint remains responsive.\n"
        "4. Re-run after correcting the latency or infrastructure issue.\n"
    )
    env = os.environ.copy()
    try:
        for label, color, desc in [
            ("automation", "5319e7", "Created by workflow automation"),
            ("bug", "d73a4a", "Bug or failure"),
        ]:
            subprocess.run(["gh", "label", "create", label, "--repo", repo, "--color", color,
                            "--description", desc], env=env, capture_output=True, text=True,
                           timeout=15, check=False)
        listed = subprocess.run(
            ["gh", "issue", "list", "--repo", repo, "--state", "open", "--json", "number,title"],
            env=env, capture_output=True, text=True, timeout=20, check=True)
        issues = json.loads(listed.stdout or "[]")
        existing = next((str(item["number"]) for item in issues if item.get("title") == title), None)
        if existing:
            subprocess.run(["gh", "issue", "comment", existing, "--repo", repo, "--body", body],
                           env=env, capture_output=True, text=True, timeout=20, check=True)
            log.warning("Updated GitHub issue #%s for invocation failure (%s)", existing, problem)
        else:
            created = subprocess.run(
                ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body,
                 "--label", "automation,bug"], env=env, capture_output=True, text=True,
                timeout=20, check=True)
            log.error("Created GitHub issue for model invocation failure: %s", created.stdout.strip())
    except Exception as exc:
        log.warning("Could not report invocation failure to GitHub Issues: %s", exc)

def run_tests(code_path: Path, spec_path: Path) -> dict:
    """Run isolated function-level tests in a subprocess; never trust model self-report."""
    runner = ROOT / "tests" / "run_cases.py"
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(runner), str(code_path), str(spec_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=EXEC_TIMEOUT,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"},
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
            error_text = f"{type(exc).__name__}: {exc}"
            history.append({"round": round_no, "model_error": error_text,
                            "failure_class": "model_invocation_error", "passed": False})
            last_test = {"passed": False, "passed_tests": 0, "total_tests": len(spec["tests"]),
                         "failures": [error_text], "error": error_text,
                         "failure_class": "model_invocation_error",
                         "timed_out": "timeout" in error_text.lower()}
            log.exception("Model invocation failed for %s", slug)
            report_invocation_issue(spec_path.name, error_text)
            break
        syntax_error = validate_syntax(code)
        solution_path.write_text(code)
        if syntax_error:
            last_test = {"passed": False, "passed_tests": 0, "total_tests": len(spec["tests"]), "failures": [syntax_error], "exit_code": None, "timed_out": False, "stdout": "", "stderr": ""}
        else:
            last_test = run_tests(solution_path, spec_path)
        failure_class = ("syntax_error" if syntax_error else last_test.get("failure_class", "unknown"))
        category_results = last_test.get("category_results", {})
        failed_categories = [name for name, stats in category_results.items() if stats.get("passed", 0) < stats.get("total", 0)]
        entry = {"round": round_no, "llm_seconds": round(llm_seconds, 4), "token_usage": token_usage or None,
                 "syntax_error": syntax_error, "failure_class": failure_class,
                 "failed_bug_categories": failed_categories, "category_results": category_results,
                 "passed": bool(last_test.get("passed")),
                 "passed_tests": last_test.get("passed_tests", 0), "total_tests": last_test.get("total_tests", len(spec["tests"])),
                 "test_report": last_test, "code_snapshot": code}
        history.append(entry)
        if last_test.get("passed"):
            break
    converged = bool(last_test.get("passed"))
    final_categories = last_test.get("category_results", {})
    failed_categories = [name for name, stats in final_categories.items() if stats.get("passed", 0) < stats.get("total", 0)]
    result = {"problem": spec_path.name, "function": spec["name"], "difficulty": spec["difficulty"],
            "bug_family": spec.get("bug_family", "unspecified"), "bug_patterns": spec.get("bug_patterns", []),
            "difficulty_rubric": spec.get("difficulty_rubric", ""), "model": MODEL,
            "failure_class": ("none" if converged else ("syntax_error" if last_test.get("syntax_error") else last_test.get("failure_class", "not_converged"))),
            "failed_bug_categories": failed_categories, "category_results": final_categories,
            "rounds": len(history), "rounds_to_converge": len(history) if converged else None,
            "converged": converged, "passed_tests": last_test.get("passed_tests", 0),
            "total_tests": last_test.get("total_tests", len(spec["tests"])),
            "problem_seconds": round(time.perf_counter() - started_problem, 4),
            "final_code_path": str(solution_path.relative_to(ROOT)), "final_code": code,
            "last_test_report": last_test, "history": history}
    cleanup_python_caches()
    return result

def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)
    specs = sorted(PROBLEM_DIR.glob("*.json"))
    if not specs:
        log.error("No JSON problem specs found in %s", PROBLEM_DIR)
        return 2
    results = [solve(path) for path in specs]
    report = {"schema_version": 3, "model": MODEL, "max_repair_rounds": MAX_ROUNDS,
              "evaluation_note": "Observed performance on this fixed, small test set; not a general claim about model capability.",
              "problem_count": len(results), "solved_count": sum(r["converged"] for r in results),
              "pass_rate": round(sum(r["converged"] for r in results) / len(results), 4), "results": results}
    LOG_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    log.info("Results: %d/%d solved. Report: %s", report["solved_count"], len(results), LOG_PATH)
    # Wrong answers are benchmark outcomes; model invocation errors fail the job.
    invocation_errors = [r for r in results if r.get("failure_class") == "model_invocation_error"]
    return 1 if invocation_errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
