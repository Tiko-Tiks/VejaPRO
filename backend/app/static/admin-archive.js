"use strict";

const ARCHIVE_MODES = new Set(["archived", "needs_human", "all"]);
const ARCHIVE_SORTS = new Set(["recent", "name", "projects"]);

const ArchiveState = {
  query: "",
  mode: "archived",
  status: "",
  sort: "recent",
  customers: [],
  projects: [],
  groups: [],
};

function setArchiveStatus(message, isError) {
  const el = document.getElementById("archiveStatus");
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("error", !!isError);
}

function sanitizeMode(value) {
  return ARCHIVE_MODES.has(value) ? value : "archived";
}

function sanitizeSort(value) {
  return ARCHIVE_SORTS.has(value) ? value : "recent";
}

function readStateFromUrl() {
  try {
    const params = new URLSearchParams(window.location.search);
    ArchiveState.query = (params.get("q") || "").trim();
    ArchiveState.mode = sanitizeMode((params.get("mode") || "archived").trim());
    ArchiveState.status = (params.get("status") || "").trim().toUpperCase();
    ArchiveState.sort = sanitizeSort((params.get("sort") || "recent").trim());
  } catch {
    ArchiveState.query = "";
    ArchiveState.mode = "archived";
    ArchiveState.status = "";
    ArchiveState.sort = "recent";
  }
}

function writeStateToUrl() {
  const url = new URL(window.location.href);
  if (ArchiveState.query) url.searchParams.set("q", ArchiveState.query);
  else url.searchParams.delete("q");

  if (ArchiveState.mode !== "archived") url.searchParams.set("mode", ArchiveState.mode);
  else url.searchParams.delete("mode");

  if (ArchiveState.status) url.searchParams.set("status", ArchiveState.status);
  else url.searchParams.delete("status");

  if (ArchiveState.sort !== "recent") url.searchParams.set("sort", ArchiveState.sort);
  else url.searchParams.delete("sort");

  window.history.replaceState({}, "", url.toString());
}

function normalize(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function sortByDateDesc(a, b) {
  const ta = Date.parse(a || "");
  const tb = Date.parse(b || "");
  if (Number.isFinite(ta) && Number.isFinite(tb)) return tb - ta;
  if (Number.isFinite(ta)) return -1;
  if (Number.isFinite(tb)) return 1;
  return String(b || "").localeCompare(String(a || ""));
}

function getGroupDisplayName(group) {
  const c = group.customer || {};
  const key = String(group.client_key || c.client_key || "unknown");
  return c.display_name || `Klientas ${key.slice(0, 8) || "-"}`;
}

function getGroupProjectCount(group) {
  const customerCount = Number((group.customer && group.customer.project_count) || 0);
  const projectRowsCount = Array.isArray(group.projects) ? group.projects.length : 0;
  return Math.max(customerCount, projectRowsCount);
}

function getGroupLastActivity(group) {
  const c = group.customer || {};
  const firstProject = group.projects && group.projects[0] ? group.projects[0] : null;
  return c.last_activity || (firstProject && (firstProject.updated_at || firstProject.last_activity)) || "";
}

function getGroupAttentionFlags(group) {
  const flags = new Set();
  const customerFlags = (group.customer && group.customer.attention_flags) || [];
  customerFlags.forEach((flag) => {
    if (flag) flags.add(String(flag));
  });
  (group.projects || []).forEach((project) => {
    const projectFlags = project.attention_flags || [];
    projectFlags.forEach((flag) => {
      if (flag) flags.add(String(flag));
    });
  });
  return Array.from(flags);
}

function buildGroups() {
  const customerByKey = new Map();
  ArchiveState.customers.forEach((row) => {
    const key = String(row.client_key || "");
    if (key) customerByKey.set(key, row);
  });

  const projectsByClient = new Map();
  ArchiveState.projects.forEach((row) => {
    const key = String(row.client_key || "unknown");
    if (!projectsByClient.has(key)) projectsByClient.set(key, []);
    projectsByClient.get(key).push(row);
  });

  projectsByClient.forEach((rows) => {
    rows.sort((a, b) => sortByDateDesc(a.updated_at || a.last_activity, b.updated_at || b.last_activity));
  });

  const allKeys = new Set([...customerByKey.keys(), ...projectsByClient.keys()]);
  const groups = [];
  allKeys.forEach((key) => {
    groups.push({
      client_key: key,
      customer: customerByKey.get(key) || null,
      projects: projectsByClient.get(key) || [],
    });
  });

  groups.sort((a, b) => sortByDateDesc(getGroupLastActivity(a), getGroupLastActivity(b)));
  ArchiveState.groups = groups;
}

function matchesQuery(group) {
  if (!ArchiveState.query) return true;
  const q = normalize(ArchiveState.query);
  const c = group.customer || {};
  const groupFlags = getGroupAttentionFlags(group);

  const baseFields = [
    group.client_key,
    c.client_key,
    c.display_name,
    c.contact_masked,
    c.last_activity,
    c.last_project && c.last_project.id,
    c.last_project && c.last_project.status,
    c.last_project && c.last_project.deposit_state,
    c.last_project && c.last_project.final_state,
    groupFlags.join(" "),
  ];

  const projectFields = (group.projects || []).flatMap((project) => [
    project.id,
    project.status,
    project.stuck_reason,
    project.updated_at,
    project.client_masked,
    (project.attention_flags || []).join(" "),
  ]);

  const haystack = normalize(baseFields.concat(projectFields).join(" "));
  return haystack.includes(q);
}

function matchesMode(group) {
  const hasAttention = getGroupAttentionFlags(group).length > 0;
  if (ArchiveState.mode === "archived") return !hasAttention;
  if (ArchiveState.mode === "needs_human") return hasAttention;
  return true;
}

function matchesStatus(group) {
  if (!ArchiveState.status) return true;
  const wanted = ArchiveState.status;

  const customerStatus = String((group.customer && group.customer.last_project && group.customer.last_project.status) || "");
  if (customerStatus === wanted) return true;

  return (group.projects || []).some((project) => String(project.status || "") === wanted);
}

function sortGroups(groups) {
  const rows = groups.slice();
  if (ArchiveState.sort === "name") {
    rows.sort((a, b) => getGroupDisplayName(a).localeCompare(getGroupDisplayName(b), "lt-LT"));
    return rows;
  }
  if (ArchiveState.sort === "projects") {
    rows.sort((a, b) => {
      const countDiff = getGroupProjectCount(b) - getGroupProjectCount(a);
      if (countDiff !== 0) return countDiff;
      return sortByDateDesc(getGroupLastActivity(a), getGroupLastActivity(b));
    });
    return rows;
  }
  rows.sort((a, b) => sortByDateDesc(getGroupLastActivity(a), getGroupLastActivity(b)));
  return rows;
}

function modeLabel(mode) {
  if (mode === "needs_human") return "Needs human";
  if (mode === "all") return "Visi";
  return "Be demesio";
}

function projectRowHtml(project, clientKey) {
  const pid = String(project.id || "");
  const safePid = encodeURIComponent(pid);
  const safeClient = clientKey && clientKey !== "unknown" ? encodeURIComponent(clientKey) : "";
  const clientLink = safeClient ? `/admin/client/${safeClient}` : "/admin/customers";

  return `<tr>
    <td data-label="Projektas" class="mono">${escapeHtml(pid.slice(0, 8))}</td>
    <td data-label="Statusas">${statusPill(project.status || "-")}</td>
    <td data-label="Depozitas">${escapeHtml(project.deposit_state || "-")}</td>
    <td data-label="Galutinis">${escapeHtml(project.final_state || "-")}</td>
    <td data-label="Priezastis">${escapeHtml(project.stuck_reason || "-")}</td>
    <td data-label="Aktyvumas">${formatDate(project.updated_at || project.last_activity)}</td>
    <td data-label="Veiksmai" style="white-space:nowrap;">
      <a class="btn btn-xs btn-ghost" href="/admin/project/${safePid}">Darbas</a>
      <a class="btn btn-xs" href="${clientLink}">Klientas</a>
    </td>
  </tr>`;
}

function renderGroup(group) {
  const c = group.customer || {};
  const clientKey = String(group.client_key || c.client_key || "unknown");
  const displayName = getGroupDisplayName(group);
  const safeClient = clientKey && clientKey !== "unknown" ? encodeURIComponent(clientKey) : "";
  const clientHref = safeClient ? `/admin/client/${safeClient}` : "/admin/customers";
  const contact = c.contact_masked || (group.projects[0] && group.projects[0].client_masked) || "-";
  const lastActivity = getGroupLastActivity(group);
  const allProjectRows = group.projects || [];
  const visibleProjectRows = allProjectRows.slice(0, 8);
  const hiddenRowsCount = Math.max(0, allProjectRows.length - visibleProjectRows.length);
  const flags = getGroupAttentionFlags(group);
  const flagsHtml = flags.length
    ? flags.map((flag) => attentionPill(flag)).join(" ")
    : '<span class="pill pill-success">No alerts</span>';

  return `<section class="planner-panel archive-card">
    <div class="archive-card-head">
      <div>
        <div class="archive-card-title">${escapeHtml(displayName)}</div>
        <div class="archive-card-meta">
          <span class="mono">client: ${escapeHtml(clientKey.slice(0, 12) || "-")}</span>
          <span>${escapeHtml(contact)}</span>
          <span>${getGroupProjectCount(group)} projektu</span>
          <span>${formatDate(lastActivity)}</span>
        </div>
        <div class="archive-card-meta">${flagsHtml}</div>
      </div>
      <div class="archive-card-actions">
        <a class="btn btn-sm" href="${clientHref}">Atidaryti Client Card</a>
      </div>
    </div>

    ${
      visibleProjectRows.length
        ? `<div class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Projektas</th>
                  <th>Statusas</th>
                  <th>Depozitas</th>
                  <th>Galutinis</th>
                  <th>Priezastis</th>
                  <th>Aktyvumas</th>
                  <th>Veiksmai</th>
                </tr>
              </thead>
              <tbody>
                ${visibleProjectRows.map((row) => projectRowHtml(row, clientKey)).join("")}
              </tbody>
            </table>
          </div>
          ${hiddenRowsCount > 0 ? `<div class="section-subtitle">Rodomi 8 is ${allProjectRows.length} projektu</div>` : ""}`
        : '<div class="empty-row">Projektu irasu nerasta.</div>'
    }
  </section>`;
}

function renderArchive() {
  const root = document.getElementById("archiveResults");
  const summary = document.getElementById("archiveSummary");
  if (!root || !summary) return;

  const filtered = sortGroups(
    ArchiveState.groups.filter((group) => matchesQuery(group) && matchesMode(group) && matchesStatus(group))
  );

  const projectCount = filtered.reduce((acc, group) => acc + getGroupProjectCount(group), 0);
  summary.textContent = `Klientai: ${filtered.length}/${ArchiveState.groups.length} | Projektai: ${projectCount} | Rezimas: ${modeLabel(ArchiveState.mode)}`;

  if (!filtered.length) {
    root.innerHTML = '<div class="empty-row">Nieko nerasta pagal nurodyta filtra ar uzklausa.</div>';
    return;
  }

  root.innerHTML = filtered.map((group) => renderGroup(group)).join("");
}

function dedupeBy(items, keyFn) {
  const out = [];
  const seen = new Set();
  (items || []).forEach((item) => {
    const key = keyFn(item);
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push(item);
  });
  return out;
}

async function fetchAllCustomers() {
  const maxPages = 5;
  let cursor = "";
  let asOf = "";
  let page = 0;
  let rows = [];

  while (page < maxPages) {
    const params = new URLSearchParams({ attention_only: "false", limit: "100" });
    if (cursor) params.set("cursor", cursor);
    if (asOf) params.set("as_of", asOf);

    const resp = await authFetch(`/api/v1/admin/customers?${params.toString()}`);
    const data = await resp.json();
    rows = rows.concat(data.items || []);

    if (!asOf && data.as_of) asOf = String(data.as_of);
    if (!data.has_more || !data.next_cursor) break;

    cursor = String(data.next_cursor);
    page += 1;
  }

  return dedupeBy(rows, (row) => String(row && row.client_key));
}

async function fetchAllProjects() {
  const maxPages = 5;
  let cursor = "";
  let asOf = "";
  let page = 0;
  let rows = [];

  while (page < maxPages) {
    const params = new URLSearchParams({ attention_only: "false", limit: "200" });
    if (cursor) params.set("cursor", cursor);
    if (asOf) params.set("as_of", asOf);

    const resp = await authFetch(`/api/v1/admin/projects/view?${params.toString()}`);
    const data = await resp.json();
    rows = rows.concat(data.items || []);

    if (!asOf && data.as_of) asOf = String(data.as_of);
    if (!data.has_more || !data.next_cursor) break;

    cursor = String(data.next_cursor);
    page += 1;
  }

  return dedupeBy(rows, (row) => String(row && row.id));
}

async function loadArchiveData() {
  setArchiveStatus("Kraunamas archyvas...", false);
  if (!Auth.isSet()) {
    setArchiveStatus("Reikalingas admin zetonas.", true);
    return;
  }

  const [customers, projects] = await Promise.all([fetchAllCustomers(), fetchAllProjects()]);
  ArchiveState.customers = customers;
  ArchiveState.projects = projects;

  buildGroups();
  renderArchive();
  setArchiveStatus("", false);
}

function syncControlsFromState() {
  const queryInput = document.getElementById("archiveQuery");
  const modeSelect = document.getElementById("archiveMode");
  const statusSelect = document.getElementById("archiveStatusFilter");
  const sortSelect = document.getElementById("archiveSort");

  if (queryInput) queryInput.value = ArchiveState.query;
  if (modeSelect) modeSelect.value = ArchiveState.mode;
  if (statusSelect) statusSelect.value = ArchiveState.status;
  if (sortSelect) sortSelect.value = ArchiveState.sort;
}

function bindArchiveEvents() {
  const form = document.getElementById("archiveSearchForm");
  const queryInput = document.getElementById("archiveQuery");
  const clearBtn = document.getElementById("archiveClearBtn");
  const refreshBtn = document.getElementById("archiveRefreshBtn");
  const modeSelect = document.getElementById("archiveMode");
  const statusSelect = document.getElementById("archiveStatusFilter");
  const sortSelect = document.getElementById("archiveSort");
  if (!form || !queryInput || !clearBtn || !refreshBtn || !modeSelect || !statusSelect || !sortSelect) return;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    ArchiveState.query = String(queryInput.value || "").trim();
    writeStateToUrl();
    renderArchive();
  });

  let inputTimer = null;
  queryInput.addEventListener("input", () => {
    clearTimeout(inputTimer);
    inputTimer = setTimeout(() => {
      ArchiveState.query = String(queryInput.value || "").trim();
      writeStateToUrl();
      renderArchive();
    }, 180);
  });

  clearBtn.addEventListener("click", () => {
    queryInput.value = "";
    ArchiveState.query = "";
    writeStateToUrl();
    renderArchive();
  });

  refreshBtn.addEventListener("click", async () => {
    try {
      await loadArchiveData();
      showToast("Archyvas atnaujintas", "success");
    } catch (err) {
      if (!(err instanceof AuthError)) setArchiveStatus("Nepavyko atnaujinti archyvo.", true);
    }
  });

  modeSelect.addEventListener("change", () => {
    ArchiveState.mode = sanitizeMode(String(modeSelect.value || "archived"));
    writeStateToUrl();
    renderArchive();
  });

  statusSelect.addEventListener("change", () => {
    ArchiveState.status = String(statusSelect.value || "").trim().toUpperCase();
    writeStateToUrl();
    renderArchive();
  });

  sortSelect.addEventListener("change", () => {
    ArchiveState.sort = sanitizeSort(String(sortSelect.value || "recent"));
    writeStateToUrl();
    renderArchive();
  });
}

async function initArchive() {
  readStateFromUrl();
  syncControlsFromState();
  bindArchiveEvents();

  try {
    await loadArchiveData();
  } catch (err) {
    if (err instanceof AuthError) return;
    setArchiveStatus("Nepavyko ikelti archyvo.", true);
  }
}

document.addEventListener("DOMContentLoaded", initArchive);
