"use strict";

const ProjectDayState = {
  projectId: null,
  day: null,
  detail: null,
};

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function pathProjectId() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 1] || "");
}

function normalizeDay(raw) {
  if (raw && /^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  return new Date().toISOString().slice(0, 10);
}

function checklistForStatus(status) {
  const base = [
    "Patikrink uzduoties konteksta ir dienos plana",
    "Surink arba atnaujink irodymus (foto)",
    "Atnaujink dienos veiksmu audita",
  ];
  if (status === "DRAFT") base.unshift("Suderink depozito plana su klientu");
  if (status === "PAID") base.unshift("Patvirtink vizito laika ir atvykimo langa");
  if (status === "CERTIFIED") base.unshift("Surink galutinius irodymus ir uzdarymo pastabas");
  return base;
}

function renderSummary() {
  const detail = ProjectDayState.detail;
  if (!detail) return;
  const project = detail.project || {};
  const status = project.status || "";

  document.getElementById("projectDayTitle").textContent = `Project ${String(project.id || "").slice(0, 8)} - ${ProjectDayState.day}`;
  document.getElementById("projectStatusPill").innerHTML = statusPill(status);
  document.getElementById("projectIdValue").textContent = project.id || "-";
  document.getElementById("dayValue").textContent = ProjectDayState.day;
  document.getElementById("plannedDurationValue").textContent = project.scheduled_for ? formatDate(project.scheduled_for) : "-";
  document.getElementById("budgetValue").textContent = project.total_price_client == null ? "-" : formatCurrency(project.total_price_client);

  const checklist = checklistForStatus(status);
  document.getElementById("projectChecklist").innerHTML = checklist.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderEvidence() {
  const detail = ProjectDayState.detail;
  const container = document.getElementById("evidenceGrid");
  if (!container || !detail) return;
  const evidences = detail.evidences || [];
  if (!evidences.length) {
    container.innerHTML = '<div class="empty-row">Nuotrauku nerasta.</div>';
    return;
  }
  container.innerHTML = evidences
    .map((ev) => {
      const img = ev.thumbnail_url || ev.medium_url || ev.file_url;
      return `
        <div class="card" style="padding:10px;">
          <div style="font-size:11px;color:var(--ink-muted);margin-bottom:6px;">${escapeHtml(ev.category || "-")}</div>
          <a href="${escapeHtml(ev.file_url)}" target="_blank" rel="noreferrer">
            <img src="${escapeHtml(img)}" alt="evidence" style="width:100%;height:180px;object-fit:cover;border-radius:6px;border:1px solid var(--border);" />
          </a>
        </div>
      `;
    })
    .join("");
}

function renderAudit() {
  const detail = ProjectDayState.detail;
  const container = document.getElementById("projectAuditTimeline");
  if (!container || !detail) return;
  const logs = (detail.audit_logs || []).slice(0, 30);
  if (!logs.length) {
    container.innerHTML = '<div class="empty-row">Audito irasu nerasta.</div>';
    return;
  }
  container.innerHTML = logs
    .map(
      (log) => `
      <div style="padding:8px 0;border-bottom:1px solid var(--border);">
        <div style="font-weight:600;font-size:13px;">${escapeHtml(log.action || "-")}</div>
        <div style="font-size:12px;color:var(--ink-muted);">${escapeHtml(log.actor_type || "-")} • ${formatDate(log.timestamp)}</div>
      </div>
    `,
    )
    .join("");
}

async function loadProjectDetail() {
  const status = document.getElementById("projectDayStatus");
  status.textContent = "Kraunama projekto informacija...";
  try {
    const resp = await authFetch(`/api/v1/projects/${encodeURIComponent(ProjectDayState.projectId)}`);
    const data = await resp.json();
    ProjectDayState.detail = data;
    renderSummary();
    renderEvidence();
    renderAudit();
    status.textContent = "";
  } catch (err) {
    if (err instanceof AuthError) return;
    status.textContent = "Nepavyko ikelti projekto duomenu.";
    status.classList.add("error");
  }
}

async function postDayAction(action, note) {
  const status = document.getElementById("projectDayStatus");
  status.textContent = "Siunciamas veiksmas...";
  try {
    await authFetch(`/api/v1/admin/ops/project/${encodeURIComponent(ProjectDayState.projectId)}/day-action`, {
      method: "POST",
      body: JSON.stringify({
        day: ProjectDayState.day,
        action,
        note: note || "",
      }),
    });
    status.textContent = "";
    showToast("Veiksmas uzfiksuotas audite", "success");
    await loadProjectDetail();
  } catch (err) {
    if (err instanceof AuthError) return;
    status.textContent = "Veiksmo issaugoti nepavyko.";
    status.classList.add("error");
  }
}

function bindActions() {
  document.getElementById("backToPlanner").href = `/admin?day=${encodeURIComponent(ProjectDayState.day)}`;
  document.getElementById("btnCheckIn").addEventListener("click", async () => {
    await postDayAction("check_in");
  });
  document.getElementById("btnJumpUpload").addEventListener("click", async () => {
    document.getElementById("uploadSection").scrollIntoView({ behavior: "smooth", block: "start" });
    await postDayAction("upload_photo", "Upload shortcut opened");
  });
  document.getElementById("btnCompleteDay").addEventListener("click", async () => {
    const note = window.prompt("Papildoma dienos pastaba (neprivaloma):", "");
    await postDayAction("complete", note || "");
  });

  document.getElementById("uploadForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const fileInput = document.getElementById("evidenceFile");
    const categoryInput = document.getElementById("evidenceCategory");
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      showToast("Pasirinkite faila", "warning");
      return;
    }
    const form = new FormData();
    form.append("project_id", ProjectDayState.projectId);
    form.append("category", categoryInput.value);
    form.append("file", file);
    try {
      await authFetch("/api/v1/upload-evidence", {
        method: "POST",
        body: form,
      });
      showToast("Nuotrauka ikelta", "success");
      await postDayAction("upload_photo", "Evidence uploaded");
      await loadProjectDetail();
      fileInput.value = "";
    } catch (err) {
      if (err instanceof AuthError) return;
      showToast("Nepavyko ikelti nuotraukos", "error");
    }
  });
}

async function initProjectDay() {
  ProjectDayState.projectId = pathProjectId();
  ProjectDayState.day = normalizeDay(qs("day"));
  if (!ProjectDayState.projectId) {
    document.getElementById("projectDayStatus").textContent = "Nerastas project id.";
    return;
  }
  if (!Auth.isSet()) {
    document.getElementById("projectDayStatus").textContent = "Reikalingas admin zetonas.";
    return;
  }
  bindActions();
  await loadProjectDetail();
}

document.addEventListener("DOMContentLoaded", initProjectDay);
