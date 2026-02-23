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
  slope_adjustment: "Nuolydžio korekcija",
  soil_preparation: "Dirvos paruošimas",
  vegetation_removal: "Augmenijos valymas",
  access_difficulty: "Priejimo sudėtingumas",
  distance_surcharge: "Atstumo antkainis",
  obstacle_clearing: "Kliūčių šalinimas",
  irrigation_bonus: "Laistymo nuolaida",
  seasonal_demand: "Sezoninė paklausa",
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
          ? "Tik 'ok' statusas leidžia patvirtinti"
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
  if (title) title.textContent = summary.display_name || "Kliento kortelė";

  const badgeEl = document.getElementById("clientKeyBadge");
  if (badgeEl) badgeEl.textContent = ClientCardState.clientKey ? String(ClientCardState.clientKey).slice(0, 12) : "";

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
    flagsEl.innerHTML = '<span class="pill pill-success">Įspėjimų nėra</span>';
    return;
  }
  flagsEl.innerHTML = flags.map((flag) => attentionPill(flag)).join(" ");
  renderWhatNowBlock();
}

function renderWhatNowBlock() {
  const block = document.getElementById("whatNowBlock");
  const textEl = document.getElementById("whatNowText");
  const ctaEl = document.getElementById("whatNowCta");
  if (!block || !textEl || !ctaEl) return;

  const summary = (ClientCardState.card && ClientCardState.card.summary) || {};
  const projects = (ClientCardState.card && ClientCardState.card.projects) || [];
  const projectId = projects[0] && projects[0].id ? String(projects[0].id) : null;
  const nextVisit = summary.next_visit;
  const depositState = String(summary.deposit_state || "").toUpperCase();
  const needsDeposit = depositState.indexOf("REIKIA") !== -1 || depositState === "REIKIA_IRASYTI";
  const aiDecisionNeeded = canApprove();
  const pricingEnabled = !!ClientCardState.featureFlags.ai_pricing;

  let actionText = "";
  let ctaLabel = "";
  let ctaHref = "/admin";

  if (!nextVisit || nextVisit === "-") {
    actionText = "Reikia suplanuoti pirmą vizitą";
    ctaLabel = "Atidaryti kalendorių";
    ctaHref = "/admin";
  } else if (pricingEnabled && aiDecisionNeeded) {
    actionText = "Po vizito: reikia priimti kainos sprendimą";
    ctaLabel = "Kainos sprendimas";
    ctaHref = "#aiPricingPanel";
  } else if (needsDeposit) {
    actionText = "Laukiama depozito mokėjimo";
    ctaLabel = "Mokėjimai";
    ctaHref = "#paymentsSection";
  } else if (projectId) {
    actionText = "Projektas vykdomas pagal planą";
    ctaLabel = "Peržiūrėti projektą";
    ctaHref = "/admin/project/" + encodeURIComponent(projectId);
  } else {
    actionText = "Projektas vykdomas pagal planą";
    ctaLabel = "Grįžti į planuotoją";
    ctaHref = "/admin";
  }

  textEl.textContent = actionText;
  ctaEl.textContent = ctaLabel;
  ctaEl.href = ctaHref;
  block.style.display = "";
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

  // "Reikia sprendimo" badge (Figma-style)
  const needsDecisionEl = document.getElementById("aiPricingNeedsDecisionBadge");
  if (needsDecisionEl) needsDecisionEl.style.display = pricing && !decision && canApprove() ? "" : "none";

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
    statusLine.innerHTML = '<span class="pill">AI kainų pasiūlymo dar nėra</span>';
    if (fallbackLine) fallbackLine.style.display = "none";
    elBase.textContent = "-";
    elAdj.textContent = "-";
    elFinal.textContent = "-";
    elRange.textContent = "-";
    elConfidence.textContent = "-";
    elSimilar.textContent = "-";
    elReasoning.textContent = "-";
    elFactors.innerHTML = '<div class="empty-row">Faktorių nėra.</div>';
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
        "<strong>Fallback:</strong> patvirtinti negalima. Galite ignoruoti arba koreguoti rankiniu būdu.";
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
    elFactors.innerHTML = '<div class="empty-row">Faktorių nėra.</div>';
  } else {
    elFactors.innerHTML =
      '<div class="table-container"><table class="data-table">' +
      "<thead><tr><th>Faktorius</th><th>Poveikis (EUR)</th><th>Aprašymas</th></tr></thead><tbody>" +
      factors
        .map((f) => {
          const sign = (f.impact_eur || 0) >= 0 ? "+" : "";
          return (
            "<tr>" +
            '<td data-label="Faktorius">' + escapeHtml(factorLabel(f.name)) + "</td>" +
            '<td data-label="Poveikis">' + sign + formatCurrency(f.impact_eur || 0) + "</td>" +
            '<td data-label="Aprašymas">' + escapeHtml(f.description || "-") + "</td>" +
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

const EXPENSE_CATEGORY_LABELS = {
  FUEL: "Kuras",
  REPAIR: "Remontas",
  MATERIALS: "Medžiagos",
  SUBCONTRACTOR: "Subrangovas",
  TAXES: "Mokesčiai",
  INSURANCE: "Draudimas",
  TOOLS: "Įrankiai",
  OTHER: "Kita",
};

function renderProjectEstimate(est) {
  if (!est) return '<div class="empty-row">Įvertinimo nėra.</div>';
  const rows = [
    ["Paslauga", escapeHtml(est.service_label || "-")],
    ["Metodas", escapeHtml(est.method_label || "-")],
    ["Plotas", est.area_m2 != null ? escapeHtml(String(est.area_m2)) + " m\u00B2" : "-"],
    ["Adresas", escapeHtml(est.address || "-")],
    ["Telefonas", escapeHtml(est.phone || "-")],
    ["Atstumas", est.km_one_way != null ? escapeHtml(String(est.km_one_way)) + " km" : "-"],
    ["Kaina", est.total_eur != null ? formatCurrency(est.total_eur) : "-"],
    ["Pageidaujamas laikas", escapeHtml(est.preferred_slot || "-")],
  ];
  if (est.addons_selected && est.addons_selected.length) {
    rows.push(["Priedai", escapeHtml(est.addons_selected.join(", "))]);
  }
  if (est.extras) {
    rows.push(["Pastabos", escapeHtml(est.extras)]);
  }
  return (
    '<div class="table-container"><table class="data-table">' +
    "<tbody>" +
    rows.map(([label, val]) => "<tr><td><strong>" + escapeHtml(label) + "</strong></td><td>" + val + "</td></tr>").join("") +
    "</tbody></table></div>"
  );
}

function renderProjectPayments(pay) {
  if (!pay) return '<div class="empty-row">Mokėjimų duomenų nėra.</div>';
  let html = '<div class="table-container"><table class="data-table"><tbody>';
  html +=
    "<tr><td><strong>Depozitas</strong></td><td>" +
    statusPill(pay.deposit_state || "-") +
    (pay.deposit_amount_eur != null ? " &mdash; " + formatCurrency(pay.deposit_amount_eur) : "") +
    "</td></tr>";
  html +=
    "<tr><td><strong>Galutinis</strong></td><td>" +
    (pay.final_state ? statusPill(pay.final_state) : "-") +
    (pay.final_amount_eur != null ? " &mdash; " + formatCurrency(pay.final_amount_eur) : "") +
    "</td></tr>";
  if (pay.next_text) {
    html += "<tr><td><strong>Kitas žingsnis</strong></td><td>" + escapeHtml(pay.next_text) + "</td></tr>";
  }
  html += "</tbody></table></div>";
  return html;
}

function renderProjectDocuments(docs) {
  if (!docs || !docs.length) return '<div class="empty-row">Dokumentų nėra.</div>';
  return (
    '<div style="display:flex;flex-wrap:wrap;gap:8px;">' +
    docs
      .map(
        (d) =>
          '<a class="btn btn-xs btn-secondary" href="' +
          escapeHtml(d.url || "#") +
          '" target="_blank" rel="noreferrer">' +
          escapeHtml(d.label || d.type || "Dokumentas") +
          "</a>"
      )
      .join("") +
    "</div>"
  );
}

function renderProjectVisits(visits) {
  if (!visits || !visits.length) return '<div class="empty-row">Vizitų nėra.</div>';
  return (
    '<div class="table-container"><table class="data-table">' +
    "<thead><tr><th>Tipas</th><th>Statusas</th><th>Data</th></tr></thead><tbody>" +
    visits
      .map(
        (v) =>
          "<tr>" +
          '<td data-label="Tipas">' + escapeHtml(v.visit_type || "-") + "</td>" +
          '<td data-label="Statusas">' + statusPill(v.status || "-") + "</td>" +
          '<td data-label="Data">' + escapeHtml(v.label || v.starts_at || "-") + "</td>" +
          "</tr>"
      )
      .join("") +
    "</tbody></table></div>"
  );
}

function renderProjectExpenses(expenses) {
  if (!expenses || !expenses.categories || !Object.keys(expenses.categories).length) {
    return '<div class="empty-row">Išlaidų nėra.</div>';
  }
  const cats = expenses.categories;
  let html =
    '<div class="table-container"><table class="data-table">' +
    "<thead><tr><th>Kategorija</th><th>Suma</th></tr></thead><tbody>";
  for (const [key, amount] of Object.entries(cats)) {
    const label = EXPENSE_CATEGORY_LABELS[key] || key;
    html += "<tr><td>" + escapeHtml(label) + "</td><td>" + formatCurrency(amount) + "</td></tr>";
  }
  html +=
    '<tr style="font-weight:700;border-top:2px solid var(--border);">' +
    "<td>Viso</td><td>" +
    formatCurrency(expenses.total || 0) +
    "</td></tr>";
  html += "</tbody></table></div>";
  return html;
}

function renderProjects() {
  const section = document.getElementById("projectsSection");
  const rows = (ClientCardState.card && ClientCardState.card.projects) || [];
  if (!section) return;
  if (!rows.length) {
    section.innerHTML = '<div class="empty-row">Projektų nerasta.</div>';
    return;
  }

  const showExpenses = !!ClientCardState.featureFlags.finance_ledger;

  section.innerHTML = rows
    .map((item) => {
      const data = item.data || {};
      const shortId = String(item.id || "").slice(0, 8);
      const area = data.area_m2 != null ? escapeHtml(String(data.area_m2)) + " m\u00B2" : "";

      let content = "";
      content +=
        '<div class="project-subsection">' +
        '<div class="project-subsection-title">Įvertinimas</div>' +
        renderProjectEstimate(data.estimate) +
        "</div>";
      content +=
        '<div class="project-subsection">' +
        '<div class="project-subsection-title">Mokėjimai</div>' +
        renderProjectPayments(data.payments_summary) +
        "</div>";
      content +=
        '<div class="project-subsection">' +
        '<div class="project-subsection-title">Dokumentai</div>' +
        renderProjectDocuments(data.documents) +
        "</div>";
      content +=
        '<div class="project-subsection">' +
        '<div class="project-subsection-title">Vizitai</div>' +
        renderProjectVisits(data.visits) +
        "</div>";
      if (showExpenses) {
        content +=
          '<div class="project-subsection">' +
          '<div class="project-subsection-title">Išlaidos</div>' +
          renderProjectExpenses(data.expenses) +
          "</div>";
      }

      return (
        '<details class="project-expand-row">' +
        "<summary>" +
        '<span class="project-expand-header">' +
        '<span class="mono">' + escapeHtml(shortId) + "</span> " +
        statusPill(data.status || "-") + " " +
        escapeHtml(data.deposit_state || "-") + " / " +
        escapeHtml(data.final_state || "-") +
        (area ? " &middot; " + area : "") +
        " " +
        '<a class="btn btn-xs" href="/admin/project/' +
        encodeURIComponent(item.id) +
        '" onclick="event.stopPropagation()">Atidaryti</a>' +
        "</span>" +
        "</summary>" +
        '<div class="project-expand-content">' +
        content +
        "</div>" +
        "</details>"
      );
    })
    .join("");
}

function renderCalls() {
  const section = document.getElementById("callsSection");
  const rows = (ClientCardState.card && ClientCardState.card.calls) || [];
  if (!section) return;
  if (!rows.length) {
    section.innerHTML =
      '<div class="empty-row">Skambučių ir laiškų istorijos nerasta arba modulis išjungtas.</div>';
    return;
  }

  section.innerHTML = `
    <div class="table-container">
      <table class="data-table">
        <thead><tr><th>ID</th><th>Statusas</th><th>Šaltinis</th><th>Kontaktas</th><th>Data</th></tr></thead>
        <tbody>
          ${rows
            .map((item) => {
              const data = item.data || {};
              return `<tr>
                <td data-label="ID" class="mono">${escapeHtml(String(item.id || "").slice(0, 8))}</td>
                <td data-label="Statusas">${statusPill(data.status || "-")}</td>
                <td data-label="Šaltinis">${escapeHtml(data.source || "-")}</td>
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
    section.innerHTML = '<div class="empty-row">Mokėjimų nerasta.</div>';
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
    section.innerHTML = '<div class="empty-row">Nuotraukų nerasta.</div>';
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
    section.innerHTML = '<div class="empty-row">Timeline įrašų nerasta.</div>';
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
    showToast("Nerastas projekto ID kainų skaičiavimui", "error");
    return;
  }
  setBusy(true);
  setStatus("Generuojamas AI kainų pasiūlymas...", false);
  try {
    await authFetch(`/api/v1/admin/pricing/${encodeURIComponent(ClientCardState.projectId)}/generate`, {
      method: "POST",
    });
    await loadCard();
    showToast("AI kainų pasiūlymas atnaujintas", "success");
    setStatus("", false);
  } catch (err) {
    if (!(err instanceof AuthError)) {
      if (err && err.status === 404) {
        setStatus("AI pricing modulis šiuo metu išjungtas (flag off).", true);
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
    showToast("Anketa išsaugota", "success");
    setStatus("", false);
  } catch (err) {
    if (!(err instanceof AuthError)) {
      setStatus("Nepavyko išsaugoti anketos.", true);
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
    showToast("Nerastas pasiūlymo fingerprint", "error");
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
    showToast("Sprendimas išsaugotas", "success");
    setStatus("", false);
  } catch (err) {
    if (!(err instanceof AuthError)) {
      if (err && err.status === 409) {
        setStatus("Pasiūlymas pasikeitė. Perkraunu kortelę...", true);
        await loadCard();
      } else if (err && err.status === 422) {
        setStatus("Validacijos klaida.", true);
      } else if (err && err.status === 404) {
        setStatus("AI pricing modulis šiuo metu išjungtas (flag off).", true);
      } else {
        setStatus("Nepavyko išsaugoti sprendimo.", true);
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
  const countEl = document.getElementById("editPriceReasonCount");
  if (!backdrop) return;
  if (input) input.value = "";
  if (reason) reason.value = "";
  if (countEl) countEl.textContent = "0 / 8 simbolių";
  backdrop.classList.add("active");
}

function updateEditPriceReasonCount() {
  const reason = document.getElementById("editPriceReason");
  const countEl = document.getElementById("editPriceReasonCount");
  if (!countEl || !reason) return;
  const len = String(reason.value).length;
  countEl.textContent = len + " / 8 simbolių";
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
    showToast("Kaina turi būti didesnė už 0", "error");
    return;
  }
  if (reasonVal.length < 8) {
    showToast("Priežastis turi būti bent 8 simbolių", "error");
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
      if (window.confirm("Ar tikrai norite ignoruoti šį pasiūlymą?")) {
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
  const reasonInput = document.getElementById("editPriceReason");
  if (reasonInput) reasonInput.addEventListener("input", updateEditPriceReasonCount);
}

/* =========================================================================
   Init
   ========================================================================= */

async function initClientCard() {
  ClientCardState.clientKey = getClientKeyFromPath();
  if (!ClientCardState.clientKey) {
    setStatus("Kliento raktas nenurodytas. Grįžkite į Archyvą arba Plannerį ir pasirinkite klientą.", true);
    return;
  }
  if (!Auth.isSet()) {
    setStatus("Reikalingas admin žetonas.", true);
    return;
  }

  try {
    setStatus("Kraunama kliento kortelė...", false);
    await loadCard();
    bindActions();
    setStatus("", false);
  } catch (err) {
    if (err instanceof AuthError) return;
    setStatus("Nepavyko įkelti kliento kortelės.", true);
  }
}

document.addEventListener("DOMContentLoaded", initClientCard);
