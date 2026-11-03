"""模型接入层：一个 Protocol + 三个实现（真实 API / 脚本回放 / 模拟脏模型）。

为什么要抽这一层：
- 单测和评测不联网、不花钱，靠 ScriptedLLM / MockLLM 就能把「校验-修复」这条
  关键路径跑到；
- 换厂商只改 base_url（OpenAI 兼容协议），业务代码零改动。
"""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str) -> str: ...


@dataclass
class OpenAICompatClient:
    """走 OpenAI 兼容协议（/chat/completions），DashScope、DeepSeek、vLLM 都支持。

    环境变量：LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
    """

    base_url: str = field(default_factory=lambda: os.environ.get("LLM_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: os.environ.get("LLM_API_KEY", ""))
    model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", "qwen-plus"))
    temperature: float = 0.0
    timeout: float = 60.0

    def complete(self, *, system: str, user: str) -> str:
        import httpx

        if not self.base_url or not self.api_key:
            raise RuntimeError("缺少 LLM_BASE_URL / LLM_API_KEY，无法调用真实模型")
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]


@dataclass
class ScriptedLLM:
    """按顺序回放预设输出，用来锁定「坏输出 → 修复」的行为。"""

    responses: list[str]
    calls: list[str] = field(default_factory=list)

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append(user)
        if not self.responses:
            raise AssertionError("ScriptedLLM 输出已用尽，说明修复次数超出预期")
        return self.responses.pop(0)


@dataclass
class EchoLLM:
    """永远返回固定文本，用于最小冒烟。"""

    text: str = "{}"

    def complete(self, *, system: str, user: str) -> str:  # noqa: ARG002
        return self.text


def strip_code_fence(raw: str) -> str:
    """模型经常把 JSON 包在 ```json 里，这里统一剥掉。"""
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        return fence.group(1).strip()
    return text


def first_json_object(raw: str) -> str:
    """截取第一个 { 到最后一个 } —— 处理「先解释再给 JSON」的废话。"""
    text = strip_code_fence(raw)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


@dataclass
class MockLLM:
    """模拟一个「有一定概率出脏输出」的模型，用来量化修复环的收益。

    行为：
    - 第一次请求：按 corrupt_rate 注入 JSON 语法错误 / 结构非法 / 幻觉字段；
    - 修复请求（提示词里带 `REPAIR:` 标记）：返回干净结果。
    这样修复率、修复轮次分布都是真实可测的，而不是写死的常量。
    """

    gold_by_text: dict[str, dict[str, Any]]
    corrupt_rate: float = 0.35
    seed: int = 7
    stats: dict[str, int] = field(default_factory=lambda: {"first_calls": 0, "corrupted": 0, "repairs": 0})

    def complete(self, *, system: str, user: str) -> str:  # noqa: ARG002
        if "REPAIR:" in user:
            self.stats["repairs"] += 1
            return json.dumps(self._lookup(user), ensure_ascii=False)

        self.stats["first_calls"] += 1
        gold = self._lookup(user)
        rng = random.Random(self.seed + self.stats["first_calls"])
        if rng.random() >= self.corrupt_rate:
            return json.dumps(gold, ensure_ascii=False)

        self.stats["corrupted"] += 1
        kind = rng.choice(("bad_json", "bad_schema", "hallucinated"))
        return self._corrupt(gold, kind, rng)

    # --- 内部 ---

    def _lookup(self, user: str) -> dict[str, Any]:
        for text, gold in self.gold_by_text.items():
            if text in user:
                return gold
        raise KeyError("MockLLM 没有匹配到原文，请确认提示词里包含简历正文")

    def _corrupt(self, gold: dict[str, Any], kind: str, rng: random.Random) -> str:
        payload = json.loads(json.dumps(gold))
        if kind == "bad_json":
            text = json.dumps(payload, ensure_ascii=False)
            return text[:-12] + ",}"  # 截断 + 多余逗号
        if kind == "bad_schema":
            payload["profile"]["years_of_experience"] = "3 年"
            payload["profile"]["unexpected_field"] = "模型多吐的字段"
            payload["profile"]["education"][0]["degree"] = "本科"
            return json.dumps(payload, ensure_ascii=False)
        # hallucinated：编一个原文里根本不存在的手机号与公司
        payload["profile"]["phone"] = "13900000000"
        if payload["profile"].get("experiences"):
            payload["profile"]["experiences"][0]["company"] = "不存在的公司"
        payload["evidence"]["phone"] = "13900000000"
        return json.dumps(payload, ensure_ascii=False)