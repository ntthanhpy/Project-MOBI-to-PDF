# MOBI to PDF Converter

Project chuyển đổi sách điện tử `.mobi` sang `.pdf` bằng **FastAPI** và công cụ dòng lệnh **Calibre `ebook-convert`**.

## Tính năng

- Giao diện web responsive hai cột, kéo-thả file MOBI.
- Theo dõi upload, phần trăm xử lý, thời gian chạy và log Calibre trực tiếp trên web.
- API job bất đồng bộ: tạo job, đọc trạng thái/log và tải PDF khi hoàn tất.
- API `POST /api/v1/convert` đồng bộ vẫn được giữ để tương thích script cũ.
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
        +-- create an in-memory conversion job
        +-- run Calibre ebook-convert without a shell
        +-- collect progress/log output
        +-- expose job status for browser polling
        +-- download PDF and delete temporary directory
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

## Theo dõi trạng thái và log trên web

Giao diện web sử dụng luồng job bất đồng bộ:

1. `POST /api/v1/jobs` upload file và trả về `job_id`.
2. Trình duyệt gọi `GET /api/v1/jobs/{job_id}` mỗi 800 ms để cập nhật tiến độ và log.
3. Khi `status=completed`, PDF được tải từ `GET /api/v1/jobs/{job_id}/download`.
4. Thư mục tạm và job được xóa sau khi phản hồi download hoàn tất. Job hoàn tất nhưng chưa tải sẽ tự hết hạn sau khoảng một giờ.

Các trạng thái gồm `queued`, `processing`, `completed` và `failed`. Log bao gồm quá trình upload phía trình duyệt, kiểm tra Calibre và từng dòng output của `ebook-convert`.

### GitHub Codespaces

Chạy server bằng địa chỉ `0.0.0.0` để port forwarding hoạt động:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Mở tab **Ports**, đặt port `8000` thành `Private` hoặc `Public` theo nhu cầu rồi chọn **Open in Browser**. Static assets dùng đường dẫn cùng origin `/static/...`, vì vậy không còn trỏ nhầm tới `localhost:8000` khi mở qua domain `app.github.dev`.

## Gọi API đồng bộ

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
- Chạy một Uvicorn worker khi dùng job store trong bộ nhớ hiện tại; Dockerfile đã cấu hình `--workers 1`.
- Giới hạn concurrency vì chuyển đổi ebook tốn CPU/RAM.
- Đẩy job sang hàng đợi như Celery/RQ nếu cần xử lý nhiều file đồng thời.
- Không ghi log nội dung file hoặc đường dẫn nhạy cảm.
- Quét malware nếu cho phép người dùng không tin cậy upload file.

## Giới hạn

- Chất lượng PDF phụ thuộc cấu trúc và CSS của file MOBI nguồn.
- File có DRM không được hỗ trợ.
- Một số font hiếm có thể bị thay thế nếu máy chủ không cài font tương ứng.
