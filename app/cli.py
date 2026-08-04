from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.converter import PdfOptions, convert_mobi_to_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a MOBI e-book to PDF")
    parser.add_argument("input", type=Path, help="Path to the source .mobi file")
    parser.add_argument("output", type=Path, nargs="?", help="Output .pdf path")
    parser.add_argument("--paper-size", default=settings.default_paper_size)
    parser.add_argument("--margin-pt", type=int, default=settings.default_margin_pt)
    parser.add_argument("--no-page-numbers", action="store_true")
    parser.add_argument("--add-toc", action="store_true")
    parser.add_argument(
        "--calibre-command",
        default=settings.calibre_command,
        help="ebook-convert command or full executable path",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=settings.conversion_timeout_seconds,
        help="Conversion timeout in seconds",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or args.input.with_suffix(".pdf")
    options = PdfOptions(
        paper_size=args.paper_size.lower(),
        margin_pt=args.margin_pt,
        add_page_numbers=not args.no_page_numbers,
        add_toc=args.add_toc,
    )

    try:
        result = convert_mobi_to_pdf(
            args.input,
            output,
            options=options,
            calibre_command=args.calibre_command,
            timeout_seconds=args.timeout,
        )
    except Exception as exc:  # CLI boundary: print a concise actionable error.
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
