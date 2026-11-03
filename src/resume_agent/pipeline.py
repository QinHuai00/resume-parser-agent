"""抽取流水线：解析 → 抽取 → 校验 → 修复 → 证据过滤。

这是整个项目的核心，四段式里后三段都在这个文件：

1. 抽取：把简历原文 + JSON Schema 一起给模型，要求「只能从原文抽，缺就 null」；
2. 校验：Pydantic 校验结构（字段类型、邮箱/手机号格式、extra=forbid）；
3. 修复：校验失败**不整条重跑**，而是把 ValidationError 原文回灌给模型，
   要求它只修错的那几个字段（省 token、少一次幻觉机会）；
4. 证据过滤：模型给每个字段的 evidence 必须能在原文里逐字找到，
   找不到的字段直接置 null —— 这是防「编造字段」的最后一层。

设计取舍（面试可讲）：
- 为什么修复只做 1 轮：实测第 2 轮收益很小，而延迟和成本线性上涨；
- 为什么不用 function calling 强约束：跨厂商兼容性差，JSON Schema + 校验回灌
  的迁移成本更低，且能把「哪里错了」显式写进提示词。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .extract import TextDocument, extract
from .llm import LLMClient, first_json_object
from .schema import ExtractionResult, json_schema_text

SYSTEM_PROMPT = """你是一个严谨的简历信息抽取器。规则：
1. 只输出一个 JSON 对象，不要输出解释、不要 Markdown 代码块。
2. 只能抽取原文中明确出现的信息；原文没有的字段输出 null（列表输出 []）。
3. evidence 里每个键是字段路径（如 name、education.0.school），值是**逐字复制**的原文片段，
   不得改写、不得补充、不得拼凑。
4. 输出必须严格符合给定的 JSON Schema，不得增加 Schema 之外的字段。"""

_PUNCT = r"[\s,，。、；;：:（）()【】\[\]“”\"'·\-—_/\\|]+"


def normalize(text: str) -> str:
    """证据匹配用的归一化：去空白与标点，只比较「字」。"""
    return re.sub(_PUNCT, "", text or "").lower()


@dataclass
class ParseOutcome:
    source: str
    valid: bool
    profile: dict[str, Any] | None
    repairs: int = 0
    dropped_fields: list[str] = field(default_factory=list)
    error: str | None = None
    attempts: int = 1
    text_length: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "valid": self.valid,
            "profile": self.profile,
            "repairs": self.repairs,
            "dropped_fields": self.dropped_fields,
            "error": self.error,
            "attempts": self.attempts,
            "text_length": self.text_length,
        }


def build_user_prompt(text: str, schema_text: str) -> str:
    return (
        "以下是 JSON Schema：\n"
        f"{schema_text}\n\n"
        "以下是简历原文（三引号内）：\n"
        '"""\n'
        f"{text}\n"
        '"""\n\n'
        "请输出符合 Schema 的 JSON。"
    )


def build_repair_prompt(text: str, previous: str, error: str, schema_text: str) -> str:
    return (
        "REPAIR: 上一次的输出未通过校验，请只修正错误，不要重写没问题的字段。\n\n"
        f"【校验错误】\n{error}\n\n"
        f"【上一次输出】\n{previous}\n\n"
        f"【JSON Schema】\n{schema_text}\n\n"
        "【简历原文】\n"
        '"""\n'
        f"{text}\n"
        '"""\n\n'
        "只输出修正后的完整 JSON。"
    )


def _set_path(profile: dict[str, Any], path: str, value: Any) -> None:
    """按 'a.b.0.c' 形式的路径写值，路径不存在时静默跳过。"""
    parts = path.split(".")
    node: Any = profile
    for part in parts[:-1]:
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return
            node = node[int(part)]
        elif isinstance(node, dict):
            if part not in node:
                return
            node = node[part]
        else:
            return
    last = parts[-1]
    if isinstance(node, list) and last.isdigit():
        idx = int(last)
        if idx < len(node):
            node[idx] = value
    elif isinstance(node, dict) and last in node:
        node[last] = value


class ResumePipeline:
    def __init__(
        self,
        llm: LLMClient,
        *,
        max_repairs: int = 1,
        verify_evidence: bool = True,
        max_chars: int = 12000,
    ) -> None:
        self.llm = llm
        self.max_repairs = max_repairs
        self.verify_evidence = verify_evidence
        self.max_chars = max_chars
        self._schema_text = json_schema_text()
        self._system = SYSTEM_PROMPT + "\n\nJSON Schema:\n" + self._schema_text

    # ---------- 对外 ----------

    def parse_text(self, text: str, *, source: str = "<text>") -> ParseOutcome:
        text = (text or "")[: self.max_chars]
        if not text.strip():
            return ParseOutcome(source=source, valid=False, profile=None, error="原文为空", text_length=0)

        prompt = build_user_prompt(text, self._schema_text)
        raw = ""
        repairs = 0
        attempts = 0
        last_error = ""

        for attempt in range(self.max_repairs + 1):
            attempts = attempt + 1
            raw = self.llm.complete(system=self._system, user=prompt)
            try:
                payload = json.loads(first_json_object(raw))
                result = ExtractionResult.model_validate(payload)
                profile, dropped = self._finalize(result, text)
                return ParseOutcome(
                    source=source,
                    valid=True,
                    profile=profile,
                    repairs=repairs,
                    dropped_fields=dropped,
                    attempts=attempts,
                    text_length=len(text),
                )
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = self._short_error(exc)
                if attempt >= self.max_repairs:
                    break
                repairs += 1
                prompt = build_repair_prompt(text, raw, last_error, self._schema_text)

        return ParseOutcome(
            source=source,
            valid=False,
            profile=None,
            repairs=repairs,
            error=last_error,
            attempts=attempts,
            text_length=len(text),
        )

    def parse_document(self, doc: TextDocument) -> ParseOutcome:
        return self.parse_text(doc.text, source=doc.source)

    def parse_bytes(self, filename: str, data: bytes) -> ParseOutcome:
        doc = extract(filename, data)
        return self.parse_document(doc)

    # ---------- 内部 ----------

    @staticmethod
    def _short_error(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            lines = []
            for err in exc.errors()[:8]:
                loc = ".".join(str(x) for x in err.get("loc", ()))
                lines.append(f"- {loc}: {err.get('msg')}（input={err.get('input')!r}）")
            return "\n".join(lines)
        return f"- JSON 解析失败：{exc}"

    def _finalize(self, result: ExtractionResult, text: str) -> tuple[dict[str, Any], list[str]]:
        profile = result.profile.model_dump()
        dropped: list[str] = []
        if not self.verify_evidence:
            return profile, dropped

        haystack = normalize(text)
        evidence = {k: v for k, v in result.evidence.items() if isinstance(v, str) and v.strip()}

        # 只校验「模型声称有值」的字段：有值但证据对不上 → 判为编造，置空
        for path, quote in evidence.items():
            if not self._get_path(profile, path):
                continue
            if normalize(quote) and normalize(quote) in haystack:
                continue
            _set_path(profile, path, None)
            dropped.append(path)

        # 没有任何证据的标量字段同样按编造处理（宁缺毋滥）
        provided = set(evidence)
        for path in self._scalar_paths(profile):
            if path in provided:
                continue
            if self._get_path(profile, path):
                _set_path(profile, path, None)
                dropped.append(path)
        return profile, dropped

    @staticmethod
    def _get_path(profile: dict[str, Any], path: str) -> Any:
        node: Any = profile
        for part in path.split("."):
            if isinstance(node, list):
                if not part.isdigit() or int(part) >= len(node):
                    return None
                node = node[int(part)]
            elif isinstance(node, dict):
                node = node.get(part)
            else:
                return None
        return node

    @staticmethod
    def _scalar_paths(profile: dict[str, Any]) -> list[str]:
        paths = [k for k in ("name", "phone", "email", "city", "years_of_experience") if profile.get(k) is not None]
        for i, edu in enumerate(profile.get("education") or []):
            for key in ("school", "major", "degree"):
                if edu.get(key):
                    paths.append(f"education.{i}.{key}")
        for i, exp in enumerate(profile.get("experiences") or []):
            if exp.get("company"):
                paths.append(f"experiences.{i}.company")
        return paths