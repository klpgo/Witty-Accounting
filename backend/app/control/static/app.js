const state = { csrf: null, tenants: [], editTenant: null, deleteTenant: null };

const loginView = document.querySelector("#login-view");
const appView = document.querySelector("#app-view");
const message = document.querySelector("#message");
const tenantList = document.querySelector("#tenant-list");
const tenantCount = document.querySelector("#tenant-count");
const editDialog = document.querySelector("#edit-dialog");
const deleteDialog = document.querySelector("#delete-dialog");

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.csrf && options.method && options.method !== "GET") {
    headers["X-Control-CSRF"] = state.csrf;
  }
  const response = await fetch(path, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Die Anfrage ist fehlgeschlagen.");
  return body;
}

function setMessage(text, error = false) {
  message.textContent = text;
  message.classList.toggle("error", error);
  message.classList.toggle("hidden", !text);
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
    empty.textContent = "Noch keine Mandanten vorhanden.";
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
        <dt>Hostname</dt><dd class="hostname"></dd>
        <dt>Datenbank</dt><dd class="database"></dd>
      </dl>
      <div class="tenant-actions">
        <button class="secondary edit-button" type="button">Anzeigename ändern</button>
        <button class="secondary state-button" type="button"></button>
        <button class="danger delete-button" type="button">Löschen</button>
      </div>`;
    card.querySelector("h4").textContent = tenant.name;
    card.querySelector(".code").textContent = tenant.code;
    card.querySelector(".hostname").textContent = tenant.hostname;
    card.querySelector(".database").textContent = tenant.db_name;
    const status = card.querySelector(".status");
    status.textContent = tenant.active ? "Aktiv" : "Gesperrt";
    status.classList.add(tenant.active ? "active" : "blocked");
    const stateButton = card.querySelector(".state-button");
    stateButton.textContent = tenant.active ? "Sperren" : "Entsperren";
    stateButton.addEventListener("click", () => changeState(tenant));
    card.querySelector(".edit-button").addEventListener("click", () => openEdit(tenant));
    card.querySelector(".delete-button").addEventListener("click", () => openDelete(tenant));
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
    setMessage(tenant.active ? "Mandant wurde gesperrt." : "Mandant wurde entsperrt.");
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

function openDelete(tenant) {
  state.deleteTenant = tenant;
  document.querySelector("#delete-title").textContent = `${tenant.name} löschen`;
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
    setMessage("Die Admin-Passwörter stimmen nicht überein.", true);
    return;
  }
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  submit.textContent = "Mandant wird angelegt …";
  try {
    await api("/api/tenants", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    await loadTenants();
    setMessage("Mandant, Datenbank und erster Administrator wurden angelegt.");
  } catch (error) { setMessage(error.message, true); }
  finally {
    submit.disabled = false;
    submit.textContent = "Mandant vollständig anlegen";
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
    setMessage("Der Anzeigename wurde geändert.");
  } catch (error) { setMessage(error.message, true); }
  finally { submit.disabled = false; }
});

document.querySelector("#delete-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const tenant = state.deleteTenant;
  if (!tenant) return;
  const submit = event.currentTarget.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    await api(`/api/tenants/${tenant.id}/delete`, {
      method: "POST",
      body: JSON.stringify({
        confirmation: document.querySelector("#delete-confirmation").value,
        control_password: document.querySelector("#delete-password").value,
      }),
    });
    deleteDialog.close();
    await loadTenants();
    setMessage("Mandant, Datenbank und Rechnungsarchiv wurden vollständig gelöscht.");
  } catch (error) { setMessage(error.message, true); }
  finally { submit.disabled = false; }
});

document.querySelector("#edit-cancel").addEventListener("click", () => editDialog.close());
document.querySelector("#delete-cancel").addEventListener("click", () => deleteDialog.close());
document.querySelector("#refresh-button").addEventListener("click", () => loadTenants().catch((error) => setMessage(error.message, true)));
document.querySelector("#logout-button").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  state.csrf = null;
  showApp(false);
});

api("/api/session")
  .then(async (session) => {
    state.csrf = session.csrf_token;
    showApp(true);
    await loadTenants();
  })
  .catch(() => showApp(false));
