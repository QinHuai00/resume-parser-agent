"""证据溯源：模型编造、或者改写原文的字段必须被清掉。"""
from __future__ import annotations

import json

from resume_agent.llm import ScriptedLLM
from resume_agent.pipeline import ResumePipeline


def _run(payload: dict, text: str) -> tuple[dict, list[str]]:
    llm = ScriptedLLM([json.dumps(payload, ensure_ascii=False)])
    outcome = ResumePipeline(llm, max_repairs=0).parse_text(text)
    assert outcome.valid is True
    return outcome.profile or {}, outcome.dropped_fields


def test_hallucinated_phone_is_dropped(sample_text: str, good_result: dict) -> None:
    payload = json.loads(json.dumps(good_result))
    payload["profile"]["phone"] = "13900000000"
    payload["evidence"]["phone"] = "13900000000"

    profile, dropped = _run(payload, sample_text)

    assert profile["phone"] is None
    assert "phone" in dropped


def test_rewritten_evidence_is_dropped(sample_text: str, good_result: dict) -> None:
    payload = json.loads(json.dumps(good_result))
    payload["evidence"]["education.0.school"] = "华南理工大学（985）"  # 原文没有括号内容

    profile, dropped = _run(payload, sample_text)

    assert profile["education"][0]["school"] is None
    assert "education.0.school" in dropped


def test_field_without_evidence_is_dropped(sample_text: str, good_result: dict) -> None:
    payload = json.loads(json.dumps(good_result))
    payload["profile"]["experiences"][0]["company"] = "不存在的公司"
    del payload["evidence"]["experiences.0.company"]

    profile, dropped = _run(payload, sample_text)

    assert profile["experiences"][0]["company"] is None
    assert "experiences.0.company" in dropped


def test_whitespace_and_punctuation_tolerated(sample_text: str, good_result: dict) -> None:
    payload = json.loads(json.dumps(good_result))
    payload["evidence"]["name"] = "姓名:  张伟"

    profile, dropped = _run(payload, sample_text)

    assert profile["name"] == "张伟"
    assert "name" not in dropped


def test_verify_evidence_can_be_disabled(sample_text: str, good_result: dict) -> None:
    payload = json.loads(json.dumps(good_result))
    payload["profile"]["phone"] = "13900000000"
    payload["evidence"]["phone"] = "13900000000"
    llm = ScriptedLLM([json.dumps(payload, ensure_ascii=False)])

    outcome = ResumePipeline(llm, max_repairs=0, verify_evidence=False).parse_text(sample_text)

    assert outcome.profile is not None
    assert outcome.profile["phone"] == "13900000000"
    assert outcome.dropped_fields == []