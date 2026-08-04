from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_PAPER_SIZES = {
    "a0",
    "a1",
    "a2",
    "a3",
    "a4",
    "a5",
    "a6",
    "b0",
    "b1",
    "b2",
    "b3",
    "b4",
    "b5",
    "b6",
    "legal",
    "letter",
}


class CalibreNotFoundError(RuntimeError):
    """Raised when the Calibre command-line converter cannot be found."""


class ConversionError(RuntimeError):
    """Raised when Calibre fails to convert a document."""


class ConversionTimeoutError(ConversionError):
    """Raised when a conversion exceeds its configured timeout."""


@dataclass(frozen=True, slots=True)
class PdfOptions:
    paper_size: str = "a4"
    margin_pt: int = 36
    add_page_numbers: bool = True
    add_toc: bool = False
    preserve_cover_aspect_ratio: bool = True

    def validate(self) -> None:
        if self.paper_size not in SUPPORTED_PAPER_SIZES:
            raise ValueError(f"Unsupported paper size: {self.paper_size}")
        if not 0 <= self.margin_pt <= 144:
            raise ValueError("margin_pt must be between 0 and 144")


def calibre_is_available(command: str = "ebook-convert") -> bool:
    return shutil.which(command) is not None or Path(command).is_file()


def build_command(
    input_path: Path,
    output_path: Path,
    options: PdfOptions,
    calibre_command: str = "ebook-convert",
) -> list[str]:
    options.validate()
    command = [
        calibre_command,
        str(input_path),
        str(output_path),
        "--paper-size",
        options.paper_size,
        "--pdf-page-margin-top",
        str(options.margin_pt),
        "--pdf-page-margin-right",
        str(options.margin_pt),
        "--pdf-page-margin-bottom",
        str(options.margin_pt),
        "--pdf-page-margin-left",
        str(options.margin_pt),
    ]

    if options.add_page_numbers:
        command.append("--pdf-page-numbers")
    if options.add_toc:
        command.append("--pdf-add-toc")
    if options.preserve_cover_aspect_ratio:
        command.append("--preserve-cover-aspect-ratio")

    return command


def _terminate_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def convert_mobi_to_pdf(
    input_path: Path,
    output_path: Path,
    *,
    options: PdfOptions,
    calibre_command: str = "ebook-convert",
    timeout_seconds: int = 300,
    log_callback: Callable[[str], None] | None = None,
) -> Path:
    if input_path.suffix.lower() != ".mobi":
        raise ValueError("Input file must have a .mobi extension")
    if output_path.suffix.lower() != ".pdf":
        raise ValueError("Output file must have a .pdf extension")
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if not calibre_is_available(calibre_command):
        raise CalibreNotFoundError(
            "Calibre ebook-convert was not found. Install Calibre or set "
            "CALIBRE_COMMAND to the full executable path."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(input_path, output_path, options, calibre_command)
    output_lines: list[str] = []
    line_queue: queue.Queue[str | None] = queue.Queue()

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
        )
    except OSError as exc:
        output_path.unlink(missing_ok=True)
        raise ConversionError(f"Unable to start Calibre: {exc}") from exc

    def read_output() -> None:
        assert process.stdout is not None
        try:
            for raw_line in process.stdout:
                line_queue.put(raw_line.rstrip())
        finally:
            line_queue.put(None)

    reader = threading.Thread(target=read_output, name="calibre-log-reader", daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds
    reader_finished = False

    try:
        while process.poll() is None or not reader_finished:
            if process.poll() is None and time.monotonic() >= deadline:
                _terminate_process(process)
                output_path.unlink(missing_ok=True)
                raise ConversionTimeoutError(
                    f"Conversion exceeded {timeout_seconds} seconds"
                )

            try:
                line = line_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if line is None:
                reader_finished = True
                continue

            clean_line = line.strip()
            if clean_line:
                output_lines.append(clean_line)
                if len(output_lines) > 300:
                    output_lines.pop(0)
                if log_callback is not None:
                    log_callback(clean_line)
    finally:
        reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()

    if process.returncode != 0 or not output_path.is_file():
        output_path.unlink(missing_ok=True)
        details = "\n".join(output_lines[-40:]).strip() or "Unknown Calibre error"
        details = details[-4000:]
        raise ConversionError(f"Calibre conversion failed: {details}")

    return output_path
