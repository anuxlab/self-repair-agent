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

def report_problem_failure(
    problem: str, spec: dict, error: str, failure_class: str = "model_invocation_error",
    passed_tests: int | None = None, total_tests: int | None = None, rounds: int | None = None,
) -> None:
    """Create/update one labeled issue per model/problem after a failed repair attempt."""
    if not ISSUE_REPORTING or not os.getenv("GH_TOKEN") or not os.getenv("GITHUB_REPOSITORY"):
        return
    repo = os.environ["GITHUB_REPOSITORY"]
    model_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", MODEL).strip("-")
    problem_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(problem).stem).strip("-").lower()
    difficulty = str(spec.get("difficulty", "unknown")).lower()
    repair_level = (
        "easy" if difficulty in {"easy", "easy-medium"} else
        "medium" if difficulty in {"medium", "medium-hard"} else
        "hard" if difficulty == "hard" else "unknown"
    )
    error_lower = error.lower()
    failure_class_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", failure_class.lower().replace("_", "-")).strip("-")
    failure_kind = (
        "dependency" if any(token in error_lower for
                            token in ("modulenotfounderror", "no module named", "pip install", "dependency", "package not found"))
        else "timeout" if "timeout" in error_lower or "timed out" in error_lower
        else "agentic"
    )
    labels = [
        "automation", "bug", "benchmark-failure", f"model-{model_slug}", f"problem-{problem_slug}",
        f"difficulty-{difficulty}", f"repair-level-{repair_level}",
        f"failure-{failure_kind}", f"failure-{failure_class_slug}",
    ]
    if failure_class == "model_invocation_error":
        labels.append("failure-model-invocation")
    title = f"Benchmark failure: {model_slug} / {problem_slug} / {difficulty}"
    run_url = os.getenv("GITHUB_RUN_URL") or (
        f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{repo}/actions/runs/{os.getenv('GITHUB_RUN_ID', 'unknown')}"
    )
    body = (
        "## Automated coding-task failure\n\n"
        f"- **Model:** `{MODEL}`\n- **Problem ID:** `{problem_slug}`\n"
        f"- **Difficulty:** `{difficulty}` (repair level: `{repair_level}`)\n"
        f"- **Bug family:** `{spec.get('bug_family', 'unspecified')}`\n"
        f"- **Failure class:** `{failure_class}`\n- **Failure category:** `{failure_kind}`\n"
        f"- **Repair rounds attempted:** `{rounds if rounds is not None else 'not recorded'}`\n"
        f"- **Independent tests passed:** `{passed_tests if passed_tests is not None else 'not evaluated'}/"
        f"{total_tests if total_tests is not None else 'not evaluated'}`\n"
        f"- **Run:** {run_url}\n\n"
        f"### Last failure details\n\n{error[:1500]}\n\n"
        "This issue is deduplicated by model + problem. It distinguishes model invocation/setup failures "
        "from syntax/runtime/wrong-output failures; it does not claim the model's source is a repository bug.\n\n"
        "### Suggested checks\n"
        "1. Inspect the model artifact, source snapshots, selfrepair_log.json, and Ollama diagnostics.\n"
        "2. For invocation/dependency failures, inspect the first failed setup or smoke-test step.\n"
        "3. For wrong outputs, compare failed test categories and repair rounds.\n"
        "4. Re-run after addressing the relevant failure class.\n"
    )
    env = os.environ.copy()
    try:
        label_specs = [
            ("automation", "5319e7", "Created by workflow automation"),
            ("bug", "d73a4a", "Bug or failure"),
            ("benchmark-failure", "b60205", "Model/problem did not converge or could not be evaluated"),
            (f"model-{model_slug}", "1d76db", "Coding model associated with the failure"),
            (f"problem-{problem_slug}", "0052cc", "Problem/question ID associated with the failure"),
            (f"difficulty-{difficulty}", "c2e0c6", "Benchmark task difficulty"),
            (f"repair-level-{repair_level}", "bfdadc", "Estimated bug-repair difficulty"),
            (f"failure-{failure_kind}", "e4e669", "Failure category"),
            (f"failure-{failure_class_slug}", "d93f0b", "Failure class for the model/problem result"),
        ]
        if failure_class == "model_invocation_error":
            label_specs.append(("failure-model-invocation", "d93f0b", "Model call failed before evaluation"))
        for label, color, desc in label_specs:
            subprocess.run(["gh", "label", "create", label, "--repo", repo, "--color", color,
                            "--description", desc[:100]], env=env, capture_output=True, text=True,
                           timeout=15, check=False)
        listed = subprocess.run(
            ["gh", "issue", "list", "--repo", repo, "--state", "open", "--json", "number,title"],
            env=env, capture_output=True, text=True, timeout=20, check=True)
        issues = json.loads(listed.stdout or "[]")
        existing = next((str(item["number"]) for item in issues if item.get("title") == title), None)
        if existing:
            subprocess.run(["gh", "issue", "comment", existing, "--repo", repo, "--body", body],
                           env=env, capture_output=True, text=True, timeout=20, check=True)
            label_csv = ",".join(labels)
            subprocess.run(["gh", "issue", "edit", existing, "--repo", repo, "--add-label", label_csv],
                           env=env, capture_output=True, text=True, timeout=20, check=False)
            log.warning("Updated GitHub issue #%s for benchmark failure (%s)", existing, problem)
        else:
            created = subprocess.run(
                ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body,
                 "--label", ",".join(labels)], env=env, capture_output=True, text=True,
                timeout=20, check=True)
            log.error("Created GitHub issue for benchmark failure: %s", created.stdout.strip())
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
            report_problem_failure(spec_path.name, spec, error_text, failure_class="model_invocation_error", total_tests=len(spec["tests"]), rounds=len(history) + 1)
            # Keep a machine-readable record even when no source was returned.
            (SOLUTIONS_DIR / f"{slug}.round-{round_no:02d}.status.json").write_text(
                json.dumps({"round": round_no, "model": MODEL, "problem": spec_path.name,
                            "failure_class": "model_invocation_error", "error": error_text},
                           indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            break
        syntax_error = validate_syntax(code)
        solution_path.write_text(code, encoding="utf-8")
        (SOLUTIONS_DIR / f"{slug}.round-{round_no:02d}.py").write_text(code, encoding="utf-8")
        if syntax_error:
            last_test = {"passed": False, "passed_tests": 0, "total_tests": len(spec["tests"]), "failures": [syntax_error], "failure_class": "syntax_error", "exit_code": None, "timed_out": False, "stdout": "", "stderr": ""}
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
            "final_code_path": str(solution_path.relative_to(ROOT)) if solution_path.exists() else None, "final_code": code,
            "last_test_report": last_test, "history": history}
    if not converged and result["failure_class"] != "model_invocation_error":
        failure_details = "\\n".join(last_test.get("failures", [])[:12]) or last_test.get("error") or result["failure_class"]
        report_problem_failure(
            spec_path.name, spec, failure_details,
            failure_class=result["failure_class"],
            passed_tests=result["passed_tests"], total_tests=result["total_tests"],
            rounds=result["rounds"],
        )
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
    manifest = {
        "model": MODEL,
        "problem_count": len(results),
        "solved_count": report["solved_count"],
        "solutions": [
            {"problem": r["problem"], "difficulty": r["difficulty"],
             "converged": r["converged"], "rounds": r["rounds"],
             "rounds_to_converge": r["rounds_to_converge"],
             "failure_class": r["failure_class"], "source": r["final_code_path"]}
            for r in results
        ],
    }
    (SOLUTIONS_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Results: %d/%d solved. Report: %s", report["solved_count"], len(results), LOG_PATH)
    # Wrong answers are benchmark outcomes; model invocation errors fail the job.
    invocation_errors = [r for r in results if r.get("failure_class") == "model_invocation_error"]
    return 1 if invocation_errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
