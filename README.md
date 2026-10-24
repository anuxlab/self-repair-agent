# Open-source SLM Self-Repair Agent

A test-driven code-generation and repair benchmark using local Ollama models and LangChain's OpenAI-compatible chat client. No paid model APIs or API secrets are required. GitHub Actions runs one model variant per independent matrix runner, then aggregates the artifacts.

## What it measures

- Five Python problems: addition, normalized palindrome, two-sum, maximum subarray, and trapping rain water.
- Independent executable test cases, including boundary cases. A zero process exit is **not** considered a pass; every test must pass.
- Up to three generate/test/repair rounds, syntax pre-checks, per-call timing, test results, code snapshots, and JSON audit logs.
- Matrix comparison of `qwen3:0.6b`, `qwen3:1.7b`, and `qwen3:4b`; each model runs on its own hosted runner. The aggregation job creates JSON and Markdown summaries.

## Run locally

Install Ollama and Python 3.11+, start `ollama serve`, and pull a model:

```bash
ollama pull qwen3:4b
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
