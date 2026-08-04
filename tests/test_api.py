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


def test_home_uses_same_origin_static_assets() -> None:
    response = client.get("/")
    assert 'href="/static/styles.css?v=2"' in response.text
    assert 'src="/static/app.js?v=2"' in response.text
    assert "Processing log" in response.text


def test_async_job_reports_logs_and_completes(monkeypatch) -> None:
    def fake_job_convert(
        input_path: Path,
        output_path: Path,
        *,
        log_callback=None,
        **_: object,
    ) -> Path:
        assert input_path.read_bytes() == b"fake mobi bytes"
        if log_callback:
            log_callback("50% Converting book content")
        output_path.write_bytes(b"%PDF-1.7\n% async fake pdf\n")
        return output_path

    monkeypatch.setattr(main_module, "calibre_is_available", lambda _command: True)
    monkeypatch.setattr(main_module, "convert_mobi_to_pdf", fake_job_convert)

    with TestClient(main_module.app) as scoped_client:
        created = scoped_client.post(
            "/api/v1/jobs",
            files={
                "file": (
                    "example.mobi",
                    b"fake mobi bytes",
                    "application/x-mobipocket-ebook",
                )
            },
            data={
                "paper_size": "a4",
                "margin_pt": "36",
                "add_page_numbers": "true",
                "add_toc": "false",
            },
        )
        assert created.status_code == 202
        job_id = created.json()["job_id"]

        completed = None
        for _ in range(20):
            status_response = scoped_client.get(f"/api/v1/jobs/{job_id}")
            assert status_response.status_code == 200
            completed = status_response.json()
            if completed["status"] == "completed":
                break

        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["progress"] == 100
        assert any("50% Converting" in log["message"] for log in completed["logs"])

        download = scoped_client.get(completed["download_url"])
        assert download.status_code == 200
        assert download.content.startswith(b"%PDF")
