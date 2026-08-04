from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module


client = TestClient(main_module.app)


def fake_convert(input_path: Path, output_path: Path, **_: object) -> Path:
    assert input_path.read_bytes() == b"fake mobi bytes"
    output_path.write_bytes(b"%PDF-1.7\n% fake test pdf\n")
    return output_path


def test_safe_output_stem() -> None:
    assert main_module._safe_output_stem("../bad:name.mobi") == "bad_name"
    assert main_module._safe_output_stem("CON.mobi") == "book-CON"


def test_home_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "MOBI" in response.text


def test_rejects_non_mobi_upload() -> None:
    response = client.post(
        "/api/v1/convert",
        files={"file": ("book.txt", b"text", "text/plain")},
    )
    assert response.status_code == 400


def test_converts_and_returns_pdf(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "convert_mobi_to_pdf", fake_convert)
    response = client.post(
        "/api/v1/convert",
        files={"file": ("example.mobi", b"fake mobi bytes", "application/x-mobipocket-ebook")},
        data={
            "paper_size": "a4",
            "margin_pt": "36",
            "add_page_numbers": "true",
            "add_toc": "false",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")
