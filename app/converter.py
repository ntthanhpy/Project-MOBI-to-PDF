from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_PAPER_SIZES = {
    "a0", "a1", "a2", "a3", "a4", "a5", "a6",
    "b0", "b1", "b2", "b3", "b4", "b5", "b6",
    "legal", "letter",
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


def convert_mobi_to_pdf(
    input_path: Path,
    output_path: Path,
    *,
    options: PdfOptions,
    calibre_command: str = "ebook-convert",
    timeout_seconds: int = 300,
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

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        output_path.unlink(missing_ok=True)
        raise ConversionTimeoutError(
            f"Conversion exceeded {timeout_seconds} seconds"
        ) from exc
    except OSError as exc:
        output_path.unlink(missing_ok=True)
        raise ConversionError(f"Unable to start Calibre: {exc}") from exc

    if result.returncode != 0 or not output_path.is_file():
        output_path.unlink(missing_ok=True)
        details = (result.stderr or result.stdout or "Unknown Calibre error").strip()
        # Avoid returning an unexpectedly massive Calibre log to clients.
        details = details[-4000:]
        raise ConversionError(f"Calibre conversion failed: {details}")

    return output_path
