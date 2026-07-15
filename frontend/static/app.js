// InkHub Module Builder frontend — vanilla JS, no build step.
//
// Two main views:
//   * "providers"  — user picks which AI APIs to use (add + remove providers).
//   * "dashboard"  — active provider + model dropdowns, plus provider management
//                    and the entry point into the build wizard.
// The wizard/build/result flow is unchanged.

const $ = (sel) => document.querySelector(sel);

const VIEWS = [
  "loading-panel",
  "providers-panel",
  "dashboard-panel",
  "wizard-panel",
  "building-panel",
  "result-panel",
];

const state = {
  view: "loading",
  settings: null,          // /api/settings response
  providers: null,         // /api/providers response
  modelsCache: {},         // { providerName: { models: [...], warning: str|null } }
  steps: [],
  currentStep: 0,
  answers: {},
  lastResult: null,
};

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
function boot() {
  $("#btn-dashboard").addEventListener("click", () => showView("dashboard"));
  $("#error-dismiss").addEventListener("click", () => $("#error-panel").classList.add("hidden"));

  $("#btn-back").addEventListener("click", () => goToStep(state.currentStep - 1));
  $("#btn-next").addEventListener("click", onNext);

  $("#add-provider-form").addEventListener("submit", (e) => {
    e.preventDefault();
    handleAddProvider(e.currentTarget, /* fromDashboard */ false);
  });
  $("#dashboard-add-provider-form").addEventListener("submit", (e) => {
    e.preventDefault();
    handleAddProvider(e.currentTarget, /* fromDashboard */ true);
  });
  $("#providers-continue").addEventListener("click", () => showView("dashboard"));
  $("#dashboard-start-wizard").addEventListener("click", startWizard);
  $("#dashboard-target-form").addEventListener("submit", handleTargetSave);

  $("#active-provider-select").addEventListener("change", handleActiveProviderChange);
  $("#active-model-select").addEventListener("change", handleActiveModelChange);

  Promise.all([refreshSettings(), refreshProviders()])
    .then(() => {
      if (state.providers.configured || (state.providers.providers || []).length > 0) {
        // Any configured provider (even without an active model) drops the
        // user straight into the dashboard so they can pick a model.
        showView("dashboard");
      } else {
        showView("providers");
      }
    })
    .catch((err) => showError("Failed to load app: " + err.message));
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------
async function api(path, options = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await r.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; }
  catch { throw new Error(`${path} returned non-JSON: ${text.slice(0, 200)}`); }
  if (!r.ok) {
    const detail = data.error || `${r.status} ${r.statusText}`;
    throw new Error(detail);
  }
  return data;
}

// ---------------------------------------------------------------------------
// View routing
// ---------------------------------------------------------------------------
function showView(name) {
  state.view = name;
  const panelId = name.endsWith("-panel") ? name : `${name}-panel`;
  VIEWS.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.toggle("hidden", id !== panelId);
  });

  const dashBtn = $("#btn-dashboard");
  const showBtn = state.providers?.configured
    && !["dashboard-panel", "loading-panel", "providers-panel"].includes(panelId);
  dashBtn.classList.toggle("hidden", !showBtn);

  if (panelId === "providers-panel") renderProvidersView();
  if (panelId === "dashboard-panel") renderDashboardView();
  if (panelId === "wizard-panel") renderStep();
}

// ---------------------------------------------------------------------------
// Data loaders
// ---------------------------------------------------------------------------
async function refreshSettings() {
  state.settings = await api("/api/settings");
}

async function refreshProviders() {
  state.providers = await api("/api/providers");
}

async function loadModelsForProvider(name, { force = false } = {}) {
  if (!name) return { models: [], warning: null };
  if (!force && state.modelsCache[name]) return state.modelsCache[name];
  try {
    const data = await api(`/api/providers/${encodeURIComponent(name)}/models`);
    state.modelsCache[name] = {
      models: data.models || [],
      warning: data.warning || null,
      defaultModel: data.default_model || "",
    };
  } catch (err) {
    state.modelsCache[name] = {
      models: [],
      warning: err.message,
      defaultModel: "",
    };
  }
  return state.modelsCache[name];
}

// ---------------------------------------------------------------------------
// View 1: Providers setup
// ---------------------------------------------------------------------------
function renderProvidersView() {
  renderProvidersList($("#providers-list"), {
    configuredProviders: state.providers.providers,
    onRemove: (name) => removeProviderAndRefresh(name),
    emptyText: "No providers added yet. Add your first one below.",
  });

  populateProviderSelect(
    $("#add-provider-form select[name='provider']"),
    unconfiguredProviders(),
  );
  updateApiKeyHint(
    $("#add-provider-form"),
    $("#add-provider-key-hint"),
  );

  const canContinue = (state.providers.providers || []).length > 0;
  const btn = $("#providers-continue");
  btn.disabled = !canContinue;
  btn.classList.toggle("primary", canContinue);
  btn.classList.toggle("ghost", !canContinue);
}

// ---------------------------------------------------------------------------
// View 2: Dashboard
// ---------------------------------------------------------------------------
async function renderDashboardView() {
  // Providers list + add-form (mirrors the providers view but embedded).
  renderProvidersList($("#dashboard-providers-list"), {
    configuredProviders: state.providers.providers,
    onRemove: (name) => removeProviderAndRefresh(name),
    emptyText: "No providers configured. Add one below to get started.",
    showActiveBadge: true,
  });
  populateProviderSelect(
    $("#dashboard-add-provider-form select[name='provider']"),
    unconfiguredProviders(),
  );
  updateApiKeyHint(
    $("#dashboard-add-provider-form"),
    $("#dashboard-add-key-hint"),
  );

  // Active-provider dropdown lists only the *configured* providers.
  const activeSelect = $("#active-provider-select");
  const configured = state.providers.providers || [];
  activeSelect.innerHTML = "";
  if (configured.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "— add a provider first —";
    activeSelect.appendChild(opt);
    activeSelect.disabled = true;
  } else {
    activeSelect.disabled = false;
    configured.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.name;
      opt.textContent = p.label;
      if (p.name === state.providers.active_provider) opt.selected = true;
      activeSelect.appendChild(opt);
    });
  }

  // Target folder + panel info.
  const targetInput = $("#dashboard-target-form input[name='target_modules_dir']");
  if (targetInput) targetInput.value = state.settings.target_modules_dir || "";
  const panelInfo = $("#dashboard-panel-info");
  if (panelInfo) {
    const size = `${state.settings.panel_width}x${state.settings.panel_height}`;
    const source = panelSizeSourceLabel(state.settings.panel_size_source);
    const driver = state.settings.inkhub_panel_driver
      ? ` (driver: ${state.settings.inkhub_panel_driver})`
      : "";
    panelInfo.textContent = `Panel size: ${size} (${source})${driver}.`;
  }

  // Populate the model dropdown for whichever provider is active.
  const activeProvider = state.providers.active_provider || (configured[0] && configured[0].name);
  await populateActiveModelSelect(activeProvider);

  updateStartWizardButton();
}

async function populateActiveModelSelect(providerName) {
  const modelSelect = $("#active-model-select");
  const loading = $("#active-model-loading");
  const warning = $("#active-model-warning");
  const status = $("#active-model-status");

  modelSelect.innerHTML = "";
  warning.classList.add("hidden");
  warning.textContent = "";

  if (!providerName) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "— pick a provider first —";
    modelSelect.appendChild(opt);
    modelSelect.disabled = true;
    status.textContent = "";
    return;
  }

  modelSelect.disabled = true;
  loading.classList.remove("hidden");
  const { models, warning: warn, defaultModel } = await loadModelsForProvider(providerName);
  loading.classList.add("hidden");

  if (!models || models.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "— no models available —";
    modelSelect.appendChild(opt);
    modelSelect.disabled = true;
  } else {
    modelSelect.disabled = false;
    const activeModel = state.providers.active_provider === providerName
      ? state.providers.active_model
      : "";
    const preferred = activeModel || defaultModel || models[0];
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      if (m === preferred) opt.selected = true;
      modelSelect.appendChild(opt);
    });
    // If active_model isn't in the returned list (edge case), keep it selectable.
    if (activeModel && !models.includes(activeModel)) {
      const opt = document.createElement("option");
      opt.value = activeModel;
      opt.textContent = `${activeModel} (custom)`;
      opt.selected = true;
      modelSelect.appendChild(opt);
    }
  }

  if (warn) {
    warning.textContent = `Live model list unavailable (${warn}). Showing fallback options.`;
    warning.classList.remove("hidden");
  }

  const currentModel = modelSelect.value;
  status.textContent = currentModel
    ? `Using ${providerLabelFor(providerName)} · ${currentModel}`
    : "";
}

async function handleActiveProviderChange(e) {
  const provider = e.currentTarget.value;
  if (!provider) return;
  await populateActiveModelSelect(provider);
  const model = $("#active-model-select").value;
  await persistActive(provider, model);
}

async function handleActiveModelChange(e) {
  const model = e.currentTarget.value;
  const provider = $("#active-provider-select").value;
  if (!provider || !model) return;
  await persistActive(provider, model);
}

async function persistActive(provider, model) {
  try {
    const result = await api("/api/active", {
      method: "POST",
      body: JSON.stringify({ provider, model }),
    });
    state.providers.active_provider = result.active_provider;
    state.providers.active_model = result.active_model;
    state.providers.configured = result.configured;
    $("#active-model-status").textContent =
      `Using ${providerLabelFor(provider)} · ${model}`;
    updateStartWizardButton();
  } catch (err) {
    showError(err.message);
  }
}

async function handleTargetSave(e) {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.currentTarget).entries());
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
    await refreshSettings();
    renderDashboardView();
  } catch (err) {
    showError(err.message);
  }
}

function updateStartWizardButton() {
  const btn = $("#dashboard-start-wizard");
  btn.disabled = !state.providers.configured;
}

// ---------------------------------------------------------------------------
// Shared provider helpers
// ---------------------------------------------------------------------------
function renderProvidersList(container, opts) {
  const { configuredProviders, onRemove, emptyText, showActiveBadge } = opts;
  container.innerHTML = "";
  if (!configuredProviders || configuredProviders.length === 0) {
    const p = document.createElement("p");
    p.className = "help";
    p.textContent = emptyText || "No providers configured yet.";
    container.appendChild(p);
    return;
  }
  configuredProviders.forEach((provider) => {
    const item = document.createElement("div");
    item.className = "provider-item";

    const left = document.createElement("div");
    left.className = "provider-info";
    const title = document.createElement("div");
    title.className = "provider-name";
    title.textContent = provider.label;
    if (showActiveBadge && state.providers.active_provider === provider.name) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "active";
      title.appendChild(badge);
    }
    const sub = document.createElement("div");
    sub.className = "provider-sub";
    if (provider.requires_api_key) {
      sub.textContent = provider.api_key_preview
        ? `Key: ${provider.api_key_preview}`
        : "No API key stored";
    } else {
      sub.textContent = provider.api_key_preview
        ? `Key: ${provider.api_key_preview}`
        : "Using public (no key required)";
    }
    left.append(title, sub);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "ghost";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => {
      if (!confirm(`Remove ${provider.label}?`)) return;
      onRemove(provider.name);
    });

    item.append(left, removeBtn);
    container.appendChild(item);
  });
}

function populateProviderSelect(selectEl, providers) {
  if (!selectEl) return;
  const currentValue = selectEl.value;
  selectEl.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = providers.length === 0
    ? "— all providers added —"
    : "— select one —";
  selectEl.appendChild(placeholder);
  providers.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = p.label;
    selectEl.appendChild(opt);
  });
  selectEl.disabled = providers.length === 0;
  if (currentValue && providers.some((p) => p.name === currentValue)) {
    selectEl.value = currentValue;
  }
  // Re-fire change to keep the api-key hint in sync.
  selectEl.dispatchEvent(new Event("change"));
}

function unconfiguredProviders() {
  const supported = state.providers.supported_providers || [];
  return supported.filter((p) => !p.configured);
}

function updateApiKeyHint(formEl, hintEl) {
  if (!formEl || !hintEl) return;
  const providerSelect = formEl.querySelector("select[name='provider']");
  const apiKeyInput = formEl.querySelector("input[name='api_key']");
  if (!providerSelect || !apiKeyInput) return;

  const apply = () => {
    const providerName = providerSelect.value;
    const providerMeta = (state.providers.supported_providers || [])
      .find((p) => p.name === providerName);
    if (!providerName || !providerMeta) {
      apiKeyInput.required = false;
      apiKeyInput.placeholder = "paste the key from your provider dashboard";
      hintEl.textContent = "(optional for OpenCode)";
      return;
    }
    apiKeyInput.required = providerMeta.requires_api_key;
    apiKeyInput.placeholder = providerMeta.requires_api_key
      ? "paste the key from your provider dashboard"
      : "optional — leave blank for public access";
    hintEl.textContent = providerMeta.requires_api_key
      ? "(required)"
      : "(optional)";
  };
  providerSelect.onchange = apply;
  apply();
}

async function handleAddProvider(formEl, fromDashboard) {
  const body = Object.fromEntries(new FormData(formEl).entries());
  const provider = String(body.provider || "").trim().toLowerCase();
  if (!provider) {
    showError("Pick a provider first.");
    return;
  }
  const apiKey = String(body.api_key || "").trim();
  try {
    await api("/api/providers", {
      method: "POST",
      body: JSON.stringify({ provider, api_key: apiKey }),
    });
    // Drop cached models — the key may have changed.
    delete state.modelsCache[provider];
    formEl.reset();
    await refreshProviders();
    if (fromDashboard) {
      renderDashboardView();
    } else {
      renderProvidersView();
    }
  } catch (err) {
    showError(err.message);
  }
}

async function removeProviderAndRefresh(name) {
  try {
    await api(`/api/providers/${encodeURIComponent(name)}`, { method: "DELETE" });
    delete state.modelsCache[name];
    await refreshProviders();
    if (state.view === "dashboard") renderDashboardView();
    else renderProvidersView();
  } catch (err) {
    showError(err.message);
  }
}

// ---------------------------------------------------------------------------
// Wizard
// ---------------------------------------------------------------------------
async function startWizard() {
  if (!state.steps.length) {
    try {
      const { steps } = await api("/api/wizard/steps");
      state.steps = steps;
    } catch (err) {
      showError("Failed to load wizard: " + err.message);
      return;
    }
  }
  state.currentStep = 0;
  state.answers = {};
  showView("wizard");
}

function renderStep() {
  const step = state.steps[state.currentStep];
  if (!step) return;
  const isLast = state.currentStep === state.steps.length - 1;
  $("#wizard-progress").textContent =
    `Step ${state.currentStep + 1} of ${state.steps.length}`;
  $("#btn-back").disabled = state.currentStep === 0;
  $("#btn-next").textContent = isLast ? "✨ Build my module" : "Next →";

  const container = $("#wizard-steps");
  container.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "stack";

  const title = document.createElement("h2");
  title.textContent = step.title;
  wrap.appendChild(title);

  const help = document.createElement("p");
  help.className = "help";
  help.textContent = step.help;
  wrap.appendChild(help);

  const existing = state.answers[step.id] ?? "";

  if (step.type === "text") {
    const input = document.createElement("input");
    input.type = "text";
    input.name = step.id;
    input.maxLength = step.max_length ?? 200;
    input.value = existing;
    input.dataset.role = "wizard-input";
    wrap.appendChild(input);
  } else if (step.type === "textarea") {
    const ta = document.createElement("textarea");
    ta.name = step.id;
    ta.maxLength = step.max_length ?? 2000;
    ta.value = existing;
    ta.dataset.role = "wizard-input";
    wrap.appendChild(ta);
  } else if (step.type === "choice") {
    const list = document.createElement("div");
    list.className = "choice-list";
    step.choices.forEach((choice) => {
      const label = document.createElement("label");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = step.id;
      radio.value = choice.value;
      radio.dataset.role = "wizard-input";
      if (existing === choice.value) {
        radio.checked = true;
        label.classList.add("checked");
      }
      radio.addEventListener("change", () => {
        list.querySelectorAll("label").forEach((el) => el.classList.remove("checked"));
        label.classList.add("checked");
      });
      const span = document.createElement("span");
      span.textContent = choice.label;
      label.append(radio, span);
      list.appendChild(label);
    });
    wrap.appendChild(list);
  }

  container.appendChild(wrap);

  setTimeout(() => {
    const el = container.querySelector('input[type="text"], textarea');
    if (el) el.focus();
  }, 30);
}

function collectStepAnswer() {
  const step = state.steps[state.currentStep];
  if (step.type === "choice") {
    const picked = document.querySelector(`input[name="${step.id}"]:checked`);
    return picked ? picked.value : "";
  }
  const el = document.querySelector(`[name="${step.id}"]`);
  return el ? el.value.trim() : "";
}

function onNext() {
  const step = state.steps[state.currentStep];
  const value = collectStepAnswer();
  if (step.required && !value) {
    alert(`Please answer: ${step.title}`);
    return;
  }
  state.answers[step.id] = value;

  if (state.currentStep < state.steps.length - 1) {
    state.currentStep += 1;
    renderStep();
  } else {
    startBuild();
  }
}

function goToStep(index) {
  if (index < 0 || index >= state.steps.length) return;
  state.answers[state.steps[state.currentStep].id] = collectStepAnswer();
  state.currentStep = index;
  renderStep();
}

// ---------------------------------------------------------------------------
// Build flow
// ---------------------------------------------------------------------------
async function startBuild() {
  showView("building");
  $("#error-panel").classList.add("hidden");
  $("#building-status").textContent = "Contacting the AI — this may take 20–60 seconds…";
  $("#building-log").innerHTML = "";
  appendLog("#building-log", "Sending your answers to the AI…");

  try {
    const result = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({ answers: state.answers }),
    });
    state.lastResult = result;
    (result.attempts || []).forEach((a) => {
      appendLog("#building-log",
        a.error ? `Attempt ${a.attempt}: ${a.error.split("\n")[0]}` : `Attempt ${a.attempt}: OK`,
        a.error ? "err" : "ok");
    });
    showResult(result);
  } catch (err) {
    showView("wizard");
    showError(err.message);
  }
}

function showResult(result) {
  const title = $("#result-title");
  const preview = $("#result-preview");
  const actions = $("#result-actions");
  const log = $("#result-log");
  preview.innerHTML = "";
  actions.innerHTML = "";
  log.innerHTML = "";

  (result.attempts || []).forEach((a) => {
    const cls = a.error ? "err" : "ok";
    const li = document.createElement("li");
    li.className = cls;
    li.textContent = `Attempt ${a.attempt}: ${a.error ? a.error.split("\n")[0] : "OK"}`;
    log.appendChild(li);
  });

  if (!result.ok) {
    title.textContent = "The AI could not produce a working module";
    const errBox = document.createElement("pre");
    errBox.textContent = result.error || "Unknown error";
    preview.appendChild(errBox);

    const retry = document.createElement("button");
    retry.className = "primary";
    retry.textContent = "Try again with a different brief";
    retry.addEventListener("click", () => showView("wizard"));
    actions.appendChild(retry);
  } else {
    title.textContent = `✓ "${result.name || result.slug}" is ready`;
    if (result.preview_png_base64) {
      const img = document.createElement("img");
      img.src = `data:image/png;base64,${result.preview_png_base64}`;
      img.alt = "Rendered preview";
      preview.appendChild(img);
    }

    const install = document.createElement("button");
    install.className = "primary";
    install.textContent = "🚀 Install into inkHub";
    install.addEventListener("click", () => installIntoInkhub(result.slug));
    actions.appendChild(install);

    const again = document.createElement("button");
    again.className = "ghost";
    again.textContent = "Build another module";
    again.addEventListener("click", () => startWizard());
    actions.appendChild(again);

    const home = document.createElement("button");
    home.className = "ghost";
    home.textContent = "Back to dashboard";
    home.addEventListener("click", () => showView("dashboard"));
    actions.appendChild(home);

    const hint = document.createElement("div");
    hint.className = "path-hint";
    hint.innerHTML = `Staged folder: <code>${result.staged_folder}</code>. If you'd rather move it yourself, just drag the whole folder into <code>inkHub/src/modules/</code>.`;
    actions.appendChild(hint);
  }

  showView("result");
}

async function installIntoInkhub(slug) {
  try {
    const r = await api("/api/deliver", {
      method: "POST",
      body: JSON.stringify({ slug }),
    });
    alert(`Installed into:\n${r.destination}\n\nRestart InkHub to activate the module.`);
  } catch (err) {
    showError(err.message);
  }
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function appendLog(sel, text, cls = "") {
  const li = document.createElement("li");
  if (cls) li.className = cls;
  li.textContent = text;
  $(sel).appendChild(li);
}

function showError(message) {
  $("#error-message").textContent = message;
  $("#error-panel").classList.remove("hidden");
}

function providerLabelFor(name) {
  const supported = (state.providers?.supported_providers) || [];
  const hit = supported.find((p) => p.name === name);
  return hit ? hit.label : name;
}

function panelSizeSourceLabel(source) {
  if (source === "inkhub_panel_driver") return "read from InkHub config";
  if (source === "unknown_panel_driver_default") return "unknown panel driver, using fallback";
  return "using fallback";
}
