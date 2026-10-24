# Coding-model run analysis — 2026-10-24

## Scope

This analysis is based on the uploaded aggregate report and the uploaded GitHub Actions logs. The previous run covered five hand-written tasks (30 independent tests per fully evaluated model). The expanded 21-task suite in this repository has **not** yet been run in GitHub Actions.

## Previous baseline results

| Model | Solved | Tests passed | Mean seconds/task | Interpretation |
|---|---:|---:|---:|---|
| `qwen2.5-coder:1.5b` | 5/5 | 30/30 | 4.2 | Passed the original suite in one round per task |
| `qwen2.5-coder:3b` | 5/5 | 30/30 | 10.7 | Passed the original suite in one round per task |
| `deepseek-coder:1.3b` | 5/5 | 30/30 | 9.3 | Passed the original suite in one round per task |
| `yi-coder:1.5b` | 5/5 | 30/30 | 9.5 | Passed the original suite in one round per task |
| `opencoder:1.5b` | 5/5 | 30/30 | 18.9 | Passed the original suite in one round per task |
| `qwen3:1.7b` | 4/5 | 22/30 | 68.4 | Four tasks passed; hard-task call timed out |
| `qwen2.5-coder:0.5b` | 3/5 | 17/30 | 64.3 | Medium and hard task calls timed out |
| `qwen3:0.6b` | 1/5 | 6/30 | 135.5 | Four invocation failures; poor CPU-runner reliability |
| `deepcoder:1.5b` | Not evaluated | — | — | Failed before evaluation in smoke test |

The success table is a small historical baseline only. Five tasks cannot establish general coding ability, and one run is not enough for a research-grade ranking.

## Root-cause findings

### DeepCoder 1.5B: smoke-test output budget / response compatibility

Ollama pulled the model successfully. The smoke-test request then returned `done_reason='length'`, empty `message.content`, and 126 characters in `message.thinking`, despite `think: false`. Because this happened before `selfrepair_log.json` was produced, DeepCoder must be recorded as **not evaluated**, not as a coding failure.

Changes in this patch:
- Increase the smoke-test output budget from 32 to 128 tokens and give it a 120-second timeout.
- Keep DeepCoder opt-in until an actual CI run proves the smoke test and benchmark complete.
- Preserve diagnostics for incomplete model artifacts.

### Qwen3 0.6B / Qwen3 1.7B / Qwen2.5-Coder 0.5B: model-call timeouts

The logs contain `openai.APITimeoutError` / `langchain_openai...ReadTimeout` during benchmark tasks. The affected task calls did not complete, so they are invocation failures rather than wrong-answer results. The supplied resource samples do not prove a memory leak.

Changes in this patch:
- Keep these variants out of the default matrix.
- Make them available through the experimental matrix.
- Report invocation errors separately from code-evaluated tasks in the aggregate report.
- Preserve per-round source snapshots and machine-readable status records.

### Existing GitHub issue

Issue [#1 — Automated benchmark workflow failure](https://github.com/anuxlab/self-repair-agent/issues/1) is still open. The uploaded logs show that the workflow reporter updated this existing issue rather than opening a duplicate. Do not close it solely because a patch is prepared. Close it only after a later run demonstrates that the workflow failure is resolved.

## Patch behavior

- Default benchmark matrix: five models that passed the previous five-task baseline.
- Experimental matrix: Qwen3 0.6B/1.7B, Qwen2.5-Coder 0.5B/7B, DeepCoder 1.5B, DeepSeek-Coder 6.7B, Granite Code 3B, and StarCoder2 3B. Qwen3 4B remains separately opt-in.
- Problem suite: 21 repository-authored task specifications, covering DP, graph traversal, weighted shortest paths, cycle detection, sliding windows, knapsack, and related edge cases.
- Generated code: final solution, per-round `.py` snapshots, and `solutions/manifest.json` are stored in each model artifact.
- Optional review PR: `publish_solutions=true` collects model artifacts under `benchmark-snapshots/run-<run_id>/`. Snapshot PRs are review-only and never close issues.
- Issue labels: model, problem ID, task difficulty, repair level, and failure category. Workflow-level failures receive a workflow/dependency/agentic label and any model labels recoverable from failed job names.

## Validation performed locally

- Nine unit tests passed, including problem-spec metadata/corpus checks.
- Python compile checks passed for `agent`, `scripts`, `tests`, and `problems`.
- All 16 new task specifications passed against independent reference implementations during patch validation.
- Both GitHub Actions workflow files parsed as YAML.
- Model-matrix selector produced unique artifact names in all four flag combinations: 5 default models, 13 experimental models, 6 with Qwen3 4B only, and 14 with both experimental flags.
- The snapshot preparation script was exercised against a synthetic artifact tree.

These checks do not replace a live GitHub Actions run. The updated repository has not been pushed to GitHub from this session.
