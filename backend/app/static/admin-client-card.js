"use strict";

/* =========================================================================
   Admin Client Card — AI Pricing Workflow (V3.0)
   ========================================================================= */

const ClientCardState = {
  clientKey: null,
  card: null,
  projectId: null,
  aiPricing: null,
  aiPricingMeta: null,
  aiPricingDecision: null,
  survey: null,
  featureFlags: {},
  busy: false,
};

const CLIENT_CARD_LIMITS = {
  projects_limit: 10,
  payments_limit: 30,
  calls_limit: 20,
  photos_limit: 30,
  timeline_limit: 50,
};

const OBSTACLE_CODES = new Set([
  "TREES",
  "FENCE",
  "UTILITIES",
  "PAVERS",
  "SLOPE_BREAK",
  "DRAINAGE",
  "OTHER_CODED",
]);

const FACTOR_LABELS = {
  slope_adjustment: "Nuolydio korekcija",
  soil_preparation: "Dirvos paruosimas",
  vegetation_removal: "Augmenijos valymas",
  access_difficulty: "Priejimo sudetingumas",
  distance_surcharge: "Atstumo antkainis",
  obstacle_clearing: "Kliuciu salinimas",
  irrigation_bonus: "Laistymo sistemos nuolaida",
  seasonal_demand: "Sezonine paklausa",
};

const DECISION_LABELS = {
  approve: "Patvirtinta",
  edit: "Koreguota",
  ignore: "Ignoruota",
};

/* =========================================================================
   Helpers
   ========================================================================= */

function getClientKeyFromPath() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 1] || "");
}

function setStatus(message, isError) {
  const el = document.getElementById("clientCardStatus");
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("error", !!isError);
}

function setBusy(v) {
  ClientCardState.busy = !!v;
  updateActionButtons();
}

function getFingerprint() {
  const meta = ClientCardState.aiPricingMeta || {};
  return typeof meta.fingerprint === "string" ? meta.fingerprint : "";
}

function hasDecision() {
  return !!ClientCardState.aiPricingDecision;
}

function canApprove() {
  return (
    !ClientCardState.busy &&
    !!ClientCardState.projectId &&
    !!ClientCardState.aiPricing &&
    ClientCardState.aiPricing.status === "ok" &&
    !!getFingerprint() &&
    !hasDecision()
  );
}

function canEditOrIgnore() {
  return !ClientCardState.busy && !!ClientCardState.projectId && !!ClientCardState.aiPricing && !!getFingerprint();
}

function canIgnore() {
  return canEditOrIgnore() && !hasDecision();
}

function confidencePill(bucket) {
  const map = { GREEN: "pill-success", YELLOW: "pill-warning", RED: "pill-error" };
  const cls = map[bucket] || "pill-info";
  return '<span class="pill ' + cls + '">' + escapeHtml(bucket || "-") + "</span>";
}

function factorLabel(name) {
  return FACTOR_LABELS[name] || name || "-";
}

/* =========================================================================
   Action button visibility
   ========================================================================= */

function updateActionButtons() {
  const btnGenerate = document.getElementById("btnGeneratePricing");
  const btnApprove = document.getElementById("btnApprovePricing");
  const btnEdit = document.getElementById("btnEditPricing");
  const btnIgnore = document.getElementById("btnIgnorePricing");
  const btnSurvey = document.getElementById("btnSaveSurvey");

  const pricingEnabled = !!ClientCardState.featureFlags.ai_pricing;

  if (btnGenerate) {
    btnGenerate.disabled = ClientCardState.busy || !ClientCardState.projectId;
    btnGenerate.style.display = pricingEnabled ? "" : "none";
  }
  if (btnApprove) {
    btnApprove.disabled = !canApprove();
    btnApprove.style.display = pricingEnabled ? "" : "none";
    btnApprove.title =
      !canApprove() && ClientCardState.aiPricing
        ? ClientCardState.aiPricing.status === "fallback"
          ? "Tik 'ok' statusas leidzia patvirtinti"
          : hasDecision()
            ? "Sprendimas jau priimtas"
            : ""
        : "";
  }
  if (btnEdit) {
    btnEdit.disabled = !canEditOrIgnore();
    btnEdit.style.display = pricingEnabled ? "" : "none";
  }
  if (btnIgnore) {
    btnIgnore.disabled = !canIgnore();
    btnIgnore.style.display = pricingEnabled ? "" : "none";
    btnIgnore.title = hasDecision() ? "Sprendimas jau priimtas" : "";
  }
  if (btnSurvey) btnSurvey.disabled = ClientCardState.busy || !ClientCardState.projectId;
}

/* =========================================================================
   Resolve data from card payload
   ========================================================================= */

function resolveTargetProjectId() {
  if (ClientCardState.card && ClientCardState.card.pricing_project_id) {
    return String(ClientCardState.card.pricing_project_id);
  }
  const proposalProject =
    ClientCardState.card && ClientCardState.card.proposal && ClientCardState.card.proposal.project_id;
  if (proposalProject) return String(proposalProject);
  const projects = (ClientCardState.card && ClientCardState.card.projects) || [];
  if (projects.length && projects[0].id) return String(projects[0].id);
  return null;
}

function applyCardPayload() {
  ClientCardState.projectId = resolveTargetProjectId();
  ClientCardState.aiPricing = (ClientCardState.card && ClientCardState.card.ai_pricing) || null;
  ClientCardState.aiPricingMeta = (ClientCardState.card && ClientCardState.card.ai_pricing_meta) || null;
  ClientCardState.aiPricingDecision = (ClientCardState.card && ClientCardState.card.ai_pricing_decision) || null;
  ClientCardState.survey = (ClientCardState.card && ClientCardState.card.extended_survey) || {};
  ClientCardState.featureFlags = (ClientCardState.card && ClientCardState.card.feature_flags) || {};
}

/* =========================================================================
   Render functions
   ========================================================================= */

function renderSummary() {
  const summary = (ClientCardState.card && ClientCardState.card.summary) || {};
  const title = document.getElementById("clientCardTitle");
  if (title) title.textContent = summary.display_name || "Client Card";

  const stage = document.getElementById("summaryStage");
  const deposit = document.getElementById("summaryDeposit");
  const visit = document.getElementById("summaryVisit");
  const earned = document.getElementById("summaryEarned");
  const flagsEl = document.getElementById("summaryFlags");

  if (stage) stage.innerHTML = statusPill(summary.stage || "-");
  if (deposit) deposit.textContent = summary.deposit_state || "-";
  if (visit) visit.textContent = summary.next_visit ? formatDate(summary.next_visit) : "-";
  if (earned) earned.textContent = formatCurrency(summary.earned_total || 0);

  if (!flagsEl) return;
  const flags = summary.attention_flags || [];
  if (!flags.length) {
    flagsEl.innerHTML = '<span class="pill pill-success">No alerts</span>';
    return;
  }
  flagsEl.innerHTML = flags.map((flag) => attentionPill(flag)).join(" ");
}

function renderPricing() {
  const pricing = ClientCardState.aiPricing || null;
  const meta = ClientCardState.aiPricingMeta || {};
  const decision = ClientCardState.aiPricingDecision || null;

  const pricingPanel = document.getElementById("aiPricingPanel");
  const surveySection = document.getElementById("surveySection");
  const pricingEnabled = !!ClientCardState.featureFlags.ai_pricing;

  // Hide pricing panel + survey when flag is off
  if (pricingPanel) pricingPanel.style.display = pricingEnabled ? "" : "none";
  if (surveySection) surveySection.style.display = pricingEnabled ? "" : "none";

  if (!pricingEnabled) return;

  const statusLine = document.getElementById("pricingStatusLine");
  const decisionBadge = document.getElementById("pricingDecisionBadge");
  const fallbackLine = document.getElementById("pricingFallbackLine");
  const elBase = document.getElementById("pricingBase");
  const elAdj = document.getElementById("pricingAdjustment");
  const elFinal = document.getElementById("pricingFinal");
  const elRange = document.getElementById("pricingRange");
  const elConfidence = document.getElementById("pricingConfidence");
  const elSimilar = document.getElementById("pricingSimilar");
  const elReasoning = document.getElementById("pricingReasoning");
  const elFactors = document.getElementById("pricingFactors");
  const elTimestamp = document.getElementById("pricingTimestamp");

  if (!statusLine || !elBase || !elAdj || !elFinal || !elRange || !elConfidence || !elSimilar || !elReasoning || !elFactors) {
    return;
  }

  // Decision badge
  if (decisionBadge) {
    if (decision) {
      const dAction = String(decision.action || "").toLowerCase();
      const dLabel = DECISION_LABELS[dAction] || dAction;
      const dPill = dAction === "approve" ? "pill-success" : dAction === "ignore" ? "pill-warning" : "pill-info";
      let badgeHtml =
        '<span class="pill ' + dPill + '">Sprendimas: ' + escapeHtml(dLabel) + "</span>";
      if (decision.adjusted_price) {
        badgeHtml += " &mdash; " + formatCurrency(decision.adjusted_price);
      }
      if (decision.reason) {
        badgeHtml +=
          ' <span style="color:var(--ink-muted);font-size:12px;">(' + escapeHtml(decision.reason) + ")</span>";
      }
      if (decision.decided_at) {
        badgeHtml +=
          ' <span style="color:var(--ink-muted);font-size:11px;">' + formatDate(decision.decided_at) + "</span>";
      }
      decisionBadge.innerHTML = badgeHtml;
      decisionBadge.style.display = "block";
    } else {
      decisionBadge.style.display = "none";
      decisionBadge.innerHTML = "";
    }
  }

  if (!pricing) {
    statusLine.innerHTML = '<span class="pill">AI kainu pasiulymo dar nera</span>';
    if (fallbackLine) fallbackLine.style.display = "none";
    elBase.textContent = "-";
    elAdj.textContent = "-";
    elFinal.textContent = "-";
    elRange.textContent = "-";
    elConfidence.textContent = "-";
    elSimilar.textContent = "-";
    elReasoning.textContent = "-";
    elFactors.innerHTML = '<div class="empty-row">Faktoriu nera.</div>';
    if (elTimestamp) elTimestamp.textContent = "";
    return;
  }

  const status = String(pricing.status || "").toLowerCase();
  const fingerprint = typeof meta.fingerprint === "string" ? meta.fingerprint : "";
  statusLine.innerHTML =
    confidencePill(pricing.confidence_bucket) +
    " " +
    '<span class="pill">' +
    escapeHtml((status || "unknown").toUpperCase()) +
    "</span> " +
    '<span class="section-subtitle">Projektas:</span> ' +
    escapeHtml(ClientCardState.projectId || "-") +
    " " +
    '<span class="section-subtitle">Fingerprint:</span> ' +
    escapeHtml(fingerprint ? fingerprint.slice(0, 12) + "..." : "-");

  if (fallbackLine) {
    if (status === "fallback") {
      fallbackLine.style.display = "block";
      fallbackLine.style.padding = "10px";
      fallbackLine.innerHTML =
        "<strong>Fallback:</strong> patvirtinti negalima. Galite ignoruoti arba koreguoti rankiniu budu.";
    } else {
      fallbackLine.style.display = "none";
      fallbackLine.innerHTML = "";
    }
  }

  elBase.textContent = formatCurrency(pricing.deterministic_base || 0);
  elAdj.textContent = formatCurrency(pricing.llm_adjustment || 0);
  elFinal.textContent = formatCurrency(pricing.recommended_price || 0);
  elRange.textContent =
    formatCurrency(pricing.price_range_min || 0) + " \u2013 " + formatCurrency(pricing.price_range_max || 0);
  elConfidence.innerHTML =
    confidencePill(pricing.confidence_bucket) + " (" + Number(pricing.confidence || 0).toFixed(2) + ")";
  elSimilar.textContent = String(pricing.similar_projects_used || 0);
  elReasoning.textContent = pricing.reasoning_lt || "-";

  // Factors table with LT labels
  const factors = Array.isArray(pricing.factors) ? pricing.factors : [];
  if (!factors.length) {
    elFactors.innerHTML = '<div class="empty-row">Faktoriu nera.</div>';
  } else {
    elFactors.innerHTML =
      '<div class="table-container"><table class="data-table">' +
      "<thead><tr><th>Faktorius</th><th>Poveikis (EUR)</th><th>Aprasas</th></tr></thead><tbody>" +
      factors
        .map((f) => {
          const sign = (f.impact_eur || 0) >= 0 ? "+" : "";
          return (
            "<tr>" +
            '<td data-label="Faktorius">' + escapeHtml(factorLabel(f.name)) + "</td>" +
            '<td data-label="Poveikis">' + sign + formatCurrency(f.impact_eur || 0) + "</td>" +
            '<td data-label="Aprasas">' + escapeHtml(f.description || "-") + "</td>" +
            "</tr>"
          );
        })
        .join("") +
      "</tbody></table></div>";
  }

  // Timestamp
  if (elTimestamp) {
    elTimestamp.textContent = pricing.generated_at ? "Sugeneruota: " + formatDate(pricing.generated_at) : "";
  }
}

function renderSurvey() {
  const survey = ClientCardState.survey || {};
  const setValue = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value == null ? "" : String(value);
  };
  setValue("surveySoilType", survey.soil_type || "UNKNOWN");
  setValue("surveySlopeGrade", survey.slope_grade || "FLAT");
  setValue("surveyVegetation", survey.existing_vegetation || "BARE");
  setValue("surveyAccess", survey.equipment_access || "EASY");
  setValue("surveyDistance", survey.distance_km == null ? 0 : survey.distance_km);

  // Obstacles — multi-checkbox
  const obstacleSet = new Set(Array.isArray(survey.obstacles) ? survey.obstacles : []);
  document.querySelectorAll(".obstacle-cb").forEach((cb) => {
    cb.checked = obstacleSet.has(cb.value);
  });

  const irrigation = document.getElementById("surveyIrrigation");
  if (irrigation) irrigation.checked = !!survey.irrigation_existing;
}

function renderProjects() {
  const section = document.getElementById("projectsSection");
  const rows = (ClientCardState.card && ClientCardState.card.projects) || [];
  if (!section) return;
  if (!rows.length) {
    section.innerHTML = '<div class="empty-row">Projektu nerasta.</div>';
    return;
  }

  section.innerHTML = `
    <div class="table-container">
      <table class="data-table">
        <thead><tr><th>ID</th><th>Statusas</th><th>Depozitas</th><th>Galutinis</th><th>Veiksmas</th></tr></thead>
        <tbody>
          ${rows
            .map((item) => {
              const data = item.data || {};
              return `<tr>
                <td data-label="ID" class="mono">${escapeHtml(String(item.id || "").slice(0, 8))}</td>
                <td data-label="Statusas">${statusPill(data.status || "-")}</td>
                <td data-label="Depozitas">${escapeHtml(data.deposit_state || "-")}</td>
                <td data-label="Galutinis">${escapeHtml(data.final_state || "-")}</td>
                <td data-label="Veiksmas"><a class="btn btn-xs" href="/admin/project/${encodeURIComponent(item.id)}">Atidaryti</a></td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderCalls() {
  const section = document.getElementById("callsSection");
  const rows = (ClientCardState.card && ClientCardState.card.calls) || [];
  if (!section) return;
  if (!rows.length) {
    section.innerHTML =
      '<div class="empty-row">Skambuciu ir laisku istorijos nerasta arba modulis isjungtas.</div>';
    return;
  }

  section.innerHTML = `
    <div class="table-container">
      <table class="data-table">
        <thead><tr><th>ID</th><th>Statusas</th><th>Saltinis</th><th>Kontaktas</th><th>Data</th></tr></thead>
        <tbody>
          ${rows
            .map((item) => {
              const data = item.data || {};
              return `<tr>
                <td data-label="ID" class="mono">${escapeHtml(String(item.id || "").slice(0, 8))}</td>
                <td data-label="Statusas">${statusPill(data.status || "-")}</td>
                <td data-label="Saltinis">${escapeHtml(data.source || "-")}</td>
                <td data-label="Kontaktas">${escapeHtml(data.contact_masked || "-")}</td>
                <td data-label="Data">${formatDate(data.updated_at || data.created_at)}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPayments() {
  const section = document.getElementById("paymentsSection");
  const rows = (ClientCardState.card && ClientCardState.card.payments) || [];
  if (!section) return;
  if (!rows.length) {
    section.innerHTML = '<div class="empty-row">Mokejimu nerasta.</div>';
    return;
  }

  section.innerHTML = `
    <div class="table-container">
      <table class="data-table">
        <thead><tr><th>Projektas</th><th>Tipas</th><th>Suma</th><th>Statusas</th><th>Data</th></tr></thead>
        <tbody>
          ${rows
            .map((item) => {
              const data = item.data || {};
              return `<tr>
                <td data-label="Projektas" class="mono">${escapeHtml(String(data.project_id || "").slice(0, 8))}</td>
                <td data-label="Tipas">${escapeHtml(data.payment_type || "-")}</td>
                <td data-label="Suma">${formatCurrency(data.amount)}</td>
                <td data-label="Statusas">${statusPill(data.status || "-")}</td>
                <td data-label="Data">${formatDate(data.received_at)}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPhotos() {
  const section = document.getElementById("photosSection");
  const rows = (ClientCardState.card && ClientCardState.card.photos) || [];
  if (!section) return;
  if (!rows.length) {
    section.innerHTML = '<div class="empty-row">Nuotrauku nerasta.</div>';
    return;
  }

  section.innerHTML = `
    <div class="form-grid">
      ${rows
        .map((item) => {
          const data = item.data || {};
          const img = data.thumbnail_url || data.medium_url || data.file_url || "";
          return `<div class="card" style="padding:8px;">
            <div style="font-size:11px;color:var(--ink-muted);margin-bottom:4px;">${escapeHtml(data.category || "-")} | ${escapeHtml(String(data.project_id || "").slice(0, 8))}</div>
            <a href="${escapeHtml(data.file_url || "#")}" target="_blank" rel="noreferrer">
              <img src="${escapeHtml(img)}" alt="evidence" style="width:100%;height:160px;object-fit:cover;border-radius:6px;border:1px solid var(--border);" />
            </a>
          </div>`;
        })
        .join("")}
    </div>
  `;
}

function renderTimeline() {
  const section = document.getElementById("timelineSection");
  const rows = (ClientCardState.card && ClientCardState.card.timeline) || [];
  if (!section) return;
  if (!rows.length) {
    section.innerHTML = '<div class="empty-row">Timeline nerasta.</div>';
    return;
  }

  section.innerHTML = rows
    .map((item) => {
      const data = item.data || {};
      return `<div style="padding:8px 0;border-bottom:1px solid var(--border);">
        <div style="font-weight:600;">${escapeHtml(data.action || "-")}</div>
        <div style="font-size:12px;color:var(--ink-muted);">${formatDate(data.timestamp)} | ${escapeHtml(data.actor_type || "-")} | ${escapeHtml(String(data.entity_id || "").slice(0, 8))}</div>
      </div>`;
    })
    .join("");
}

function renderAll() {
  renderSummary();
  renderPricing();
  renderSurvey();
  renderProjects();
  renderCalls();
  renderPayments();
  renderPhotos();
  renderTimeline();
  updateActionButtons();
}

/* =========================================================================
   Data loading
   ========================================================================= */

function buildCardUrl() {
  const params = new URLSearchParams();
  Object.entries(CLIENT_CARD_LIMITS).forEach(([k, v]) => params.set(k, String(v)));
  return `/api/v1/admin/ops/client/${encodeURIComponent(ClientCardState.clientKey)}/card?${params.toString()}`;
}

async function loadCard() {
  const response = await authFetch(buildCardUrl());
  ClientCardState.card = await response.json();
  applyCardPayload();
  renderAll();
}

/* =========================================================================
   Survey helpers
   ========================================================================= */

function buildSurveyPayload() {
  const read = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : "";
  };
  const irrigation = document.getElementById("surveyIrrigation");
  const distanceRaw = read("surveyDistance");
  const distance = distanceRaw === "" ? 0 : Number(distanceRaw);

  // Collect obstacle checkboxes
  const obstacles = [];
  document.querySelectorAll(".obstacle-cb").forEach((cb) => {
    if (cb.checked && OBSTACLE_CODES.has(cb.value)) {
      obstacles.push(cb.value);
    }
  });

  return {
    soil_type: read("surveySoilType") || "UNKNOWN",
    slope_grade: read("surveySlopeGrade") || "FLAT",
    existing_vegetation: read("surveyVegetation") || "BARE",
    equipment_access: read("surveyAccess") || "EASY",
    distance_km: Number.isFinite(distance) ? Math.max(0, distance) : 0,
    obstacles: obstacles,
    irrigation_existing: !!(irrigation && irrigation.checked),
  };
}

/* =========================================================================
   API actions
   ========================================================================= */

async function generatePricing() {
  if (!ClientCardState.projectId) {
    showToast("Nerastas projekto ID kainos skaiciavimui", "error");
    return;
  }
  setBusy(true);
  setStatus("Generuojamas AI kainu pasiulymas...", false);
  try {
    await authFetch(`/api/v1/admin/pricing/${encodeURIComponent(ClientCardState.projectId)}/generate`, {
      method: "POST",
    });
    await loadCard();
    showToast("AI kainu pasiulymas atnaujintas", "success");
    setStatus("", false);
  } catch (err) {
    if (!(err instanceof AuthError)) {
      if (err && err.status === 404) {
        setStatus("AI pricing modulis siuo metu isjungtas (flag off).", true);
      } else {
        setStatus("Nepavyko sugeneruoti AI kainos.", true);
      }
    }
  } finally {
    setBusy(false);
  }
}

async function saveSurvey() {
  if (!ClientCardState.projectId) {
    showToast("Nerastas projekto ID anketai", "error");
    return;
  }
  const payload = buildSurveyPayload();
  setBusy(true);
  setStatus("Saugoma vietos anketa...", false);
  try {
    await authFetch(`/api/v1/admin/pricing/${encodeURIComponent(ClientCardState.projectId)}/survey`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    await loadCard();
    showToast("Anketa issaugota", "success");
    setStatus("", false);
  } catch (err) {
    if (!(err instanceof AuthError)) {
      setStatus("Nepavyko issaugoti anketos.", true);
    }
  } finally {
    setBusy(false);
  }
}

async function decidePricing(action, extraPayload) {
  if (!ClientCardState.projectId) {
    showToast("Nerastas projekto ID sprendimui", "error");
    return;
  }
  const fingerprint = getFingerprint();
  if (!fingerprint) {
    showToast("Nerastas pasiulymo fingerprint", "error");
    return;
  }

  const body = Object.assign(
    {
      action,
      proposal_fingerprint: fingerprint,
    },
    extraPayload || {}
  );

  setBusy(true);
  setStatus("Saugomas sprendimas...", false);
  try {
    await authFetch(`/api/v1/admin/pricing/${encodeURIComponent(ClientCardState.projectId)}/decide`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    await loadCard();
    showToast("Sprendimas issaugotas", "success");
    setStatus("", false);
  } catch (err) {
    if (!(err instanceof AuthError)) {
      if (err && err.status === 409) {
        setStatus("Pasiulymas pasikeite. Perkraunu kortele...", true);
        await loadCard();
      } else if (err && err.status === 422) {
        setStatus("Validacijos klaida.", true);
      } else if (err && err.status === 404) {
        setStatus("AI pricing modulis siuo metu isjungtas (flag off).", true);
      } else {
        setStatus("Nepavyko issaugoti sprendimo.", true);
      }
    }
  } finally {
    setBusy(false);
  }
}

/* =========================================================================
   Edit modal
   ========================================================================= */

function openEditModal() {
  const backdrop = document.getElementById("editPriceBackdrop");
  const input = document.getElementById("editPriceInput");
  const reason = document.getElementById("editPriceReason");
  if (!backdrop) return;
  if (input) input.value = "";
  if (reason) reason.value = "";
  backdrop.classList.add("active");
}

function closeEditModal() {
  const backdrop = document.getElementById("editPriceBackdrop");
  if (backdrop) backdrop.classList.remove("active");
}

function submitEditModal() {
  const input = document.getElementById("editPriceInput");
  const reason = document.getElementById("editPriceReason");
  const priceVal = input ? Number(input.value) : 0;
  const reasonVal = reason ? String(reason.value).trim() : "";

  if (!Number.isFinite(priceVal) || priceVal <= 0) {
    showToast("Kaina turi buti didesne uz 0", "error");
    return;
  }
  if (reasonVal.length < 8) {
    showToast("Priezastis turi buti bent 8 simboliu", "error");
    return;
  }

  closeEditModal();
  decidePricing("edit", { adjusted_price: priceVal, reason: reasonVal });
}

/* =========================================================================
   Event binding
   ========================================================================= */

function bindActions() {
  const btnGenerate = document.getElementById("btnGeneratePricing");
  const btnApprove = document.getElementById("btnApprovePricing");
  const btnEdit = document.getElementById("btnEditPricing");
  const btnIgnore = document.getElementById("btnIgnorePricing");
  const btnSaveSurvey = document.getElementById("btnSaveSurvey");

  if (btnGenerate) btnGenerate.addEventListener("click", generatePricing);
  if (btnSaveSurvey) btnSaveSurvey.addEventListener("click", saveSurvey);
  if (btnApprove) btnApprove.addEventListener("click", () => decidePricing("approve"));
  if (btnEdit) btnEdit.addEventListener("click", openEditModal);
  if (btnIgnore) {
    btnIgnore.addEventListener("click", () => {
      if (window.confirm("Ar tikrai norite ignoruoti si pasiulyma?")) {
        decidePricing("ignore");
      }
    });
  }

  // Modal events
  const closeBtn = document.getElementById("editPriceClose");
  const cancelBtn = document.getElementById("editPriceCancel");
  const submitBtn = document.getElementById("editPriceSubmit");
  const backdrop = document.getElementById("editPriceBackdrop");

  if (closeBtn) closeBtn.addEventListener("click", closeEditModal);
  if (cancelBtn) cancelBtn.addEventListener("click", closeEditModal);
  if (submitBtn) submitBtn.addEventListener("click", submitEditModal);
  if (backdrop) {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeEditModal();
    });
  }
}

/* =========================================================================
   Init
   ========================================================================= */

async function initClientCard() {
  ClientCardState.clientKey = getClientKeyFromPath();
  if (!ClientCardState.clientKey) {
    setStatus("Nerastas client key.", true);
    return;
  }
  if (!Auth.isSet()) {
    setStatus("Reikalingas admin zetonas.", true);
    return;
  }

  try {
    setStatus("Kraunama kliento kortele...", false);
    await loadCard();
    bindActions();
    setStatus("", false);
  } catch (err) {
    if (err instanceof AuthError) return;
    setStatus("Nepavyko ikelti kliento korteles.", true);
  }
}

document.addEventListener("DOMContentLoaded", initClientCard);
