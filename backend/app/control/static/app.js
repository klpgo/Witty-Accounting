// Texte in der Sprache der Server-Konfiguration (WITTY_CONTROL_LANGUAGE)
let texts = {};

function t(key, params = {}) {
  let text = texts[key] || key;
  for (const [name, value] of Object.entries(params)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

async function loadTexts() {
  try {
    const response = await fetch("/api/i18n");
    const body = await response.json();
    texts = body.texts || {};
    document.documentElement.lang = body.language || "en";
  } catch {
    texts = {};
  }
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
}

const state = {
  csrf: null,
  tenants: [],
  editTenant: null,
  hostnameTenant: null,
  deleteTenant: null,
  deletingTenantId: null,
};

const loginView = document.querySelector("#login-view");
const appView = document.querySelector("#app-view");
const message = document.querySelector("#message");
const tenantList = document.querySelector("#tenant-list");
const tenantCount = document.querySelector("#tenant-count");
const editDialog = document.querySelector("#edit-dialog");
const hostnameDialog = document.querySelector("#hostname-dialog");
const deleteDialog = document.querySelector("#delete-dialog");
const deleteProgress = document.querySelector("#delete-progress");
const deleteProgressTitle = document.querySelector("#delete-progress-title");
const deleteProgressState = document.querySelector("#delete-progress-state");
const deleteProgressSteps = document.querySelector("#delete-progress-steps");

function requestHeaders(options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.csrf && options.method && options.method !== "GET") {
    headers["X-Control-CSRF"] = state.csrf;
  }
  return headers;
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: requestHeaders(options) });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || t("error.request"));
  return body;
}

function setMessage(text, error = false) {
  message.textContent = text;
  message.classList.toggle("error", error);
  message.classList.toggle("hidden", !text);
}

function beginDeleteProgress(tenant) {
  state.deletingTenantId = tenant.id;
  deleteProgressTitle.textContent = `${tenant.name} (${tenant.code})`;
  deleteProgressState.textContent = t("progress.running");
  deleteProgressState.className = "progress-state";
  deleteProgressSteps.replaceChildren();
  deleteProgress.classList.remove("hidden");
  appendDeleteProgress(t("progress.checking"), "current");
  renderTenants();
}

function appendDeleteProgress(text, status) {
  const current = deleteProgressSteps.querySelector(".current");
  if (current) {
    current.className = `progress-step ${status === "error" ? "error" : "done"}`;
  }

  const item = document.createElement("li");
  item.className = `progress-step ${status}`;
  item.textContent = text;
  deleteProgressSteps.append(item);
}

function showDeleteEvent(event) {
  if (event.type === "error") {
    appendDeleteProgress(event.message, "error");
    deleteProgressState.textContent = t("progress.error");
    deleteProgressState.className = "progress-state error";
    return;
  }

  if (event.type === "complete") {
    appendDeleteProgress(event.message, "done");
    deleteProgressState.textContent = t("progress.done");
    deleteProgressState.className = "progress-state complete";
    return;
  }

  appendDeleteProgress(event.message, "current");
}

function showDeleteError(text) {
  if (!deleteProgressState.classList.contains("error")) {
    showDeleteEvent({ type: "error", message: text });
  }
}

async function deleteTenantWithProgress(tenant, payload) {
  const options = {
    method: "POST",
    body: JSON.stringify(payload),
  };
  const response = await fetch(`/api/tenants/${tenant.id}/delete`, {
    ...options,
    headers: requestHeaders(options),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || t("error.deleteStart"));
  }
  if (!response.body) {
    throw new Error(t("error.deleteProgress"));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;

  const processLine = (line) => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    showDeleteEvent(event);
    if (event.type === "error") throw new Error(event.message);
    if (event.type === "complete") completed = true;
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    lines.forEach(processLine);
    if (done) break;
  }
  processLine(buffer);

  if (!completed) {
    throw new Error(t("error.deleteNoCompletion"));
  }
}

function showApp(authenticated) {
  loginView.classList.toggle("hidden", authenticated);
  appView.classList.toggle("hidden", !authenticated);
  if (authenticated) {
    document.querySelector("#admin-password").value = "";
    document.querySelector("#admin-password-confirmation").value = "";
  }
}

async function loadTenants() {
  state.tenants = await api("/api/tenants");
  renderTenants();
}

function renderTenants() {
  tenantCount.textContent = String(state.tenants.length);
  tenantList.replaceChildren();
  if (!state.tenants.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = t("list.empty");
    tenantList.append(empty);
    return;
  }

  for (const tenant of state.tenants) {
    const card = document.createElement("article");
    card.className = "tenant-card";
    card.innerHTML = `
      <div class="tenant-card-head">
        <div><h4></h4><span class="muted code"></span></div>
        <span class="status"></span>
      </div>
      <dl class="tenant-meta">
        <dt class="label-hostname"></dt><dd class="hostname"></dd>
        <dt class="label-database"></dt><dd class="database"></dd>
      </dl>
      <div class="tenant-actions">
        <button class="secondary edit-button" type="button"></button>
        <button class="secondary hostname-button" type="button"></button>
        <button class="secondary state-button" type="button"></button>
        <button class="danger delete-button" type="button"></button>
      </div>`;
    card.querySelector(".label-hostname").textContent = t("list.hostname");
    card.querySelector(".label-database").textContent = t("list.database");
    card.querySelector(".edit-button").textContent = t("list.rename");
    card.querySelector(".hostname-button").textContent = t("list.changeHostname");
    card.querySelector(".delete-button").textContent = t("list.delete");
    card.querySelector("h4").textContent = tenant.name;
    card.querySelector(".code").textContent = tenant.code;
    card.querySelector(".hostname").textContent = tenant.hostname;
    card.querySelector(".database").textContent = tenant.db_name;
    const status = card.querySelector(".status");
    status.textContent = tenant.active ? t("list.active") : t("list.locked");
    status.classList.add(tenant.active ? "active" : "blocked");
    const stateButton = card.querySelector(".state-button");
    stateButton.textContent = tenant.active ? t("list.lock") : t("list.unlock");
    stateButton.addEventListener("click", () => changeState(tenant));
    const editButton = card.querySelector(".edit-button");
    const hostnameButton = card.querySelector(".hostname-button");
    const deleteButton = card.querySelector(".delete-button");
    editButton.addEventListener("click", () => openEdit(tenant));
    hostnameButton.addEventListener("click", () => openHostname(tenant));
    deleteButton.addEventListener("click", () => openDelete(tenant));
    const deletionRunning = state.deletingTenantId !== null;
    stateButton.disabled = deletionRunning;
    editButton.disabled = deletionRunning;
    hostnameButton.disabled = deletionRunning;
    deleteButton.disabled = deletionRunning;
    tenantList.append(card);
  }
}

async function changeState(tenant) {
  setMessage("");
  try {
    await api(`/api/tenants/${tenant.id}/state`, {
      method: "PUT",
      body: JSON.stringify({ active: !tenant.active }),
    });
    await loadTenants();
    setMessage(tenant.active ? t("state.locked") : t("state.unlocked"));
  } catch (error) { setMessage(error.message, true); }
}

function openEdit(tenant) {
  state.editTenant = tenant;
  document.querySelector("#edit-code").textContent = tenant.code;
  const nameInput = document.querySelector("#edit-name");
  nameInput.value = tenant.name;
  editDialog.showModal();
  nameInput.select();
}

function openHostname(tenant) {
  state.hostnameTenant = tenant;
  document.querySelector("#hostname-code").textContent = tenant.code;
  const hostnameInput = document.querySelector("#hostname-value");
  hostnameInput.value = tenant.hostname;
  hostnameDialog.showModal();
  hostnameInput.select();
}

function openDelete(tenant) {
  state.deleteTenant = tenant;
  document.querySelector("#delete-title").textContent = t("delete.titleNamed", { name: tenant.name });
  document.querySelector("#delete-code").textContent = tenant.code;
  document.querySelector("#delete-confirmation").value = "";
  document.querySelector("#delete-password").value = "";
  deleteDialog.showModal();
}

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ password: document.querySelector("#login-password").value }),
    });
    state.csrf = result.csrf_token;
    showApp(true);
    await loadTenants();
  } catch (error) {
    const localMessage = loginView.querySelector(".muted");
    localMessage.textContent = error.message;
  }
});

document.querySelector("#create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("");
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  if (data.admin_password !== document.querySelector("#admin-password-confirmation").value) {
    setMessage(t("create.passwordMismatch"), true);
    return;
  }
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  submit.textContent = t("create.submitting");
  try {
    await api("/api/tenants", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    await loadTenants();
    setMessage(t("create.done"));
  } catch (error) { setMessage(error.message, true); }
  finally {
    submit.disabled = false;
    submit.textContent = t("create.submit");
  }
});

document.querySelector("#edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const tenant = state.editTenant;
  if (!tenant) return;
  const submit = event.currentTarget.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    await api(`/api/tenants/${tenant.id}/name`, {
      method: "PUT",
      body: JSON.stringify({ name: document.querySelector("#edit-name").value }),
    });
    editDialog.close();
    state.editTenant = null;
    await loadTenants();
    setMessage(t("edit.done"));
  } catch (error) { setMessage(error.message, true); }
  finally { submit.disabled = false; }
});

document.querySelector("#hostname-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const tenant = state.hostnameTenant;
  if (!tenant) return;
  const submit = event.currentTarget.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    await api(`/api/tenants/${tenant.id}/hostname`, {
      method: "PUT",
      body: JSON.stringify({
        hostname: document.querySelector("#hostname-value").value,
      }),
    });
    hostnameDialog.close();
    state.hostnameTenant = null;
    await loadTenants();
    setMessage(t("hostname.done"));
  } catch (error) { setMessage(error.message, true); }
  finally { submit.disabled = false; }
});

document.querySelector("#delete-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const tenant = state.deleteTenant;
  if (!tenant) return;
  const submit = event.currentTarget.querySelector("button[type=submit]");
  submit.disabled = true;
  const payload = {
    confirmation: document.querySelector("#delete-confirmation").value,
    control_password: document.querySelector("#delete-password").value,
  };
  deleteDialog.close();
  state.deleteTenant = null;
  setMessage("");
  beginDeleteProgress(tenant);
  try {
    await deleteTenantWithProgress(tenant, payload);
    await loadTenants();
    setMessage(t("delete.done"));
  } catch (error) {
    showDeleteError(error.message);
    setMessage(error.message, true);
    await loadTenants().catch(() => {});
  } finally {
    state.deletingTenantId = null;
    submit.disabled = false;
    renderTenants();
  }
});

document.querySelector("#edit-cancel").addEventListener("click", () => editDialog.close());
document.querySelector("#hostname-cancel").addEventListener("click", () => hostnameDialog.close());
document.querySelector("#delete-cancel").addEventListener("click", () => deleteDialog.close());
document.querySelector("#refresh-button").addEventListener("click", () => loadTenants().catch((error) => setMessage(error.message, true)));
document.querySelector("#logout-button").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  state.csrf = null;
  showApp(false);
});

loadTexts()
  .then(() => api("/api/session"))
  .then(async (session) => {
    state.csrf = session.csrf_token;
    showApp(true);
    await loadTenants();
  })
  .catch(() => showApp(false));
