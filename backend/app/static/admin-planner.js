"use strict";

const PlannerState = {
  monthCursor: null,
  selectedDate: null,
  monthSummary: new Map(),
};

function toIsoDateUTC(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function queryDay() {
  const raw = new URLSearchParams(window.location.search).get("day");
  if (raw && /^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  return null;
}

function parseIsoDate(isoDate) {
  const [year, month, day] = isoDate.split("-").map((v) => Number(v));
  return new Date(Date.UTC(year, month - 1, day));
}

function firstOfMonth(date) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

function addMonths(date, amount) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + amount, 1));
}

function startOfCalendarGrid(firstDayOfMonth) {
  const weekday = firstDayOfMonth.getUTCDay(); // 0=Sun, 1=Mon
  const mondayOffset = (weekday + 6) % 7;
  return new Date(Date.UTC(firstDayOfMonth.getUTCFullYear(), firstDayOfMonth.getUTCMonth(), 1 - mondayOffset));
}

function durationMinutes(startIso, endIso) {
  if (!startIso || !endIso) return 0;
  const start = Date.parse(startIso);
  const end = Date.parse(endIso);
  if (Number.isNaN(start) || Number.isNaN(end)) return 0;
  return Math.max(0, Math.floor((end - start) / 60000));
}

function formatInboxDate(iso) {
  if (!iso || typeof iso !== "string") return "–";
  const d = iso.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : "–";
}

function urgencyPill(urgency) {
  if (urgency === "high") return '<span class="pill pill-error">HIGH</span>';
  if (urgency === "medium") return '<span class="pill pill-warning">MEDIUM</span>';
  return '<span class="pill pill-gray">LOW</span>';
}

function monthLabel(date) {
  return date.toLocaleDateString("lt-LT", { month: "long", year: "numeric", timeZone: "UTC" });
}

function dayLabel(isoDate) {
  return parseIsoDate(isoDate).toLocaleDateString("lt-LT", { weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}

function renderCalendar() {
  const grid = document.getElementById("plannerCalendar");
  const monthTitle = document.getElementById("plannerMonthLabel");
  if (!grid || !monthTitle || !PlannerState.monthCursor) return;

  monthTitle.textContent = monthLabel(PlannerState.monthCursor);

  const weekdays = ["Pr", "An", "Tr", "Kt", "Pn", "St", "Sk"];
  let html = weekdays.map((d) => `<div class="calendar-weekday">${d}</div>`).join("");

  const start = startOfCalendarGrid(PlannerState.monthCursor);
  for (let i = 0; i < 42; i += 1) {
    const day = new Date(start.getTime() + i * 86400000);
    const iso = toIsoDateUTC(day);
    const sameMonth = day.getUTCMonth() === PlannerState.monthCursor.getUTCMonth();
    const selected = iso === PlannerState.selectedDate;
    const summary = PlannerState.monthSummary.get(iso) || { jobs: 0, minutes: 0 };
    const hours = (summary.minutes / 60).toFixed(1);

    const classes = [
      "calendar-cell",
      sameMonth ? "" : "is-outside",
      selected ? "is-selected" : "",
    ]
      .filter(Boolean)
      .join(" ");

    html += `
      <button type="button" class="${classes}" data-day="${iso}">
        <div class="calendar-day">${day.getUTCDate()}</div>
        <div class="calendar-meta">
          <div>${summary.jobs} darb.</div>
          <div>${hours} val.</div>
        </div>
      </button>
    `;
  }

  grid.innerHTML = html;
  grid.querySelectorAll("button[data-day]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const iso = btn.getAttribute("data-day");
      if (!iso) return;
      PlannerState.selectedDate = iso;
      renderCalendar();
      loadDayPlan();
    });
  });
}

async function loadMonthSummary() {
  const status = document.getElementById("plannerStatus");
  const fromDate = firstOfMonth(PlannerState.monthCursor);
  const toDate = addMonths(fromDate, 1);
  const fromTs = fromDate.toISOString();
  const toTs = toDate.toISOString();

  try {
    const resp = await authFetch(
      `/api/v1/admin/appointments?from_ts=${encodeURIComponent(fromTs)}&to_ts=${encodeURIComponent(toTs)}&limit=200`,
    );
    const data = await resp.json();
    const summary = new Map();
    for (const item of data.items || []) {
      const day = String(item.starts_at || "").slice(0, 10);
      if (!day) continue;
      const prev = summary.get(day) || { jobs: 0, minutes: 0 };
      prev.jobs += 1;
      prev.minutes += durationMinutes(item.starts_at, item.ends_at);
      summary.set(day, prev);
    }
    PlannerState.monthSummary = summary;
    renderCalendar();
    if (status) status.textContent = "";
  } catch (err) {
    if (status) status.textContent = "Nepavyko ikelti menesio plano.";
    if (!(err instanceof AuthError)) {
      showToast("Nepavyko ikelti kalendoriaus", "error");
    }
  }
}

function defaultInboxTarget(task) {
  if (task.entity_type === "project" && task.client_key) {
    return `/admin/client/${encodeURIComponent(task.client_key)}`;
  }
  if (task.entity_type === "project" && task.payload && task.payload.project_id) {
    return `/admin/project/${encodeURIComponent(task.payload.project_id)}?day=${encodeURIComponent(PlannerState.selectedDate)}`;
  }
  if (task.entity_type === "call_request") return "/admin/calls";
  if (task.entity_type === "appointment") return "/admin/calendar";
  return "/admin";
}

function renderInbox(items) {
  const list = document.getElementById("plannerInboxList");
  if (!list) return;
  if (!items || !items.length) {
    list.innerHTML = '<li class="empty-row">Inbox tuscias.</li>';
    return;
  }
  list.innerHTML = items.map((task) => {
    const target = defaultInboxTarget(task);
    const entityType = (task.entity_type || "").trim();
    const entityId = (task.entity_id || "").trim();
    const canDelete = entityType === "call_request" && entityId;
    const deleteBtn = canDelete
      ? `<button type="button" class="inbox-item-delete" data-entity-id="${escapeHtml(entityId)}" title="Ištrinti užklausą" aria-label="Ištrinti">Ištrinti</button>`
      : "";
    let titleLine = task.title || "Užduotis";
    if (entityType === "project" && task.payload) {
      const created = formatInboxDate(task.payload.created_at);
      const preferred = formatInboxDate(task.payload.preferred_slot_start);
      const name = (task.payload.client_display_name || task.title || "–").trim();
      const parts = [
        "Sukurta: " + created,
        "Pasirinkta data: " + preferred,
        name !== "–" ? name : "Klientas",
      ];
      titleLine = parts.join(" · ");
    }
    return `
      <li class="inbox-item" data-target="${escapeHtml(target)}" data-entity-type="${escapeHtml(entityType)}" data-entity-id="${escapeHtml(entityId)}">
        <div class="inbox-item-head">
          <span class="inbox-item-title">${escapeHtml(titleLine)}</span>
          <span class="inbox-item-head-right">${urgencyPill(task.urgency)}${deleteBtn}</span>
        </div>
        <div class="inbox-item-reason">${escapeHtml(task.reason || "Reikia veiksmo")}</div>
      </li>
    `;
  }).join("");

  list.querySelectorAll(".inbox-item").forEach((node) => {
    node.addEventListener("click", (e) => {
      if (e.target.closest(".inbox-item-delete")) return;
      const target = node.getAttribute("data-target");
      if (target) window.location.href = target;
    });
  });

  list.querySelectorAll(".inbox-item-delete").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const id = btn.getAttribute("data-entity-id");
      if (!id) return;
      if (!window.confirm("Ištrinti šią skambučio užklausą iš sąrašo?")) return;
      btn.disabled = true;
      try {
        const resp = await authFetch(`/api/v1/admin/call-requests/${encodeURIComponent(id)}`, { method: "DELETE" });
        if (resp && resp.status === 204) {
          const li = btn.closest(".inbox-item");
          if (li) li.remove();
          const countEl = document.getElementById("plannerInboxCount");
          if (countEl) countEl.textContent = String(list.querySelectorAll(".inbox-item").length);
          showToast("Užklausa ištrinta", "success");
        } else {
          showToast("Nepavyko ištrinti", "error");
          btn.disabled = false;
        }
      } catch (err) {
        if (!(err instanceof AuthError)) showToast("Nepavyko ištrinti", "error");
        btn.disabled = false;
      }
    });
  });
}

async function loadInbox() {
  const status = document.getElementById("plannerStatus");
  try {
    const resp = await authFetch("/api/v1/admin/ops/inbox?limit=30");
    const data = await resp.json();
    renderInbox(data.items || []);
    const inboxCount = document.getElementById("plannerInboxCount");
    if (inboxCount) inboxCount.textContent = String((data.items || []).length);
    if (status) status.textContent = "";
  } catch (err) {
    if (status) status.textContent = "Nepavyko ikelti Inbox.";
    if (!(err instanceof AuthError)) {
      showToast("Nepavyko ikelti Inbox", "error");
    }
  }
}

function renderDayPlan(data) {
  const dayTitle = document.getElementById("plannerDayLabel");
  const jobsValue = document.getElementById("plannerDayJobs");
  const hoursValue = document.getElementById("plannerDayHours");
  const list = document.getElementById("plannerDayList");
  if (!dayTitle || !jobsValue || !hoursValue || !list) return;

  dayTitle.textContent = dayLabel(PlannerState.selectedDate);
  const summary = data.summary || {};
  const items = data.items || [];
  const hours = ((summary.total_minutes || 0) / 60).toFixed(1);
  jobsValue.textContent = String(summary.jobs_count || items.length || 0);
  hoursValue.textContent = `${hours} val.`;

  if (!items.length) {
    list.innerHTML = '<li class="empty-row">Siai dienai darbu nerasta.</li>';
    return;
  }

  list.innerHTML = items.map((item) => {
    const startTime = item.start ? new Date(item.start).toLocaleTimeString("lt-LT", { hour: "2-digit", minute: "2-digit" }) : "--:--";
    const endTime = item.end ? new Date(item.end).toLocaleTimeString("lt-LT", { hour: "2-digit", minute: "2-digit" }) : "--:--";
    const duration = Number(item.duration_min || 0);
    return `
      <li class="day-plan-item">
        <div class="inbox-item-head">
          <span class="inbox-item-title">${escapeHtml(item.title || "Darbas")}</span>
          ${statusPill(item.status || "")}
        </div>
        <div class="day-plan-item-meta">
          <span>${escapeHtml(startTime)} - ${escapeHtml(endTime)}</span>
          <span>${duration} min.</span>
          <span>${item.budget == null ? "-" : formatCurrency(item.budget)}</span>
        </div>
        <div class="day-plan-item-links">
          <a class="btn btn-xs" href="${escapeHtml(item.links.project)}">Projektas</a>
          <a class="btn btn-xs btn-ghost" href="${escapeHtml(item.links.client)}">Klientas</a>
        </div>
      </li>
    `;
  }).join("");
}

async function loadDayPlan() {
  const status = document.getElementById("plannerStatus");
  try {
    const resp = await authFetch(`/api/v1/admin/ops/day/${encodeURIComponent(PlannerState.selectedDate)}/plan?limit=50`);
    const data = await resp.json();
    renderDayPlan(data);
    if (status) status.textContent = "";
  } catch (err) {
    if (status) status.textContent = "Nepavyko ikelti dienos plano.";
    if (!(err instanceof AuthError)) {
      showToast("Nepavyko ikelti dienos plano", "error");
    }
  }
}

function bindPlannerActions() {
  document.getElementById("plannerPrevMonth")?.addEventListener("click", () => {
    PlannerState.monthCursor = addMonths(PlannerState.monthCursor, -1);
    loadMonthSummary();
    renderCalendar();
  });
  document.getElementById("plannerNextMonth")?.addEventListener("click", () => {
    PlannerState.monthCursor = addMonths(PlannerState.monthCursor, 1);
    loadMonthSummary();
    renderCalendar();
  });
  document.getElementById("plannerToday")?.addEventListener("click", () => {
    const today = new Date();
    PlannerState.monthCursor = firstOfMonth(new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1)));
    PlannerState.selectedDate = toIsoDateUTC(today);
    loadMonthSummary();
    loadDayPlan();
  });
  document.getElementById("plannerRefreshInbox")?.addEventListener("click", () => {
    loadInbox();
  });
}

function renderMissingToken() {
  const root = document.getElementById("plannerRoot");
  if (!root) return;
  root.innerHTML = `
    <div class="planner-panel">
      <h2>Reikalingas administratoriaus zetonas</h2>
      <p class="section-subtitle" style="margin-top:8px;">Prisijunkite per /login arba sugeneruokite tokena.</p>
    </div>
  `;
}

async function initPlanner() {
  const today = new Date();
  PlannerState.monthCursor = firstOfMonth(new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1)));
  PlannerState.selectedDate = queryDay() || toIsoDateUTC(today);
  const selected = parseIsoDate(PlannerState.selectedDate);
  PlannerState.monthCursor = firstOfMonth(selected);

  if (!Auth.isSet()) {
    renderMissingToken();
    return;
  }

  bindPlannerActions();
  renderCalendar();
  await Promise.all([loadMonthSummary(), loadInbox(), loadDayPlan()]);

  window.setInterval(() => {
    loadInbox();
  }, 30000);
}

document.addEventListener("DOMContentLoaded", initPlanner);
