# Open-Source SLM Self-Repair Agent

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Ollama](https://img.shields.io/badge/Inference-Ollama-black?logo=ollama&logoColor=white)
![Open-source models](https://img.shields.io/badge/Models-Open%20source-success)
![Test-driven](https://img.shields.io/badge/Evaluation-Test--driven-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

**Tags:** `coding-agents` · `self-repair` · `local-LLM` · `Ollama` · `LangChain` · `GitHub-Actions` · `benchmark` · `dynamic-programming` · `graph-algorithms` · `shortest-path` · `bug-triage`

A test-driven code-generation and repair benchmark using local Ollama models and LangChain's OpenAI-compatible chat client. No paid model APIs or model-provider secrets are required. GitHub Actions runs each model on an independent runner, preserves generated code and round-by-round snapshots, and aggregates the results.

## Proven baseline (previous 5-problem suite)

The latest uploaded run completed all five original tasks and 30/30 tests in one repair round for each of these models. These are **historical baseline results**, not results on the expanded 21-problem suite below.

| Model | Original tasks solved | Tests passed | Repair rounds for solved tasks | Mean seconds/task | Default? |
|---|---:|---:|---:|---:|---|
| `qwen2.5-coder:1.5b` | 5/5 | 30/30 | 1 | 4.2 | Yes |
| `qwen2.5-coder:3b` | 5/5 | 30/30 | 1 | 10.7 | Yes |
| `deepseek-coder:1.3b` | 5/5 | 30/30 | 1 | 9.3 | Yes |
| `yi-coder:1.5b` | 5/5 | 30/30 | 1 | 9.5 | Yes |
| `opencoder:1.5b` | 5/5 | 30/30 | 1 | 18.9 | Yes |

Models that timed out on the previous suite, and DeepCoder (which failed its smoke test before evaluation), are experimental/opt-in rather than default. A new baseline must be established after the larger problem corpus runs in CI. See [`reports/2026-10-24-run-analysis.md`](reports/2026-10-24-run-analysis.md) for the log diagnosis and validation notes.

## What it measures

- 21 Python problems and 134 independent test cases spanning correctness and normalization, hashing, dynamic programming, grid DP, knapsack, string segmentation, sliding windows, graph traversal, cycle detection, bipartite checks, Dijkstra shortest paths, network delay, and word-ladder BFS.
- Independent executable test cases, including boundary cases. A zero process exit is **not** considered a pass; every test must pass.
- Up to three generate/test/repair rounds, syntax pre-checks, per-call timing, test results, code snapshots, and JSON audit logs.
- Default matrix runs only the five models that passed the previous 5-problem baseline. A manual `run_extended_coders=true` run adds slower/experimental Qwen3 0.6B/1.7B, Qwen2.5-Coder 0.5B/7B, DeepCoder 1.5B, DeepSeek-Coder 6.7B, Granite Code 3B, and StarCoder2 3B. Qwen3 4B remains separately opt-in.

## Run locally

Install Ollama and Python 3.11+, start `ollama serve`, and pull a model:

```bash
ollama pull qwen2.5-coder:1.5b
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
QWEN_MODEL=qwen2.5-coder:1.5b python agent/self_repair_agent.py
```

Artifacts are written under `artifacts/solutions/` and `artifacts/selfrepair_log.json`.

## CI

Push to `main` or manually run **Open-Source SLM Self-Repair Benchmark** from Actions. The workflow installs Ollama, pulls each model on its own runner, runs a smoke test and the benchmark, then uploads per-model and aggregate reports. Leave `run_extended_coders` disabled for the stable baseline; enable it to investigate slower or experimental models. For a manual run, `publish_solutions=true` opens a review-only PR containing generated source snapshots and evaluation logs. It never merges generated code automatically. Hosted Ubuntu runners are CPU-only unless a different runner is configured.

## Problem corpus and references

The repository's JSON task statements and expected outputs are authored for this project; the benchmark does not bundle copied proprietary problem statements or hidden test sets. They use standard algorithm families and are mapped to public reference problems for terminology and comparison:

- Dynamic programming: [Coin Change](https://leetcode.com/problems/coin-change/), [Longest Increasing Subsequence](https://leetcode.com/problems/longest-increasing-subsequence/), [Edit Distance](https://leetcode.com/problems/edit-distance/), [Word Break](https://leetcode.com/problems/word-break/), [0/1 Knapsack](https://en.wikipedia.org/wiki/Knapsack_problem).
- Graphs and shortest paths: [Number of Islands](https://leetcode.com/problems/number-of-islands/), [Course Schedule](https://leetcode.com/problems/course-schedule/), [Network Delay Time](https://leetcode.com/problems/network-delay-time/), [Is Graph Bipartite?](https://leetcode.com/problems/is-graph-bipartite/), [Word Ladder](https://leetcode.com/problems/word-ladder/).
- Other algorithm families: [Minimum Window Substring](https://leetcode.com/problems/minimum-window-substring/), [Merge Intervals](https://leetcode.com/problems/merge-intervals/), [Best Time to Buy and Sell Stock IV](https://leetcode.com/problems/best-time-to-buy-and-sell-stock-iv/).

Additional open-weight coding-model families worth testing include [StarCoder2](https://ollama.com/library/starcoder2), [CodeGemma](https://ollama.com/library/codegemma), and [Granite Code](https://ollama.com/library/granite-code). The experimental workflow currently includes StarCoder2 3B and Granite Code 3B; CodeGemma is listed as a future candidate because its small variants differ in instruction-following behavior.

The references are algorithmic pointers, not claims that these repository tasks reproduce the official platforms' exact tests or constraints. Use the same fixed problem set and multiple seeds when comparing models; keep an eye on runtime and test coverage as the suite grows.

## Reliability and safety notes

The runner uses subprocess timeouts and strips most environment variables, but this is **not a hardened sandbox**. Generated code can still access the runner's filesystem and network under the runner account. Do not expose secrets to this job or execute untrusted generated code on a privileged/self-hosted runner. Keep GitHub Actions permissions minimal.

The benchmark improves evaluation quality, not the underlying model weights. Deterministic tests, a repair loop, explicit edge cases, and optional model-size comparisons can improve observed task performance; they do not guarantee correctness or prove general reasoning ability. Use multiple seeds/repetitions before drawing research conclusions.


## Reliability fixes for CI

- Artifact names use model slugs (`qwen3-0.6b`, `qwen3-1.7b`, `qwen3-4b`); Ollama tags contain `:` which GitHub artifact names reject.
- Aggregation validates report files and exits non-zero when no valid records are present, while still writing diagnostic aggregate files.
- Default model calls use bounded per-model timeouts, no automatic retry, and a 1536-token output cap. Qwen3 4B is explicitly opt-in and uses a 300-second timeout. Tune these only after reviewing measured runtime and resource diagnostics.
- The model benchmark is CPU-based on standard GitHub-hosted Ubuntu runners; these runners do not provide a general-purpose GPU. Treat model timing as CPU-runner timing, not GPU performance.
- Each round is saved under `artifacts/solutions/` as `<problem>.round-NN.py`; the latest code is `<problem>.py`. `manifest.json` records per-problem convergence and rounds. All these files are uploaded as model artifacts.
- A manual `publish_solutions=true` run can open a PR under `benchmark-snapshots/run-<run_id>/` for code review. Snapshot PRs are not application patches and do not close issues.
- Model-call/setup failures are separated from wrong answers. A non-converged model/problem creates or updates one deduplicated issue after the repair budget is exhausted—not one issue per failed test. Labels include model, problem ID, task difficulty, repair level, and failure category.

## Optional repository coding agent (PR-only)

The separate **Qwen Repository Coding Agent (PR-only)** workflow can be run manually from GitHub Actions. Supply a specific task and select a model from the coding-model list, including Qwen3, Qwen2.5-Coder, DeepCoder, OpenCoder, Yi-Coder, DeepSeek-Coder, Granite Code, and StarCoder2. Qwen3 4B is available only when deliberately selected. The default is `qwen2.5-coder:1.5b`, the fastest model that passed the previous baseline. It reads a bounded set of tracked repository files, asks the local Ollama model for a unified diff, validates the patch paths, applies it in a job without write credentials, and runs the existing unit tests and syntax checks. If checks pass, a separate job opens a pull request. It never pushes directly to the default branch, and the model-generation job never receives a write token.

### Token configuration

By default, the PR job uses GitHub's short-lived `GITHUB_TOKEN` (`github.token`) with job-level `contents: write` and `pull-requests: write`. This is preferred and is enough to push a branch and open a PR in this repository. Depending on repository settings, a PR created with `GITHUB_TOKEN` may not automatically trigger other workflows; a maintainer can approve the resulting run if GitHub requests it.

An optional repository Actions secret named `GH_CLASSIC_TOKEN` is supported as a fallback for cases where you explicitly need a personal access token's event-triggering behavior. **Do not add a classic PAT unless you have a specific need.** Classic PATs can have broad access to all repositories available to the account. Prefer the built-in token, or a GitHub App / narrowly scoped fine-grained token where supported. Never put a token in workflow inputs, source files, prompts, artifacts, or logs. The token is only used in the final PR-creation job, after patch generation and tests; it is not passed to Ollama or generated-code execution.

### Guardrails and limitations

- The model cannot modify `.github/workflows/`, dependency manifests, or arbitrary paths; the patch is allowlisted to `agent/`, `problems/`, `tests/`, `scripts/`, and `README.md`.
- It proposes a diff rather than receiving shell access or a general-purpose file-writing tool.
- The workflow tests proposed changes before the PR job. A passing test suite is not proof of security or correctness; inspect the PR diff before merging.
- This is a starter agent, not a production-autonomous maintainer. The model sees a bounded source snapshot, may misunderstand tasks, and can return invalid patches. It does not merge PRs automatically.
- Keep the coding-agent workflow restricted to trusted maintainers because the workflow can create repository branches and PRs.


## Bug-level capability reporting

Each problem spec labels tests with a bug category and declares a broad difficulty rubric. The run log records per-round failure classes (syntax error, runtime exception, wrong output, timeout/model error), test-category outcomes, convergence, rounds and elapsed time. The aggregate report summarizes observed success by difficulty and bug category. These are empirical results on the included fixed tests, not a universal claim about model capability. Expand the test corpus and repeat seeds before drawing strong conclusions.

Suggested interpretation: Easy = basic correctness; Easy-medium = normalization and edge cases; Medium = algorithm pattern/indexing/duplicates; Medium-hard = state invariants and negative cases; Hard = multi-step invariants and boundary handling. The expanded corpus includes multiple tasks across medium, medium-hard, and hard levels; each run should still be repeated with multiple seeds before drawing general conclusions.


## Automated GitHub Issues and closure

- The repository coding-agent workflow creates or comments on a deduplicated GitHub Issue when its generation/test job fails. It includes the run URL, selected model, task, and investigation checklist.
- The self-repair benchmark workflow creates or comments on a deduplicated issue when a model benchmark job or aggregation job fails. A model merely failing a test is an evaluation result; workflow/job failures are reported separately.
- Both reporter jobs use the workflow-scoped `GITHUB_TOKEN` with `issues: write`; model-generation jobs do not receive issue-write permissions.
- To ask the coding agent to fix an existing issue, manually run **Qwen Repository Coding Agent (PR-only)** and enter that issue number in the optional `issue_number` input.
- The resulting PR body includes `Fixes #N`. GitHub closes the issue automatically when that fix PR is merged, rather than prematurely closing an issue when an unmerged patch merely passes tests.
- The agent never directly closes issues based solely on its own claim. Human review and merge remain the closure gate. If you require automatic merging, configure GitHub branch protection and a separate trusted policy; do not give model-generated code unrestricted repository-write access.

The issue reporters deduplicate by workflow-specific title and append a comment to an existing open issue. Ensure Actions are allowed to create issues using the repository's `GITHUB_TOKEN` (Settings → Actions → General → Workflow permissions). No personal access token is needed for these issue operations.


## Resource efficiency and slow-model handling

- The default matrix includes only the five models that completed the previous five-task baseline. Slow or unverified models are opt-in; Qwen3 4B remains separately opt-in.
- Model-file caching is disabled because it can consume GitHub cache quota without reducing inference memory. Each runner pulls one model, executes sequentially, uploads outputs, then unloads it.
- Ollama uses one parallel request and one loaded model. Model calls have bounded timeouts and a 1536-token output budget for the expanded tasks.
- Python bytecode generation is disabled in test subprocesses, and caches are removed before artifact upload.
- Invocation exceptions are written to the JSON audit log and can create a deduplicated, labeled GitHub Issue. They are distinct from a model producing incorrect code. Generated-code test subprocesses receive a minimal environment without the issue-reporting token.
- The uploaded run showed read timeouts for the slow models. This is evidence of inference latency or endpoint responsiveness, not proof of a memory leak.

## Issue triage and labels

The benchmark checks for an existing open issue with the same model/problem identifier before creating another. Generated labels include `model-*`, `problem-*`, `difficulty-*`, `repair-level-easy|medium|hard`, and `failure-agentic|dependency|timeout`. The global workflow reporter uses `failure-workflow`, `failure-dependency`, or `failure-agentic` based on the failed step. A model's wrong answer is benchmark evidence, not automatically a repository bug. Reporters check for an existing open model/problem issue before creating another. Issues are not auto-closed merely because a later run passes; close them through a reviewed repair PR (`Fixes #N`) or an explicit maintainer decision after verification.
