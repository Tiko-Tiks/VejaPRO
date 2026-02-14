"use strict";

const ClientCardState = {
  clientKey: null,
  card: null,
  projectId: null,
  aiPricing: null,
  aiPricingMeta: null,
  survey: null,
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

function canApprove() {
  return (
    !ClientCardState.busy &&
    !!ClientCardState.projectId &&
    !!ClientCardState.aiPricing &&
    ClientCardState.aiPricing.status === "ok" &&
    !!getFingerprint()
  );
}

function canEditOrIgnore() {
  return !ClientCardState.busy && !!ClientCardState.projectId && !!ClientCardState.aiPricing && !!getFingerprint();
}

function updateActionButtons() {
  const btnGenerate = document.getElementById("btnGeneratePricing");
  const btnApprove = document.getElementById("btnApprovePricing");
  const btnEdit = document.getElementById("btnEditPricing");
  const btnIgnore = document.getElementById("btnIgnorePricing");
  const btnSurvey = document.getElementById("btnSaveSurvey");

  if (btnGenerate) btnGenerate.disabled = ClientCardState.busy || !ClientCardState.projectId;
  if (btnApprove) btnApprove.disabled = !canApprove();
  if (btnEdit) btnEdit.disabled = !canEditOrIgnore();
  if (btnIgnore) btnIgnore.disabled = !canEditOrIgnore();
  if (btnSurvey) btnSurvey.disabled = ClientCardState.busy || !ClientCardState.projectId;
}

function resolveTargetProjectId() {
  if (ClientCardState.card && ClientCardState.card.pricing_project_id) {
    return String(ClientCardState.card.pricing_project_id);
  }
  const proposalProject = ClientCardState.card && ClientCardState.card.proposal && ClientCardState.card.proposal.project_id;
  if (proposalProject) return String(proposalProject);
  const projects = (ClientCardState.card && ClientCardState.card.projects) || [];
  if (projects.length && projects[0].id) return String(projects[0].id);
  return null;
}

function applyCardPayload() {
  ClientCardState.projectId = resolveTargetProjectId();
  ClientCardState.aiPricing = (ClientCardState.card && ClientCardState.card.ai_pricing) || null;
  ClientCardState.aiPricingMeta = (ClientCardState.card && ClientCardState.card.ai_pricing_meta) || null;
  ClientCardState.survey = (ClientCardState.card && ClientCardState.card.extended_survey) || {};
}

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

  const statusLine = document.getElementById("pricingStatusLine");
  const fallbackLine = document.getElementById("pricingFallbackLine");
  const elBase = document.getElementById("pricingBase");
  const elAdj = document.getElementById("pricingAdjustment");
  const elFinal = document.getElementById("pricingFinal");
  const elRange = document.getElementById("pricingRange");
  const elConfidence = document.getElementById("pricingConfidence");
  const elSimilar = document.getElementById("pricingSimilar");
  const elReasoning = document.getElementById("pricingReasoning");
  const elFactors = document.getElementById("pricingFactors");

  if (!statusLine || !elBase || !elAdj || !elFinal || !elRange || !elConfidence || !elSimilar || !elReasoning || !elFactors) {
    return;
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
    return;
  }

  const status = String(pricing.status || "").toLowerCase();
  const fingerprint = typeof meta.fingerprint === "string" ? meta.fingerprint : "";
  statusLine.innerHTML =
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
        '<strong>Fallback:</strong> patvirtinti negalima. Galite ignoruoti arba koreguoti rankiniu budu.';
    } else {
      fallbackLine.style.display = "none";
      fallbackLine.innerHTML = "";
    }
  }

  elBase.textContent = formatCurrency(pricing.deterministic_base || 0);
  elAdj.textContent = formatCurrency(pricing.llm_adjustment || 0);
  elFinal.textContent = formatCurrency(pricing.recommended_price || 0);
  elRange.textContent = formatCurrency(pricing.price_range_min || 0) + " - " + formatCurrency(pricing.price_range_max || 0);
  elConfidence.textContent =
    escapeHtml(String(pricing.confidence_bucket || "-")) +
    " (" +
    Number(pricing.confidence || 0).toFixed(2) +
    ")";
  elSimilar.textContent = String(pricing.similar_projects_used || 0);
  elReasoning.textContent = pricing.reasoning_lt || "-";

  const factors = Array.isArray(pricing.factors) ? pricing.factors : [];
  if (!factors.length) {
    elFactors.innerHTML = '<div class="empty-row">Faktoriu nera.</div>';
  } else {
    elFactors.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr><th>Faktorius</th><th>Poveikis</th><th>Aprasas</th></tr></thead>
          <tbody>
            ${factors
              .map((f) => {
                return `<tr>
                  <td data-label="Faktorius">${escapeHtml(f.name || "-")}</td>
                  <td data-label="Poveikis">${formatCurrency(f.impact_eur || 0)}</td>
                  <td data-label="Aprasas">${escapeHtml(f.description || "-")}</td>
                </tr>`;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    `;
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
  setValue("surveyObstacles", Array.isArray(survey.obstacles) ? survey.obstacles.join(",") : "");
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
    section.innerHTML = '<div class="empty-row">Skambuciu ir laisku istorijos nerasta arba modulis isjungtas.</div>';
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

function normalizeObstacleCodes(raw) {
  if (!raw) return [];
  return String(raw)
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter((v) => v && OBSTACLE_CODES.has(v));
}

function buildSurveyPayload() {
  const read = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : "";
  };
  const irrigation = document.getElementById("surveyIrrigation");
  const distanceRaw = read("surveyDistance");
  const distance = distanceRaw === "" ? 0 : Number(distanceRaw);
  return {
    soil_type: read("surveySoilType") || "UNKNOWN",
    slope_grade: read("surveySlopeGrade") || "FLAT",
    existing_vegetation: read("surveyVegetation") || "BARE",
    equipment_access: read("surveyAccess") || "EASY",
    distance_km: Number.isFinite(distance) ? Math.max(0, distance) : 0,
    obstacles: normalizeObstacleCodes(read("surveyObstacles")),
    irrigation_existing: !!(irrigation && irrigation.checked),
  };
}

async function generatePricing() {
  if (!ClientCardState.projectId) {
    showToast("Nerastas projekto ID kainos skaiciavimui", "error");
    return;
  }
  setBusy(true);
  setStatus("Generuojamas AI kainu pasiulymas...", false);
  try {
    await authFetch(`/api/v1/admin/ops/pricing/${encodeURIComponent(ClientCardState.projectId)}/generate`, {
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
    await authFetch(`/api/v1/admin/ops/pricing/${encodeURIComponent(ClientCardState.projectId)}/survey`, {
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
    await authFetch(`/api/v1/admin/ops/pricing/${encodeURIComponent(ClientCardState.projectId)}/decide`, {
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

function openEditDialogAndSubmit() {
  const priceRaw = window.prompt("Iveskite koreguota kaina (EUR):", "");
  if (priceRaw == null) return;
  const adjusted = Number(priceRaw);
  if (!Number.isFinite(adjusted) || adjusted <= 0) {
    showToast("Kaina turi buti didesne uz 0", "error");
    return;
  }
  const reason = window.prompt("Iveskite priezasti (min 8 simboliai):", "");
  if (reason == null) return;
  if (String(reason).trim().length < 8) {
    showToast("Priezastis turi buti bent 8 simboliu", "error");
    return;
  }
  decidePricing("edit", { adjusted_price: adjusted, reason: String(reason).trim() });
}

function bindActions() {
  const btnGenerate = document.getElementById("btnGeneratePricing");
  const btnApprove = document.getElementById("btnApprovePricing");
  const btnEdit = document.getElementById("btnEditPricing");
  const btnIgnore = document.getElementById("btnIgnorePricing");
  const btnSaveSurvey = document.getElementById("btnSaveSurvey");

  if (btnGenerate) btnGenerate.addEventListener("click", generatePricing);
  if (btnSaveSurvey) btnSaveSurvey.addEventListener("click", saveSurvey);
  if (btnApprove) btnApprove.addEventListener("click", () => decidePricing("approve"));
  if (btnEdit) btnEdit.addEventListener("click", openEditDialogAndSubmit);
  if (btnIgnore) btnIgnore.addEventListener("click", () => decidePricing("ignore"));
}

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
