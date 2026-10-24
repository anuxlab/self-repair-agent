#!/usr/bin/env python3
import json, sys
from pathlib import Path
src = Path(sys.argv[1] if len(sys.argv) > 1 else "downloaded-results")
out = Path("aggregate-report"); out.mkdir(parents=True, exist_ok=True)
records=[]; errors=[]
for path in sorted(src.rglob("selfrepair_log.json")):
    try:
        report=json.loads(path.read_text())
        for r in report.get("results", []):
            records.append({"model":report.get("model",r.get("model","unknown")),"problem":r.get("problem"),"difficulty":r.get("difficulty"),"converged":r.get("converged",False),"passed_tests":r.get("passed_tests",0),"total_tests":r.get("total_tests",0),"rounds":r.get("rounds",0),"rounds_to_converge":r.get("rounds_to_converge"),"problem_seconds":r.get("problem_seconds")})
    except Exception as e: errors.append({"path":str(path),"error":str(e)})
summary={"schema_version":1,"runs":records,"errors":errors}
(out/"aggregate.json").write_text(json.dumps(summary,indent=2)+"\n")
models=sorted({r["model"] for r in records})
lines=["# Qwen3 Self-Repair Benchmark Results","",f"Records: **{len(records)}** | Model reports with errors: **{len(errors)}**","","## Per-model summary","","| Model | Solved | Problems | Pass rate | Mean seconds/problem |","|---|---:|---:|---:|---:|"]
for model in models:
    rs=[r for r in records if r["model"]==model]; solved=sum(bool(r["converged"]) for r in rs); mean=sum(float(r.get("problem_seconds") or 0) for r in rs)/len(rs) if rs else 0
    lines.append(f"| {model} | {solved} | {len(rs)} | {solved/len(rs):.1%} | {mean:.2f} |" if rs else f"| {model} | 0 | 0 | n/a | n/a |")
lines += ["","## Per-problem results","","| Model | Problem | Passed tests | Rounds | Converged | Seconds |","|---|---|---:|---:|---|---:|"]
for r in records: lines.append(f"| {r['model']} | {r['problem']} | {r['passed_tests']}/{r['total_tests']} | {r['rounds']} | {'yes' if r['converged'] else 'no'} | {float(r.get('problem_seconds') or 0):.2f} |")
if errors: lines += ["","## Artifact errors",""] + [f"- `{e['path']}`: {e['error']}" for e in errors]
(out/"aggregate-report.md").write_text("\n".join(lines)+"\n")
print((out/"aggregate-report.md").read_text())
