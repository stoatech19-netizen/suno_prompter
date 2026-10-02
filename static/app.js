const dropzone = document.getElementById("dropzone");
const dropzoneText = document.getElementById("dropzone-text");
const fileInput = document.getElementById("file-input");
const form = document.getElementById("upload-form");
const submitBtn = document.getElementById("submit-btn");
const tabFile = document.getElementById("tab-file");
const tabCategory = document.getElementById("tab-category");
const categoryForm = document.getElementById("category-form");
const categoryInput = document.getElementById("category-input");
const categorySubmitBtn = document.getElementById("category-submit-btn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const featuresBody = document.getElementById("features-body");
const titleEl = document.getElementById("title-suggestion");
const sunoPromptEl = document.getElementById("suno-prompt");
const lyricsStructureEl = document.getElementById("lyrics-structure");
const refreshBtn = document.getElementById("refresh-btn");
const variationNav = document.getElementById("variation-nav");
const variationCounter = document.getElementById("variation-counter");
const prevVariationBtn = document.getElementById("prev-variation-btn");
const nextVariationBtn = document.getElementById("next-variation-btn");

const fixedTagsInput = document.getElementById("fixed-tags-input");
const settingsBtn = document.getElementById("settings-btn");
const settingsCloseBtn = document.getElementById("settings-close-btn");
const settingsDialog = document.getElementById("settings-dialog");

settingsBtn.addEventListener("click", () => settingsDialog.showModal());
settingsCloseBtn.addEventListener("click", () => settingsDialog.close());
// Clicking the backdrop (a click whose target is the <dialog> itself, not
// something inside it) should close too, matching native modal UX.
settingsDialog.addEventListener("click", (e) => {
  if (e.target === settingsDialog) settingsDialog.close();
});

const FIXED_TAGS_STORAGE_KEY = "sunoFixedStyleTags";
const DEFAULT_FIXED_TAGS = [
  "short punchy intro",
  "seamless repeating loop, no build-up or breakdown",
];

// Fixed style tags live only in this browser's localStorage (never sent to
// a file on disk), so a per-PC setting survives a page reload but isn't
// subject to any corporate document-security policy that might lock/encrypt
// a plain config file the way a .txt file on disk could be.
function loadFixedTagsText() {
  try {
    const raw = localStorage.getItem(FIXED_TAGS_STORAGE_KEY);
    if (raw !== null) return raw;
  } catch {
    // localStorage unavailable (private mode, blocked storage, etc.) — fall
    // through to defaults for this session.
  }
  return DEFAULT_FIXED_TAGS.join("\n");
}

function saveFixedTagsText(value) {
  try {
    localStorage.setItem(FIXED_TAGS_STORAGE_KEY, value);
  } catch {
    // Ignore — worst case the setting just doesn't persist across reloads.
  }
}

function getFixedTagsArray() {
  return fixedTagsInput.value
    .split("\n")
    .flatMap((line) => line.split(","))
    .map((tag) => tag.trim())
    .filter((tag) => tag && !tag.startsWith("#"));
}

fixedTagsInput.value = loadFixedTagsText();
fixedTagsInput.addEventListener("input", () => saveFixedTagsText(fixedTagsInput.value));

const EMPTY_LOCAL_FEATURES = { duration_sec: null, bpm: null, key: null, mode: null };

// Each tab keeps its own result state so switching tabs never loses what
// the other one generated; only one network request runs at a time
// (requestInFlight), but its result is always written into the tab it
// belongs to, and only redrawn on screen if that tab is still active when
// it completes.
const tabState = {
  file: { localFeatures: EMPTY_LOCAL_FEATURES, variationBatch: [], variationIndex: 0 },
  category: { localFeatures: EMPTY_LOCAL_FEATURES, variationBatch: [], variationIndex: 0 },
};
let activeTab = "file";
let requestInFlight = false;

function setStatus(message, isError) {
  if (!message) {
    statusEl.hidden = true;
    return;
  }
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.classList.toggle("error", !!isError);
}

function renderFeatures(mode, localFeatures, analysis) {
  featuresBody.innerHTML = "";
  const genreMoodRows = [
    ["장르", [analysis.genre, analysis.sub_genre].filter(Boolean).join(" / ")],
    ["무드", (analysis.mood || []).join(", ")],
    ["악기", (analysis.instruments || []).join(", ")],
    ["시대감", analysis.era_influence || "-"],
    ["에너지", analysis.energy_level || "-"],
  ];
  const rows = mode === "category"
    ? [
        ["BPM(제안)", analysis.bpm ?? "-"],
        ...genreMoodRows,
        ["보컬", analysis.vocal_style || "-"],
      ]
    : [
        ["BPM", localFeatures.bpm ?? "감지 실패"],
        ["Key", localFeatures.key ? `${localFeatures.key} ${localFeatures.mode}` : "감지 실패"],
        ["길이(초)", localFeatures.duration_sec ? `${localFeatures.duration_sec}s` : "-"],
        ...genreMoodRows,
        ["원곡 보컬", analysis.vocal_style || "-"],
      ];
  for (const [label, value] of rows) {
    const tr = document.createElement("tr");
    const th = document.createElement("td");
    th.textContent = label;
    const td = document.createElement("td");
    td.textContent = value || "-";
    tr.append(th, td);
    featuresBody.appendChild(tr);
  }
}

function updateVariationNav(tab) {
  const state = tabState[tab];
  if (state.variationBatch.length <= 1) {
    variationNav.hidden = true;
    return;
  }
  variationNav.hidden = false;
  variationCounter.textContent = `${state.variationIndex + 1} / ${state.variationBatch.length}`;
  prevVariationBtn.disabled = state.variationIndex === 0;
  nextVariationBtn.disabled = state.variationIndex === state.variationBatch.length - 1;
}

// Redraws the shared result panel from the given tab's own stored state.
// Called on tab switch and whenever that tab's batch/index changes.
function showTabResult(tab) {
  const state = tabState[tab];
  const item = state.variationBatch[state.variationIndex];

  if (!item) {
    resultEl.hidden = true;
    refreshBtn.disabled = true;
    variationNav.hidden = true;
    return;
  }

  titleEl.value = item.title || "";
  sunoPromptEl.value = item.suno_prompt;
  lyricsStructureEl.value = item.lyrics_structure || "";
  renderFeatures(tab, state.localFeatures, item.analysis);
  updateVariationNav(tab);
  resultEl.hidden = false;
  refreshBtn.disabled = requestInFlight;
}

function setActiveTab(tab) {
  activeTab = tab;
  tabFile.classList.toggle("active", tab === "file");
  tabCategory.classList.toggle("active", tab === "category");
  form.hidden = tab !== "file";
  categoryForm.hidden = tab !== "category";
  // Status text is left alone: if a request from the other tab is still in
  // flight, its progress message must stay visible across tab switches.
  showTabResult(tab);
}

tabFile.addEventListener("click", () => setActiveTab("file"));
tabCategory.addEventListener("click", () => setActiveTab("category"));

categoryInput.addEventListener("input", () => {
  categorySubmitBtn.disabled = requestInFlight || !categoryInput.value.trim();
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  dropzoneText.textContent = file ? file.name : "파일을 선택하거나 여기로 드래그하세요 (mp3, wav / 최대 20MB)";
  submitBtn.disabled = !file;
});

["dragover", "dragenter"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    fileInput.files = e.dataTransfer.files;
    fileInput.dispatchEvent(new Event("change"));
  }
});

function wireCopyButton(buttonId, textareaEl) {
  const btn = document.getElementById(buttonId);
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(textareaEl.value);
      const original = btn.textContent;
      btn.textContent = "복사됨!";
      setTimeout(() => (btn.textContent = original), 1500);
    } catch {
      textareaEl.select();
      document.execCommand("copy");
    }
  });
}

wireCopyButton("copy-title-btn", titleEl);
wireCopyButton("copy-btn", sunoPromptEl);
wireCopyButton("copy-lyrics-btn", lyricsStructureEl);

async function regenerate() {
  const tab = activeTab;
  const state = tabState[tab];
  const current = state.variationBatch[state.variationIndex];
  if (!current || requestInFlight) return;

  requestInFlight = true;
  refreshBtn.disabled = true;
  submitBtn.disabled = true;
  categorySubmitBtn.disabled = true;
  refreshBtn.textContent = "생성 중...";
  setStatus("같은 분위기로 새로운 변형들을 만드는 중입니다...", false);

  try {
    const res = await fetch("/api/regenerate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analysis: current.analysis, bpm: current.bpm, fixed_tags: getFixedTagsArray() }),
    });
    const data = await res.json();

    if (!res.ok) {
      setStatus(data.error || "새로고침에 실패했습니다.", true);
      return;
    }

    setStatus(null);
    state.variationBatch = data.variations || [];
    state.variationIndex = 0;
    if (activeTab === tab) {
      showTabResult(tab);
    }
  } catch (err) {
    setStatus("서버와 통신할 수 없습니다.", true);
  } finally {
    requestInFlight = false;
    submitBtn.disabled = !fileInput.files[0];
    categorySubmitBtn.disabled = !categoryInput.value.trim();
    refreshBtn.textContent = "확장하기";
    refreshBtn.disabled = !tabState[activeTab].variationBatch.length;
  }
}

refreshBtn.addEventListener("click", regenerate);

prevVariationBtn.addEventListener("click", () => {
  const state = tabState[activeTab];
  if (state.variationIndex <= 0) return;
  state.variationIndex -= 1;
  showTabResult(activeTab);
});

nextVariationBtn.addEventListener("click", () => {
  const state = tabState[activeTab];
  if (state.variationIndex >= state.variationBatch.length - 1) return;
  state.variationIndex += 1;
  showTabResult(activeTab);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file || requestInFlight) return;

  requestInFlight = true;
  submitBtn.disabled = true;
  categorySubmitBtn.disabled = true;
  setStatus("분석 중입니다... (최대 30초 정도 소요될 수 있습니다)", false);

  const formData = new FormData();
  formData.append("file", file);
  getFixedTagsArray().forEach((tag) => formData.append("fixed_tags", tag));

  try {
    const res = await fetch("/api/analyze", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      setStatus(data.error || "분석에 실패했습니다.", true);
      return;
    }

    setStatus(null);
    tabState.file.localFeatures = data.local_features;
    tabState.file.variationBatch = data.variations || [];
    tabState.file.variationIndex = 0;
    if (activeTab === "file") {
      showTabResult("file");
    }
  } catch (err) {
    setStatus("서버와 통신할 수 없습니다.", true);
  } finally {
    requestInFlight = false;
    submitBtn.disabled = !fileInput.files[0];
    categorySubmitBtn.disabled = !categoryInput.value.trim();
    refreshBtn.disabled = !tabState[activeTab].variationBatch.length;
  }
});

categoryForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const category = categoryInput.value.trim();
  if (!category || requestInFlight) return;

  requestInFlight = true;
  submitBtn.disabled = true;
  categorySubmitBtn.disabled = true;
  setStatus("카테고리에 맞는 배경음악 스타일을 만드는 중입니다...", false);

  try {
    const res = await fetch("/api/analyze-category", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category, fixed_tags: getFixedTagsArray() }),
    });
    const data = await res.json();

    if (!res.ok) {
      setStatus(data.error || "생성에 실패했습니다.", true);
      return;
    }

    setStatus(null);
    tabState.category.localFeatures = EMPTY_LOCAL_FEATURES;
    tabState.category.variationBatch = data.variations || [];
    tabState.category.variationIndex = 0;
    if (activeTab === "category") {
      showTabResult("category");
    }
  } catch (err) {
    setStatus("서버와 통신할 수 없습니다.", true);
  } finally {
    requestInFlight = false;
    submitBtn.disabled = !fileInput.files[0];
    categorySubmitBtn.disabled = !categoryInput.value.trim();
    refreshBtn.disabled = !tabState[activeTab].variationBatch.length;
  }
});
