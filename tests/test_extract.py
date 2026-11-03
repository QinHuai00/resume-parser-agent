"""文本抽取层：三种格式各测一遍，外加不支持的类型。"""
from __future__ import annotations

import io

import pytest

from resume_agent.extract import UnsupportedDocument, extract, extract_path
from resume_agent.schema import ExtractionResult  # noqa: F401  (确包可 import)


def test_txt_utf8() -> None:
    doc = extract("cv.txt", "姓名：张伟\n手机：13812345678".encode("utf-8"))
    assert "张伟" in doc.text
    assert doc.kind == "txt"


def test_txt_gbk_fallback() -> None:
    doc = extract("cv.txt", "姓名：李娜".encode("gb18030"))
    assert "李娜" in doc.text


def test_docx_paragraphs_and_tables(tmp_path) -> None:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("姓名：王强")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "邮箱"
    table.cell(0, 1).text = "wangqiang@example.com"
    buf = io.BytesIO()
    document.save(buf)

    doc = extract("cv.docx", buf.getvalue())

    assert "姓名：王强" in doc.text
    assert "wangqiang@example.com" in doc.text


def test_unsupported_suffix() -> None:
    with pytest.raises(UnsupportedDocument):
        extract("cv.rtf", b"whatever")


def test_empty_text_uses_ocr_hook() -> None:
    doc = extract("scan.txt", b"   ", ocr_hook=lambda _: "姓名：赵磊")
    assert doc.text == "姓名：赵磊"
    assert doc.kind.endswith("+ocr")


def test_extract_path(tmp_path) -> None:
    p = tmp_path / "cv.md"
    p.write_text("# 姓名：周静", encoding="utf-8")
    doc = extract_path(p)
    assert doc.source == "cv.md"
    assert "周静" in doc.text