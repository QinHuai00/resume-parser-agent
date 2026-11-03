"""校验-修复环的行为锁定。

这三条是这个项目最值得讲的部分：
- 坏 JSON → 一次修复就回来，且修复提示词里带上了错误原因；
- 结构非法（字段类型错 / 多吐字段）→ 同样能修回来；
- 修不回来时必须是「明确失败」，而不是静默返回半截脏数据。
"""
from __future__ import annotations

import json

from resume_agent.llm import ScriptedLLM
from resume_agent.pipeline import ResumePipeline


def test_bad_json_triggers_one_repair(sample_text: str, good_result: dict) -> None:
    broken = json.dumps(good_result, ensure_ascii=False)[:-15] + ",}"
    llm = ScriptedLLM([broken, json.dumps(good_result, ensure_ascii=False)])
    outcome = ResumePipeline(llm, max_repairs=1).parse_text(sample_text, source="cv.txt")

    assert outcome.valid is True
    assert outcome.repairs == 1
    assert len(llm.calls) == 2
    assert "REPAIR:" in llm.calls[1]
    assert "JSON 解析失败" in llm.calls[1]


def test_schema_violation_repair_prompt_carries_error(sample_text: str, good_result: dict) -> None:
    dirty = json.loads(json.dumps(good_result))
    dirty["profile"]["years_of_experience"] = "3 年"
    llm = ScriptedLLM([json.dumps(dirty, ensure_ascii=False), json.dumps(good_result, ensure_ascii=False)])
    outcome = ResumePipeline(llm, max_repairs=1).parse_text(sample_text)

    assert outcome.valid is True
    assert outcome.repairs == 1
    assert "years_of_experience" in llm.calls[1]


def test_repair_exhausted_reports_failure(sample_text: str) -> None:
    llm = ScriptedLLM(["not json at all", "still not json"])
    outcome = ResumePipeline(llm, max_repairs=1).parse_text(sample_text)

    assert outcome.valid is False
    assert outcome.profile is None
    assert outcome.error


def test_no_repair_mode_does_not_retry(sample_text: str) -> None:
    llm = ScriptedLLM(["{}"])
    outcome = ResumePipeline(llm, max_repairs=0).parse_text(sample_text)

    assert outcome.valid is False
    assert outcome.repairs == 0
    assert len(llm.calls) == 1


def test_code_fence_is_stripped(sample_text: str, good_result: dict) -> None:
    fenced = "```json\n" + json.dumps(good_result, ensure_ascii=False) + "\n```"
    llm = ScriptedLLM([fenced])
    outcome = ResumePipeline(llm, max_repairs=0).parse_text(sample_text)

    assert outcome.valid is True
    assert outcome.repairs == 0


def test_chatty_prefix_is_tolerated(sample_text: str, good_result: dict) -> None:
    chatty = "好的，抽取结果如下：\n" + json.dumps(good_result, ensure_ascii=False) + "\n希望有帮助。"
    llm = ScriptedLLM([chatty])
    outcome = ResumePipeline(llm, max_repairs=0).parse_text(sample_text)

    assert outcome.valid is True