const POLL_INTERVAL_MS = 1500;

const form = document.getElementById("form");
const urlInput = document.getElementById("url");
const presetSelect = document.getElementById("preset");
const submitBtn = document.getElementById("submit");

const previewBox = document.getElementById("preview");
const thumb = document.getElementById("thumb");
const previewTitle = document.getElementById("preview-title");
const previewMeta = document.getElementById("preview-meta");

const statusBox = document.getElementById("status");
const statusText = document.getElementById("status-text");
const barFill = document.getElementById("bar-fill");
const downloadLink = document.getElementById("download");
const errorBox = document.getElementById("error");

let pollTimer = null;

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

function showError(message) {
  errorBox.textContent = message;
  show(errorBox);
}

function clearError() {
  errorBox.textContent = "";
  hide(errorBox);
}

function formatDuration(seconds) {
  if (!seconds) return "";
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function formatSize(bytes) {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(1)} MB`;
}

async function readError(response) {
  try {
    const body = await response.json();
    return body.detail || "Permintaan gagal.";
  } catch {
    return `Permintaan gagal (HTTP ${response.status}).`;
  }
}

async function loadPresets() {
  const response = await fetch("/api/presets");
  const data = await response.json();
  for (const preset of data.presets) {
    const option = document.createElement("option");
    option.value = preset.id;
    option.textContent = preset.label;
    option.selected = preset.id === data.default;
    presetSelect.append(option);
  }
}

// Metadata diambil saat user selesai menempel tautan, supaya dia bisa
// memastikan videonya benar sebelum antre.
async function loadPreview(url) {
  hide(previewBox);
  try {
    const response = await fetch("/api/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!response.ok) return;
    const info = await response.json();
    if (!info.title) return;

    previewTitle.textContent = info.title;
    previewMeta.textContent = [info.uploader, formatDuration(info.duration)]
      .filter(Boolean)
      .join(" · ");
    if (info.thumbnail) {
      thumb.src = info.thumbnail;
      show(thumb);
    } else {
      hide(thumb);
    }
    show(previewBox);
  } catch {
    // Preview bersifat opsional; kegagalan di sini tidak menghalangi download.
  }
}

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function renderProgress(job) {
  const labels = {
    queued: "Menunggu giliran di antrean...",
    downloading: `Mengunduh... ${job.progress.toFixed(0)}%`,
    done: "Selesai.",
    error: "Gagal.",
  };
  statusText.textContent = labels[job.status] || job.status;
  barFill.style.width = `${job.status === "queued" ? 3 : job.progress}%`;
}

async function pollJob(jobId) {
  let response;
  try {
    response = await fetch(`/api/jobs/${jobId}`);
  } catch {
    pollTimer = setTimeout(() => pollJob(jobId), POLL_INTERVAL_MS);
    return;
  }

  if (!response.ok) {
    stopPolling();
    submitBtn.disabled = false;
    showError(await readError(response));
    return;
  }

  const job = await response.json();
  renderProgress(job);

  if (job.status === "done") {
    stopPolling();
    submitBtn.disabled = false;
    downloadLink.href = `/api/jobs/${jobId}/file`;
    downloadLink.textContent = `Simpan file${job.filesize ? ` (${formatSize(job.filesize)})` : ""}`;
    show(downloadLink);
    if (job.title) {
      previewTitle.textContent = job.title;
      show(previewBox);
    }
    return;
  }

  if (job.status === "error") {
    stopPolling();
    submitBtn.disabled = false;
    showError(job.error || "Gagal memproses video.");
    return;
  }

  pollTimer = setTimeout(() => pollJob(jobId), POLL_INTERVAL_MS);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  stopPolling();
  clearError();
  hide(downloadLink);
  submitBtn.disabled = true;

  show(statusBox);
  statusText.textContent = "Mengirim permintaan...";
  barFill.style.width = "0%";

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlInput.value, preset: presetSelect.value }),
    });

    if (!response.ok) {
      submitBtn.disabled = false;
      hide(statusBox);
      showError(await readError(response));
      return;
    }

    const job = await response.json();
    renderProgress(job);
    pollJob(job.id);
  } catch {
    submitBtn.disabled = false;
    hide(statusBox);
    showError("Tidak bisa menghubungi server.");
  }
});

urlInput.addEventListener("change", () => {
  const url = urlInput.value.trim();
  if (url) loadPreview(url);
});

loadPresets();
