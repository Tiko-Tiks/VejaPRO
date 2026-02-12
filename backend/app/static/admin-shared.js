/* ===================================================================
   VejaPRO Admin — Shared JavaScript (V3.0)
   Auth, authFetch, UI utilities, sidebar logic.
   =================================================================== */

"use strict";

/* --- Auth / Token Management --- */
const Auth = {
  STORAGE_KEY: "vejapro_admin_token",
  SUPABASE_SESSION_KEY: "vejapro_supabase_session",
  _refreshPromise: null,

  _readSupabaseSession() {
    const raw = sessionStorage.getItem(this.SUPABASE_SESSION_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") {
        sessionStorage.removeItem(this.SUPABASE_SESSION_KEY);
        return null;
      }
      return parsed;
    } catch {
      sessionStorage.removeItem(this.SUPABASE_SESSION_KEY);
      return null;
    }
  },

  get() {
    return this.getToken();
  },

  set(token) {
    localStorage.setItem(this.STORAGE_KEY, this.normalize(token));
  },

  remove() {
    localStorage.removeItem(this.STORAGE_KEY);
  },

  normalize(v) {
    if (!v) return "";
    v = v.trim();
    if (v.startsWith("Bearer ")) v = v.slice(7);
    return v.trim();
  },

  hasSupabaseSession() {
    return !!this._readSupabaseSession();
  },

  getToken() {
    const session = this._readSupabaseSession();
    if (session) {
      const accessToken = this.normalize(String(session.access_token || ""));
      if (accessToken) return accessToken;
    }
    return localStorage.getItem(this.STORAGE_KEY) || "";
  },

  setSupabaseSession(session) {
    sessionStorage.setItem(this.SUPABASE_SESSION_KEY, JSON.stringify(session));
  },

  headers() {
    const t = this.getToken();
    if (!t) return {};
    return { Authorization: "Bearer " + t };
  },

  /** Manual-only: call ONLY from user button click. Never auto-generate. */
  async generate(secret) {
    const headers = {};
    if (secret) headers["X-Admin-Token-Secret"] = secret;
    const resp = await fetch("/api/v1/admin/token", { headers });
    if (!resp.ok) {
      const err = await parseErrorDetail(resp);
      throw new Error(err);
    }
    const data = await resp.json();
    const token = data.access_token || data.token || "";
    if (token) this.set(token);
    return token;
  },

  isSet() {
    return this.hasSupabaseSession() || !!localStorage.getItem(this.STORAGE_KEY);
  },

  logout() {
    sessionStorage.removeItem(this.SUPABASE_SESSION_KEY);
    this._refreshPromise = null;
    window.location.href = "/login";
  },

  async refreshIfNeeded() {
    const session = this._readSupabaseSession();
    if (!session) return;

    const refreshToken = String(session.refresh_token || "").trim();
    if (!refreshToken) {
      this.logout();
      throw new AuthError("Session refresh token missing", 401);
    }

    const now = Math.floor(Date.now() / 1000);
    const expiresAt = Number(session.expires_at || 0);
    if (expiresAt - now > 300) return;

    if (this._refreshPromise) {
      return this._refreshPromise;
    }

    this._refreshPromise = (async () => {
      try {
        const resp = await fetch("/api/v1/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!resp.ok) {
          this.logout();
          throw new AuthError("Session refresh failed", resp.status);
        }

        let data = null;
        try {
          data = await resp.json();
        } catch {
          this.logout();
          throw new AuthError("Session refresh failed", 502);
        }

        const nextAccess = this.normalize(String(data.access_token || ""));
        if (!nextAccess) {
          this.logout();
          throw new AuthError("Session refresh failed", 502);
        }

        const nextRefresh = String(data.refresh_token || refreshToken).trim() || refreshToken;
        const nextExpiresRaw = Number(data.expires_at || 0);
        const nextExpires = Number.isFinite(nextExpiresRaw) && nextExpiresRaw > 0
          ? Math.floor(nextExpiresRaw)
          : Math.floor(Date.now() / 1000) + 3600;

        this.setSupabaseSession({
          access_token: nextAccess,
          refresh_token: nextRefresh,
          expires_at: nextExpires,
        });
      } finally {
        this._refreshPromise = null;
      }
    })();

    return this._refreshPromise;
  },
};

/* --- authFetch: fetch with Bearer + error handling + 15s timeout --- */
async function authFetch(url, options = {}) {
  await Auth.refreshIfNeeded();
  const headers = Object.assign({}, Auth.headers(), options.headers || {});
  if (!headers["Content-Type"] && options.body && typeof options.body === "string") {
    headers["Content-Type"] = "application/json";
  }

  const timeoutMs = options.timeout || 15000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let resp;
  try {
    resp = await fetch(url, { ...options, headers, signal: controller.signal });
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      showToast("Serveris neatsako (timeout)", "error");
      throw new FetchError("Timeout", 0);
    }
    showToast("Tinklo klaida", "error");
    throw err;
  }
  clearTimeout(timer);

  if (resp.ok) return resp;

  // Error handling strategy
  const status = resp.status;
  if (status === 401) {
    if (Auth.hasSupabaseSession()) {
      Auth.logout();
      throw new AuthError("Unauthorized", 401);
    }
    showToast("Prisijunkite per /login arba sugeneruokite zetoną.", "error");
    showTokenCard();
    throw new AuthError("Unauthorized", 401);
  }
  if (status === 403 || status === 404) {
    showToast("Nerastas arba nera prieigos", "error");
    throw new FetchError("Not found or forbidden", status);
  }
  if (status === 429) {
    showToast("Per daug uzklaisu, palaukite", "warning");
    throw new FetchError("Rate limited", 429);
  }
  // 5xx
  const method = (options.method || "GET").toUpperCase();
  const urlPath = new URL(url, window.location.origin).pathname;
  const reqId = resp.headers.get("x-request-id") || "-";
  console.log("Server error:", method, urlPath, status, "req-id:", reqId);
  // NEVER log response body

  const detail = await parseErrorDetail(resp);
  showToast("Serverio klaida: " + detail, "error");
  throw new FetchError(detail, status);
}

class AuthError extends Error {
  constructor(msg, status) { super(msg); this.status = status; }
}

class FetchError extends Error {
  constructor(msg, status) { super(msg); this.status = status; }
}

/* --- parseErrorDetail: FastAPI {detail:...} or {message:...} --- */
async function parseErrorDetail(resp) {
  try {
    const data = await resp.json();
    if (typeof data.detail === "string") return data.detail;
    if (typeof data.detail === "object" && data.detail !== null) {
      // FastAPI validation errors
      if (Array.isArray(data.detail)) {
        return data.detail.map(e => e.msg || JSON.stringify(e)).join("; ");
      }
      return JSON.stringify(data.detail);
    }
    if (data.message) return data.message;
    return "Klaida " + resp.status;
  } catch {
    return "Klaida " + resp.status;
  }
}

/* --- UI Utilities --- */

function escapeHtml(s) {
  if (!s) return "";
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(s).replace(/[&<>"']/g, c => map[c]);
}

function formatDate(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("lt-LT") + " " + d.toLocaleTimeString("lt-LT", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function formatDateShort(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleDateString("lt-LT");
  } catch {
    return iso;
  }
}

function formatCurrency(n) {
  if (n == null) return "-";
  return Number(n).toLocaleString("lt-LT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " \u20AC";
}

function maskEmail(email) {
  if (!email) return "-";
  const [local, domain] = email.split("@");
  if (!domain) return email.charAt(0) + "***";
  const dl = domain.split(".");
  return local.charAt(0) + "***@" + dl[0].charAt(0) + "***." + dl.slice(1).join(".");
}

function maskPhone(phone) {
  if (!phone) return "-";
  const clean = phone.replace(/\s/g, "");
  if (clean.length < 6) return clean.charAt(0) + "***";
  return clean.slice(0, 4) + "*".repeat(clean.length - 6) + clean.slice(-2);
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast("Nukopijuota", "success");
  }).catch(() => {
    showToast("Nepavyko nukopijuoti", "error");
  });
}

/* --- Status pill helper --- */
const STATUS_PILLS = {
  DRAFT: { cls: "pill-gray", label: "Juodrastis" },
  PAID: { cls: "pill-info", label: "Apmoketas" },
  SCHEDULED: { cls: "pill-info", label: "Suplanuotas" },
  PENDING_EXPERT: { cls: "pill-warning", label: "Laukia eksperto" },
  CERTIFIED: { cls: "pill-success", label: "Sertifikuotas" },
  ACTIVE: { cls: "pill-success", label: "Aktyvus" },
  SUCCEEDED: { cls: "pill-success", label: "Pavyko" },
  FAILED: { cls: "pill-error", label: "Nepavyko" },
  PENDING: { cls: "pill-warning", label: "Laukia" },
  CONFIRMED: { cls: "pill-success", label: "Patvirtinta" },
  EXPIRED: { cls: "pill-gray", label: "Pasibaige" },
  SENT: { cls: "pill-success", label: "Issiusta" },
  QUEUED: { cls: "pill-info", label: "Eileje" },
};

function statusPill(status) {
  const s = STATUS_PILLS[status] || { cls: "pill-gray", label: status || "-" };
  return `<span class="pill ${s.cls}" title="${escapeHtml(status || '')}">${escapeHtml(s.label)}</span>`;
}

/* --- Attention flag pills --- */
const ATTENTION_FLAGS = {
  pending_confirmation: { cls: "pill-error", label: "Laukia patvirtinimo" },
  failed_outbox: { cls: "pill-warning", label: "Nepavykes pranesimas" },
  missing_deposit: { cls: "pill-yellow", label: "Nera depozito" },
  missing_final: { cls: "pill-yellow", label: "Nera galutinio" },
  stale_paid_no_schedule: { cls: "pill-gray", label: "Apmoketas, nesuplanuotas" },
};

function attentionPill(flag) {
  const f = ATTENTION_FLAGS[flag] || { cls: "pill-gray", label: flag };
  return `<span class="pill ${f.cls}" title="${escapeHtml(flag)}">${escapeHtml(f.label)}</span>`;
}

/* --- Toast System --- */
let _toastContainer = null;

function _ensureToastContainer() {
  if (!_toastContainer) {
    _toastContainer = document.createElement("div");
    _toastContainer.className = "toast-container";
    document.body.appendChild(_toastContainer);
  }
  return _toastContainer;
}

function showToast(msg, type = "info", duration = 4000) {
  const container = _ensureToastContainer();
  const el = document.createElement("div");
  el.className = "toast toast-" + type;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = "toastOut 300ms ease forwards";
    setTimeout(() => el.remove(), 300);
  }, duration);
}

/* --- Token Card toggle --- */
function showTokenCard() {
  const body = document.querySelector(".token-card-body");
  if (body) body.classList.add("open");
}

function initTokenCard() {
  const header = document.querySelector(".token-card-header");
  const body = document.querySelector(".token-card-body");
  if (!header || !body) return;

  header.addEventListener("click", () => {
    body.classList.toggle("open");
  });

  if (!document.getElementById("tokenQuickActions")) {
    const actions = document.createElement("div");
    actions.id = "tokenQuickActions";
    actions.className = "token-quick-actions";
    actions.innerHTML = `
      <a class="btn btn-sm btn-primary" href="/login">Prisijungti</a>
      <div style="display:flex;gap:6px;align-items:center;">
        <input id="tokenSecretInput" type="password" class="form-input" placeholder="Admin secret..." style="font-size:11px;padding:6px 10px;flex:1;" />
        <button type="button" id="btnGenSecret" class="btn btn-sm btn-secondary" style="white-space:nowrap;">Gen.</button>
      </div>
    `;
    body.appendChild(actions);

    document.getElementById("btnGenSecret")?.addEventListener("click", async () => {
      const secretInput = document.getElementById("tokenSecretInput");
      const secret = (secretInput?.value || "").trim();
      if (!secret) {
        showToast("Iveskite admin secret", "warning");
        return;
      }
      try {
        const token = await Auth.generate(secret);
        if (token) {
          showToast("Zetonas sugeneruotas", "success");
          if (secretInput) secretInput.value = "";
          window.location.reload();
        }
      } catch (err) {
        showToast("Nepavyko: " + err.message, "error");
      }
    });
  }
}

/* --- Sidebar --- */
let _sidebarInitialized = false;

function initSidebar() {
  // Idempotent — safe to call multiple times
  if (_sidebarInitialized) return;
  _sidebarInitialized = true;

  const sidebar = document.querySelector(".sidebar");
  const hamburger = document.querySelector(".hamburger");
  const overlay = document.querySelector(".sidebar-overlay");

  if (hamburger && sidebar && overlay) {
    hamburger.addEventListener("click", () => {
      sidebar.classList.toggle("open");
      overlay.classList.toggle("active");
    });

    overlay.addEventListener("click", () => {
      sidebar.classList.remove("open");
      overlay.classList.remove("active");
    });
  }

  renderSidebarAuthActions();

  // Global search input (V3 Diena 5–6) — inject after sidebar-header
  if (sidebar && !document.getElementById("sidebarSearchWrap")) {
    const header = sidebar.querySelector(".sidebar-header");
    const wrap = document.createElement("div");
    wrap.id = "sidebarSearchWrap";
    wrap.style.cssText = "padding:8px 12px;border-bottom:1px solid rgba(255,255,255,0.08);";
    wrap.innerHTML = `<input id="sidebarSearch" type="text" class="form-input" placeholder="Ieškoti (Ctrl+K)..." style="width:100%;font-size:12px;" />`;
    if (header) {
      sidebar.insertBefore(wrap, header.nextElementSibling || null);
    } else {
      sidebar.insertBefore(wrap, sidebar.firstChild);
    }
    initGlobalSearch();
  }

  // Mark active nav item based on current path
  const path = window.location.pathname;
  document.querySelectorAll(".nav-item").forEach(item => {
    const href = item.getAttribute("href");
    if (!href) return;
    if (path === href || (href !== "/admin" && path.startsWith(href))) {
      item.classList.add("active");
    }
  });
}

function renderSidebarAuthActions() {
  const sidebar = document.querySelector(".sidebar");
  if (!sidebar) return;

  const existing = document.getElementById("sidebarAuthActions");
  if (existing) existing.remove();

  if (!Auth.hasSupabaseSession()) return;

  const footer = sidebar.querySelector(".sidebar-footer");
  const wrap = document.createElement("div");
  wrap.id = "sidebarAuthActions";
  wrap.className = "sidebar-auth-actions";
  wrap.innerHTML = '<button type="button" class="btn btn-secondary btn-sm" id="btnLogoutSupabase">Atsijungti</button>';

  if (footer) {
    sidebar.insertBefore(wrap, footer);
  } else {
    sidebar.appendChild(wrap);
  }

  document.getElementById("btnLogoutSupabase")?.addEventListener("click", () => {
    Auth.logout();
  });
}

/* --- Sidebar HTML generator --- */
function sidebarHTML(activePage) {
  const pages = [
    { href: "/admin", icon: "dashboard", label: "Dashboard" },
    { href: "/admin/customers", icon: "people", label: "Klientai" },
    { href: "/admin/projects", icon: "folder", label: "Projektai" },
    { href: "/admin/calls", icon: "phone", label: "Skambuciai" },
    { href: "/admin/calendar", icon: "calendar", label: "Kalendorius" },
    { href: "/admin/audit", icon: "history", label: "Auditas" },
    { href: "/admin/margins", icon: "calculator", label: "Marzos" },
    { href: "/admin/finance", icon: "wallet", label: "Finansai" },
    { href: "/admin/ai", icon: "brain", label: "AI" },
  ];

  const ICONS = {
    dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    people: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
    phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    calendar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    calculator: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="8" y2="10.01"/><line x1="12" y1="10" x2="12" y2="10.01"/><line x1="16" y1="10" x2="16" y2="10.01"/><line x1="8" y1="14" x2="8" y2="14.01"/><line x1="12" y1="14" x2="12" y2="14.01"/><line x1="16" y1="14" x2="16" y2="14.01"/><line x1="8" y1="18" x2="16" y2="18"/></svg>',
    wallet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="5" width="22" height="16" rx="2"/><path d="M1 10h22"/><circle cx="18" cy="15" r="1"/></svg>',
    brain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7z"/><line x1="9" y1="21" x2="15" y2="21"/></svg>',
  };

  return pages.map(p => {
    const active = activePage === p.href ? " active" : "";
    return `<a href="${p.href}" class="nav-item${active}">${ICONS[p.icon] || ""}${escapeHtml(p.label)}</a>`;
  }).join("\n");
}

/* --- Dashboard SSE (operator workflow) --- */
let _dashboardSSE = null;

function startDashboardSSE() {
  if (_dashboardSSE) return;
  const token = Auth.getToken();
  if (!token) return;

  const url = "/api/v1/admin/dashboard/sse?token=" + encodeURIComponent(token);
  _dashboardSSE = new EventSource(url);

  _dashboardSSE.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "triage_update" && data.triage) {
        const container = document.getElementById("triageContainer");
        if (container && typeof renderTriage === "function") {
          const prevKeys = new Set(Array.from(container.querySelectorAll(".triage-card")).map((el) => el.dataset.clientKey));
          renderTriage(data.triage, false);
          const newCards = container.querySelectorAll(".triage-card");
          newCards.forEach((card) => {
            const key = card.dataset.clientKey || "";
            if (!prevKeys.has(key)) card.classList.add("highlight-new");
          });
          if (container.querySelector(".triage-card") && !prevKeys.size) {
            showToast("Naujas klientas reikalauja dėmesio", "info");
          }
        }
      }
      if (data.type === "call_request_created") {
        window.dispatchEvent(new CustomEvent("dashboard-sse-call-created", { detail: data }));
      }
    } catch (err) {
      console.error("Dashboard SSE parse error:", err);
    }
  };

  _dashboardSSE.onerror = () => {
    stopDashboardSSE();
  };
}

function stopDashboardSSE() {
  if (_dashboardSSE) {
    _dashboardSSE.close();
    _dashboardSSE = null;
  }
}

/* --- Quick action (one-click workflow redirect / action endpoint) --- */
function quickAction(type, projectId, clientKey) {
  switch (type) {
    case "record_deposit":
      if (projectId) window.location.href = "/admin/projects#manual-deposit-" + projectId;
      break;
    case "record_final":
      if (projectId) window.location.href = "/admin/projects#manual-final-" + projectId;
      break;
    case "schedule_visit":
      window.location.href = "/admin/calendar";
      break;
    case "assign_expert":
      if (projectId) window.location.href = "/admin/projects#assign-expert-" + projectId;
      break;
    case "certify_project":
      if (projectId) window.location.href = "/admin/projects#certify-" + projectId;
      break;
    case "resend_confirmation":
      if (clientKey) window.location.href = "/admin/customers/" + encodeURIComponent(clientKey);
      else showToast("Persiuntimas galimas kliento profilyje.", "info");
      break;
    default:
      if (clientKey) window.location.href = "/admin/customers/" + encodeURIComponent(clientKey);
      else window.location.href = "/admin/customers";
  }
}

/* --- renderMiniTriage: Reusable (V3 Diena 4) --- */
function renderMiniTriage(items, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!items || !items.length) {
    container.style.display = "none";
    return;
  }
  container.style.display = "flex";
  container.classList.add("horizontal-scroll");
  container.innerHTML = items.map((t) => {
    const pa = t.primary_action || {};
    const label = escapeHtml(pa.label || "Veiksmas");
    const actionKey = escapeHtml(pa.action_key || "");
    const projectId = escapeHtml(t.project_id || "");
    const clientKey = escapeHtml(t.client_key || "");
    const contact = escapeHtml(t.contact_masked || "-");
    const reason = escapeHtml(t.stuck_reason || "");
    return `<div class="triage-card" data-project-id="${projectId}">
      <div class="triage-contact">${contact}</div>
      <div class="triage-reason">${reason}</div>
      <button class="btn triage-action btn-primary" data-action-key="${actionKey}" data-project-id="${projectId}" data-client-key="${clientKey}">${label}</button>
    </div>`;
  }).join("");

  container.querySelectorAll("button[data-action-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const type = btn.getAttribute("data-action-key");
      const pid = btn.getAttribute("data-project-id");
      const ck = btn.getAttribute("data-client-key");
      if (typeof quickAction === "function") quickAction(type, pid, ck);
    });
  });
}

/* --- Global search (V3 Diena 5–6) --- */
let _globalSearchInitialized = false;

function initGlobalSearch() {
  if (_globalSearchInitialized) return;
  _globalSearchInitialized = true;

  const input = document.getElementById("sidebarSearch");
  if (!input) return;

  document.addEventListener("keydown", (e) => {
    if (e.key === "k" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (input) {
        input.focus();
        input.select();
      }
    }
  });

  let searchDebounce = null;
  input.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    const q = input.value.trim();
    if (q.length < 2) return;
    searchDebounce = setTimeout(() => doGlobalSearch(q), 300);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      doGlobalSearch(input.value.trim());
    }
  });
}

async function doGlobalSearch(q) {
  if (!q || q.length < 2) return;
  if (!Auth.isSet()) {
    showToast("Žetonas reikalingas", "warning");
    return;
  }
  try {
    const resp = await authFetch("/api/v1/admin/search?q=" + encodeURIComponent(q) + "&limit=10");
    if (!resp.ok) return;
    const data = await resp.json();
    const items = data.items || [];
    if (items.length === 0) {
      showToast("Nieko nerasta", "info");
      return;
    }
    if (items.length === 1) {
      window.location.href = items[0].href;
      return;
    }
    // Multiple — go to first or show brief toast
    showToast(items.length + " rasta. Atidaryti pirmą?", "info");
    setTimeout(() => { window.location.href = items[0].href; }, 500);
  } catch {}
}

/* --- Init all shared features --- */
function initAdmin() {
  initSidebar();
  initTokenCard();
}

/* --- DOMContentLoaded auto-init --- */
document.addEventListener("DOMContentLoaded", initAdmin);
