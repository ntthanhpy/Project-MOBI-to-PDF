const form = document.querySelector("#convert-form");
const fileInput = document.querySelector("#file-input");
const fileLabel = document.querySelector("#file-label");
const dropZone = document.querySelector("#drop-zone");
const submitButton = document.querySelector("#submit-button");
const progress = document.querySelector("#progress");
const message = document.querySelector("#message");
const serviceStatus = document.querySelector("#service-status");

function showFilename() {
  fileLabel.textContent = fileInput.files.length
    ? fileInput.files[0].name
    : "Kéo thả file MOBI vào đây";
}

fileInput.addEventListener("change", showFilename);

for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
}

dropZone.addEventListener("drop", (event) => {
  if (event.dataTransfer.files.length) {
    fileInput.files = event.dataTransfer.files;
    showFilename();
  }
});

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const data = await response.json();
    if (data.calibre_available) {
      serviceStatus.textContent = "Dịch vụ chuyển đổi đã sẵn sàng.";
      serviceStatus.classList.add("ok");
    } else {
      serviceStatus.textContent = "Chưa tìm thấy Calibre ebook-convert trên máy chủ.";
      serviceStatus.classList.add("error");
    }
  } catch {
    serviceStatus.textContent = "Không thể kiểm tra trạng thái dịch vụ.";
    serviceStatus.classList.add("error");
  }
}

function filenameFromDisposition(header, fallback) {
  const utf8Match = header?.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) return decodeURIComponent(utf8Match[1]);
  const basicMatch = header?.match(/filename="?([^";]+)"?/i);
  return basicMatch ? basicMatch[1] : fallback;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";

  if (!fileInput.files.length) {
    message.textContent = "Vui lòng chọn một file MOBI.";
    return;
  }

  const data = new FormData(form);
  if (!form.elements.add_page_numbers.checked) data.set("add_page_numbers", "false");
  if (!form.elements.add_toc.checked) data.set("add_toc", "false");

  submitButton.disabled = true;
  progress.hidden = false;

  try {
    const response = await fetch(form.action, { method: "POST", body: data });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Chuyển đổi thất bại (${response.status}).`);
    }

    const blob = await response.blob();
    const fallback = fileInput.files[0].name.replace(/\.mobi$/i, ".pdf");
    const filename = filenameFromDisposition(response.headers.get("content-disposition"), fallback);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    message.style.color = "#17643a";
    message.textContent = "Chuyển đổi thành công.";
  } catch (error) {
    message.style.color = "#a12424";
    message.textContent = error.message;
  } finally {
    submitButton.disabled = false;
    progress.hidden = true;
  }
});

checkHealth();
