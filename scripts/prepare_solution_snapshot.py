#!/usr/bin/env python3
"""Collect generated solution files and evaluation evidence into a review-only snapshot."""
from __future__ import annotations
import json
import os
import re
import shutil
import sys
from pathlib import Path

def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()

def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: prepare_solution_snapshot.py DOWNLOADED_RESULTS OUTPUT_ROOT", file=sys.stderr)
        return 2
    downloaded = Path(sys.argv[1])
    output_root = Path(sys.argv[2])
    run_id = os.environ.get("SNAPSHOT_RUN_ID", "local")
    run_dir = output_root / f"run-{run_id}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for artifact_dir in sorted(p for p in downloaded.iterdir() if p.is_dir()):
        name = artifact_dir.name
        if name == "selfrepair-aggregate-report":
            target = run_dir / "_aggregate"
            target.mkdir(parents=True, exist_ok=True)
            for filename in ("aggregate-report.md", "aggregate.json"):
                src = artifact_dir / filename
                if src.is_file():
                    shutil.copy2(src, target / filename)
                    copied += 1
            continue
        if not name.startswith("selfrepair-"):
            continue
        model_slug = name.removeprefix("selfrepair-")
        # Matrix artifacts are named selfrepair-<job-index>-<model-slug>.
        match = re.match(r"^\d+-(.+)$", model_slug)
        if match:
            model_slug = match.group(1)
        target = run_dir / slug(model_slug)
        solutions_dir = artifact_dir / "solutions"
        if solutions_dir.is_dir():
            shutil.copytree(solutions_dir, target / "solutions", dirs_exist_ok=True)
            copied += sum(1 for p in (target / "solutions").rglob("*") if p.is_file())
        for filename in ("selfrepair_log.json",):
            src = artifact_dir / filename
            if src.is_file():
                shutil.copy2(src, target / filename)
                copied += 1
        diagnostics = artifact_dir / "diagnostics"
        if diagnostics.is_dir():
            for filename in ("model-info.txt", "model-details.json", "runner-resources.txt"):
                src = diagnostics / filename
                if src.is_file():
                    diag_target = target / "diagnostics"
                    diag_target.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, diag_target / filename)
                    copied += 1
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
        meta = {
            "artifact": name,
            "model_slug": slug(model_slug),
            "has_evaluation_log": (target / "selfrepair_log.json").is_file(),
            "has_generated_solutions": (target / "solutions").is_dir(),
            "note": "Model-generated files are untrusted outputs. Review before reuse.",
        }
        (target / "snapshot-metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        copied += 1
    if copied == 0:
        print("No model artifacts or generated solution files were found.", file=sys.stderr)
        return 1
    readme = run_dir / "README.md"
    readme.write_text(
        "# Generated coding-model snapshots\n\n"
        f"GitHub Actions run: {run_id}\n\n"
        "Each model folder contains source snapshots for each generated round, a final solution "
        "when available, and the evaluation log. Diagnostics are included when available. "
        "An absent `selfrepair_log.json` means evaluation did not complete. These files are "
        "untrusted model outputs and must be reviewed before reuse; this PR does not merge them "
        "into application code or close benchmark issues.\n",
        encoding="utf-8",
    )
    print(f"Prepared {copied} review artifacts under {run_dir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
