"""服务层：FastAPI。

三件事：
1. 单份解析：`POST /api/v1/parse`（上传即返回结构化结果）；
2. 批量解析：`POST /api/v1/batch` 立刻返回 task_id，耗时任务交后台协程跑，
   前端轮询 `GET /api/v1/tasks/{task_id}` —— 先返回句柄、再异步推进；
3. 失败隔离：单个文件失败只把它标 failed，不影响整批；并发度用 Semaphore 控。

为什么单份接口是同步的：单份 1~3 秒可接受；批量不能同步，否则 worker 被占住。
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from .extract import UnsupportedDocument
from .pipeline import ParseOutcome, ResumePipeline

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 5 * 1024 * 1024))
BATCH_CONCURRENCY = int(os.environ.get("BATCH_CONCURRENCY", 4))


class ParseResponse(BaseModel):
    source: str
    valid: bool
    profile: dict[str, Any] | None = None
    repairs: int = 0
    dropped_fields: list[str] = []
    error: str | None = None


class BatchCreateResponse(BaseModel):
    task_id: str
    total: int


class TaskResponse(BaseModel):
    task_id: str
    status: str
    total: int
    done: int
    succeeded: int
    failed: int
    elapsed_ms: int
    results: list[ParseResponse]


@dataclass
class _Task:
    task_id: str
    total: int
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    results: list[ParseResponse] = field(default_factory=list)

    @property
    def done(self) -> int:
        return len(self.results)

    def snapshot(self) -> TaskResponse:
        return TaskResponse(
            task_id=self.task_id,
            status=self.status,
            total=self.total,
            done=self.done,
            succeeded=sum(1 for r in self.results if r.valid),
            failed=sum(1 for r in self.results if not r.valid),
            elapsed_ms=int((time.time() - self.started_at) * 1000),
            results=self.results,
        )


def _to_response(outcome: ParseOutcome) -> ParseResponse:
    return ParseResponse(
        source=outcome.source,
        valid=outcome.valid,
        profile=outcome.profile,
        repairs=outcome.repairs,
        dropped_fields=outcome.dropped_fields,
        error=outcome.error,
    )


def create_app(pipeline: ResumePipeline) -> FastAPI:
    app = FastAPI(title="resume-parser-agent", version="0.1.0")
    tasks: dict[str, _Task] = {}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    async def _read(file: UploadFile) -> bytes:
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{file.filename} 超过 {MAX_UPLOAD_BYTES} 字节上限")
        return data

    @app.post("/api/v1/parse", response_model=ParseResponse)
    async def parse_one(file: UploadFile = File(...)) -> ParseResponse:
        data = await _read(file)
        try:
            outcome = await asyncio.to_thread(pipeline.parse_bytes, file.filename or "unnamed.txt", data)
        except UnsupportedDocument as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        return _to_response(outcome)

    @app.post("/api/v1/batch", response_model=BatchCreateResponse, status_code=202)
    async def parse_batch(files: list[UploadFile] = File(...)) -> BatchCreateResponse:
        payload: list[tuple[str, bytes]] = []
        for f in files:
            payload.append((f.filename or "unnamed.txt", await _read(f)))
        task = _Task(task_id=uuid.uuid4().hex[:12], total=len(payload))
        tasks[task.task_id] = task

        async def run() -> None:
            sem = asyncio.Semaphore(BATCH_CONCURRENCY)
            ordered: list[ParseResponse | None] = [None] * len(payload)

            async def one(idx: int, name: str, blob: bytes) -> None:
                async with sem:
                    try:
                        outcome = await asyncio.to_thread(pipeline.parse_bytes, name, blob)
                    except Exception as exc:  # noqa: BLE001 单份失败不影响整批
                        outcome = ParseOutcome(source=name, valid=False, profile=None, error=f"{type(exc).__name__}: {exc}")
                    ordered[idx] = _to_response(outcome)

            await asyncio.gather(*(one(i, n, b) for i, (n, b) in enumerate(payload)))
            task.results = [r for r in ordered if r is not None]
            task.status = "done"

        asyncio.create_task(run())  # noqa: RUF006 后台任务，句柄即 task_id
        return BatchCreateResponse(task_id=task.task_id, total=task.total)

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskResponse)
    async def get_task(task_id: str) -> TaskResponse:
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task 不存在")
        return task.snapshot()

    return app