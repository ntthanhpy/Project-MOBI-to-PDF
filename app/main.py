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

BASE_DIR = Path(__file__).resolve().parent
CHUNK_SIZE = 1024 * 1024

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Upload a MOBI e-book and receive a converted PDF.",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _cleanup(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)


def _safe_output_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" .")
    if not stem:
        return "converted-book"
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"book-{stem}"
    return stem[:120]


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
    original_name = Path(file.filename or "book.mobi").name
    if Path(original_name).suffix.lower() != ".mobi":
        raise HTTPException(status_code=400, detail="Only .mobi files are supported.")

    paper_size = paper_size.lower()
    options = PdfOptions(
        paper_size=paper_size,
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
    safe_stem = _safe_output_stem(original_name)
    output_name = f"{safe_stem}.pdf"
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
