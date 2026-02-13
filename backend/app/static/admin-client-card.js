"use strict";

const ClientCardState = {
  clientKey: null,
  card: null,
};

const CLIENT_CARD_LIMITS = {
  projects_limit: 10,
  payments_limit: 30,
  calls_limit: 20,
  photos_limit: 30,
  timeline_limit: 50,
};

function getClientKeyFromPath() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 1] || "");
}

function getProposalProjectId() {
  return (ClientCardState.card && ClientCardState.card.proposal && ClientCardState.card.proposal.project_id) || null;
}

function setStatus(message, isError) {
  const el = document.getElementById("clientCardStatus");
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("error", !!isError);
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

function renderProposal() {
  const proposal = (ClientCardState.card && ClientCardState.card.proposal) || {};
  const dryRun = (ClientCardState.card && ClientCardState.card.dry_run) || {};
  const block = document.getElementById("proposalBlock");
  const dry = document.getElementById("dryRunBlock");
  if (!block || !dry) return;

  if (!proposal.type) {
    block.innerHTML = '<div class="empty-row">AI proposal nera.</div>';
    dry.textContent = JSON.stringify(dryRun, null, 2);
    return;
  }

  const confidence = proposal.confidence == null ? "-" : Number(proposal.confidence).toFixed(2);
  block.innerHTML = `
    <div class="card" style="padding:10px;">
      <div style="font-size:12px;color:var(--ink-muted);">Proposal</div>
      <div style="font-size:15px;font-weight:700;">${escapeHtml(proposal.label || proposal.type)}</div>
      <div style="font-size:12px;color:var(--ink-muted);margin-top:6px;">Action key: ${escapeHtml(proposal.type || "-")}</div>
      <div style="font-size:12px;color:var(--ink-muted);">Confidence: ${escapeHtml(confidence)}</div>
      <div style="font-size:12px;color:var(--ink-muted);">Reason: ${escapeHtml(proposal.reason || "-")}</div>
    </div>
  `;
  dry.textContent = JSON.stringify(dryRun, null, 2);
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
  renderProposal();
  renderProjects();
  renderCalls();
  renderPayments();
  renderPhotos();
  renderTimeline();
}

async function sendProposalAction(action, note) {
  await authFetch(`/api/v1/admin/ops/client/${encodeURIComponent(ClientCardState.clientKey)}/proposal-action`, {
    method: "POST",
    body: JSON.stringify({
      action,
      note: note || "",
      project_id: getProposalProjectId(),
    }),
  });
}

function executeProposalRedirect() {
  const proposal = (ClientCardState.card && ClientCardState.card.proposal) || {};
  const projectId = proposal.project_id || "";

  if (proposal.type === "record_deposit") {
    window.location.href = `/admin/projects#manual-deposit-${projectId}`;
    return;
  }
  if (proposal.type === "record_final") {
    window.location.href = `/admin/projects#manual-final-${projectId}`;
    return;
  }
  if (proposal.type === "schedule_visit") {
    window.location.href = "/admin/calendar";
    return;
  }
  if (proposal.type === "resend_confirmation") {
    window.location.href = `/admin/projects#${projectId}`;
    return;
  }
  showToast("Proposal neturi automatinio approve kelio", "info");
}

function bindActions() {
  const approveBtn = document.getElementById("btnApproveProposal");
  const editBtn = document.getElementById("btnEditProposal");
  const escalateBtn = document.getElementById("btnEscalateProposal");

  if (approveBtn) {
    approveBtn.addEventListener("click", async () => {
      try {
        await sendProposalAction("approve", "");
        executeProposalRedirect();
      } catch (err) {
        if (!(err instanceof AuthError)) showToast("Nepavyko uzfiksuoti approve", "error");
      }
    });
  }

  if (editBtn) {
    editBtn.addEventListener("click", async () => {
      const note = window.prompt("Pataisymo pastaba:", "");
      if (note == null) return;
      try {
        await sendProposalAction("edit", note);
        showToast("Pataisymo pastaba issaugota", "success");
      } catch (err) {
        if (!(err instanceof AuthError)) showToast("Nepavyko issaugoti pataisymo", "error");
      }
    });
  }

  if (escalateBtn) {
    escalateBtn.addEventListener("click", async () => {
      const note = window.prompt("Eskalavimo priezastis:", "");
      if (note == null) return;
      try {
        await sendProposalAction("escalate", note);
        showToast("Eskalacija uzfiksuota", "warning");
      } catch (err) {
        if (!(err instanceof AuthError)) showToast("Nepavyko eskaluoti", "error");
      }
    });
  }
}

function buildCardUrl() {
  const params = new URLSearchParams();
  Object.entries(CLIENT_CARD_LIMITS).forEach(([k, v]) => params.set(k, String(v)));
  return `/api/v1/admin/ops/client/${encodeURIComponent(ClientCardState.clientKey)}/card?${params.toString()}`;
}

async function loadCard() {
  setStatus("Kraunama kliento kortele...", false);
  const response = await authFetch(buildCardUrl());
  ClientCardState.card = await response.json();
  renderAll();
  setStatus("", false);
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
    await loadCard();
    bindActions();
  } catch (err) {
    if (err instanceof AuthError) return;
    setStatus("Nepavyko ikelti kliento korteles.", true);
  }
}

document.addEventListener("DOMContentLoaded", initClientCard);
