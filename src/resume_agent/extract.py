"""文本抽取层：按文件类型分流，扫描件走 OCR 钩子（默认不启用，避免强依赖）。"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

SUPPORTED_SUFFIXES = {".txt", ".md", ".docx", ".pdf"}


@dataclass
class TextDocument:
    text: str
    source: str
    kind: str

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class UnsupportedDocument(ValueError):
    pass


def _extract_txt(data: bytes) -> str:
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "ignore")


def _extract_docx(data: bytes) -> str:
    import docx  # python-docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


_EXTRACTORS: dict[str, Callable[[bytes], str]] = {
    ".txt": _extract_txt,
    ".md": _extract_txt,
    ".docx": _extract_docx,
    ".pdf": _extract_pdf,
}


def extract(filename: str, data: bytes, *, ocr_hook: Optional[Callable[[bytes], str]] = None) -> TextDocument:
    """按后缀分流抽取文本；抽不出字时尝试 ocr_hook。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in _EXTRACTORS:
        raise UnsupportedDocument(f"不支持的文件类型：{suffix}（支持 {sorted(SUPPORTED_SUFFIXES)}）")

    try:
        text = _EXTRACTORS[suffix](data)
    except ImportError as exc:  # 缺依赖时给出人话
        raise UnsupportedDocument(f"解析 {suffix} 缺少依赖：{exc}") from exc

    kind = suffix.lstrip(".")
    if not text.strip() and ocr_hook is not None:
        text = ocr_hook(data)
        kind = f"{kind}+ocr"
    return TextDocument(text=text, source=filename, kind=kind)


def extract_path(path: str | Path, *, ocr_hook: Optional[Callable[[bytes], str]] = None) -> TextDocument:
    p = Path(path)
    return extract(p.name, p.read_bytes(), ocr_hook=ocr_hook)