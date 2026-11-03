"""简历结构化数据模型（Pydantic v2）。

设计要点：
1. 所有字段默认 None / 空列表 —— 抽取不到就是 null，**不允许模型编造**；
2. `extra="forbid"` —— 模型多吐字段直接判为非法，交由修复环处理；
3. 字段级约束（邮箱格式、年限区间、手机号位数）就是「校验」这一步的判据，
   校验错误原文会被回灌给模型做定向修复。
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


class Education(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school: Optional[str] = Field(None, description="学校名称")
    major: Optional[str] = Field(None, description="专业")
    degree: Optional[str] = Field(None, description="学历：本科/硕士/专科/博士")
    start: Optional[str] = Field(None, description="入学时间，YYYY.MM")
    end: Optional[str] = Field(None, description="毕业时间，YYYY.MM；在读写 null")


class Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: Optional[str] = Field(None, description="公司名称")
    title: Optional[str] = Field(None, description="职位")
    start: Optional[str] = None
    end: Optional[str] = None
    highlights: list[str] = Field(default_factory=list, description="职责/业绩要点，逐条原文）")


class ProjectItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, description="项目名称")
    role: Optional[str] = Field(None, description="担任角色")
    tech: list[str] = Field(default_factory=list, description="技术栈关键词")
    description: Optional[str] = Field(None, description="一句话描述")


class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    years_of_experience: Optional[float] = Field(None, description="工作年限，单位年；应届生写 0")
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError(f"email 格式非法：{v!r}")
        return v

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        digits = re.sub(r"\D", "", v)
        if not 7 <= len(digits) <= 15:
            raise ValueError(f"phone 位数非法：{v!r}")
        return v

    @field_validator("years_of_experience")
    @classmethod
    def _check_years(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if not 0 <= v <= 60:
            raise ValueError(f"years_of_experience 超出合理区间：{v!r}")
        return float(v)


class ExtractionResult(BaseModel):
    """模型必须返回的顶层结构：结构化档案 + 每个字段的原文证据。"""

    model_config = ConfigDict(extra="forbid")

    profile: CandidateProfile
    evidence: dict[str, str] = Field(
        default_factory=dict,
        description="字段路径 -> 支撑该字段的原文片段（必须逐字来自原文，不得改写）",
    )


#: 参与证据校验的标量字段路径（按结构展开，带下标）
SCALAR_PATHS = (
    "name",
    "phone",
    "email",
    "city",
    "years_of_experience",
)


def json_schema_text() -> str:
    """给提示词用的 JSON Schema（去掉 pydantic 的 title 噪声）。"""
    import json

    schema = ExtractionResult.model_json_schema()
    return json.dumps(schema, ensure_ascii=False, indent=2)