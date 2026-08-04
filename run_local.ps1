$ErrorActionPreference = "Stop"

$calibreCandidates = @(
    "ebook-convert",
    "C:\Program Files\Calibre2\ebook-convert.exe",
    "C:\Program Files (x86)\Calibre2\ebook-convert.exe"
)

$calibre = $null
foreach ($candidate in $calibreCandidates) {
    if ($candidate -eq "ebook-convert") {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            $calibre = $candidate
            break
        }
    } elseif (Test-Path $candidate) {
        $calibre = $candidate
        break
    }
}

if (-not $calibre) {
    throw "Không tìm thấy Calibre. Hãy cài Calibre trước khi chạy project."
}

$env:CALIBRE_COMMAND = $calibre

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
