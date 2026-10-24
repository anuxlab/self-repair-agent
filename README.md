# Open-source SLM Self-Repair Agent

A test-driven code-generation and repair benchmark using local Ollama models and LangChain's OpenAI-compatible chat client. No paid model APIs or API secrets are required. GitHub Actions runs one model variant per independent matrix runner, then aggregates the artifacts.

## What it measures

- Five Python problems: addition, normalized palindrome, two-sum, maximum subarray, and trapping rain water.
- Independent executable test cases, including boundary cases. A zero process exit is **not** considered a pass; every test must pass.
- Up to three generate/test/repair rounds, syntax pre-checks, per-call timing, test results, code snapshots, and JSON audit logs.
- Default matrix compares `qwen3:0.6b`, `qwen3:1.7b`, and the coding-specialist `qwen2.5-coder:1.5b`; each model runs on its own hosted runner. Qwen3 4B is paused and only included when explicitly enabled in a manual workflow run.

## Run locally

Install Ollama and Python 3.11+, start `ollama serve`, and pull a model:

```bash
ollama pull qwen3:1.7b
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
QWEN_MODEL=qwen3:4b python agent/self_repair_agent.py
```

Artifacts are written under `artifacts/solutions/` and `artifacts/selfrepair_log.json`.

## CI

Push to `main` or manually run **Open-Source SLM Self-Repair Benchmark** from Actions. The workflow installs Ollama, pulls each model on its own runner, runs a smoke test and the benchmark, then uploads per-model and aggregate reports. The hosted Ubuntu runner is CPU-only unless a different runner is configured; the 4B model can therefore take several minutes per problem. Increase the job timeout or reduce the model matrix if needed.

## Reliability and safety notes

The runner uses subprocess timeouts and strips most environment variables, but this is **not a hardened sandbox**. Generated code can still access the runner's filesystem and network under the runner account. Do not expose secrets to this job or execute untrusted generated code on a privileged/self-hosted runner. Keep GitHub Actions permissions minimal.

The benchmark improves evaluation quality, not the underlying model weights. Deterministic tests, a repair loop, explicit edge cases, and optional model-size comparisons can improve observed task performance; they do not guarantee correctness or prove general reasoning ability. Use multiple seeds/repetitions before drawing research conclusions.


## Reliability fixes for CI

- Artifact names use model slugs (`qwen3-0.6b`, `qwen3-1.7b`, `qwen3-4b`); Ollama tags contain `:` which GitHub artifact names reject.
- Aggregation validates report files and exits non-zero when no valid records are present, while still writing diagnostic aggregate files.
- Default model calls use a bounded 150-second timeout, no automatic retry, and a 1024-token output cap. Qwen3 4B is explicitly opt-in and uses a 240-second timeout. Tune these only after reviewing measured runtime and resource diagnostics.
- The model benchmark is CPU-based on standard GitHub-hosted Ubuntu runners; these runners do not provide a general-purpose GPU. Treat model timing as CPU-runner timing, not GPU performance.

## Optional repository coding agent (PR-only)

The separate **Qwen Repository Coding Agent (PR-only)** workflow can be run manually from GitHub Actions. Supply a specific task and select `qwen3:0.6b`, `qwen3:1.7b`, `qwen2.5-coder:1.5b`, or (only when needed) `qwen3:4b`. The default is `qwen3:1.7b`. It reads a bounded set of tracked repository files, asks the local Ollama model for a unified diff, validates the patch paths, applies it in a job without write credentials, and runs the existing unit tests and syntax checks. If checks pass, a separate job opens a pull request. It never pushes directly to the default branch, and the model-generation job never receives a write token.

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

Suggested interpretation: Easy = basic correctness; Easy-medium = normalization and edge cases; Medium = algorithm pattern/indexing/duplicates; Medium-hard = state invariants and negative cases; Hard = multi-step invariants and boundary handling. The benchmark currently has only one task per difficulty band, so difficulty-level conclusions are preliminary.


## Automated GitHub Issues and closure

- The repository coding-agent workflow creates or comments on a deduplicated GitHub Issue when its generation/test job fails. It includes the run URL, selected model, task, and investigation checklist.
- The self-repair benchmark workflow creates or comments on a deduplicated issue when a model benchmark job or aggregation job fails. A model merely failing a test is an evaluation result; workflow/job failures are reported separately.
- Both reporter jobs use the workflow-scoped `GITHUB_TOKEN` with `issues: write`; model-generation jobs do not receive issue-write permissions.
- To ask the coding agent to fix an existing issue, manually run **Qwen Repository Coding Agent (PR-only)** and enter that issue number in the optional `issue_number` input.
- The resulting PR body includes `Fixes #N`. GitHub closes the issue automatically when that fix PR is merged, rather than prematurely closing an issue when an unmerged patch merely passes tests.
- The agent never directly closes issues based solely on its own claim. Human review and merge remain the closure gate. If you require automatic merging, configure GitHub branch protection and a separate trusted policy; do not give model-generated code unrestricted repository-write access.

The issue reporters deduplicate by workflow-specific title and append a comment to an existing open issue. Ensure Actions are allowed to create issues using the repository's `GITHUB_TOKEN` (Settings → Actions → General → Workflow permissions). No personal access token is needed for these issue operations.


## Resource efficiency and slow-model handling

- Qwen3 4B is paused by default because CPU-hosted runners repeatedly hit the 240-second model-call read timeout. It can only be enabled deliberately through `workflow_dispatch` (`run_qwen3_4b=true`).
- Default comparison includes Qwen3 0.6B, Qwen3 1.7B, and the coding-specialist `qwen2.5-coder:1.5b`. This keeps the experiment open-source and tests a coding-tuned model before spending runner time on 4B.
- Model-file caching through `actions/cache` is disabled. It saved download time but did not reduce inference RAM usage and could consume GitHub cache quota. Each job pulls its model, uploads results, then unloads the model and removes local Ollama model files.
- Ollama is configured for one parallel request, one loaded model, a short idle keep-alive, Flash Attention, and a 2048-token smoke-test context. The generation output budget is 1024 tokens by default to reduce CPU time.
- Python bytecode generation is disabled in test subprocesses, and `__pycache__`/`.pyc` files are removed after each problem and before artifacts are uploaded. The previous artifact bundles contained `solutions/__pycache__` files; these are disposable bytecode, not evidence of a Python memory leak.
- Model invocation exceptions are written to the JSON audit log, make the benchmark job fail, and trigger a best-effort deduplicated GitHub Issue immediately. The agent receives `GH_TOKEN` only for issue reporting; generated solution subprocesses receive a minimal environment without the token. Workflow-level failures are also summarized in a separate issue.
- The logs provided so far show `httpx`/OpenAI-compatible client `ReadTimeout` after roughly 240 seconds. That is evidence of inference latency or an unresponsive endpoint, not proof of a memory leak. The workflow now captures Ollama logs and runner memory/disk diagnostics to help distinguish slow generation, OOM/resource pressure, and endpoint failure.


## CI troubleshooting note (v7)

The 2026-10-24 Actions run failed before the benchmark started because the model metadata probe called the Ollama `/api/show` endpoint with malformed shell line continuations, resulting in HTTP 405. The metadata probe now uses Python's `urllib` with an explicit POST request. The benchmark failure reporter's issue body also avoids unquoted shell backticks, which previously triggered command substitution and removed diagnostic paths from the issue text.

If the aggregate report says no `selfrepair_log.json` files were found, check the first failed model setup/smoke-test step: model artifacts may contain diagnostics only because the evaluation process never started.
