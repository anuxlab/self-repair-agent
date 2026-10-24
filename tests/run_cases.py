#!/usr/bin/env python3
"""Run JSON-defined tests and emit per-bug-category evidence as JSON."""
import importlib.util, json, sys, traceback
from pathlib import Path

def classify_exception(exc):
    name = type(exc).__name__
    if name in {"AttributeError", "NameError", "ImportError", "TypeError"}:
        return "runtime_exception:" + name
    return "runtime_exception:" + name

def main():
    code_path, spec_path = map(Path, sys.argv[1:3])
    spec = json.loads(spec_path.read_text())
    cases = spec["tests"]
    result = {"passed": False, "passed_tests": 0, "total_tests": len(cases), "failures": [], "error": None,
              "bug_family": spec.get("bug_family", "unspecified"), "difficulty": spec.get("difficulty", "unspecified"),
              "category_results": {}}
    try:
        module_spec = importlib.util.spec_from_file_location("candidate_solution", code_path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        fn = getattr(module, spec["name"])
        for i, case in enumerate(cases, 1):
            category = case.get("category", "uncategorized")
            stats = result["category_results"].setdefault(category, {"passed": 0, "total": 0, "failures": []})
            stats["total"] += 1
            try:
                actual = fn(*case["args"])
                expected = case["expected"]
                if case.get("unordered_list"):
                    ok = sorted(actual) == sorted(expected) if isinstance(actual, (list, tuple)) else False
                else:
                    ok = actual == expected
                if ok:
                    result["passed_tests"] += 1
                    stats["passed"] += 1
                else:
                    msg = f"Test {i} [{category}]: expected {expected!r}, got {actual!r}"
                    result["failures"].append(msg)
                    stats["failures"].append(msg)
            except Exception as exc:
                msg = f"Test {i} [{category}]: {classify_exception(exc)}: {exc}"
                result["failures"].append(msg)
                stats["failures"].append(msg)
        result["passed"] = result["passed_tests"] == result["total_tests"]
        result["failure_class"] = "none" if result["passed"] else ("runtime_exception" if any("runtime_exception:" in f for f in result["failures"]) else "wrong_output")
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["failures"].append(result["error"])
        result["failure_class"] = "load_or_entrypoint_error"
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
