"""评测脚本的自检：保证「修复环确实把坏输出救回来」，指标不是写死的。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from resume_agent.evaluate import load_dataset, run_eval

DATASET = Path(__file__).resolve().parents[1] / "eval" / "dataset.jsonl"


def _ensure_dataset() -> Path:
    if not DATASET.exists():
        script = Path(__file__).resolve().parents[1] / "eval" / "make_dataset.py"
        subprocess.run([sys.executable, str(script)], check=True)
    return DATASET


def test_dataset_has_min_10_samples() -> None:
    data = load_dataset(_ensure_dataset())
    assert len(data) >= 10
    first = data[0]
    assert first["text"] and first["gold"]["profile"]["name"]


def test_repair_recovers_all_structures() -> None:
    data = load_dataset(_ensure_dataset())
    report = run_eval(data, provider="mock", corrupt_rate=0.4, max_repairs=1, seed=7)

    assert report.samples == len(data)
    assert report.structural_success == 1.0, [d for d in report.details if not d["valid"]]
    assert report.repair_rate > 0, "注入 40% 脏输出后应当有样本触发修复"


def test_without_repair_some_samples_fail() -> None:
    data = load_dataset(_ensure_dataset())
    report = run_eval(data, provider="mock", corrupt_rate=0.4, max_repairs=0, seed=7)

    assert report.structural_success < 1.0


def test_hallucination_filter_reduces_fake_fields() -> None:
    data = load_dataset(_ensure_dataset())
    with_filter = run_eval(data, provider="mock", corrupt_rate=1.0, max_repairs=1, seed=3)
    without = run_eval(data, provider="mock", corrupt_rate=1.0, max_repairs=1, seed=3, verify_evidence=False)

    assert with_filter.dropped_fields >= 1
    assert without.dropped_fields == 0


def test_report_markdown_renders() -> None:
    data = load_dataset(_ensure_dataset())
    md = run_eval(data, provider="mock", corrupt_rate=0.35).to_markdown()
    assert "结构合法率" in md
    assert "| --- | --- |" in md