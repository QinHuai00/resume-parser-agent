"""导出层：结构化结果 → Excel（人工复核用）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

HEADERS = [
    "来源文件",
    "姓名",
    "手机号",
    "邮箱",
    "城市",
    "工作年限",
    "最高学历学校",
    "专业",
    "学历",
    "技能",
    "是否合规",
    "修复次数",
    "被丢弃字段",
]


def _row(source: str, profile: dict[str, Any] | None, valid: bool, repairs: int, dropped: list[str]) -> list[Any]:
    profile = profile or {}
    edus = profile.get("education") or []
    top = edus[0] if edus else {}
    return [
        source,
        profile.get("name"),
        profile.get("phone"),
        profile.get("email"),
        profile.get("city"),
        profile.get("years_of_experience"),
        top.get("school"),
        top.get("major"),
        top.get("degree"),
        ",".join(profile.get("skills") or []),
        "是" if valid else "否",
        repairs,
        ",".join(dropped),
    ]


def export_xlsx(items: Iterable[dict[str, Any]], path: str | Path) -> Path:
    """items 的元素就是 ParseOutcome.to_dict() 的形态。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "候选人"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for item in items:
        ws.append(
            _row(
                item.get("source", ""),
                item.get("profile"),
                bool(item.get("valid")),
                int(item.get("repairs", 0)),
                item.get("dropped_fields") or [],
            )
        )

    widths = [22, 10, 16, 24, 10, 10, 22, 16, 8, 30, 10, 10, 24]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = width
    ws.freeze_panes = "A2"

    out = Path(path)
    if out.suffix.lower() != ".xlsx":
        out = out.with_suffix(".xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out