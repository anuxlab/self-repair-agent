#!/usr/bin/env python3
"""Aggregate benchmark reports into per-model difficulty and bug-family profiles."""
import json, sys
from pathlib import Path
src = Path(sys.argv[1] if len(sys.argv) > 1 else "downloaded-results")
out = Path("aggregate-report"); out.mkdir(parents=True, exist_ok=True)
paths = sorted(src.rglob("selfrepair_log.json")) if src.exists() else []
records, errors, seen = [], [], []
artifact_dirs = sorted(p for p in src.iterdir() if p.is_dir()) if src.exists() else []
missing_report_dirs = []
for artifact_dir in artifact_dirs:
    if not any(artifact_dir.rglob("selfrepair_log.json")):
        missing_report_dirs.append(artifact_dir.name)
        errors.append({
            "path": str(artifact_dir),
            "error": "Artifact has no selfrepair_log.json; the model likely failed before evaluation (inspect diagnostics and the first failed workflow step).",
        })
if not paths:
    errors.append({"path": str(src), "error": "No selfrepair_log.json files found."})
for path in paths:
    try:
        report=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report,dict) or not isinstance(report.get("results"),list): raise ValueError("Expected results list")
        model=report.get("model")
        if not model: raise ValueError("Missing model")
        seen.append(model)
        if not report["results"]: errors.append({"path":str(path),"error":"Zero result entries"})
        for r in report["results"]:
            if not isinstance(r,dict) or not r.get("problem"): raise ValueError("Malformed result entry")
            records.append({"model":model,"problem":r.get("problem"),"difficulty":r.get("difficulty","unknown"),
              "bug_family":r.get("bug_family","unspecified"),"converged":bool(r.get("converged")),
              "passed_tests":r.get("passed_tests",0),"total_tests":r.get("total_tests",0),"rounds":r.get("rounds",0),
              "rounds_to_converge":r.get("rounds_to_converge"),"problem_seconds":r.get("problem_seconds"),
              "failure_class":r.get("failure_class","unknown"),"failed_bug_categories":r.get("failed_bug_categories",[]),
              "category_results":r.get("category_results",{})})
    except Exception as exc: errors.append({"path":str(path),"error":f"{type(exc).__name__}: {exc}"})
models=sorted(set(seen)); summary={"schema_version":3,"artifacts_found":len(artifact_dirs),"artifacts_missing_reports":missing_report_dirs,"report_files_found":len(paths),"models_found":models,"runs":records,"errors":errors}
(out/"aggregate.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
problem_count = len({r.get("problem") for r in records})
lines=["# Self-Repair Agent: Bug-Level Capability Report","",f"Unique benchmark problems evaluated or attempted: **{problem_count}**","",f"Artifacts found: **{len(artifact_dirs)}** | Report files: **{len(paths)}** | Model-problem records: **{len(records)}** | Report errors: **{len(errors)}**",""]
if missing_report_dirs:
 lines += ["## Incomplete model artifacts","", "These artifacts were uploaded but contain no evaluation log. They must not be counted as model failures or successes; inspect the first failed setup/smoke-test step.",""] + [f"- `{name}`: missing `selfrepair_log.json`" for name in missing_report_dirs] + [""]
lines += [
"> Difficulty and capability labels describe this repository's hand-written tasks only. Invocation failures are reported separately from wrong answers; they are not counted as evaluated coding attempts. Small fixed test sets do not establish general coding ability.","",
"## Overall results","","| Model | Solved / attempted (code-evaluated) | Invocation errors | Pass rate on evaluated code | Tests passed | Mean repair rounds (solved) | Mean seconds/task |","|---|---:|---:|---:|---:|---:|---:|"]
for m in models:
 rs=[r for r in records if r['model']==m]
 evaluated=[r for r in rs if r.get('failure_class') != 'model_invocation_error']
 solved=sum(r['converged'] for r in evaluated)
 invocation_errors=sum(r.get('failure_class') == 'model_invocation_error' for r in rs)
 tests=sum(r['passed_tests'] for r in evaluated)
 total=sum(r['total_tests'] for r in evaluated)
 sec=sum(float(r.get('problem_seconds') or 0) for r in rs)/len(rs) if rs else 0
 solved_rounds=[float(r.get('rounds_to_converge') or r.get('rounds') or 0) for r in evaluated if r['converged']]
 mean_rounds=(sum(solved_rounds)/len(solved_rounds)) if solved_rounds else 0
 rate=(solved/len(evaluated)) if evaluated else 0
 status=f"{solved}/{len(rs)} ({len(evaluated)} evaluated)"
 lines.append(f"| {m} | {status} | {invocation_errors} | {rate:.1%} | {tests}/{total} ({tests/total:.1%}) | {mean_rounds:.2f} | {sec:.1f} |" if evaluated and total else f"| {m} | {status} | {invocation_errors} | n/a | n/a | n/a | {sec:.1f} |")
lines += ["","## Performance by difficulty","","Only tasks where code reached the independent test harness are counted below.","","| Model | Difficulty | Solved | Code evaluated | Pass rate |","|---|---|---:|---:|---:|"]
for m in models:
 for diff in sorted({r['difficulty'] for r in records if r['model']==m and r.get('failure_class') != 'model_invocation_error'}):
  rs=[r for r in records if r['model']==m and r['difficulty']==diff and r.get('failure_class') != 'model_invocation_error']; n=sum(r['converged'] for r in rs)
  lines.append(f"| {m} | {diff} | {n} | {len(rs)} | {n/len(rs):.1%} |")
lines += ["","## Bug-category diagnostic","","Category pass rate measures tagged tests passed across each model's evaluated problems. A category with few tests is weak evidence; inspect the denominators.","","| Model | Bug category | Passed | Total | Rate |","|---|---|---:|---:|---:|"]
for m in models:
 agg={}
 for r in records:
  if r['model']!=m or r.get('failure_class') == 'model_invocation_error': continue
  for cat,st in r.get('category_results',{}).items():
   a=agg.setdefault(cat,[0,0]); a[0]+=int(st.get('passed',0)); a[1]+=int(st.get('total',0))
 for cat,(p,t) in sorted(agg.items()): lines.append(f"| {m} | {cat} | {p} | {t} | {p/t:.1%} |" if t else f"| {m} | {cat} | {p} | {t} | n/a |")
lines += ["","## Per-problem outcomes","","| Model | Problem | Difficulty | Bug family | Tests passed | Repair rounds | Converged | Failure class | Failed categories | Seconds |","|---|---|---|---|---:|---:|---|---|---|---:|"]
for r in records:
 lines.append(f"| {r['model']} | {r['problem']} | {r['difficulty']} | {r['bug_family']} | {r['passed_tests']}/{r['total_tests']} | {r['rounds']} | {'yes' if r['converged'] else 'no'} | {r['failure_class']} | {', '.join(r['failed_bug_categories']) or '—'} | {float(r.get('problem_seconds') or 0):.1f} |")
if errors: lines += ["","## Missing or invalid reports",""]+[f"- `{e['path']}`: {e['error']}" for e in errors]
(out/"aggregate-report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
print((out/"aggregate-report.md").read_text(encoding="utf-8"))
if errors or not records: sys.exit(2)
