"""导出层：确认 Excel 表头与行内容。"""
from __future__ import annotations

import pytest

openpyxl = pytest.importorskip("openpyxl")

from resume_agent.export import HEADERS, export_xlsx  # noqa: E402

ITEM = {
    "source": "cv.txt",
    "valid": True,
    "repairs": 1,
    "dropped_fields": ["phone"],
    "profile": {
        "name": "张伟",
        "phone": None,
        "email": "zhangwei01@example.com",
        "city": "深圳",
        "years_of_experience": 3.0,
        "education": [{"school": "华南理工大学", "major": "软件工程", "degree": "本科"}],
        "skills": ["Python", "FastAPI"],
    },
}


def test_export_roundtrip(tmp_path) -> None:
    path = export_xlsx([ITEM], tmp_path / "summary.xlsx")
    wb = openpyxl.load_workbook(path)
    ws = wb.active

    assert [c.value for c in ws[1]] == HEADERS
    row = [c.value for c in ws[2]]
    assert row[0] == "cv.txt"
    assert row[1] == "张伟"
    assert row[6] == "华南理工大学"
    assert row[9] == "Python,FastAPI"
    assert row[10] == "是"
    assert row[12] == "phone"
    assert ws.freeze_panes == "A2"


def test_export_adds_suffix(tmp_path) -> None:
    path = export_xlsx([ITEM], tmp_path / "summary")
    assert path.suffix == ".xlsx"
    assert path.exists()