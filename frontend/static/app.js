// InkHub Module Builder frontend — vanilla JS, no build step.

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  steps: [],
  currentStep: 0,
  answers: {},
  lastResult: null,
};

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  $("#btn-settings").addEventListener("click", openSettingsModal);
  $("#setup-form").addEventListener("submit", submitSetup);
  $("#btn-back").addEventListener("click", () => goToStep(state.currentStep - 1));
  $("#btn-next").addEventListener("click", onNext);
  $("#error-dismiss").addEventListener("click", () => $("#error-panel").classList.add("hidden"));

  try {
    const { steps } = await api("/api/wizard/steps");
    state.steps = steps;
  } catch (err) {
    showError("Failed to load wizard: " + err.message);
    return;
  }

  const settings = await api("/api/settings");
  if (settings.configured) {
    renderWizard();
  }
});

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
// Setup form
// ---------------------------------------------------------------------------
async function submitSetup(e) {
  e.preventDefault();
  const form = new FormData(e.currentTarget);
  const body = Object.fromEntries(form.entries());
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
    $("#setup-panel").classList.add("hidden");
    $("#wizard-panel").classList.remove("hidden");
    renderWizard();
  } catch (err) {
    showError(err.message);
  }
}

// ---------------------------------------------------------------------------
// Wizard
// ---------------------------------------------------------------------------
function renderWizard() {
  state.currentStep = 0;
  state.answers = {};
  renderStep();
}

function renderStep() {
  const step = state.steps[state.currentStep];
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

  // Autofocus for text/textarea
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
  $("#wizard-panel").classList.add("hidden");
  $("#result-panel").classList.add("hidden");
  $("#error-panel").classList.add("hidden");
  $("#building-panel").classList.remove("hidden");
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
    $("#building-panel").classList.add("hidden");
    showResult(result);
  } catch (err) {
    $("#building-panel").classList.add("hidden");
    $("#wizard-panel").classList.remove("hidden");
    showError(err.message);
  }
}

function showResult(result) {
  const panel = $("#result-panel");
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
    retry.addEventListener("click", () => {
      $("#result-panel").classList.add("hidden");
      $("#wizard-panel").classList.remove("hidden");
    });
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
    again.addEventListener("click", () => {
      $("#result-panel").classList.add("hidden");
      $("#wizard-panel").classList.remove("hidden");
      renderWizard();
    });
    actions.appendChild(again);

    const hint = document.createElement("div");
    hint.className = "path-hint";
    hint.innerHTML = `Staged folder: <code>${result.staged_folder}</code>. If you'd rather move it yourself, just drag the whole folder into <code>inkHub/src/modules/</code>.`;
    actions.appendChild(hint);
  }

  panel.classList.remove("hidden");
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

// ---------------------------------------------------------------------------
// Settings modal
// ---------------------------------------------------------------------------
async function openSettingsModal() {
  const s = await api("/api/settings");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });

  const modal = document.createElement("div");
  modal.className = "modal";
  modal.innerHTML = `
    <h2>Settings</h2>
    <form id="modal-settings-form" class="stack">
      <label>
        <span class="label-text">AI provider</span>
        <select name="provider">
          ${s.supported_providers.map(p => `<option value="${p}"${s.provider === p ? " selected" : ""}>${p}</option>`).join("")}
        </select>
      </label>
      <label>
        <span class="label-text">API key <small>${s.api_key_preview ? "current: " + s.api_key_preview : ""}</small></span>
        <input type="password" name="api_key" autocomplete="off" placeholder="leave blank to keep current">
      </label>
      <label>
        <span class="label-text">Model</span>
        <input type="text" name="model" value="${s.model || ""}">
      </label>
      <label>
        <span class="label-text">Target modules folder</span>
        <input type="text" name="target_modules_dir" value="${s.target_modules_dir || ""}">
      </label>
      <div class="row">
        <label class="half">
          <span class="label-text">Panel width</span>
          <input type="number" name="panel_width" min="100" value="${s.panel_width || 800}">
        </label>
        <label class="half">
          <span class="label-text">Panel height</span>
          <input type="number" name="panel_height" min="100" value="${s.panel_height || 480}">
        </label>
      </div>
      <div class="wizard-nav">
        <button type="button" class="ghost" id="cancel-settings">Cancel</button>
        <button type="submit" class="primary">Save</button>
      </div>
    </form>
  `;
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);

  modal.querySelector("#cancel-settings").addEventListener("click", () => backdrop.remove());
  modal.querySelector("#modal-settings-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.currentTarget).entries());
    // Drop empty api_key so we don't wipe the current one.
    if (!body.api_key) delete body.api_key;
    try {
      await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
      backdrop.remove();
    } catch (err) {
      showError(err.message);
    }
  });
}
