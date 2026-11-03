from __future__ import annotations

import pytest
from pydantic import ValidationError

from resume_agent.schema import CandidateProfile, ExtractionResult, json_schema_text


def test_minimal_profile_is_all_null_not_error() -> None:
    profile = CandidateProfile()
    assert profile.name is None
    assert profile.skills == []


def test_bad_email_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        CandidateProfile(email="not-an-email")
    assert "email 格式非法" in str(exc.value)


def test_bad_phone_rejected() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile(phone="12")


def test_years_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile(years_of_experience=99)


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile(unexpected="x")  # type: ignore[call-arg]


def test_schema_text_is_json_schema() -> None:
    text = json_schema_text()
    assert '"profile"' in text
    assert '"evidence"' in text


def test_extraction_result_requires_profile(good_result: dict) -> None:
    result = ExtractionResult.model_validate(good_result)
    assert result.profile.name == "张伟"
    assert result.evidence["education.0.school"] == "华南理工大学"