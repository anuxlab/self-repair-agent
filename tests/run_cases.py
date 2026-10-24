\
#!/usr/bin/env python3
"""Minimal isolated runner for JSON-defined function tests; emits JSON on last stdout line."""
import importlib.util, json, sys, traceback
from pathlib import Path

def main():
    code_path, spec_path = map(Path, sys.argv[1:3])
    spec = json.loads(spec_path.read_text())
    result = {"passed": False, "passed_tests": 0, "total_tests": len(spec["tests"]), "failures": [], "error": None}
    try:
        module_spec = importlib.util.spec_from_file_location("candidate_solution", code_path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        fn = getattr(module, spec["name"])
        for i, case in enumerate(spec["tests"], 1):
            try:
                actual = fn(*case["args"])
                expected = case["expected"]
                if case.get("unordered_list"):
                    ok = sorted(actual) == sorted(expected) if isinstance(actual, (list, tuple)) else False
                else:
                    ok = actual == expected
                if ok:
                    result["passed_tests"] += 1
                else:
                    result["failures"].append(f"Test {i}: args={case['args']!r}; expected {expected!r}, got {actual!r}")
            except Exception as exc:
                result["failures"].append(f"Test {i}: {type(exc).__name__}: {exc}")
        result["passed"] = result["passed_tests"] == result["total_tests"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["failures"].append(result["error"])
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
