const dropzone = document.getElementById("dropzone");
const dropzoneText = document.getElementById("dropzone-text");
const fileInput = document.getElementById("file-input");
const form = document.getElementById("upload-form");
const submitBtn = document.getElementById("submit-btn");
const tabFile = document.getElementById("tab-file");
const tabCategory = document.getElementById("tab-category");
const tabCta = document.getElementById("tab-cta");
const categoryForm = document.getElementById("category-form");
const categoryInput = document.getElementById("category-input");
const categorySubmitBtn = document.getElementById("category-submit-btn");
const ctaForm = document.getElementById("cta-form");
const ctaKeywordInput = document.getElementById("cta-keyword-input");
const ctaLanguageSelect = document.getElementById("cta-language-select");
const ctaTempoSelect = document.getElementById("cta-tempo-select");
const ctaSubmitBtn = document.getElementById("cta-submit-btn");
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

const fixedTagsList = document.getElementById("fixed-tags-list");
const addFixedTagBtn = document.getElementById("add-fixed-tag-btn");
const ctaFixedTagsList = document.getElementById("cta-fixed-tags-list");
const addCtaFixedTagBtn = document.getElementById("add-cta-fixed-tag-btn");
const settingsBtn = document.getElementById("settings-btn");
const settingsCloseBtn = document.getElementById("settings-close-btn");
const settingsDialog = document.getElementById("settings-dialog");
const settingsTabKeys = document.getElementById("settings-tab-keys");
const settingsTabTags = document.getElementById("settings-tab-tags");
const settingsTabCtaTags = document.getElementById("settings-tab-cta-tags");
const settingsPanelKeys = document.getElementById("settings-panel-keys");
const settingsPanelTags = document.getElementById("settings-panel-tags");
const settingsPanelCtaTags = document.getElementById("settings-panel-cta-tags");
const apiKeysList = document.getElementById("api-keys-list");
const addApiKeyBtn = document.getElementById("add-api-key-btn");

settingsBtn.addEventListener("click", () => settingsDialog.showModal());
settingsCloseBtn.addEventListener("click", () => settingsDialog.close());
// No backdrop-click-to-close: a drag-select in the textarea that ends
// outside it can report the dialog itself as the click target, closing the
// dialog by accident. The close button and the native Escape handling
// (built into showModal()) are the only ways to close it.

function setSettingsTab(tab) {
  settingsTabTags.classList.toggle("active", tab === "tags");
  settingsTabCtaTags.classList.toggle("active", tab === "cta-tags");
  settingsTabKeys.classList.toggle("active", tab === "keys");
  settingsPanelTags.hidden = tab !== "tags";
  settingsPanelCtaTags.hidden = tab !== "cta-tags";
  settingsPanelKeys.hidden = tab !== "keys";
}
settingsTabTags.addEventListener("click", () => setSettingsTab("tags"));
settingsTabCtaTags.addEventListener("click", () => setSettingsTab("cta-tags"));
settingsTabKeys.addEventListener("click", () => setSettingsTab("keys"));

// Gemini API keys live only in this browser's localStorage, exactly like
// the fixed style tags above -- no install-time prompt and no .env file
// for corporate document-security software to lock/encrypt. At least one
// key is required for analysis to work; extra keys are used as automatic
// fallbacks when one hits its free-tier quota (see analyzer.py).
const API_KEYS_STORAGE_KEY = "sunoGeminiApiKeys";

function loadApiKeys() {
  try {
    const raw = localStorage.getItem(API_KEYS_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length) return parsed;
    }
  } catch {
    // localStorage unavailable or the stored value isn't valid JSON --
    // fall through to a single empty slot.
  }
  return [""];
}

function saveApiKeys() {
  try {
    localStorage.setItem(API_KEYS_STORAGE_KEY, JSON.stringify(apiKeys));
  } catch {
    // Ignore -- worst case the keys just don't persist across reloads.
  }
}

function getApiKeysForRequest() {
  return apiKeys.map((k) => k.trim()).filter(Boolean);
}

let apiKeys = loadApiKeys();
// Tracks which rows show their key in plain text; UI-only, not persisted,
// so every key is masked again after a reload.
const revealedKeyRows = new Set();

function removeApiKey(index) {
  apiKeys.splice(index, 1);
  const shifted = new Set();
  revealedKeyRows.forEach((i) => {
    if (i < index) shifted.add(i);
    else if (i > index) shifted.add(i - 1);
  });
  revealedKeyRows.clear();
  shifted.forEach((i) => revealedKeyRows.add(i));
  saveApiKeys();
  renderApiKeys();
}

function renderApiKeys() {
  apiKeysList.innerHTML = "";
  apiKeys.forEach((value, index) => {
    const row = document.createElement("div");
    row.className = "key-row";

    const top = document.createElement("div");
    top.className = "key-row-top";

    const idWrap = document.createElement("div");
    idWrap.className = "key-row-id";
    const labelSpan = document.createElement("span");
    labelSpan.textContent = `키 ${index + 1}`;
    idWrap.appendChild(labelSpan);
    if (index === 0) {
      const badge = document.createElement("span");
      badge.className = "key-badge";
      badge.textContent = "기본";
      idWrap.appendChild(badge);
    }
    top.appendChild(idWrap);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove-key-btn";
    removeBtn.textContent = "✕";
    removeBtn.setAttribute("aria-label", `키 ${index + 1} 삭제`);
    if (apiKeys.length <= 1) {
      removeBtn.disabled = true;
      removeBtn.title = "최소 1개의 키가 필요합니다";
    } else {
      removeBtn.title = "삭제";
      removeBtn.addEventListener("click", () => removeApiKey(index));
    }
    top.appendChild(removeBtn);
    row.appendChild(top);

    const main = document.createElement("div");
    main.className = "key-row-main";

    const input = document.createElement("input");
    input.id = `api-key-input-${index}`;
    input.type = revealedKeyRows.has(index) ? "text" : "password";
    input.value = value;
    input.placeholder = "API 키를 붙여넣으세요";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.addEventListener("input", (e) => {
      apiKeys[index] = e.target.value;
      saveApiKeys();
    });
    main.appendChild(input);

    const revealBtn = document.createElement("button");
    revealBtn.type = "button";
    revealBtn.className = "reveal-key-btn";
    const isRevealed = revealedKeyRows.has(index);
    revealBtn.setAttribute("aria-label", isRevealed ? "키 가리기" : "키 표시");
    revealBtn.textContent = isRevealed ? "🙈" : "👁";
    revealBtn.addEventListener("click", () => {
      if (revealedKeyRows.has(index)) revealedKeyRows.delete(index);
      else revealedKeyRows.add(index);
      renderApiKeys();
    });
    main.appendChild(revealBtn);

    row.appendChild(main);
    apiKeysList.appendChild(row);
  });
}

addApiKeyBtn.addEventListener("click", () => {
  const index = apiKeys.length;
  apiKeys.push("");
  revealedKeyRows.add(index);
  saveApiKeys();
  renderApiKeys();
  const el = document.getElementById(`api-key-input-${index}`);
  if (el) el.focus();
});

renderApiKeys();

// First run (no key saved yet) -- open straight to the key tab instead of
// making the user find the kebab menu on their own, since there's no more
// install-time prompt for this.
if (getApiKeysForRequest().length === 0) {
  setSettingsTab("keys");
  settingsDialog.showModal();
}

const FIXED_TAGS_STORAGE_KEY = "sunoFixedStyleTags";
const DEFAULT_FIXED_TAGS = [
  "full-energy hook hits from the very first second",
  "relentless driving rhythm with unbroken momentum",
  "wall-of-sound density at uniform peak intensity throughout",
  "seamless repeating loop with identical energy at every point",
  "punchy analog-saturated mix with tight, warm low end",
];

const CTA_FIXED_TAGS_STORAGE_KEY = "sunoCtaFixedStyleTags";
// Deliberately NOT loop/no-sag tags (those are BGM-only) -- a CTA track is
// a complete song, so its fixed tags describe things any full vocal song
// benefits from instead.
const DEFAULT_CTA_FIXED_TAGS = [
  "catchy, singable chorus hook that's easy to repeat after one listen",
  "polished mix with a clear, present lead vocal",
];

// A fixed-tag list (BGM or CTA) lives only in this browser's localStorage
// (never sent to a file on disk), so a per-PC setting survives a page
// reload but isn't subject to any corporate document-security policy that
// might lock/encrypt a plain config file the way a .txt file on disk
// could be. Stored as a JSON array (one tag per settings-UI row) so tags
// never run together without a visible separator between them. Returns
// {getArray, render} backed by its own `tags` array and storage key; the
// two lists (BGM / CTA) are independent instances of this.
function createFixedTagList({ storageKey, defaultTags, listEl, addBtnEl, inputIdPrefix, legacyMigrate }) {
  function load() {
    let raw;
    try {
      raw = localStorage.getItem(storageKey);
    } catch {
      return [...defaultTags];
    }
    if (raw === null) return [...defaultTags];
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    } catch {
      if (legacyMigrate) {
        const migrated = legacyMigrate(raw);
        if (migrated.length) return migrated;
      }
    }
    return [...defaultTags];
  }

  let tags = load();

  function save() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(tags));
    } catch {
      // Ignore — worst case the setting just doesn't persist across reloads.
    }
  }

  function getArray() {
    return tags.map((tag) => tag.trim()).filter(Boolean);
  }

  function remove(index) {
    tags.splice(index, 1);
    save();
    render();
  }

  function render() {
    listEl.innerHTML = "";
    tags.forEach((value, index) => {
      const row = document.createElement("div");
      row.className = "tag-row";

      const input = document.createElement("input");
      input.id = `${inputIdPrefix}-${index}`;
      input.type = "text";
      input.value = value;
      input.placeholder = "태그 입력";
      input.autocomplete = "off";
      input.addEventListener("input", (e) => {
        tags[index] = e.target.value;
        save();
      });
      row.appendChild(input);

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "remove-tag-btn";
      removeBtn.textContent = "✕";
      removeBtn.setAttribute("aria-label", `태그 ${index + 1} 삭제`);
      removeBtn.title = "삭제";
      removeBtn.addEventListener("click", () => remove(index));
      row.appendChild(removeBtn);

      listEl.appendChild(row);
    });
  }

  addBtnEl.addEventListener("click", () => {
    const index = tags.length;
    tags.push("");
    save();
    render();
    const el = document.getElementById(`${inputIdPrefix}-${index}`);
    if (el) el.focus();
  });

  render();
  return { getArray };
}

// Old installs stored this as a single textarea blob (newline- or
// comma-separated); migrate straight into the new per-row list.
function legacyMigrateFixedTags(raw) {
  return raw
    .split("\n")
    .flatMap((line) => line.split(","))
    .map((tag) => tag.trim())
    .filter((tag) => tag && !tag.startsWith("#"));
}

const bgmFixedTags = createFixedTagList({
  storageKey: FIXED_TAGS_STORAGE_KEY,
  defaultTags: DEFAULT_FIXED_TAGS,
  listEl: fixedTagsList,
  addBtnEl: addFixedTagBtn,
  inputIdPrefix: "fixed-tag-input",
  legacyMigrate: legacyMigrateFixedTags,
});
function getFixedTagsArray() {
  return bgmFixedTags.getArray();
}

const ctaFixedTags = createFixedTagList({
  storageKey: CTA_FIXED_TAGS_STORAGE_KEY,
  defaultTags: DEFAULT_CTA_FIXED_TAGS,
  listEl: ctaFixedTagsList,
  addBtnEl: addCtaFixedTagBtn,
  inputIdPrefix: "cta-fixed-tag-input",
});
function getCtaFixedTagsArray() {
  return ctaFixedTags.getArray();
}

const EMPTY_LOCAL_FEATURES = { duration_sec: null, bpm: null, key: null, mode: null };

// Each tab keeps its own result state so switching tabs never loses what
// the other one generated; only one network request runs at a time
// (requestInFlight), but its result is always written into the tab it
// belongs to, and only redrawn on screen if that tab is still active when
// it completes.
const tabState = {
  file: { localFeatures: EMPTY_LOCAL_FEATURES, variationBatch: [], variationIndex: 0 },
  // inputStyle ("category" or "literal") comes back from the server, which
  // has Gemini decide whether the typed keyword was a product/category or a
  // literal music description; "literal" means the fixed style tags get
  // skipped (see regenerate() below, which resends it on every "다시 생성").
  category: { localFeatures: EMPTY_LOCAL_FEATURES, variationBatch: [], variationIndex: 0, inputStyle: null },
  cta: { localFeatures: EMPTY_LOCAL_FEATURES, variationBatch: [], variationIndex: 0, language: "ko", tempo: "medium", inputStyle: null },
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
  const rows = mode === "category" || mode === "cta"
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
  tabCta.classList.toggle("active", tab === "cta");
  form.hidden = tab !== "file";
  categoryForm.hidden = tab !== "category";
  ctaForm.hidden = tab !== "cta";
  // Status text is left alone: if a request from the other tab is still in
  // flight, its progress message must stay visible across tab switches.
  showTabResult(tab);
}

tabFile.addEventListener("click", () => setActiveTab("file"));
tabCategory.addEventListener("click", () => setActiveTab("category"));
tabCta.addEventListener("click", () => setActiveTab("cta"));

categoryInput.addEventListener("input", () => {
  categorySubmitBtn.disabled = requestInFlight || !categoryInput.value.trim();
});

ctaKeywordInput.addEventListener("input", () => {
  ctaSubmitBtn.disabled = requestInFlight || !ctaKeywordInput.value.trim();
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
  ctaSubmitBtn.disabled = true;
  refreshBtn.textContent = "생성 중...";
  setStatus("같은 분위기로 새로운 변형들을 만드는 중입니다...", false);

  try {
    const res = tab === "cta"
      ? await fetch("/api/regenerate-cta", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            analysis: current.analysis,
            language: state.language,
            tempo: state.tempo,
            fixed_tags: getCtaFixedTagsArray(),
            api_keys: getApiKeysForRequest(),
            input_style: state.inputStyle,
          }),
        })
      : await fetch("/api/regenerate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            analysis: current.analysis,
            bpm: current.bpm,
            fixed_tags: getFixedTagsArray(),
            api_keys: getApiKeysForRequest(),
            input_style: state.inputStyle,
          }),
        });
    const data = await res.json();

    if (!res.ok) {
      setStatus(data.error || "새로고침에 실패했습니다.", true);
      return;
    }

    setStatus(null);
    state.variationBatch = data.variations || [];
    state.variationIndex = 0;
    if ("input_style" in data) {
      state.inputStyle = data.input_style;
    }
    if (activeTab === tab) {
      showTabResult(tab);
    }
  } catch (err) {
    setStatus("서버와 통신할 수 없습니다.", true);
  } finally {
    requestInFlight = false;
    submitBtn.disabled = !fileInput.files[0];
    categorySubmitBtn.disabled = !categoryInput.value.trim();
    ctaSubmitBtn.disabled = !ctaKeywordInput.value.trim();
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
  ctaSubmitBtn.disabled = true;
  setStatus("분석 중입니다... (최대 30초 정도 소요될 수 있습니다)", false);

  const formData = new FormData();
  formData.append("file", file);
  getFixedTagsArray().forEach((tag) => formData.append("fixed_tags", tag));
  getApiKeysForRequest().forEach((key) => formData.append("api_keys", key));

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
    ctaSubmitBtn.disabled = !ctaKeywordInput.value.trim();
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
  ctaSubmitBtn.disabled = true;
  setStatus("카테고리에 맞는 배경음악 스타일을 만드는 중입니다...", false);

  try {
    const res = await fetch("/api/analyze-category", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category, fixed_tags: getFixedTagsArray(), api_keys: getApiKeysForRequest() }),
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
    tabState.category.inputStyle = data.input_style ?? null;
    if (activeTab === "category") {
      showTabResult("category");
    }
  } catch (err) {
    setStatus("서버와 통신할 수 없습니다.", true);
  } finally {
    requestInFlight = false;
    submitBtn.disabled = !fileInput.files[0];
    categorySubmitBtn.disabled = !categoryInput.value.trim();
    ctaSubmitBtn.disabled = !ctaKeywordInput.value.trim();
    refreshBtn.disabled = !tabState[activeTab].variationBatch.length;
  }
});

ctaForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const keyword = ctaKeywordInput.value.trim();
  const language = ctaLanguageSelect.value;
  const tempo = ctaTempoSelect.value;
  if (!keyword || requestInFlight) return;

  requestInFlight = true;
  submitBtn.disabled = true;
  categorySubmitBtn.disabled = true;
  ctaSubmitBtn.disabled = true;
  setStatus("CTA 프롬프트를 만드는 중입니다...", false);

  try {
    const res = await fetch("/api/generate-cta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keyword,
        language,
        tempo,
        fixed_tags: getCtaFixedTagsArray(),
        api_keys: getApiKeysForRequest(),
      }),
    });
    const data = await res.json();

    if (!res.ok) {
      setStatus(data.error || "생성에 실패했습니다.", true);
      return;
    }

    setStatus(null);
    tabState.cta.localFeatures = EMPTY_LOCAL_FEATURES;
    tabState.cta.variationBatch = data.variations || [];
    tabState.cta.variationIndex = 0;
    tabState.cta.language = language;
    tabState.cta.tempo = tempo;
    tabState.cta.inputStyle = data.input_style ?? null;
    if (activeTab === "cta") {
      showTabResult("cta");
    }
  } catch (err) {
    setStatus("서버와 통신할 수 없습니다.", true);
  } finally {
    requestInFlight = false;
    submitBtn.disabled = !fileInput.files[0];
    categorySubmitBtn.disabled = !categoryInput.value.trim();
    ctaSubmitBtn.disabled = !ctaKeywordInput.value.trim();
    refreshBtn.disabled = !tabState[activeTab].variationBatch.length;
  }
});

// The server has no visible window to close (see launch.vbs), so it relies
// on this page pinging it to know it's still open. As long as one tab is
// pinging, the server stays up; once every tab stops (closed, navigated
// away, PC asleep), the server's watcher thread shuts it down on its own.
setInterval(() => {
  fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
}, 3000);
