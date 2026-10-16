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
const categoryTempoSelect = document.getElementById("category-tempo-select");
const categoryTagsToggle = document.getElementById("category-tags-toggle");
const categorySubmitBtn = document.getElementById("category-submit-btn");
const ctaForm = document.getElementById("cta-form");
const ctaKeywordInput = document.getElementById("cta-keyword-input");
const ctaLanguageSelect = document.getElementById("cta-language-select");
const ctaTempoSelect = document.getElementById("cta-tempo-select");
const ctaTagsToggle = document.getElementById("cta-tags-toggle");
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
const settingsTabTheme = document.getElementById("settings-tab-theme");
const settingsPanelKeys = document.getElementById("settings-panel-keys");
const settingsPanelTags = document.getElementById("settings-panel-tags");
const settingsPanelCtaTags = document.getElementById("settings-panel-cta-tags");
const settingsPanelTheme = document.getElementById("settings-panel-theme");
const themeOptions = document.querySelectorAll(".theme-option");
const apiKeysList = document.getElementById("api-keys-list");
const addApiKeyBtn = document.getElementById("add-api-key-btn");
const openSavedBtn = document.getElementById("open-saved-btn");
const savedCountBadge = document.getElementById("saved-count-badge");
const savedDialog = document.getElementById("saved-dialog");
const savedCloseBtn = document.getElementById("saved-close-btn");
const savedListEl = document.getElementById("saved-list");
const savedEmptyEl = document.getElementById("saved-empty");
const savePromptBtn = document.getElementById("save-prompt-btn");
const savePromptStar = document.getElementById("save-prompt-star");
const savePromptLabel = document.getElementById("save-prompt-label");

settingsBtn.addEventListener("click", () => {
  if (savedDialog.open) savedDialog.close();
  settingsDialog.showModal();
});
settingsCloseBtn.addEventListener("click", () => settingsDialog.close());
// No backdrop-click-to-close: a drag-select in the textarea that ends
// outside it can report the dialog itself as the click target, closing the
// dialog by accident. The close button and the native Escape handling
// (built into showModal()) are the only ways to close it.

function setSettingsTab(tab) {
  settingsTabTags.classList.toggle("active", tab === "tags");
  settingsTabCtaTags.classList.toggle("active", tab === "cta-tags");
  settingsTabKeys.classList.toggle("active", tab === "keys");
  settingsTabTheme.classList.toggle("active", tab === "theme");
  settingsPanelTags.hidden = tab !== "tags";
  settingsPanelCtaTags.hidden = tab !== "cta-tags";
  settingsPanelKeys.hidden = tab !== "keys";
  settingsPanelTheme.hidden = tab !== "theme";
}
settingsTabTags.addEventListener("click", () => setSettingsTab("tags"));
settingsTabCtaTags.addEventListener("click", () => setSettingsTab("cta-tags"));
settingsTabKeys.addEventListener("click", () => setSettingsTab("keys"));
settingsTabTheme.addEventListener("click", () => setSettingsTab("theme"));

// "system" (the default) stores nothing and removes data-theme entirely, so
// style.css's @media (prefers-color-scheme) decides -- see the inline
// script in index.html's <head>, which applies a saved light/dark choice
// before first paint to avoid a flash of the wrong theme.
const THEME_STORAGE_KEY = "sunoTheme";

function loadTheme() {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // localStorage unavailable -- fall through to "system".
  }
  return "system";
}

function applyTheme(theme) {
  if (theme === "light" || theme === "dark") {
    document.documentElement.setAttribute("data-theme", theme);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  themeOptions.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.themeValue === theme);
  });
}

function saveTheme(theme) {
  try {
    if (theme === "system") {
      localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    }
  } catch {
    // Ignore -- worst case the choice just doesn't persist across reloads.
  }
}

applyTheme(loadTheme());
themeOptions.forEach((btn) => {
  btn.addEventListener("click", () => {
    const theme = btn.dataset.themeValue;
    applyTheme(theme);
    saveTheme(theme);
  });
});

// Saved prompts live only in this browser's localStorage, same as the API
// keys/fixed tags above -- no server-side storage at all. Each entry
// bundles the exact variation object already used by tabState (analysis,
// suno_prompt, title, lyrics_structure, bpm) plus display metadata, so
// "불러오기" can drop it straight into tabState[mode].variationBatch and
// reuse the normal render path (showTabResult).
const SAVED_PROMPTS_STORAGE_KEY = "sunoSavedPrompts";
const MODE_LABELS = { file: "파일분석", category: "BGM", cta: "CTA" };

function loadSavedPrompts() {
  try {
    const raw = localStorage.getItem(SAVED_PROMPTS_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    }
  } catch {
    // localStorage unavailable or corrupt -- fall through to empty.
  }
  return [];
}

function persistSavedPrompts() {
  try {
    localStorage.setItem(SAVED_PROMPTS_STORAGE_KEY, JSON.stringify(savedPrompts));
  } catch {
    // Ignore -- worst case the list just doesn't persist across reloads.
  }
}

let savedPrompts = loadSavedPrompts();

function makeSavedId() {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function findSavedEntryForCurrent(mode, item) {
  if (!item) return null;
  const serialized = JSON.stringify(item);
  return savedPrompts.find((e) => e.mode === mode && JSON.stringify(e.item) === serialized) || null;
}

function summarizeSavedEntry(entry) {
  const analysis = entry.item.analysis || {};
  const bits = [];
  if (analysis.genre) bits.push(analysis.sub_genre ? `${analysis.genre} · ${analysis.sub_genre}` : analysis.genre);
  if (entry.keyword) bits.push(entry.keyword);
  if (entry.item.bpm) bits.push(`${entry.item.bpm} bpm`);
  return bits.join(" · ") || "-";
}

function updateSavedBadge() {
  const count = savedPrompts.length;
  savedCountBadge.hidden = count === 0;
  savedCountBadge.textContent = count > 99 ? "99+" : String(count);
}

function renderSavedList() {
  savedListEl.innerHTML = "";
  const sorted = [...savedPrompts].sort((a, b) => b.savedAt - a.savedAt);
  savedListEl.hidden = sorted.length === 0;
  savedEmptyEl.hidden = sorted.length > 0;

  for (const entry of sorted) {
    const row = document.createElement("div");
    row.className = "saved-item";

    const main = document.createElement("div");
    main.className = "saved-item-main";

    const top = document.createElement("div");
    top.className = "saved-item-top";
    const badge = document.createElement("span");
    badge.className = `mode-badge ${entry.mode}`;
    badge.textContent = MODE_LABELS[entry.mode] || entry.mode;
    const title = document.createElement("span");
    title.className = "saved-title";
    title.textContent = entry.item.title || "(제목 없음)";
    top.append(badge, title);

    const sub = document.createElement("div");
    sub.className = "saved-sub";
    sub.textContent = summarizeSavedEntry(entry);

    const date = document.createElement("div");
    date.className = "saved-date";
    date.textContent = `${new Date(entry.savedAt).toLocaleString("ko-KR", {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    })} 저장`;

    main.append(top, sub, date);

    const actions = document.createElement("div");
    actions.className = "saved-actions";
    const loadBtn = document.createElement("button");
    loadBtn.type = "button";
    loadBtn.className = "icon-sm-btn load-btn";
    loadBtn.title = "불러오기";
    loadBtn.textContent = "↩";
    loadBtn.addEventListener("click", () => loadSavedEntry(entry.id));
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "icon-sm-btn delete-saved-btn";
    delBtn.title = "삭제";
    delBtn.textContent = "🗑";
    delBtn.addEventListener("click", () => deleteSavedEntry(entry.id));
    actions.append(loadBtn, delBtn);

    row.append(main, actions);
    savedListEl.appendChild(row);
  }

  updateSavedBadge();
}

function updateSaveButtonState() {
  const state = tabState[activeTab];
  const item = state.variationBatch[state.variationIndex];
  if (!item) {
    savePromptBtn.disabled = true;
    savePromptBtn.classList.remove("saved");
    savePromptStar.textContent = "☆";
    savePromptLabel.textContent = "저장";
    return;
  }
  savePromptBtn.disabled = false;
  const already = !!findSavedEntryForCurrent(activeTab, item);
  savePromptBtn.classList.toggle("saved", already);
  savePromptStar.textContent = already ? "★" : "☆";
  savePromptLabel.textContent = already ? "저장됨" : "저장";
}

function currentKeywordFor(mode) {
  if (mode === "category") return categoryInput.value.trim();
  if (mode === "cta") return ctaKeywordInput.value.trim();
  return "";
}

function toggleSaveCurrent() {
  const state = tabState[activeTab];
  const item = state.variationBatch[state.variationIndex];
  if (!item) return;

  const existing = findSavedEntryForCurrent(activeTab, item);
  if (existing) {
    savedPrompts = savedPrompts.filter((e) => e.id !== existing.id);
  } else {
    savedPrompts.push({
      id: makeSavedId(),
      mode: activeTab,
      savedAt: Date.now(),
      keyword: currentKeywordFor(activeTab),
      localFeatures: activeTab === "file" ? state.localFeatures : null,
      item,
    });
  }
  persistSavedPrompts();
  renderSavedList();
  updateSaveButtonState();
}

function loadSavedEntry(id) {
  const entry = savedPrompts.find((e) => e.id === id);
  if (!entry) return;
  const state = tabState[entry.mode];
  state.variationBatch = [entry.item];
  state.variationIndex = 0;
  if (entry.mode === "file" && entry.localFeatures) {
    state.localFeatures = entry.localFeatures;
  }
  setActiveTab(entry.mode);
  savedDialog.close();
}

function deleteSavedEntry(id) {
  savedPrompts = savedPrompts.filter((e) => e.id !== id);
  persistSavedPrompts();
  renderSavedList();
  updateSaveButtonState();
}

savePromptBtn.addEventListener("click", toggleSaveCurrent);
openSavedBtn.addEventListener("click", () => {
  if (settingsDialog.open) settingsDialog.close();
  renderSavedList();
  savedDialog.showModal();
});
savedCloseBtn.addEventListener("click", () => savedDialog.close());

updateSavedBadge();

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
  "massive hook explodes in at full peak energy from the very first beat",
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

  // Order matters (earlier tags carry more weight in the final Style
  // string — see build_suno_prompt), so dragging by the handle lets the
  // user reorder without retyping. Dropping on a row always inserts the
  // dragged tag immediately before it, regardless of drag direction.
  //
  // Deliberately NOT using the native HTML5 drag-and-drop API (draggable
  // + dragstart/dragover/drop): some userscripts/extensions that "unblock"
  // page drag restrictions do so by calling stopPropagation() on dragstart
  // at the document level in the capture phase, which silently kills our
  // own dragstart listener too (the native drag ghost still shows, but our
  // reorder logic never runs). Plain mouse events sidestep that entirely.
  function reorder(fromIndex, toIndex) {
    if (fromIndex === toIndex) return;
    const [moved] = tags.splice(fromIndex, 1);
    const insertAt = fromIndex < toIndex ? toIndex - 1 : toIndex;
    tags.splice(insertAt, 0, moved);
    save();
    render();
  }

  function startDrag(sourceIndex, row, startEvent) {
    const startY = startEvent.clientY;
    // Snapshot every row's position once, before the dragged row gets a
    // CSS transform applied — getBoundingClientRect() reflects live
    // transforms, so re-measuring mid-drag would make the floating row's
    // own rect chase the cursor and corrupt the hit-test.
    const rows = Array.from(listEl.querySelectorAll(".tag-row"));
    const rects = rows.map((r) => r.getBoundingClientRect());

    // Midpoint-based hit test (not rect.top/bottom containment) so every
    // y value maps to a row with no dead zone in the gaps between them —
    // releasing the mouse in a gap used to silently drop the reorder.
    function indexAtY(y) {
      for (let i = 0; i < rects.length; i++) {
        if (y < rects[i].top + rects[i].height / 2) return i;
      }
      return rects.length - 1;
    }

    row.classList.add("dragging");

    function onMouseMove(e) {
      row.style.transform = `translateY(${e.clientY - startY}px)`;
      rows.forEach((r) => r.classList.remove("drag-over"));
      const overIndex = indexAtY(e.clientY);
      if (overIndex !== sourceIndex) rows[overIndex].classList.add("drag-over");
    }

    function onMouseUp(e) {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      const targetIndex = indexAtY(e.clientY);
      row.style.transform = "";
      rows.forEach((r) => r.classList.remove("dragging", "drag-over"));
      if (targetIndex !== sourceIndex) {
        reorder(sourceIndex, targetIndex);
      }
    }

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }

  function render() {
    listEl.innerHTML = "";
    tags.forEach((value, index) => {
      const row = document.createElement("div");
      row.className = "tag-row";

      const handle = document.createElement("span");
      handle.className = "drag-handle";
      handle.setAttribute("aria-hidden", "true");
      handle.title = "드래그하여 순서 변경";
      handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        startDrag(index, row, e);
      });
      row.appendChild(handle);

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
  // applyFixedTags mirrors the tab's own toggle switch at the time of the
  // last generate/regenerate, so regenerate() (which doesn't re-read the
  // DOM) resends the same choice on every "다시 생성".
  category: { localFeatures: EMPTY_LOCAL_FEATURES, variationBatch: [], variationIndex: 0, applyFixedTags: true, tempo: "medium" },
  cta: { localFeatures: EMPTY_LOCAL_FEATURES, variationBatch: [], variationIndex: 0, language: "ko", tempo: "medium", applyFixedTags: true },
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
    updateSaveButtonState();
    return;
  }

  titleEl.value = item.title || "";
  sunoPromptEl.value = item.suno_prompt;
  lyricsStructureEl.value = item.lyrics_structure || "";
  renderFeatures(tab, state.localFeatures, item.analysis);
  updateVariationNav(tab);
  resultEl.hidden = false;
  refreshBtn.disabled = requestInFlight;
  updateSaveButtonState();
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
            apply_fixed_tags: state.applyFixedTags,
          }),
        })
      : await fetch("/api/regenerate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            analysis: current.analysis,
            bpm: current.bpm,
            tempo: state.tempo,
            fixed_tags: getFixedTagsArray(),
            api_keys: getApiKeysForRequest(),
            apply_fixed_tags: state.applyFixedTags,
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
  const tempo = categoryTempoSelect.value;
  const applyFixedTags = categoryTagsToggle.checked;
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
      body: JSON.stringify({
        category,
        tempo,
        fixed_tags: getFixedTagsArray(),
        api_keys: getApiKeysForRequest(),
        apply_fixed_tags: applyFixedTags,
      }),
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
    tabState.category.applyFixedTags = applyFixedTags;
    tabState.category.tempo = tempo;
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
  const applyFixedTags = ctaTagsToggle.checked;
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
        apply_fixed_tags: applyFixedTags,
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
    tabState.cta.applyFixedTags = applyFixedTags;
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
