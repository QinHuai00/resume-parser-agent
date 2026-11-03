"""评测脚本：用可复现的「模拟脏模型」量化校验-修复环的收益。

为什么要有这个文件：
- 面试官问「准确率多少」时，不能只说「大概挺准」；
- 修复环的价值必须能被证伪：如果它没用，指标会直接掉下来。

两种模式：
1. `--provider mock`（默认，离线、可复现）：MockLLM 按 corrupt_rate 注入真实故障
   （JSON 截断、字段类型错、多吐字段、幻觉手机号），第一次请求脏、修复请求干净。
   → 能测出「结构合法率」「修复轮次」「幻觉字段被丢弃数」；
2. `--provider openai`：接真实模型，任何数字都要自己跑，不做任何预设。
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm import MockLLM, OpenAICompatClient
from .pipeline import ParseOutcome, ResumePipeline

SCALAR_FIELDS = ("name", "phone", "email", "city", "years_of_experience")


@dataclass
class EvalReport:
    provider: str
    samples: int
    structural_success: float = 0.0
    repair_rate: float = 0.0
    avg_repairs: float = 0.0
    dropped_fields: int = 0
    field_accuracy: dict[str, float] = field(default_factory=dict)
    skills_f1: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_markdown(self) -> str:
        rows = [
            "| 指标 | 数值 |",
            "| --- | --- |",
            f"| 样本数 | {self.samples} |",
            f"| 结构合法率 | {self.structural_success:.1%} |",
            f"| 触发修复的比例 | {self.repair_rate:.1%} |",
            f"| 平均修复轮次 | {self.avg_repairs:.2f} |",
            f"| 幻觉字段被丢弃 | {self.dropped_fields} 个 |",
            f"| 技能集合 F1 | {self.skills_f1:.3f} |",
        ]
        for name, acc in self.field_accuracy.items():
            rows.append(f"| 字段准确率 · {name} | {acc:.1%} |")
        return "\n".join(rows)


def load_dataset(path: str | Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return "".join(value.split()).lower()
    return value


def _field_equal(a: Any, b: Any) -> bool:
    return _normalize(a) == _normalize(b)


def _skills_f1(pred: list[str], gold: list[str]) -> float:
    p = {_normalize(x) for x in pred if x}
    g = {_normalize(x) for x in gold if x}
    if not p and not g:
        return 1.0
    if not p or not g:
        return 0.0
    tp = len(p & g)
    precision = tp / len(p)
    recall = tp / len(g)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _top_education(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    edus = profile.get("education") or []
    return edus[0] if edus else {}


def run_eval(
    dataset: list[dict[str, Any]],
    *,
    provider: str = "mock",
    corrupt_rate: float = 0.35,
    max_repairs: int = 1,
    verify_evidence: bool = True,
    seed: int = 7,
) -> EvalReport:
    gold_by_text = {item["text"]: item["gold"] for item in dataset}
    client: Any
    if provider == "mock":
        client = MockLLM(gold_by_text=gold_by_text, corrupt_rate=corrupt_rate, seed=seed)
    elif provider == "openai":
        client = OpenAICompatClient()
    else:
        raise ValueError(f"未知 provider：{provider}")

    pipeline = ResumePipeline(client, max_repairs=max_repairs, verify_evidence=verify_evidence)

    report = EvalReport(provider=provider, samples=len(dataset))
    hits: dict[str, int] = {name: 0 for name in SCALAR_FIELDS}
    f1s: list[float] = []
    repaired = 0
    repairs_total = 0
    dropped_total = 0
    ok = 0

    for item in dataset:
        outcome: ParseOutcome = pipeline.parse_text(item["text"], source=item["id"])
        gold = item["gold"]
        gold_profile = gold["profile"]
        if outcome.valid:
            ok += 1
        repaired += 1 if outcome.repairs else 0
        repairs_total += outcome.repairs
        dropped_total += len(outcome.dropped_fields)

        pred = outcome.profile or {}
        for name in SCALAR_FIELDS:
            if _field_equal(pred.get(name), gold_profile.get(name)):
                hits[name] += 1
        if _field_equal(_top_education(pred).get("school"), _top_education(gold_profile).get("school")):
            hits.setdefault("education.school", 0)
            hits["education.school"] += 1
        f1s.append(_skills_f1(pred.get("skills") or [], gold_profile.get("skills") or []))

        report.details.append(
            {
                "id": item["id"],
                "valid": outcome.valid,
                "repairs": outcome.repairs,
                "dropped": outcome.dropped_fields,
                "error": outcome.error,
            }
        )

    n = max(len(dataset), 1)
    report.structural_success = ok / n
    report.repair_rate = repaired / n
    report.avg_repairs = repairs_total / n
    report.dropped_fields = dropped_total
    report.field_accuracy = {k: v / n for k, v in hits.items()}
    report.skills_f1 = statistics.fmean(f1s) if f1s else 0.0
    return report