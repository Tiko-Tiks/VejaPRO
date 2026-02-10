/* VejaPRO Admin - Projects Page JS (V3.0) */
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const sidebarNav = document.getElementById("sidebarNav");
  if (sidebarNav) sidebarNav.innerHTML = sidebarHTML("/admin/projects");
  initProjectsPage();
});

// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------

let _items = [];
let _nextCursor = null;
let _itemIds = new Set();

let _assignProjectId = null;
let _assignKind = null; // "contractor" | "expert"

let _manualPaymentProjectId = null;
let _paymentLinkProjectId = null;

let _rowsEl = null;
let _countEl = null;
let _loadMoreBtn = null;

function initProjectsPage() {
  initTokenUI();
  initListUI();
  initCreateUI();
  initModalsUI();
  initDeepLinks();

  if (Auth.isSet()) fetchProjects({ reset: true });
  handleDeepLink();
}

function initTokenUI() {
  const tokenInput = document.getElementById("tokenInput");
  const tokenStatus = document.getElementById("tokenStatus");
  const tokenBadge = document.getElementById("tokenBadge");
  const btnSaveToken = document.getElementById("btnSaveToken");
  const btnGenerate = document.getElementById("btnGenerate");

  const updateTokenBadge = () => {
    if (!tokenBadge) return;
    if (Auth.isSet()) {
      tokenBadge.textContent = "Aktyvus";
      tokenBadge.className = "pill pill-success";
    } else {
      tokenBadge.textContent = "Nenustatytas";
      tokenBadge.className = "pill pill-gray";
    }
  };

  if (tokenInput && tokenStatus && Auth.isSet()) {
    tokenInput.value = Auth.get();
    tokenStatus.textContent = "Zetonas ikeltas is narsykles.";
  }
  updateTokenBadge();

  if (btnSaveToken && tokenInput && tokenStatus) {
    btnSaveToken.addEventListener("click", () => {
      const val = Auth.normalize(tokenInput.value);
      if (val) {
        Auth.set(val);
        tokenInput.value = val;
        tokenStatus.textContent = "Zetonas issaugotas.";
        showToast("Zetonas issaugotas", "success");
        fetchProjects({ reset: true });
        handleDeepLink();
      } else {
        Auth.remove();
        tokenStatus.textContent = "Zetonas istrintas.";
        showToast("Zetonas istrintas", "info");
        _items = [];
        _nextCursor = null;
        _itemIds = new Set();
        _renderRows();
      }
      updateTokenBadge();
    });
  }

  if (btnGenerate && tokenInput && tokenStatus) {
    btnGenerate.addEventListener("click", async () => {
      tokenStatus.textContent = "Generuojamas...";
      try {
        const token = await Auth.generate();
        if (token) {
          tokenInput.value = token;
          tokenStatus.textContent = "Zetonas sugeneruotas ir issaugotas.";
          showToast("Zetonas sugeneruotas", "success");
          updateTokenBadge();
          fetchProjects({ reset: true });
          handleDeepLink();
        } else {
          tokenStatus.textContent = "Zetono generavimas nepavyko.";
        }
      } catch (err) {
        tokenStatus.textContent = (err && err.message) || "Tinklo klaida.";
        showToast("Nepavyko sugeneruoti zetono", "error");
      }
    });
  }
}
function initListUI() {
  _rowsEl = document.getElementById("rows");
  _countEl = document.getElementById("count");
  _loadMoreBtn = document.getElementById("btnLoadMore");

  const btnApply = document.getElementById("btnApply");
  const btnClear = document.getElementById("btnClear");
  const btnRefresh = document.getElementById("btnRefresh");

  if (btnApply) btnApply.addEventListener("click", () => fetchProjects({ reset: true }));
  if (btnRefresh) btnRefresh.addEventListener("click", () => fetchProjects({ reset: true }));
  if (_loadMoreBtn) _loadMoreBtn.addEventListener("click", () => fetchProjects({ reset: false }));

  if (btnClear) {
    btnClear.addEventListener("click", () => {
      const s = document.getElementById("filterStatus");
      const c = document.getElementById("filterContractor");
      const e = document.getElementById("filterExpert");
      const l = document.getElementById("filterLimit");
      if (s) s.value = "";
      if (c) c.value = "";
      if (e) e.value = "";
      if (l) l.value = "50";
      fetchProjects({ reset: true });
    });
  }
}
function initCreateUI() {
  const btnCreate = document.getElementById("btnCreate");
  const createStatus = document.getElementById("createStatus");
  if (!btnCreate) return;

  btnCreate.addEventListener("click", async () => {
    if (!Auth.isSet()) {
      if (createStatus) createStatus.textContent = "Reikia zetono.";
      return;
    }
    const name = ((document.getElementById("createName") || {}).value || "").trim();
    const clientId = ((document.getElementById("createClientId") || {}).value || "").trim();
    const phone = ((document.getElementById("createPhone") || {}).value || "").trim();
    if (!name || !clientId) {
      if (createStatus) createStatus.textContent = "Kliento vardas ir ID yra privalomi.";
      return;
    }
    if (createStatus) createStatus.textContent = "Kuriama...";

    try {
      await authFetch("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify({
          client_info: {
            name,
            client_id: clientId,
            ...(phone ? { phone } : {}),
          },
        }),
      });
      if (createStatus) createStatus.textContent = "Projektas sukurtas.";
      showToast("Projektas sukurtas", "success");
      const phoneEl = document.getElementById("createPhone");
      if (phoneEl) phoneEl.value = "";
      fetchProjects({ reset: true });
    } catch (err) {
      if (err instanceof AuthError) return;
      if (createStatus) createStatus.textContent = "Sukurimas nepavyko.";
    }
  });
}
function initModalsUI() {
  // Assign modal
  const btnAssignClose = document.getElementById("btnAssignClose");
  const btnAssignCancel = document.getElementById("btnAssignCancel");
  const btnAssignConfirm = document.getElementById("btnAssignConfirm");
  const assignBackdrop = document.getElementById("assignBackdrop");

  if (btnAssignClose) btnAssignClose.addEventListener("click", closeAssignModal);
  if (btnAssignCancel) btnAssignCancel.addEventListener("click", closeAssignModal);
  if (assignBackdrop) {
    assignBackdrop.addEventListener("click", (e) => {
      if (e.target && e.target.id === "assignBackdrop") closeAssignModal();
    });
  }

  if (btnAssignConfirm) {
    btnAssignConfirm.addEventListener("click", async () => {
      if (!_assignProjectId || !_assignKind) return;
      const assigneeInput = document.getElementById("assigneeInput");
      const confirmCheck = document.getElementById("confirmAssignCheck");
      const assignStatus = document.getElementById("assignStatus");

      if (confirmCheck && !confirmCheck.checked) {
        if (assignStatus) assignStatus.textContent = "Pazymekite patvirtinima.";
        return;
      }

      const userId = ((assigneeInput || {}).value || "").trim();
      if (!userId) {
        if (assignStatus) assignStatus.textContent = "Iveskite UUID.";
        return;
      }

      if (assignStatus) assignStatus.textContent = "Atnaujinama...";
      const path =
        _assignKind === "contractor"
          ? `/api/v1/admin/projects/${encodeURIComponent(_assignProjectId)}/assign-contractor`
          : `/api/v1/admin/projects/${encodeURIComponent(_assignProjectId)}/assign-expert`;

      try {
        await authFetch(path, { method: "POST", body: JSON.stringify({ user_id: userId }) });
        showToast("Priskyrimas atnaujintas", "success");
        closeAssignModal();
        fetchProjects({ reset: true });
      } catch (err) {
        if (err instanceof AuthError) return;
        if (assignStatus) assignStatus.textContent = "Nepavyko.";
      }
    });
  }

  // Details modal
  const btnDetailsClose = document.getElementById("btnDetailsClose");
  const detailsBackdrop = document.getElementById("detailsBackdrop");
  if (btnDetailsClose) btnDetailsClose.addEventListener("click", () => modalClose("detailsBackdrop"));
  if (detailsBackdrop) {
    detailsBackdrop.addEventListener("click", (e) => {
      if (e.target && e.target.id === "detailsBackdrop") modalClose("detailsBackdrop");
    });
  }

  // Client token modal
  const btnClientTokenClose = document.getElementById("btnClientTokenClose");
  const clientTokenBackdrop = document.getElementById("clientTokenBackdrop");
  if (btnClientTokenClose) btnClientTokenClose.addEventListener("click", () => modalClose("clientTokenBackdrop"));
  if (clientTokenBackdrop) {
    clientTokenBackdrop.addEventListener("click", (e) => {
      if (e.target && e.target.id === "clientTokenBackdrop") modalClose("clientTokenBackdrop");
    });
  }

  // Manual payment modal
  const btnManualPaymentClose = document.getElementById("btnManualPaymentClose");
  const btnManualPaymentCancel = document.getElementById("btnManualPaymentCancel");
  const manualPaymentBackdrop = document.getElementById("manualPaymentBackdrop");
  if (btnManualPaymentClose) btnManualPaymentClose.addEventListener("click", () => modalClose("manualPaymentBackdrop"));
  if (btnManualPaymentCancel) btnManualPaymentCancel.addEventListener("click", () => modalClose("manualPaymentBackdrop"));
  if (manualPaymentBackdrop) {
    manualPaymentBackdrop.addEventListener("click", (e) => {
      if (e.target && e.target.id === "manualPaymentBackdrop") modalClose("manualPaymentBackdrop");
    });
  }

  // Payment link modal
  const btnPaymentLinkClose = document.getElementById("btnPaymentLinkClose");
  const paymentLinkBackdrop = document.getElementById("paymentLinkBackdrop");
  if (btnPaymentLinkClose) btnPaymentLinkClose.addEventListener("click", () => modalClose("paymentLinkBackdrop"));
  if (paymentLinkBackdrop) {
    paymentLinkBackdrop.addEventListener("click", (e) => {
      if (e.target && e.target.id === "paymentLinkBackdrop") modalClose("paymentLinkBackdrop");
    });
  }

  // Copy buttons
  const btnCopyClientToken = document.getElementById("btnCopyClientToken");
  const btnCopyClientLink = document.getElementById("btnCopyClientLink");
  if (btnCopyClientToken) btnCopyClientToken.addEventListener("click", () => {
    const token = ((document.getElementById("clientTokenBackdrop") || {}).dataset || {}).token || "";
    if (token) copyToClipboard(token);
  });
  if (btnCopyClientLink) btnCopyClientLink.addEventListener("click", () => {
    const link = ((document.getElementById("clientTokenBackdrop") || {}).dataset || {}).link || "";
    if (link) copyToClipboard(link);
  });

  const btnCopyPaymentLink = document.getElementById("btnCopyPaymentLink");
  if (btnCopyPaymentLink) btnCopyPaymentLink.addEventListener("click", () => {
    const v = ((document.getElementById("paymentLinkValue") || {}).value || "").trim();
    if (v) copyToClipboard(v);
  });

  const btnManualPaymentConfirm = document.getElementById("btnManualPaymentConfirm");
  if (btnManualPaymentConfirm) btnManualPaymentConfirm.addEventListener("click", recordManualPayment);

  const btnWaiveDeposit = document.getElementById("btnWaiveDeposit");
  if (btnWaiveDeposit) btnWaiveDeposit.addEventListener("click", waiveDeposit);

  const btnCreatePaymentLink = document.getElementById("btnCreatePaymentLink");
  if (btnCreatePaymentLink) btnCreatePaymentLink.addEventListener("click", createPaymentLink);
}
function initDeepLinks() {
  window.addEventListener("hashchange", handleDeepLink);
}

function _isUuid(v) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(v || ""));
}

function _getFilters() {
  const status = (document.getElementById("filterStatus") || {}).value || "";
  const contractor = ((document.getElementById("filterContractor") || {}).value || "").trim();
  const expert = ((document.getElementById("filterExpert") || {}).value || "").trim();
  const limit = (document.getElementById("filterLimit") || {}).value || "50";
  return {
    status: status || null,
    assigned_contractor_id: contractor || null,
    assigned_expert_id: expert || null,
    limit: limit || "50",
  };
}

function _buildQuery(filters, cursor) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) params.append(k, v); });
  if (cursor) params.append("cursor", cursor);
  return params.toString();
}

function _shortenId(value) {
  if (!value) return "-";
  return String(value).slice(0, 8) + "...";
}

function _setCount() {
  if (!_countEl) return;
  _countEl.textContent = _items.length ? (_items.length + " irasu") : "0 irasu";
}

function _renderRows() {
  if (!_rowsEl) return;
  _rowsEl.innerHTML = "";
  for (const item of _items) {
    const tr = document.createElement("tr");
    const auditUrl = "/admin/audit?entity_type=project&entity_id=" + encodeURIComponent(item.id);
    tr.innerHTML = `
      <td data-label="ID" class="mono" title="${escapeHtml(item.id)}">
        <a href="/admin/projects#${escapeHtml(item.id)}">${escapeHtml(_shortenId(item.id))}</a>
      </td>
      <td data-label="Status">${statusPill(item.status)}</td>
      <td data-label="Suplanuota">${escapeHtml(formatDate(item.scheduled_for))}</td>
      <td data-label="Rangovas" class="mono">${escapeHtml(item.assigned_contractor_id || "-")}</td>
      <td data-label="Ekspertas" class="mono">${escapeHtml(item.assigned_expert_id || "-")}</td>
      <td data-label="Sukurta">${escapeHtml(formatDate(item.created_at))}</td>
      <td data-label="Atnaujinta">${escapeHtml(formatDate(item.updated_at))}</td>
      <td data-label="Veiksmai">
        <div class="row-actions">
          <button class="btn btn-xs btn-ghost" data-action="details" data-id="${escapeHtml(item.id)}">Detales</button>
          <a class="btn btn-xs btn-ghost" href="${escapeHtml(auditUrl)}" onclick="event.stopPropagation();">Auditas</a>
          <button class="btn btn-xs btn-ghost" data-action="client-token" data-id="${escapeHtml(item.id)}">Kliento zetonas</button>
          <button class="btn btn-xs btn-ghost" data-action="manual-payment" data-id="${escapeHtml(item.id)}">Rankinis</button>
          <button class="btn btn-xs btn-ghost" data-action="payment-link" data-id="${escapeHtml(item.id)}">Stripe</button>
          <button class="btn btn-xs btn-ghost" data-action="seed-evidence" data-id="${escapeHtml(item.id)}">Sert. foto</button>
          <button class="btn btn-xs btn-ghost" data-action="certify" data-id="${escapeHtml(item.id)}">Sertifikuoti</button>
          ${item.status === "CERTIFIED" ? `<button class="btn btn-xs btn-primary" data-action="admin-confirm" data-id="${escapeHtml(item.id)}">Aktyvuoti</button>` : ""}
          <button class="btn btn-xs btn-ghost" data-action="assign-contractor" data-id="${escapeHtml(item.id)}">Rangovas</button>
          <button class="btn btn-xs btn-ghost" data-action="assign-expert" data-id="${escapeHtml(item.id)}">Ekspertas</button>
        </div>
      </td>
    `;
    _rowsEl.appendChild(tr);
  }

  _setCount();
  if (_loadMoreBtn) _loadMoreBtn.disabled = !_nextCursor;
  _wireRowActions();
}

function _wireRowActions() {
  if (!_rowsEl) return;
  _rowsEl.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      const action = event.currentTarget.getAttribute("data-action");
      const id = event.currentTarget.getAttribute("data-id");
      if (!action || !id) return;
      if (action === "details") return openDetailModal(id);
      if (action === "client-token") return openClientTokenModal(id);
      if (action === "manual-payment") return openManualPaymentModal(id);
      if (action === "payment-link") return openPaymentLinkModal(id);
      if (action === "seed-evidence") return seedCertPhotos(id);
      if (action === "certify") return certifyProject(id);
      if (action === "admin-confirm") return adminConfirmProject(id);
      if (action === "assign-contractor") return openAssignModal(id, "contractor");
      if (action === "assign-expert") return openAssignModal(id, "expert");
    });
  });
}

async function fetchProjects(opts) {
  const reset = !!(opts && opts.reset);
  if (!Auth.isSet()) {
    showToast("Sugeneruokite arba issaugokite zetona.", "warning");
    return;
  }

  if (reset) {
    _items = [];
    _nextCursor = null;
    _itemIds = new Set();
    _renderRows();
  }

  const filters = _getFilters();
  const query = _buildQuery(filters, _nextCursor);
  try {
    const resp = await authFetch("/api/v1/admin/projects?" + query);
    const data = await resp.json();
    const newItems = (data.items || []).filter((it) => {
      if (_itemIds.has(it.id)) return false;
      _itemIds.add(it.id);
      return true;
    });
    _items = _items.concat(newItems);
    _nextCursor = data.next_cursor || null;
    _renderRows();
  } catch (err) {
    if (err instanceof AuthError) return;
    showToast("Nepavyko ikelti projektu.", "error");
  }
}
function handleDeepLink() {
  const raw = String(window.location.hash || "").replace(/^#/, "");
  if (!raw) return;
  if (!Auth.isSet()) return;

  // #manual-deposit-<uuid> or #manual-final-<uuid>
  const m = raw.match(/^manual-(deposit|final)-(.+)$/i);
  if (m) {
    const kind = String(m[1] || "").toUpperCase();
    const projectId = String(m[2] || "").trim();
    if (_isUuid(projectId)) {
      openManualPaymentModal(projectId, kind === "DEPOSIT" ? "DEPOSIT" : "FINAL");
    }
    return;
  }

  // #<uuid> (open details)
  if (_isUuid(raw)) {
    openDetailModal(raw);
  }
}

function modalOpen(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add("active");
  el.setAttribute("aria-hidden", "false");
}

function modalClose(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove("active");
  el.setAttribute("aria-hidden", "true");
}

function openAssignModal(projectId, kind) {
  _assignProjectId = projectId;
  _assignKind = kind;
  const title = document.getElementById("assignTitle");
  const assigneeInput = document.getElementById("assigneeInput");
  const confirmCheck = document.getElementById("confirmAssignCheck");
  const assignStatus = document.getElementById("assignStatus");

  if (title) title.textContent = kind === "contractor" ? "Priskirti rangova" : "Priskirti eksperta";
  if (assigneeInput) assigneeInput.value = "";
  if (confirmCheck) confirmCheck.checked = false;
  if (assignStatus) assignStatus.textContent = "";

  modalOpen("assignBackdrop");
}

function closeAssignModal() {
  modalClose("assignBackdrop");
  _assignProjectId = null;
  _assignKind = null;
}

function _redactPII(obj) {
  if (obj == null) return obj;
  if (Array.isArray(obj)) return obj.map(_redactPII);
  if (typeof obj !== "object") return obj;
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (k === "email") out[k] = maskEmail(String(v || ""));
    else if (k === "phone") out[k] = maskPhone(String(v || ""));
    else out[k] = _redactPII(v);
  }
  return out;
}

async function openDetailModal(projectId) {
  modalOpen("detailsBackdrop");
  const detailsJson = document.getElementById("detailsJson");
  if (detailsJson) detailsJson.textContent = "Kraunama...";
  try {
    const resp = await authFetch(`/api/v1/projects/${encodeURIComponent(projectId)}`);
    const data = await resp.json();
    if (detailsJson) detailsJson.textContent = JSON.stringify(_redactPII(data), null, 2);
  } catch (err) {
    if (err instanceof AuthError) return;
    if (detailsJson) detailsJson.textContent = "Nepavyko ikelti.";
    showToast("Nepavyko ikelti detaliu", "error");
  }
}

async function openClientTokenModal(projectId) {
  modalOpen("clientTokenBackdrop");
  const backdrop = document.getElementById("clientTokenBackdrop");
  const tokenEl = document.getElementById("clientTokenValue");
  const metaEl = document.getElementById("clientTokenMeta");
  const statusEl = document.getElementById("clientTokenStatus");
  const linkEl = document.getElementById("clientPortalLink");

  if (statusEl) statusEl.textContent = "Generuojamas...";
  if (tokenEl) tokenEl.value = "";
  if (metaEl) metaEl.textContent = "";
  if (linkEl) {
    linkEl.href = "#";
    linkEl.textContent = "Atidaryti kliento portala";
  }
  if (backdrop) {
    backdrop.dataset.token = "";
    backdrop.dataset.link = "";
  }

  try {
    const resp = await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/client-token`);
    const data = await resp.json();
    const token = Auth.normalize(data.token || "");
    if (!token) {
      if (statusEl) statusEl.textContent = "Zetonas nerastas.";
      return;
    }
    const portalUrl = `/client?project=${encodeURIComponent(projectId)}&token=${encodeURIComponent(token)}`;
    if (tokenEl) tokenEl.value = token;
    if (metaEl) metaEl.textContent = `Kliento ID: ${data.client_id || "-"} | Galioja iki: ${data.expires_at || "-"}`;
    if (linkEl) {
      linkEl.href = portalUrl;
      linkEl.textContent = portalUrl;
    }
    if (backdrop) {
      backdrop.dataset.token = token;
      backdrop.dataset.link = portalUrl;
    }
    if (statusEl) statusEl.textContent = "Paruosta.";
  } catch (err) {
    if (err instanceof AuthError) return;
    if (statusEl) statusEl.textContent = "Nepavyko.";
    showToast("Nepavyko sugeneruoti kliento zetono", "error");
  }
}

function _nowCompact() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return (
    d.getFullYear() +
    pad(d.getMonth() + 1) +
    pad(d.getDate()) +
    pad(d.getHours()) +
    pad(d.getMinutes()) +
    pad(d.getSeconds())
  );
}

function openManualPaymentModal(projectId, forceType) {
  _manualPaymentProjectId = projectId;
  const backdrop = document.getElementById("manualPaymentBackdrop");
  if (backdrop) backdrop.dataset.projectId = projectId;

  const title = document.getElementById("manualPaymentTitle");
  const typeEl = document.getElementById("manualPaymentType");
  const currencyEl = document.getElementById("manualPaymentCurrency");
  const amountEl = document.getElementById("manualPaymentAmount");
  const methodEl = document.getElementById("manualPaymentMethod");
  const providerEl = document.getElementById("manualProviderEventId");
  const receiptEl = document.getElementById("manualReceiptNo");
  const notesEl = document.getElementById("manualPaymentNotes");
  const statusEl = document.getElementById("manualPaymentStatus");
  const waiveBtn = document.getElementById("btnWaiveDeposit");

  if (title) title.textContent = "Rankinis mokejimas (" + _shortenId(projectId) + ")";
  if (typeEl) {
    typeEl.value = "DEPOSIT";
    typeEl.disabled = false;
  }
  if (typeEl && forceType) {
    typeEl.value = String(forceType).toUpperCase() === "FINAL" ? "FINAL" : "DEPOSIT";
    typeEl.disabled = true; // deep link should be explicit
  }
  if (currencyEl) currencyEl.value = "EUR";
  if (amountEl) amountEl.value = "";
  if (methodEl) methodEl.value = "BANK_TRANSFER";
  if (providerEl) providerEl.value = `MANUAL-${projectId.slice(0, 8)}-${_nowCompact()}`;
  if (receiptEl) receiptEl.value = "";
  if (notesEl) notesEl.value = "";
  if (statusEl) statusEl.textContent = "";

  const setWaiveEnabled = () => {
    const t = ((typeEl || {}).value || "DEPOSIT").toUpperCase();
    if (!waiveBtn) return;
    // Waive applies only to deposit (DRAFT) flow.
    waiveBtn.disabled = t !== "DEPOSIT";
  };
  if (typeEl) typeEl.onchange = setWaiveEnabled;
  setWaiveEnabled();

  modalOpen("manualPaymentBackdrop");
}

async function recordManualPayment() {
  const projectId =
    _manualPaymentProjectId ||
    (((document.getElementById("manualPaymentBackdrop") || {}).dataset || {}).projectId || "");
  if (!projectId) return;

  const typeEl = document.getElementById("manualPaymentType");
  const currencyEl = document.getElementById("manualPaymentCurrency");
  const amountEl = document.getElementById("manualPaymentAmount");
  const methodEl = document.getElementById("manualPaymentMethod");
  const providerEl = document.getElementById("manualProviderEventId");
  const receiptEl = document.getElementById("manualReceiptNo");
  const notesEl = document.getElementById("manualPaymentNotes");
  const statusEl = document.getElementById("manualPaymentStatus");

  const payment_type = String(((typeEl || {}).value || "DEPOSIT")).toUpperCase();
  const currency = String(((currencyEl || {}).value || "EUR")).trim().toUpperCase();
  const amount = Number(((amountEl || {}).value || "").trim());
  const payment_method = String(((methodEl || {}).value || "")).trim().toUpperCase();
  const provider_event_id = String(((providerEl || {}).value || "")).trim();
  const receipt_no = String(((receiptEl || {}).value || "")).trim();
  const notes = String(((notesEl || {}).value || "")).trim();

  if (!provider_event_id) {
    if (statusEl) statusEl.textContent = "Reikia idempotencijos ID.";
    return;
  }
  if (!payment_method) {
    if (statusEl) statusEl.textContent = "Pasirinkite mokejimo buda.";
    return;
  }
  if (!Number.isFinite(amount) || amount <= 0) {
    if (statusEl) statusEl.textContent = "Iveskite suma (> 0).";
    return;
  }
  if (!currency || currency.length !== 3) {
    if (statusEl) statusEl.textContent = "Valiuta turi buti 3 raidziu (pvz. EUR).";
    return;
  }

  if (statusEl) statusEl.textContent = "Siunciama...";
  try {
    const resp = await authFetch(`/api/v1/projects/${encodeURIComponent(projectId)}/payments/manual`, {
      method: "POST",
      body: JSON.stringify({
        payment_type,
        amount,
        currency,
        payment_method,
        provider_event_id,
        ...(receipt_no ? { receipt_no } : {}),
        ...(notes ? { notes } : {}),
      }),
    });
    const data = await resp.json();
    showToast(data.idempotent ? "Mokejimas jau buvo irasytas (idempotent)" : "Mokejimas irasytas", "success");
    if (statusEl) statusEl.textContent = "OK";
    modalClose("manualPaymentBackdrop");
    _manualPaymentProjectId = null;
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
    if (statusEl) statusEl.textContent = "Nepavyko.";
  }
}

async function waiveDeposit() {
  const projectId =
    _manualPaymentProjectId ||
    (((document.getElementById("manualPaymentBackdrop") || {}).dataset || {}).projectId || "");
  if (!projectId) return;

  const typeEl = document.getElementById("manualPaymentType");
  const currencyEl = document.getElementById("manualPaymentCurrency");
  const providerEl = document.getElementById("manualProviderEventId");
  const notesEl = document.getElementById("manualPaymentNotes");
  const statusEl = document.getElementById("manualPaymentStatus");

  const payment_type = String(((typeEl || {}).value || "DEPOSIT")).toUpperCase();
  if (payment_type !== "DEPOSIT") {
    showToast("Inaso atidejimas galimas tik DEPOSIT", "warning");
    return;
  }

  const ok = confirm("Atideti inasa? (tik DRAFT projektams)");
  if (!ok) return;

  const currency = String(((currencyEl || {}).value || "EUR")).trim().toUpperCase();
  let provider_event_id = String(((providerEl || {}).value || "")).trim();
  const notes = String(((notesEl || {}).value || "")).trim();
  if (!provider_event_id || provider_event_id.startsWith("MANUAL-")) {
    provider_event_id = `WAIVE-${projectId.slice(0, 8)}-${_nowCompact()}`;
  }

  if (statusEl) statusEl.textContent = "Siunciama...";
  try {
    const resp = await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/payments/deposit-waive`, {
      method: "POST",
      body: JSON.stringify({
        provider_event_id,
        currency,
        ...(notes ? { notes } : {}),
      }),
    });
    const data = await resp.json();
    showToast(data.idempotent ? "Inasas jau buvo atidetas (idempotent)" : "Inasas atidetas", "success");
    if (statusEl) statusEl.textContent = "OK";
    modalClose("manualPaymentBackdrop");
    _manualPaymentProjectId = null;
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
    if (statusEl) statusEl.textContent = "Nepavyko.";
  }
}

function openPaymentLinkModal(projectId) {
  _paymentLinkProjectId = projectId;
  const backdrop = document.getElementById("paymentLinkBackdrop");
  if (backdrop) backdrop.dataset.projectId = projectId;

  const typeEl = document.getElementById("paymentType");
  const currencyEl = document.getElementById("paymentCurrency");
  const amountEl = document.getElementById("paymentAmount");
  const descEl = document.getElementById("paymentDescription");
  const successEl = document.getElementById("paymentSuccessUrl");
  const cancelEl = document.getElementById("paymentCancelUrl");
  const linkValueEl = document.getElementById("paymentLinkValue");
  const statusEl = document.getElementById("paymentStatus");
  const openLinkEl = document.getElementById("openPaymentLink");

  if (typeEl) typeEl.value = "DEPOSIT";
  if (currencyEl) currencyEl.value = "EUR";
  if (amountEl) amountEl.value = "";
  if (descEl) descEl.value = "";
  if (successEl) successEl.value = "";
  if (cancelEl) cancelEl.value = "";
  if (linkValueEl) linkValueEl.value = "";
  if (statusEl) statusEl.textContent = "";
  if (openLinkEl) {
    openLinkEl.href = "#";
    openLinkEl.textContent = "Atidaryti mokejimo nuoroda";
  }

  modalOpen("paymentLinkBackdrop");
}

async function createPaymentLink() {
  const projectId =
    _paymentLinkProjectId ||
    (((document.getElementById("paymentLinkBackdrop") || {}).dataset || {}).projectId || "");
  if (!projectId) return;

  const typeEl = document.getElementById("paymentType");
  const currencyEl = document.getElementById("paymentCurrency");
  const amountEl = document.getElementById("paymentAmount");
  const descEl = document.getElementById("paymentDescription");
  const successEl = document.getElementById("paymentSuccessUrl");
  const cancelEl = document.getElementById("paymentCancelUrl");
  const linkValueEl = document.getElementById("paymentLinkValue");
  const statusEl = document.getElementById("paymentStatus");
  const openLinkEl = document.getElementById("openPaymentLink");

  const payment_type = String(((typeEl || {}).value || "DEPOSIT")).toUpperCase();
  const currency = String(((currencyEl || {}).value || "EUR")).trim().toUpperCase();
  const amount = Number(((amountEl || {}).value || "").trim());
  const description = String(((descEl || {}).value || "")).trim();
  const success_url = String(((successEl || {}).value || "")).trim();
  const cancel_url = String(((cancelEl || {}).value || "")).trim();

  if (!Number.isFinite(amount) || amount <= 0) {
    if (statusEl) statusEl.textContent = "Iveskite suma (> 0).";
    return;
  }
  if (!currency || currency.length !== 3) {
    if (statusEl) statusEl.textContent = "Valiuta turi buti 3 raidziu (pvz. EUR).";
    return;
  }

  if (statusEl) statusEl.textContent = "Kuriama...";
  try {
    const resp = await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/payment-link`, {
      method: "POST",
      body: JSON.stringify({
        payment_type,
        amount,
        currency,
        ...(description ? { description } : {}),
        ...(success_url ? { success_url } : {}),
        ...(cancel_url ? { cancel_url } : {}),
      }),
    });
    const data = await resp.json();
    if (linkValueEl) linkValueEl.value = data.url || "";
    if (openLinkEl && data.url) {
      openLinkEl.href = data.url;
      openLinkEl.textContent = data.url;
    }
    if (statusEl) statusEl.textContent = "OK";
    showToast("Stripe nuoroda sukurta", "success");
  } catch (err) {
    if (err instanceof AuthError) return;
    if (statusEl) statusEl.textContent = "Nepavyko.";
  }
}

async function seedCertPhotos(projectId) {
  const ok = confirm("Sukurti 3 testines sertifikavimo nuotraukas (seed)?");
  if (!ok) return;
  try {
    await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/seed-cert-photos`, {
      method: "POST",
      body: JSON.stringify({ count: 3 }),
    });
    showToast("Nuotraukos sukurtos", "success");
  } catch (err) {
    if (err instanceof AuthError) return;
  }
}

async function certifyProject(projectId) {
  const ok = confirm("Sertifikuoti projekta? (reikia >=3 sertifikavimo nuotrauku ir statuso PENDING_EXPERT)");
  if (!ok) return;
  try {
    await authFetch("/api/v1/certify-project", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, checklist: {}, notes: "" }),
    });
    showToast("Projektas sertifikuotas", "success");
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
  }
}

async function adminConfirmProject(projectId) {
  const reason = prompt("Iveskite priezasti (privaloma):");
  if (!reason) return;
  try {
    await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/admin-confirm`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    showToast("Projektas aktyvuotas", "success");
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
  }
}
