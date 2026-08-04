from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

from app.config import settings
from app.converter import (
    SUPPORTED_PAPER_SIZES,
    CalibreNotFoundError,
    ConversionError,
    ConversionTimeoutError,
    PdfOptions,
    calibre_is_available,
    convert_mobi_to_pdf,
)
from app.jobs import ConversionJob, JobStore

BASE_DIR = Path(__file__).resolve().parent
CHUNK_SIZE = 1024 * 1024

app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    description="Upload a MOBI e-book, follow live processing logs, and download a PDF.",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
jobs = JobStore(ttl_seconds=3600)
_background_tasks: set[asyncio.Task[None]] = set()

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _cleanup(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)


def _cleanup_download(job_id: str, directory: Path) -> None:
    jobs.pop(job_id)
    _cleanup(directory)


def _safe_output_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" .")
    if not stem:
        return "converted-book"
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"book-{stem}"
    return stem[:120]


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


async def _save_upload(upload: UploadFile, destination: Path) -> int:
    total = 0
    with destination.open("wb") as target:
        while chunk := await upload.read(CHUNK_SIZE):
            total += len(chunk)
            if total > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {settings.max_upload_mb} MB limit.",
                )
            await asyncio.to_thread(target.write, chunk)
    return total


def _progress_from_calibre_line(line: str) -> int | None:
    match = re.search(r"(?<!\d)(\d{1,3})%", line)
    if not match:
        return None
    calibre_progress = max(0, min(100, int(match.group(1))))
    return min(94, 40 + round(calibre_progress * 0.54))


async def _run_conversion(job_id: str, options: PdfOptions) -> None:
    job = jobs.get(job_id)
    if job is None:
        return

    try:
        job.add_log(
            "Đang kiểm tra công cụ Calibre ebook-convert.",
            stage="Kiểm tra môi trường",
            progress=30,
            status="processing",
        )
        if not calibre_is_available(settings.calibre_command):
            raise CalibreNotFoundError(
                "Không tìm thấy Calibre ebook-convert trên máy chủ. "
                "Hãy cài Calibre hoặc cấu hình CALIBRE_COMMAND."
            )

        job.add_log(
            f"Bắt đầu chuyển đổi với khổ giấy {options.paper_size.upper()}, "
            f"lề {options.margin_pt} pt.",
            stage="Calibre đang xử lý",
            progress=40,
        )

        def on_calibre_log(line: str) -> None:
            progress = _progress_from_calibre_line(line)
            job.add_log(
                line,
                stage="Calibre đang xử lý",
                progress=progress,
            )

        await asyncio.to_thread(
            convert_mobi_to_pdf,
            job.input_path,
            job.output_path,
            options=options,
            calibre_command=settings.calibre_command,
            timeout_seconds=settings.conversion_timeout_seconds,
            log_callback=on_calibre_log,
        )

        output_size = job.output_path.stat().st_size
        job.add_log(
            f"Đã tạo {job.output_name} ({_human_size(output_size)}).",
            level="success",
            stage="Hoàn tất",
            progress=100,
            status="completed",
        )
    except CalibreNotFoundError as exc:
        job.fail(str(exc))
    except ConversionTimeoutError as exc:
        job.fail(str(exc))
    except ConversionError as exc:
        job.fail(str(exc))
    except Exception as exc:  # Defensive job boundary; details remain visible to the user.
        job.fail(f"Lỗi không mong đợi: {exc}")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "max_upload_mb": settings.max_upload_mb,
            "paper_sizes": sorted(SUPPORTED_PAPER_SIZES),
            "default_paper_size": settings.default_paper_size,
            "default_margin_pt": settings.default_margin_pt,
            "default_add_page_numbers": settings.default_add_page_numbers,
            "default_add_toc": settings.default_add_toc,
        },
    )


@app.get("/health")
async def health() -> dict[str, object]:
    available = calibre_is_available(settings.calibre_command)
    return {
        "status": "ok" if available else "degraded",
        "calibre_available": available,
        "max_upload_mb": settings.max_upload_mb,
    }


@app.get("/ready")
async def readiness() -> JSONResponse:
    available = calibre_is_available(settings.calibre_command)
    return JSONResponse(
        status_code=200 if available else 503,
        content={"ready": available},
    )


@app.post("/api/v1/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_conversion_job(
    file: Annotated[UploadFile, File(description="A .mobi e-book")],
    paper_size: Annotated[str, Form()] = settings.default_paper_size,
    margin_pt: Annotated[int, Form()] = settings.default_margin_pt,
    add_page_numbers: Annotated[bool, Form()] = settings.default_add_page_numbers,
    add_toc: Annotated[bool, Form()] = settings.default_add_toc,
) -> dict[str, object]:
    original_name = Path(file.filename or "book.mobi").name
    if Path(original_name).suffix.lower() != ".mobi":
        raise HTTPException(status_code=400, detail="Only .mobi files are supported.")

    options = PdfOptions(
        paper_size=paper_size.lower(),
        margin_pt=margin_pt,
        add_page_numbers=add_page_numbers,
        add_toc=add_toc,
    )
    try:
        options.validate()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    work_dir = Path(tempfile.mkdtemp(prefix="mobi-to-pdf-job-"))
    input_path = work_dir / "input.mobi"
    output_name = f"{_safe_output_stem(original_name)}.pdf"
    output_path = work_dir / output_name

    try:
        file_size = await _save_upload(file, input_path)
        if file_size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    except Exception:
        _cleanup(work_dir)
        raise
    finally:
        await file.close()

    job = jobs.add(
        ConversionJob(
            original_name=original_name,
            output_name=output_name,
            work_dir=work_dir,
            input_path=input_path,
            output_path=output_path,
            file_size=file_size,
        )
    )
    job.add_log(
        f"Đã nhận file {original_name} ({_human_size(file_size)}).",
        level="success",
        stage="Đã tải file lên",
        progress=25,
    )
    job.add_log("Job đã được đưa vào hàng đợi chuyển đổi.", stage="Đang chờ xử lý")

    task = asyncio.create_task(_run_conversion(job.id, options))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "job_id": job.id,
        "status_url": f"/api/v1/jobs/{job.id}",
        "status": job.status,
    }


@app.get("/api/v1/jobs/{job_id}")
async def get_conversion_job(job_id: str) -> dict[str, object]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Conversion job not found or expired.")
    return job.snapshot()


@app.get("/api/v1/jobs/{job_id}/download", response_class=FileResponse)
async def download_conversion(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Conversion job not found or expired.")
    if job.status != "completed" or not job.output_path.is_file():
        raise HTTPException(status_code=409, detail="PDF is not ready for download.")

    return FileResponse(
        path=job.output_path,
        media_type="application/pdf",
        filename=job.output_name,
        background=BackgroundTask(_cleanup_download, job.id, job.work_dir),
    )


@app.post(
    "/api/v1/convert",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/pdf": {}}},
        400: {"description": "Invalid input"},
        413: {"description": "Upload too large"},
        500: {"description": "Conversion failed"},
        503: {"description": "Calibre is unavailable"},
        504: {"description": "Conversion timed out"},
    },
)
async def convert(
    file: Annotated[UploadFile, File(description="A .mobi e-book")],
    paper_size: Annotated[str, Form()] = settings.default_paper_size,
    margin_pt: Annotated[int, Form()] = settings.default_margin_pt,
    add_page_numbers: Annotated[bool, Form()] = settings.default_add_page_numbers,
    add_toc: Annotated[bool, Form()] = settings.default_add_toc,
) -> FileResponse:
    """Backward-compatible synchronous API used by scripts and existing clients."""
    original_name = Path(file.filename or "book.mobi").name
    if Path(original_name).suffix.lower() != ".mobi":
        raise HTTPException(status_code=400, detail="Only .mobi files are supported.")

    options = PdfOptions(
        paper_size=paper_size.lower(),
        margin_pt=margin_pt,
        add_page_numbers=add_page_numbers,
        add_toc=add_toc,
    )
    try:
        options.validate()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    work_dir = Path(tempfile.mkdtemp(prefix="mobi-to-pdf-"))
    input_path = work_dir / "input.mobi"
    output_name = f"{_safe_output_stem(original_name)}.pdf"
    output_path = work_dir / output_name

    try:
        await _save_upload(file, input_path)
        if input_path.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        await asyncio.to_thread(
            convert_mobi_to_pdf,
            input_path,
            output_path,
            options=options,
            calibre_command=settings.calibre_command,
            timeout_seconds=settings.conversion_timeout_seconds,
        )
    except HTTPException:
        _cleanup(work_dir)
        raise
    except CalibreNotFoundError as exc:
        _cleanup(work_dir)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ConversionTimeoutError as exc:
        _cleanup(work_dir)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ConversionError as exc:
        _cleanup(work_dir)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception:
        _cleanup(work_dir)
        raise
    finally:
        await file.close()

    return FileResponse(
        path=output_path,
        media_type="application/pdf",
        filename=output_name,
        background=BackgroundTask(_cleanup, work_dir),
    )
