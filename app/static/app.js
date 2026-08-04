const form = document.querySelector("#convert-form");
const fileInput = document.querySelector("#file-input");
const fileLabel = document.querySelector("#file-label");
const fileHelper = document.querySelector("#file-helper");
const dropZone = document.querySelector("#drop-zone");
const selectedFile = document.querySelector("#selected-file");
const selectedFileName = document.querySelector("#selected-file-name");
const selectedFileSize = document.querySelector("#selected-file-size");
const removeFileButton = document.querySelector("#remove-file");
const submitButton = document.querySelector("#submit-button");
const formMessage = document.querySelector("#form-message");
const serviceStatus = document.querySelector("#service-status");
const statusBadge = document.querySelector("#job-status-badge");
const progressStage = document.querySelector("#progress-stage");
const progressPercent = document.querySelector("#progress-percent");
const progressBar = document.querySelector("#progress-bar");
const elapsedTime = document.querySelector("#elapsed-time");
const logOutput = document.querySelector("#log-output");
const clearLogButton = document.querySelector("#clear-log");
const copyLogButton = document.querySelector("#copy-log");
const resultCard = document.querySelector("#result-card");
const resultFilename = document.querySelector("#result-filename");
const downloadButton = document.querySelector("#download-button");
const steps = [...document.querySelectorAll(".step")];

let activeJobId = null;
let latestLogId = 0;
let pollingTimer = null;
let elapsedTimer = null;
let startedAt = null;
let lastKnownLogs = [];

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / (1024 ** index);
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function localTime(isoTimestamp) {
  if (!isoTimestamp) return new Date().toLocaleTimeString("vi-VN", { hour12: false });
  return new Date(isoTimestamp).toLocaleTimeString("vi-VN", { hour12: false });
}

function appendLog(message, level = "info", timestamp = null) {
  const emptyLine = logOutput.querySelector(".muted");
  if (emptyLine) emptyLine.remove();

  const row = document.createElement("div");
  row.className = `log-line ${level}`;
  const time = document.createElement("time");
  time.textContent = localTime(timestamp);
  const content = document.createElement("span");
  content.textContent = message;
  row.append(time, content);
  logOutput.appendChild(row);
  logOutput.scrollTop = logOutput.scrollHeight;
}

function clearLogView(message = "Log đã được xóa trên giao diện.") {
  logOutput.replaceChildren();
  appendLog(message, "muted");
}

function setStatusBadge(status) {
  const labels = {
    idle: "Chưa chạy",
    uploading: "Đang upload",
    queued: "Đang chờ",
    processing: "Đang xử lý",
    completed: "Hoàn tất",
    failed: "Thất bại",
  };
  statusBadge.className = `job-badge ${status}`;
  statusBadge.textContent = labels[status] || status;
}

function updateProgress(value, stage, status = null) {
  const progress = Math.max(0, Math.min(100, Math.round(value)));
  progressBar.style.width = `${progress}%`;
  progressPercent.textContent = `${progress}%`;
  if (stage) progressStage.textContent = stage;
  if (status) setStatusBadge(status);

  steps.forEach((step, index) => {
    const thresholds = [5, 28, 40, 100];
    step.classList.toggle("active", progress >= thresholds[index] && progress < thresholds[index + 1]);
    step.classList.toggle("done", progress > thresholds[index + 1] || progress === 100);
  });
}

function startElapsedTimer() {
  startedAt = Date.now();
  clearInterval(elapsedTimer);
  elapsedTimer = setInterval(() => {
    const totalSeconds = Math.floor((Date.now() - startedAt) / 1000);
    const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
    const seconds = String(totalSeconds % 60).padStart(2, "0");
    elapsedTime.textContent = `${minutes}:${seconds}`;
  }, 1000);
}

function stopElapsedTimer() {
  clearInterval(elapsedTimer);
  elapsedTimer = null;
}

function resetMonitor() {
  clearTimeout(pollingTimer);
  stopElapsedTimer();
  activeJobId = null;
  latestLogId = 0;
  lastKnownLogs = [];
  elapsedTime.textContent = "00:00";
  resultCard.hidden = true;
  downloadButton.removeAttribute("href");
  updateProgress(0, "Sẵn sàng nhận file", "idle");
  clearLogView("Chọn một file MOBI để bắt đầu.");
}

function setSelectedFile(file) {
  if (!file) {
    fileLabel.textContent = "Thả file MOBI vào đây";
    fileHelper.textContent = "hoặc bấm để chọn file";
    selectedFile.hidden = true;
    dropZone.classList.remove("has-file");
    return;
  }

  fileLabel.textContent = "File đã sẵn sàng";
  fileHelper.textContent = "Bấm để chọn file khác";
  selectedFileName.textContent = file.name;
  selectedFileSize.textContent = formatBytes(file.size);
  selectedFile.hidden = false;
  dropZone.classList.add("has-file");
}

function validateFile(file) {
  if (!file) return "Vui lòng chọn một file MOBI.";
  if (!file.name.toLowerCase().endsWith(".mobi")) return "Chỉ hỗ trợ file có đuôi .mobi.";
  return null;
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  formMessage.textContent = "";
  setSelectedFile(file);
});

removeFileButton.addEventListener("click", () => {
  fileInput.value = "";
  setSelectedFile(null);
});

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
  if (!event.dataTransfer.files.length) return;
  const transfer = new DataTransfer();
  transfer.items.add(event.dataTransfer.files[0]);
  fileInput.files = transfer.files;
  fileInput.dispatchEvent(new Event("change"));
});

async function checkHealth() {
  serviceStatus.className = "service-pill checking";
  try {
    const response = await fetch("/health", { cache: "no-store" });
    const data = await response.json();
    if (data.calibre_available) {
      serviceStatus.className = "service-pill ok";
      serviceStatus.querySelector("span:last-child").textContent = "Calibre sẵn sàng";
    } else {
      serviceStatus.className = "service-pill error";
      serviceStatus.querySelector("span:last-child").textContent = "Chưa có Calibre";
    }
  } catch {
    serviceStatus.className = "service-pill error";
    serviceStatus.querySelector("span:last-child").textContent = "Không kết nối được server";
  }
}

function renderJobLogs(logs) {
  lastKnownLogs = logs;
  for (const entry of logs) {
    if (entry.id <= latestLogId) continue;
    appendLog(entry.message, entry.level, entry.timestamp);
    latestLogId = entry.id;
  }
}

async function pollJob(jobId) {
  try {
    const response = await fetch(`/api/v1/jobs/${jobId}`, { cache: "no-store" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Không đọc được trạng thái job.");
    }

    const job = await response.json();
    renderJobLogs(job.logs || []);
    updateProgress(job.progress, job.stage, job.status);

    if (job.status === "completed") {
      stopElapsedTimer();
      submitButton.disabled = false;
      resultFilename.textContent = job.output_name;
      downloadButton.href = job.download_url;
      resultCard.hidden = false;
      appendLog("Nhấn “Tải PDF” để nhận file kết quả.", "success");
      return;
    }

    if (job.status === "failed") {
      stopElapsedTimer();
      submitButton.disabled = false;
      formMessage.textContent = job.error || "Chuyển đổi thất bại.";
      return;
    }

    pollingTimer = setTimeout(() => pollJob(jobId), 800);
  } catch (error) {
    stopElapsedTimer();
    submitButton.disabled = false;
    setStatusBadge("failed");
    formMessage.textContent = error.message;
    appendLog(error.message, "error");
  }
}

function uploadAndCreateJob(data) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.responseType = "json";

    let lastUploadBucket = -1;
    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.round((event.loaded / event.total) * 100);
      const mappedProgress = Math.max(3, Math.min(24, Math.round(percent * 0.24)));
      updateProgress(mappedProgress, `Đang tải file lên máy chủ · ${percent}%`, "uploading");
      const bucket = Math.floor(percent / 25);
      if (bucket > lastUploadBucket) {
        appendLog(`Upload: ${percent}% (${formatBytes(event.loaded)} / ${formatBytes(event.total)}).`);
        lastUploadBucket = bucket;
      }
    });

    xhr.addEventListener("load", () => {
      const body = xhr.response || {};
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(body.detail || `Upload thất bại (${xhr.status}).`));
        return;
      }
      resolve(body);
    });

    xhr.addEventListener("error", () => reject(new Error("Mất kết nối khi upload file.")));
    xhr.addEventListener("abort", () => reject(new Error("Upload đã bị hủy.")));
    xhr.send(data);
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  const validationError = validateFile(file);
  formMessage.textContent = validationError || "";
  if (validationError) return;

  clearTimeout(pollingTimer);
  latestLogId = 0;
  lastKnownLogs = [];
  logOutput.replaceChildren();
  resultCard.hidden = true;
  submitButton.disabled = true;
  startElapsedTimer();
  updateProgress(2, "Đang chuẩn bị upload", "uploading");
  appendLog(`Đã chọn file ${file.name} (${formatBytes(file.size)}).`, "success");

  const data = new FormData(form);
  data.set("add_page_numbers", form.elements.add_page_numbers.checked ? "true" : "false");
  data.set("add_toc", form.elements.add_toc.checked ? "true" : "false");

  try {
    const response = await uploadAndCreateJob(data);
    activeJobId = response.job_id;
    updateProgress(25, "Đã upload · đang tạo job", "queued");
    appendLog(`Job ${activeJobId.slice(0, 8)} đã được tạo.`);
    pollJob(activeJobId);
  } catch (error) {
    stopElapsedTimer();
    submitButton.disabled = false;
    updateProgress(0, "Không thể bắt đầu chuyển đổi", "failed");
    formMessage.textContent = error.message;
    appendLog(error.message, "error");
  }
});

clearLogButton.addEventListener("click", () => {
  logOutput.replaceChildren();
  appendLog("Log trên giao diện đã được xóa. Job vẫn tiếp tục chạy.", "muted");
});

copyLogButton.addEventListener("click", async () => {
  const text = [...logOutput.querySelectorAll(".log-line")]
    .map((line) => `${line.querySelector("time")?.textContent || ""} ${line.querySelector("span")?.textContent || ""}`)
    .join("\n");
  try {
    await navigator.clipboard.writeText(text);
    copyLogButton.textContent = "Đã chép";
    setTimeout(() => { copyLogButton.textContent = "Sao chép"; }, 1400);
  } catch {
    appendLog("Trình duyệt không cho phép sao chép log tự động.", "warning");
  }
});

downloadButton.addEventListener("click", () => {
  appendLog("Đang tải file PDF về máy. File tạm sẽ được xóa sau phản hồi.", "success");
});

checkHealth();
resetMonitor();
