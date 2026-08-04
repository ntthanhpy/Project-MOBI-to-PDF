from pathlib import Path

import pytest

from app.converter import PdfOptions, build_command


def test_build_command_contains_expected_pdf_options(tmp_path: Path) -> None:
    input_path = tmp_path / "book.mobi"
    output_path = tmp_path / "book.pdf"
    options = PdfOptions(paper_size="a4", margin_pt=36, add_page_numbers=True, add_toc=True)

    command = build_command(input_path, output_path, options)

    assert command[:3] == ["ebook-convert", str(input_path), str(output_path)]
    assert "--paper-size" in command
    assert "a4" in command
    assert "--pdf-page-numbers" in command
    assert "--pdf-add-toc" in command
    assert "--preserve-cover-aspect-ratio" in command


def test_invalid_margin_is_rejected() -> None:
    with pytest.raises(ValueError, match="margin_pt"):
        PdfOptions(margin_pt=145).validate()


def test_invalid_paper_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="paper size"):
        PdfOptions(paper_size="tabloid").validate()
