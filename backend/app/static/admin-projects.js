/* VejaPRO Admin — Projects Page JS (V6.1 Operator Compact) */
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  initProjectsPage();
});

// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------

let _items = [];
let _nextCursor = null;
let _asOf = null;
let _itemIds = new Set();

let _ctrlProjectId = null;
let _ctrlProjectData = null;

let _rowsEl = null;
let _countEl = null;
let _loadMoreBtn = null;

let _currentStatus = "";
let _currentAttentionOnly = true;

// ---------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------

function initProjectsPage() {
  initTokenUI();
  initListUI();
  initFilterChips();
  initCreateUI();
  initControlModal();
  initDeepLinks();

  if (Auth.isSet()) {
    fetchProjects({ reset: true });
    if (typeof startDashboardSSE === "function") startDashboardSSE();
  }
  handleDeepLink();
}

// ---------------------------------------------------------------------
// Token UI (reuse from shared)
// ---------------------------------------------------------------------

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

// ---------------------------------------------------------------------
// List UI
// ---------------------------------------------------------------------

function initListUI() {
  _rowsEl = document.getElementById("rows");
  _countEl = document.getElementById("count");
  _loadMoreBtn = document.getElementById("btnLoadMore");

  if (_loadMoreBtn) _loadMoreBtn.addEventListener("click", () => fetchProjects({ reset: false }));
}

function initFilterChips() {
  const chips = document.querySelectorAll("#filterChips .filter-chip");
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      _currentStatus = (chip.dataset.status || "").trim();
      _currentAttentionOnly = (chip.dataset.attention || "") === "true";
      fetchProjects({ reset: true });
    });
  });
  _currentStatus = "";
  _currentAttentionOnly = true;
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
          client_info: { name, client_id: clientId, ...(phone ? { phone } : {}) },
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

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------

function _isUuid(v) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(v || ""));
}

function _getViewParams(cursor) {
  const params = new URLSearchParams();
  params.set("limit", "50");
  if (_currentStatus) params.set("status", _currentStatus);
  params.set("attention_only", _currentAttentionOnly ? "true" : "false");
  if (cursor) params.append("cursor", cursor);
  if (_asOf && !cursor) params.set("as_of", _asOf);
  return params.toString();
}

function _shortenId(value) {
  if (!value) return "-";
  return String(value).slice(0, 8) + "...";
}

function _urgencyFromFlags(flags) {
  if (!flags || !flags.length) return "low";
  if (flags.includes("pending_confirmation")) return "high";
  if (flags.includes("failed_outbox")) return "medium";
  return "low";
}

function _flagLabel(flag) {
  const map = {
    pending_confirmation: "Laukia patvirtinimo",
    failed_outbox: "Siuntimo klaida",
    missing_deposit: "Nera inaso",
    missing_final: "Nera galutinio",
    stale_paid_no_schedule: "Nesuplanuotas",
  };
  return map[flag] || flag;
}

function _setCount() {
  if (!_countEl) return;
  _countEl.textContent = _items.length ? (_items.length + " irasu") : "0 irasu";
}

function _nowCompact() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + pad(d.getHours()) + pad(d.getMinutes()) + pad(d.getSeconds());
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

// ---------------------------------------------------------------------
// Compact row renderer (6 columns)
// ---------------------------------------------------------------------

function _renderRows() {
  if (!_rowsEl) return;
  _rowsEl.innerHTML = "";

  if (!_items.length) {
    _rowsEl.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--ink-muted);">Nera irasu</td></tr>';
    _setCount();
    if (_loadMoreBtn) _loadMoreBtn.disabled = true;
    return;
  }

  for (const item of _items) {
    const flags = item.attention_flags || [];
    const urgency = _urgencyFromFlags(flags);
    const nba = item.next_best_action;

    // Flag pills HTML
    let flagsHtml = "";
    if (flags.length) {
      flagsHtml = '<div class="flag-pills">' + flags.map((f) => {
        const cls = f === "pending_confirmation" ? "high" : f === "failed_outbox" ? "medium" : "";
        return `<span class="flag-pill ${cls}">${escapeHtml(_flagLabel(f))}</span>`;
      }).join("") + "</div>";
    }

    // Primary action button
    const primaryBtn = nba && nba.type
      ? `<button class="btn btn-xs btn-primary" data-action="quick" data-type="${escapeHtml(nba.type)}" data-id="${escapeHtml(item.id)}" data-key="${escapeHtml(item.client_key || "")}">${escapeHtml(nba.label || nba.type)}</button>`
      : '<span style="color:var(--ink-muted);font-size:11px;">—</span>';

    const tr = document.createElement("tr");
    tr.className = "row-urgency-" + urgency;
    tr.innerHTML = `
      <td data-label="Klientas">
        <div class="row-main">${escapeHtml(item.client_masked || "-")}</div>
        <div class="row-sub">${escapeHtml(_shortenId(item.id))}</div>
      </td>
      <td data-label="Statusas">
        ${statusPill(item.status)}
        ${flagsHtml}
      </td>
      <td data-label="Problema">
        <span class="row-sub">${escapeHtml(item.stuck_reason || "—")}</span>
      </td>
      <td data-label="Paskutinis">
        <span class="row-sub">${escapeHtml(formatDate(item.updated_at))}</span>
      </td>
      <td data-label="Veiksmas">${primaryBtn}</td>
      <td data-label="Valdyti">
        <button class="btn btn-xs btn-secondary" data-action="control" data-id="${escapeHtml(item.id)}">Valdyti</button>
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
      const type = event.currentTarget.getAttribute("data-type");
      const key = event.currentTarget.getAttribute("data-key");
      if (!action || !id) return;
      if (action === "quick") {
        // Handle quick actions locally when on projects page
        _handleQuickAction(type, id, key);
        return;
      }
      if (action === "control") return openControlModal(id);
    });
  });
}

function _handleQuickAction(type, projectId, clientKey) {
  switch (type) {
    case "record_deposit":
      openControlModal(projectId, "ctrlActionDeposit");
      break;
    case "record_final":
      openControlModal(projectId, "ctrlActionFinal");
      break;
    case "schedule_visit":
      window.location.href = "/admin/calendar";
      break;
    case "assign_expert":
      openControlModal(projectId, "ctrlActionAssign");
      break;
    case "certify_project":
      openControlModal(projectId, "ctrlActionCertify");
      break;
    case "resend_confirmation":
      if (clientKey) window.location.href = "/admin/customers/" + encodeURIComponent(clientKey);
      else showToast("Persiuntimas galimas kliento profilyje.", "info");
      break;
    default:
      openControlModal(projectId);
  }
}

// ---------------------------------------------------------------------
// AI Summary
// ---------------------------------------------------------------------

function _renderAiSummary() {
  const pill = document.getElementById("aiSummaryPill");
  if (!pill) return;
  const count = (_items || []).filter((it) => (it.attention_flags || []).length > 0).length;
  if (count > 0) {
    const scheduleCount = (_items || []).filter((it) => {
      const nba = it.next_best_action;
      return nba && nba.type === "schedule_visit";
    }).length;
    pill.textContent = scheduleCount > 0
      ? `Rekomenduojama: ${scheduleCount} laukiantys schedule`
      : `${count} reikalauja demesio`;
    pill.style.display = "inline-block";
  } else {
    pill.style.display = "none";
  }
}

// ---------------------------------------------------------------------
// Fetch projects
// ---------------------------------------------------------------------

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
    _asOf = null;
    _renderRows();
  }

  const query = _getViewParams(_nextCursor);
  try {
    const resp = await authFetch("/api/v1/admin/projects/view?" + query);
    const data = await resp.json();
    const newItems = (data.items || []).filter((it) => {
      if (_itemIds.has(it.id)) return false;
      _itemIds.add(it.id);
      return true;
    });
    _items = _items.concat(newItems);
    _nextCursor = data.next_cursor || null;
    _asOf = data.as_of || _asOf;
    _renderRows();
    _renderAiSummary();
  } catch (err) {
    if (err instanceof AuthError) return;
    showToast("Nepavyko ikelti projektu.", "error");
  }
}

// ---------------------------------------------------------------------
// Control Modal
// ---------------------------------------------------------------------

const _allCtrlSections = [
  "ctrlActionFinalQuote", "ctrlActionDeposit", "ctrlActionSchedule", "ctrlActionAssign",
  "ctrlActionCertify", "ctrlActionFinal", "ctrlActionConfirm", "ctrlActionDone",
];

function _hideAllCtrlSections() {
  for (const id of _allCtrlSections) {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  }
}

function _showCtrlSection(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = "block";
}

function openControlModal(projectId, forceSection) {
  _ctrlProjectId = projectId;
  _ctrlProjectData = _items.find((it) => it.id === projectId) || null;

  const clientNameEl = document.getElementById("ctrlClientName");
  const metaEl = document.getElementById("ctrlProjectMeta");
  const pillsEl = document.getElementById("ctrlPills");
  const titleEl = document.getElementById("ctrlTitle");
  const statusEl = document.getElementById("ctrlStatus");
  const jsonEl = document.getElementById("ctrlDetailsJson");

  // Reset
  _hideAllCtrlSections();
  if (statusEl) statusEl.textContent = "";
  // Hide advanced result areas
  const advHide = ["ctrlClientTokenResult", "ctrlStripeLinkResult", "ctrlAdvAssignResult"];
  advHide.forEach((id) => { const el = document.getElementById(id); if (el) el.style.display = "none"; });

  const item = _ctrlProjectData;
  if (item) {
    if (titleEl) titleEl.textContent = "Projekto valdymas (" + _shortenId(item.id) + ")";
    if (clientNameEl) clientNameEl.textContent = item.client_masked || "-";

    // Meta line: dates, contractor, expert
    const parts = [];
    if (item.scheduled_for) parts.push("Suplanuota: " + formatDate(item.scheduled_for));
    if (item.assigned_contractor_id) parts.push("Rangovas: " + _shortenId(item.assigned_contractor_id));
    if (item.assigned_expert_id) parts.push("Ekspertas: " + _shortenId(item.assigned_expert_id));
    parts.push("Sukurta: " + formatDate(item.created_at));
    if (metaEl) metaEl.textContent = parts.join(" | ");

    // Pills
    if (pillsEl) {
      pillsEl.innerHTML = statusPill(item.status);
      if (item.deposit_state) pillsEl.innerHTML += ` <span class="pill pill-gray" style="font-size:10px;">Dep: ${escapeHtml(item.deposit_state)}</span>`;
      if (item.final_state) pillsEl.innerHTML += ` <span class="pill pill-gray" style="font-size:10px;">Fin: ${escapeHtml(item.final_state)}</span>`;
    }

    // Audit link
    const auditLink = document.getElementById("ctrlBtnAudit");
    if (auditLink) auditLink.href = "/admin/audit?entity_type=project&entity_id=" + encodeURIComponent(item.id);

    // JSON details
    if (jsonEl) jsonEl.textContent = JSON.stringify(_redactPII(item), null, 2);

    // Determine which section to show
    const section = forceSection || _determineSection(item);
    _showCtrlSection(section);
    _prefillSection(section, item);
  } else {
    if (titleEl) titleEl.textContent = "Projekto valdymas";
    if (clientNameEl) clientNameEl.textContent = "Projektas nerastas saraso";
    if (metaEl) metaEl.textContent = "ID: " + projectId;
    if (pillsEl) pillsEl.innerHTML = "";
    if (jsonEl) jsonEl.textContent = "{}";
    // Try to load project details from API
    _loadProjectFromApi(projectId, forceSection);
  }

  modalOpen("controlBackdrop");
}

function _determineSection(item) {
  if (!item) return "ctrlActionDone";
  const s = item.status;
  if (s === "DRAFT") {
    if (item.quote_pending === true || (item.client_info && item.client_info.quote_pending === true)) return "ctrlActionFinalQuote";
    return "ctrlActionDeposit";
  }
  if (s === "PAID") return "ctrlActionSchedule";
  if (s === "SCHEDULED") return "ctrlActionAssign";
  if (s === "PENDING_EXPERT") return "ctrlActionCertify";
  if (s === "CERTIFIED") {
    if (item.final_state === "paid") return "ctrlActionConfirm";
    return "ctrlActionFinal";
  }
  if (s === "ACTIVE") return "ctrlActionDone";
  return "ctrlActionDone";
}

function _updateFqMethods(svc) {
  const el = document.getElementById("ctrlFqMethod");
  if (!el) return;
  const methods = {
    vejos_irengimas: [
      { value: "sejimas", label: "Sejimas" },
      { value: "ritinine", label: "Ritinine veja" },
      { value: "hidroseija", label: "Hidroseija" },
    ],
    apleisto_sklypo_tvarkymas: [
      { value: "mazas", label: "Mazas (<20cm)" },
      { value: "vidutinis", label: "Vidutinis (20-50cm)" },
      { value: "didelis", label: "Didelis (>50cm)" },
    ],
  };
  const opts = methods[svc] || methods.vejos_irengimas;
  el.innerHTML = opts.map(function (o) { return '<option value="' + o.value + '">' + o.label + '</option>'; }).join("");
}

function _prefillSection(section, item) {
  if (section === "ctrlActionFinalQuote") {
    const ci = item.client_info || item._raw_client_info || {};
    const est = (ci.estimate) || {};
    const svcEl = document.getElementById("ctrlFqService");
    const methEl = document.getElementById("ctrlFqMethod");
    const areaEl = document.getElementById("ctrlFqArea");
    const totalEl = document.getElementById("ctrlFqTotal");
    const notesEl = document.getElementById("ctrlFqNotes");
    if (svcEl && est.service) svcEl.value = est.service;
    if (methEl && est.method) methEl.value = est.method;
    if (areaEl) areaEl.value = est.area_m2 || item.area_m2 || "";
    if (totalEl) totalEl.value = est.total_eur || "";
    if (notesEl) notesEl.value = "";
    // Update method options based on service
    _updateFqMethods(svcEl ? svcEl.value : "vejos_irengimas");
    if (methEl && est.method) methEl.value = est.method;
    if (svcEl) svcEl.addEventListener("change", function () { _updateFqMethods(svcEl.value); });
  }
  if (section === "ctrlActionDeposit") {
    const providerEl = document.getElementById("ctrlDepositProviderId");
    if (providerEl) providerEl.value = `MANUAL-${(item.id || "").slice(0, 8)}-${_nowCompact()}`;
    const amountEl = document.getElementById("ctrlDepositAmount");
    if (amountEl) amountEl.value = "";
    const receiptEl = document.getElementById("ctrlDepositReceipt");
    if (receiptEl) receiptEl.value = "";
    const notesEl = document.getElementById("ctrlDepositNotes");
    if (notesEl) notesEl.value = "";
  }
  if (section === "ctrlActionFinal") {
    const providerEl = document.getElementById("ctrlFinalProviderId");
    if (providerEl) providerEl.value = `MANUAL-${(item.id || "").slice(0, 8)}-${_nowCompact()}`;
    const amountEl = document.getElementById("ctrlFinalAmount");
    if (amountEl) amountEl.value = "";
    const receiptEl = document.getElementById("ctrlFinalReceipt");
    if (receiptEl) receiptEl.value = "";
    const notesEl = document.getElementById("ctrlFinalNotes");
    if (notesEl) notesEl.value = "";
  }
  if (section === "ctrlActionAssign") {
    const uuidEl = document.getElementById("ctrlAssignUuid");
    if (uuidEl) uuidEl.value = "";
    const titleEl = document.getElementById("ctrlAssignTitle");
    if (titleEl) titleEl.textContent = "Priskirti eksperta";
  }
  if (section === "ctrlActionConfirm") {
    const reasonEl = document.getElementById("ctrlConfirmReason");
    if (reasonEl) reasonEl.value = "";
  }
}

async function _loadProjectFromApi(projectId, forceSection) {
  try {
    const resp = await authFetch(`/api/v1/projects/${encodeURIComponent(projectId)}`);
    const data = await resp.json();
    // Build a minimal item for display
    const item = {
      id: data.id || projectId,
      status: data.status || "DRAFT",
      client_masked: data.client_info ? maskEmail(data.client_info.email || "") || data.client_info.name || "-" : "-",
      scheduled_for: data.scheduled_for,
      assigned_contractor_id: data.assigned_contractor_id,
      assigned_expert_id: data.assigned_expert_id,
      created_at: data.created_at,
      updated_at: data.updated_at,
      deposit_state: data.deposit_state,
      final_state: data.final_state,
      attention_flags: [],
      stuck_reason: null,
      next_best_action: null,
      client_key: data.client_info ? data.client_info.client_id : null,
      client_info: data.client_info || null,
      area_m2: data.area_m2,
    };
    _ctrlProjectData = item;

    const clientNameEl = document.getElementById("ctrlClientName");
    const metaEl = document.getElementById("ctrlProjectMeta");
    const pillsEl = document.getElementById("ctrlPills");
    const jsonEl = document.getElementById("ctrlDetailsJson");

    if (clientNameEl) clientNameEl.textContent = item.client_masked;
    const parts = [];
    if (item.scheduled_for) parts.push("Suplanuota: " + formatDate(item.scheduled_for));
    if (item.assigned_contractor_id) parts.push("Rangovas: " + _shortenId(item.assigned_contractor_id));
    if (item.assigned_expert_id) parts.push("Ekspertas: " + _shortenId(item.assigned_expert_id));
    parts.push("Sukurta: " + formatDate(item.created_at));
    if (metaEl) metaEl.textContent = parts.join(" | ");

    if (pillsEl) pillsEl.innerHTML = statusPill(item.status);
    if (jsonEl) jsonEl.textContent = JSON.stringify(_redactPII(data), null, 2);

    const auditLink = document.getElementById("ctrlBtnAudit");
    if (auditLink) auditLink.href = "/admin/audit?entity_type=project&entity_id=" + encodeURIComponent(item.id);

    _hideAllCtrlSections();
    const section = forceSection || _determineSection(item);
    _showCtrlSection(section);
    _prefillSection(section, item);
  } catch (err) {
    if (err instanceof AuthError) return;
    const statusEl = document.getElementById("ctrlStatus");
    if (statusEl) statusEl.textContent = "Nepavyko ikelti projekto duomenu.";
  }
}

function closeControlModal() {
  modalClose("controlBackdrop");
  _ctrlProjectId = null;
  _ctrlProjectData = null;
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

// ---------------------------------------------------------------------
// Control Modal: Wire up all actions
// ---------------------------------------------------------------------

function initControlModal() {
  // Close
  const btnClose = document.getElementById("btnCtrlClose");
  if (btnClose) btnClose.addEventListener("click", closeControlModal);
  const backdrop = document.getElementById("controlBackdrop");
  if (backdrop) backdrop.addEventListener("click", (e) => {
    if (e.target && e.target.id === "controlBackdrop") closeControlModal();
  });

  // --- Primary actions ---

  // Final quote
  const btnFinalQuote = document.getElementById("ctrlBtnSaveFinalQuote");
  if (btnFinalQuote) btnFinalQuote.addEventListener("click", _ctrlSaveFinalQuote);

  // Deposit
  const btnDeposit = document.getElementById("ctrlBtnRecordDeposit");
  if (btnDeposit) btnDeposit.addEventListener("click", _ctrlRecordPayment.bind(null, "DEPOSIT"));

  const btnWaive = document.getElementById("ctrlBtnWaiveDeposit");
  if (btnWaive) btnWaive.addEventListener("click", _ctrlWaiveDeposit);

  // Final
  const btnFinal = document.getElementById("ctrlBtnRecordFinal");
  if (btnFinal) btnFinal.addEventListener("click", _ctrlRecordPayment.bind(null, "FINAL"));

  // Assign expert (primary)
  const btnAssign = document.getElementById("ctrlBtnAssign");
  if (btnAssign) btnAssign.addEventListener("click", () => {
    const uuid = ((document.getElementById("ctrlAssignUuid") || {}).value || "").trim();
    if (!uuid) { _ctrlSetStatus("Iveskite UUID."); return; }
    _ctrlDoAssign(_ctrlProjectId, "expert", uuid);
  });

  // Certify
  const btnCertify = document.getElementById("ctrlBtnCertify");
  if (btnCertify) btnCertify.addEventListener("click", () => _ctrlCertify(_ctrlProjectId));

  // Seed photos
  const btnSeed = document.getElementById("ctrlBtnSeedPhotos");
  if (btnSeed) btnSeed.addEventListener("click", () => _ctrlSeedPhotos(_ctrlProjectId));

  // Admin confirm
  const btnConfirm = document.getElementById("ctrlBtnAdminConfirm");
  if (btnConfirm) btnConfirm.addEventListener("click", () => {
    const reason = ((document.getElementById("ctrlConfirmReason") || {}).value || "").trim();
    if (!reason) { _ctrlSetStatus("Iveskite priezasti."); return; }
    _ctrlAdminConfirm(_ctrlProjectId, reason);
  });

  // --- Advanced actions ---

  // Client token
  const btnToken = document.getElementById("ctrlBtnClientToken");
  if (btnToken) btnToken.addEventListener("click", () => _ctrlGenClientToken(_ctrlProjectId));

  // Copy token/link
  const btnCopyToken = document.getElementById("ctrlBtnCopyToken");
  if (btnCopyToken) btnCopyToken.addEventListener("click", () => {
    const v = ((document.getElementById("ctrlClientTokenValue") || {}).value || "").trim();
    if (v) copyToClipboard(v);
  });
  const btnCopyLink = document.getElementById("ctrlBtnCopyLink");
  if (btnCopyLink) btnCopyLink.addEventListener("click", () => {
    const meta = ((document.getElementById("ctrlClientTokenMeta") || {}).dataset || {}).link || "";
    if (meta) copyToClipboard(meta);
  });

  // Stripe link
  const btnStripe = document.getElementById("ctrlBtnStripeLink");
  if (btnStripe) btnStripe.addEventListener("click", () => {
    const el = document.getElementById("ctrlStripeLinkResult");
    if (el) el.style.display = el.style.display === "none" ? "block" : "none";
  });
  const btnCreateStripe = document.getElementById("ctrlBtnCreateStripe");
  if (btnCreateStripe) btnCreateStripe.addEventListener("click", () => _ctrlCreateStripeLink(_ctrlProjectId));
  const btnCopyStripe = document.getElementById("ctrlBtnCopyStripe");
  if (btnCopyStripe) btnCopyStripe.addEventListener("click", () => {
    const v = ((document.getElementById("ctrlStripeLinkValue") || {}).value || "").trim();
    if (v) copyToClipboard(v);
  });

  // Assign contractor / expert (advanced)
  const btnAssignContractor = document.getElementById("ctrlBtnAssignContractor");
  if (btnAssignContractor) btnAssignContractor.addEventListener("click", () => {
    const el = document.getElementById("ctrlAdvAssignResult");
    if (el) el.style.display = el.style.display === "none" ? "block" : "none";
    const typeEl = document.getElementById("ctrlAdvAssignType");
    if (typeEl) typeEl.value = "contractor";
  });
  const btnAssignExpert2 = document.getElementById("ctrlBtnAssignExpert2");
  if (btnAssignExpert2) btnAssignExpert2.addEventListener("click", () => {
    const el = document.getElementById("ctrlAdvAssignResult");
    if (el) el.style.display = el.style.display === "none" ? "block" : "none";
    const typeEl = document.getElementById("ctrlAdvAssignType");
    if (typeEl) typeEl.value = "expert";
  });
  const btnAdvAssign = document.getElementById("ctrlBtnAdvAssign");
  if (btnAdvAssign) btnAdvAssign.addEventListener("click", () => {
    const kind = ((document.getElementById("ctrlAdvAssignType") || {}).value || "expert");
    const uuid = ((document.getElementById("ctrlAdvAssignUuid") || {}).value || "").trim();
    const statusEl = document.getElementById("ctrlAdvAssignStatus");
    if (!uuid) { if (statusEl) statusEl.textContent = "Iveskite UUID."; return; }
    _ctrlDoAssign(_ctrlProjectId, kind, uuid, statusEl);
  });
}

// ---------------------------------------------------------------------
// Control Modal: Action implementations
// ---------------------------------------------------------------------

function _ctrlSetStatus(msg) {
  const el = document.getElementById("ctrlStatus");
  if (el) el.textContent = msg;
}

async function _ctrlSaveFinalQuote() {
  const projectId = _ctrlProjectId;
  if (!projectId) return;

  const service = ((document.getElementById("ctrlFqService") || {}).value || "").trim();
  const method = ((document.getElementById("ctrlFqMethod") || {}).value || "").trim();
  const area = Number(((document.getElementById("ctrlFqArea") || {}).value || "").trim());
  const total = Number(((document.getElementById("ctrlFqTotal") || {}).value || "").trim());
  const notes = ((document.getElementById("ctrlFqNotes") || {}).value || "").trim();

  if (!service || !method) { _ctrlSetStatus("Pasirinkite paslauga ir metoda."); return; }
  if (!Number.isFinite(area) || area <= 0) { _ctrlSetStatus("Iveskite plota (> 0)."); return; }
  if (!Number.isFinite(total) || total <= 0) { _ctrlSetStatus("Iveskite galutine kaina (> 0)."); return; }

  _ctrlSetStatus("Issaugoma...");
  try {
    await authFetch(`/api/v1/admin/ops/project/${encodeURIComponent(projectId)}/final-quote`, {
      method: "POST",
      body: JSON.stringify({
        service, method,
        actual_area_m2: area,
        final_total_eur: total,
        ...(notes ? { notes } : {}),
      }),
    });
    showToast("Galutine kaina issaugota", "success");
    _ctrlSetStatus("OK");
    closeControlModal();
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
    _ctrlSetStatus("Nepavyko issaugoti galutines kainos.");
  }
}

async function _ctrlRecordPayment(paymentType) {
  const projectId = _ctrlProjectId;
  if (!projectId) return;

  const prefix = paymentType === "FINAL" ? "ctrlFinal" : "ctrlDeposit";
  const amount = Number(((document.getElementById(prefix + "Amount") || {}).value || "").trim());
  const method = ((document.getElementById(prefix + "Method") || {}).value || "BANK_TRANSFER").trim().toUpperCase();
  const currency = ((document.getElementById(prefix + "Currency") || {}).value || "EUR").trim().toUpperCase();
  const providerId = ((document.getElementById(prefix + "ProviderId") || {}).value || "").trim();
  const receipt = ((document.getElementById(prefix + "Receipt") || {}).value || "").trim();
  const notes = ((document.getElementById(prefix + "Notes") || {}).value || "").trim();

  if (!providerId) { _ctrlSetStatus("Reikia idempotencijos ID."); return; }
  if (!Number.isFinite(amount) || amount <= 0) { _ctrlSetStatus("Iveskite suma (> 0)."); return; }
  if (!currency || currency.length !== 3) { _ctrlSetStatus("Valiuta turi buti 3 raidziu."); return; }

  _ctrlSetStatus("Siunciama...");
  try {
    const resp = await authFetch(`/api/v1/projects/${encodeURIComponent(projectId)}/payments/manual`, {
      method: "POST",
      body: JSON.stringify({
        payment_type: paymentType,
        amount, currency, payment_method: method,
        provider_event_id: providerId,
        ...(receipt ? { receipt_no: receipt } : {}),
        ...(notes ? { notes } : {}),
      }),
    });
    const data = await resp.json();
    showToast(data.idempotent ? "Mokejimas jau buvo irasytas (idempotent)" : "Mokejimas irasytas", "success");
    _ctrlSetStatus("OK");
    closeControlModal();
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
    _ctrlSetStatus("Nepavyko irasyti mokejimo.");
  }
}

async function _ctrlWaiveDeposit() {
  const projectId = _ctrlProjectId;
  if (!projectId) return;

  const ok = confirm("Atideti inasa? (tik DRAFT projektams)");
  if (!ok) return;

  const currency = ((document.getElementById("ctrlDepositCurrency") || {}).value || "EUR").trim().toUpperCase();
  let providerId = ((document.getElementById("ctrlDepositProviderId") || {}).value || "").trim();
  const notes = ((document.getElementById("ctrlDepositNotes") || {}).value || "").trim();
  if (!providerId || providerId.startsWith("MANUAL-")) {
    providerId = `WAIVE-${projectId.slice(0, 8)}-${_nowCompact()}`;
  }

  _ctrlSetStatus("Siunciama...");
  try {
    const resp = await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/payments/deposit-waive`, {
      method: "POST",
      body: JSON.stringify({ provider_event_id: providerId, currency, ...(notes ? { notes } : {}) }),
    });
    const data = await resp.json();
    showToast(data.idempotent ? "Inasas jau buvo atidetas (idempotent)" : "Inasas atidetas", "success");
    _ctrlSetStatus("OK");
    closeControlModal();
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
    _ctrlSetStatus("Nepavyko.");
  }
}

async function _ctrlDoAssign(projectId, kind, userId, statusEl) {
  if (!projectId || !userId) return;
  const sEl = statusEl || document.getElementById("ctrlStatus");
  if (sEl) sEl.textContent = "Priskiriama...";

  const path = kind === "contractor"
    ? `/api/v1/admin/projects/${encodeURIComponent(projectId)}/assign-contractor`
    : `/api/v1/admin/projects/${encodeURIComponent(projectId)}/assign-expert`;

  try {
    await authFetch(path, { method: "POST", body: JSON.stringify({ user_id: userId }) });
    showToast("Priskyrimas atnaujintas", "success");
    if (sEl) sEl.textContent = "OK";
    closeControlModal();
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
    if (sEl) sEl.textContent = "Nepavyko.";
  }
}

async function _ctrlCertify(projectId) {
  if (!projectId) return;
  const ok = confirm("Sertifikuoti projekta? (reikia >=3 sertifikavimo nuotrauku ir statuso PENDING_EXPERT)");
  if (!ok) return;
  _ctrlSetStatus("Sertifikuojama...");
  try {
    await authFetch("/api/v1/certify-project", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, checklist: {}, notes: "" }),
    });
    showToast("Projektas sertifikuotas", "success");
    _ctrlSetStatus("OK");
    closeControlModal();
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
    _ctrlSetStatus("Nepavyko sertifikuoti.");
  }
}

async function _ctrlSeedPhotos(projectId) {
  if (!projectId) return;
  const ok = confirm("Sukurti 3 testines sertifikavimo nuotraukas (seed)?");
  if (!ok) return;
  _ctrlSetStatus("Kuriamos nuotraukos...");
  try {
    await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/seed-cert-photos`, {
      method: "POST",
      body: JSON.stringify({ count: 3 }),
    });
    showToast("Nuotraukos sukurtos", "success");
    _ctrlSetStatus("Nuotraukos sukurtos.");
  } catch (err) {
    if (err instanceof AuthError) return;
    _ctrlSetStatus("Nepavyko sukurti nuotrauku.");
  }
}

async function _ctrlAdminConfirm(projectId, reason) {
  if (!projectId || !reason) return;
  _ctrlSetStatus("Aktyvuojama...");
  try {
    await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/admin-confirm`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    showToast("Projektas aktyvuotas", "success");
    _ctrlSetStatus("OK");
    closeControlModal();
    fetchProjects({ reset: true });
  } catch (err) {
    if (err instanceof AuthError) return;
    _ctrlSetStatus("Nepavyko aktyvuoti.");
  }
}

async function _ctrlGenClientToken(projectId) {
  if (!projectId) return;
  const resultEl = document.getElementById("ctrlClientTokenResult");
  const tokenEl = document.getElementById("ctrlClientTokenValue");
  const metaEl = document.getElementById("ctrlClientTokenMeta");

  if (resultEl) resultEl.style.display = "block";
  if (tokenEl) tokenEl.value = "Generuojamas...";
  if (metaEl) { metaEl.textContent = ""; metaEl.dataset.link = ""; }

  try {
    const resp = await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/client-token`);
    const data = await resp.json();
    const token = Auth.normalize(data.token || "");
    if (!token) {
      if (tokenEl) tokenEl.value = "Zetonas nerastas.";
      return;
    }
    const portalUrl = `/client?project=${encodeURIComponent(projectId)}&token=${encodeURIComponent(token)}`;
    if (tokenEl) tokenEl.value = token;
    if (metaEl) {
      metaEl.textContent = `Kliento ID: ${data.client_id || "-"} | Galioja iki: ${data.expires_at || "-"}`;
      metaEl.dataset.link = portalUrl;
    }
  } catch (err) {
    if (err instanceof AuthError) return;
    if (tokenEl) tokenEl.value = "Nepavyko.";
  }
}

async function _ctrlCreateStripeLink(projectId) {
  if (!projectId) return;
  const typeEl = document.getElementById("ctrlStripeType");
  const amountEl = document.getElementById("ctrlStripeAmount");
  const currencyEl = document.getElementById("ctrlStripeCurrency");
  const linkEl = document.getElementById("ctrlStripeLinkValue");
  const statusEl = document.getElementById("ctrlStripeStatus");

  const payment_type = ((typeEl || {}).value || "DEPOSIT").toUpperCase();
  const amount = Number(((amountEl || {}).value || "").trim());
  const currency = ((currencyEl || {}).value || "EUR").trim().toUpperCase();

  if (!Number.isFinite(amount) || amount <= 0) {
    if (statusEl) statusEl.textContent = "Iveskite suma (> 0).";
    return;
  }

  if (statusEl) statusEl.textContent = "Kuriama...";
  try {
    const resp = await authFetch(`/api/v1/admin/projects/${encodeURIComponent(projectId)}/payment-link`, {
      method: "POST",
      body: JSON.stringify({ payment_type, amount, currency }),
    });
    const data = await resp.json();
    if (linkEl) linkEl.value = data.url || "";
    if (statusEl) statusEl.textContent = "Nuoroda sukurta.";
    showToast("Stripe nuoroda sukurta", "success");
  } catch (err) {
    if (err instanceof AuthError) return;
    if (statusEl) statusEl.textContent = "Nepavyko.";
  }
}

// ---------------------------------------------------------------------
// Deep links
// ---------------------------------------------------------------------

function initDeepLinks() {
  window.addEventListener("hashchange", handleDeepLink);
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
      openControlModal(projectId, kind === "FINAL" ? "ctrlActionFinal" : "ctrlActionDeposit");
    }
    return;
  }

  // #assign-expert-<uuid> or #assign-contractor-<uuid>
  const assignMatch = raw.match(/^assign-(expert|contractor)-(.+)$/i);
  if (assignMatch) {
    const projectId = String(assignMatch[2] || "").trim();
    if (_isUuid(projectId)) {
      openControlModal(projectId, "ctrlActionAssign");
    }
    return;
  }

  // #certify-<uuid>
  const certMatch = raw.match(/^certify-(.+)$/i);
  if (certMatch) {
    const projectId = String(certMatch[1] || "").trim();
    if (_isUuid(projectId)) {
      openControlModal(projectId, "ctrlActionCertify");
    }
    return;
  }

  // #<uuid> (open control modal)
  if (_isUuid(raw)) {
    openControlModal(raw);
  }
}
