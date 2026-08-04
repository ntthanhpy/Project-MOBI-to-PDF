from __future__ import annotations

import shutil
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

JobStatus = Literal["queued", "processing", "completed", "failed"]
LogLevel = Literal["info", "success", "warning", "error"]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ConversionJob:
    original_name: str
    output_name: str
    work_dir: Path
    input_path: Path
    output_path: Path
    file_size: int
    id: str = field(default_factory=lambda: uuid4().hex)
    status: JobStatus = "queued"
    stage: str = "Đang chờ xử lý"
    progress: int = 25
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    _sequence: int = 0
    _logs: deque[dict[str, object]] = field(default_factory=lambda: deque(maxlen=300))
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def add_log(
        self,
        message: str,
        *,
        level: LogLevel = "info",
        stage: str | None = None,
        progress: int | None = None,
        status: JobStatus | None = None,
    ) -> None:
        clean_message = " ".join(message.strip().split())
        if not clean_message:
            return

        with self._lock:
            self._sequence += 1
            if stage is not None:
                self.stage = stage
            if progress is not None:
                self.progress = max(0, min(100, progress))
            if status is not None:
                self.status = status
            self.updated_at = _now()
            self._logs.append(
                {
                    "id": self._sequence,
                    "timestamp": self.updated_at.isoformat(),
                    "level": level,
                    "message": clean_message[:1000],
                }
            )

    def fail(self, message: str) -> None:
        with self._lock:
            self.error = message
        self.add_log(
            message,
            level="error",
            stage="Chuyển đổi thất bại",
            status="failed",
        )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            result: dict[str, object] = {
                "id": self.id,
                "original_name": self.original_name,
                "output_name": self.output_name,
                "file_size": self.file_size,
                "status": self.status,
                "stage": self.stage,
                "progress": self.progress,
                "error": self.error,
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
                "logs": list(self._logs),
            }
            if self.status == "completed":
                result["download_url"] = f"/api/v1/jobs/{self.id}/download"
            return result


class JobStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._jobs: dict[str, ConversionJob] = {}
        self._lock = threading.RLock()
        self._ttl = timedelta(seconds=ttl_seconds)

    def add(self, job: ConversionJob) -> ConversionJob:
        self.purge_expired()
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> ConversionJob | None:
        self.purge_expired()
        with self._lock:
            return self._jobs.get(job_id)

    def pop(self, job_id: str) -> ConversionJob | None:
        with self._lock:
            return self._jobs.pop(job_id, None)

    def purge_expired(self) -> None:
        cutoff = _now() - self._ttl
        expired: list[ConversionJob] = []
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.updated_at < cutoff and job.status in {"completed", "failed"}:
                    expired.append(self._jobs.pop(job_id))
        for job in expired:
            shutil.rmtree(job.work_dir, ignore_errors=True)
