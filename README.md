# MOBI to PDF Converter

Project chuyển đổi sách điện tử `.mobi` sang `.pdf` bằng **FastAPI** và công cụ dòng lệnh **Calibre `ebook-convert`**.

## Tính năng

- Giao diện web kéo-thả file MOBI.
- API `POST /api/v1/convert` trả trực tiếp file PDF.
- CLI cho batch/script automation.
- Chọn khổ giấy, lề trang, số trang và mục lục in.
- Giới hạn dung lượng upload, timeout chuyển đổi và kiểm tra định dạng.
- Không dùng `shell=True`; tên file được chuẩn hóa và mỗi request dùng thư mục tạm riêng.
- File tạm được xóa sau khi tải xuống hoàn tất.
- Docker, health check và test tự động.

> Project không phá DRM. Chỉ chuyển đổi các file mà Calibre có thể đọc hợp pháp và không bị khóa DRM.

## Kiến trúc

```text
Browser / API client
        |
        v
FastAPI upload endpoint
        |
        +-- validate extension, size and PDF options
        +-- save into isolated temporary directory
        +-- run Calibre ebook-convert without a shell
        +-- stream PDF response
        +-- delete temporary directory
```

## Cách 1 — Chạy nhanh bằng Docker

Yêu cầu: Docker Desktop.

```bash
docker compose up --build
```

Mở: `http://localhost:8000`

Dừng dịch vụ:

```bash
docker compose down
```

Lưu ý: image Docker có thể khá lớn vì Calibre và bộ font được cài bên trong.

## Cách 2 — Chạy trực tiếp trên Windows

1. Cài Python 3.11+.
2. Cài Calibre.
3. Mở PowerShell trong thư mục project:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run_local.ps1
```

Mở: `http://127.0.0.1:8000`

Script tự tìm `ebook-convert.exe` tại thư mục Calibre phổ biến. Có thể chỉ định thủ công:

```powershell
$env:CALIBRE_COMMAND = "C:\Program Files\Calibre2\ebook-convert.exe"
uvicorn app.main:app --reload
```

## Cách 3 — CLI

Sau khi đã cài dependency Python và Calibre:

```bash
python -m app.cli input.mobi output.pdf
```

Ví dụ tùy chỉnh:

```bash
python -m app.cli input.mobi output.pdf \
  --paper-size a4 \
  --margin-pt 36 \
  --add-toc
```

## Gọi API

```bash
curl -X POST http://localhost:8000/api/v1/convert \
  -F "file=@book.mobi" \
  -F "paper_size=a4" \
  -F "margin_pt=36" \
  -F "add_page_numbers=true" \
  -F "add_toc=false" \
  --output book.pdf
```

Swagger UI: `http://localhost:8000/docs`

## Cấu hình môi trường

Sao chép `.env.example` thành `.env` hoặc khai báo biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|---|---:|---|
| `CALIBRE_COMMAND` | `ebook-convert` | Lệnh hoặc đường dẫn đầy đủ tới Calibre CLI |
| `MAX_UPLOAD_MB` | `100` | Dung lượng upload tối đa |
| `CONVERSION_TIMEOUT_SECONDS` | `300` | Timeout một lần chuyển đổi |
| `DEFAULT_PAPER_SIZE` | `a4` | Khổ giấy mặc định |
| `DEFAULT_MARGIN_PT` | `36` | Lề PDF mặc định |
| `DEFAULT_ADD_PAGE_NUMBERS` | `true` | Thêm số trang |
| `DEFAULT_ADD_TOC` | `false` | Thêm mục lục có số trang ở cuối PDF |

## Test và lint

```bash
python -m pip install -r requirements-dev.txt
pytest
ruff check .
```

Các test API mock engine Calibre nên không cần file MOBI thật.

## Production checklist

- Đặt reverse proxy như Nginx/Traefik phía trước nếu public Internet.
- Thêm authentication và rate limit.
- Chạy một worker hoặc giới hạn concurrency vì chuyển đổi ebook tốn CPU/RAM.
- Đẩy job sang hàng đợi như Celery/RQ nếu cần xử lý nhiều file đồng thời.
- Không ghi log nội dung file hoặc đường dẫn nhạy cảm.
- Quét malware nếu cho phép người dùng không tin cậy upload file.

## Giới hạn

- Chất lượng PDF phụ thuộc cấu trúc và CSS của file MOBI nguồn.
- File có DRM không được hỗ trợ.
- Một số font hiếm có thể bị thay thế nếu máy chủ không cài font tương ứng.
