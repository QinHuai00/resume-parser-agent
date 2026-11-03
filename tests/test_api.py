"""HTTP 层：单份解析 + 批量任务 + 失败隔离。"""
from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from resume_agent.llm import ScriptedLLM  # noqa: E402
from resume_agent.pipeline import ResumePipeline  # noqa: E402
from resume_agent.service import create_app  # noqa: E402

GOOD = json.dumps(
    {
        "profile": {"name": "张伟", "skills": [], "education": [], "experiences": [], "projects": []},
        "evidence": {"name": "姓名：张伟"},
    },
    ensure_ascii=False,
)


def _client(responses: list[str]) -> TestClient:
    pipeline = ResumePipeline(ScriptedLLM(responses), max_repairs=0)
    return TestClient(create_app(pipeline))


def test_healthz() -> None:
    client = _client([])
    assert client.get("/healthz").json()["status"] == "ok"


def test_parse_single_txt() -> None:
    client = _client([GOOD])
    resp = client.post(
        "/api/v1/parse",
        files={"file": ("cv.txt", "姓名：张伟".encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["profile"]["name"] == "张伟"


def test_parse_rejects_unsupported_type() -> None:
    client = _client([GOOD])
    resp = client.post("/api/v1/parse", files={"file": ("cv.rtf", b"x", "application/rtf")})
    assert resp.status_code == 415


def test_batch_isolates_failures() -> None:
    # 3 个文件，其中第 2 个拿到的输出是坏 JSON
    client = _client([GOOD, "not json", GOOD])

    resp = client.post(
        "/api/v1/batch",
        files=[
            ("files", ("a.txt", "姓名：张伟".encode(), "text/plain")),
            ("files", ("b.txt", "姓名：李娜".encode(), "text/plain")),
            ("files", ("c.txt", "姓名：王强".encode(), "text/plain")),
        ],
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    task = client.get(f"/api/v1/tasks/{task_id}").json()
    assert task["status"] == "done"
    assert task["total"] == 3
    assert task["failed"] == 1
    assert task["succeeded"] == 2


def test_task_not_found() -> None:
    client = _client([])
    assert client.get("/api/v1/tasks/nope").status_code == 404