/**
 * VejaPRO Admin shared JS v3.0
 * Auth, authFetch, sidebar, utils — NIEKADA automatiškai generuoti tokeno
 */
(function () {
  "use strict";

  const Auth = {
    STORAGE_KEY: "vejapro_admin_token",
    get() {
      return localStorage.getItem(this.STORAGE_KEY) || "";
    },
    set(token) {
      const v = this.normalize(token);
      if (v) localStorage.setItem(this.STORAGE_KEY, v);
      else localStorage.removeItem(this.STORAGE_KEY);
      return v;
    },
    remove() {
      localStorage.removeItem(this.STORAGE_KEY);
    },
    normalize(v) {
      if (!v) return "";
      return String(v).replace(/^Bearer\s+/i, "").replace(/\s+/g, "").trim();
    },
    headers() {
      const token = this.normalize(this.get());
      return token ? { Authorization: `Bearer ${token}` } : {};
    },
    async generate() {
      const resp = await fetch("/api/v1/admin/token");
      if (!resp.ok) return null;
      const data = await resp.json();
      const token = this.normalize(data.token || "");
      if (token) this.set(token);
      return token;
    },
  };

  window.Auth = Auth;

  function showToast(msg, type) {
    type = type || "info";
    const existing = document.getElementById("vejapro-toast");
    if (existing) existing.remove();
    const div = document.createElement("div");
    div.id = "vejapro-toast";
    div.setAttribute("role", "alert");
    div.style.cssText = "position:fixed;bottom:20px;right:20px;padding:14px 20px;border-radius:8px;font-size:14px;font-weight:500;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.15);max-width:320px;";
    const colors = { success: "#16a34a", error: "#dc2626", warning: "#ea580c", info: "#0284c7" };
    div.style.background = colors[type] || colors.info;
    div.style.color = "#fff";
    div.textContent = msg;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 4000);
  }

  window.showToast = showToast;

  function parseErrorDetail(resp) {
    return resp.json().then(
      (data) => {
        if (data && typeof data.detail === "string") return data.detail;
        if (data && typeof data.message === "string") return data.message;
        return data ? JSON.stringify(data) : "";
      },
      () => resp.text().catch(() => "")
    );
  }

  async function authFetch(url, options) {
    options = options || {};
    const headers = { ...(options.headers || {}), ...Auth.headers() };
    let resp = await fetch(url, { ...options, headers });

    if (resp.status === 401) {
      showToast("Žetonas negalioja. Generuokite naują.", "error");
      return resp;
    }
    if (resp.status === 403 || resp.status === 404) {
      const detail = await parseErrorDetail(resp);
      showToast(detail || "Nerastas arba nėra prieigos", "error");
      return resp;
    }
    if (resp.status === 429) {
      showToast("Per daug užklausų, palaukite.", "warning");
      return resp;
    }
    if (resp.status >= 500) {
      const path = url.replace(/^[^?]+/, "").split("?")[0] || url;
      const reqId = resp.headers.get("x-request-id") || "";
      console.log("5xx", path, resp.status, reqId);
      showToast("Serverio klaida.", "error");
      return resp;
    }
    return resp;
  }

  window.authFetch = authFetch;

  function escapeHtml(s) {
    if (s == null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatDate(iso) {
    if (!iso) return "-";
    try {
      return new Date(iso).toLocaleString("lt-LT");
    } catch (_) {
      return String(iso);
    }
  }

  function formatCurrency(amount, currency) {
    if (amount == null || amount === undefined || isNaN(amount)) return "-";
    try {
      return new Intl.NumberFormat("lt-LT", {
        style: "currency",
        currency: currency || "EUR",
      }).format(amount);
    } catch (_) {
      return String(amount);
    }
  }

  function maskEmail(email) {
    if (!email || typeof email !== "string") return "-";
    const at = email.indexOf("@");
    if (at <= 0) return "***";
    const local = email.slice(0, at);
    const domain = email.slice(at + 1);
    const m = Math.min(2, Math.floor(local.length / 2));
    return local.slice(0, m) + "***@" + (domain.slice(0, 1) + "***" + (domain.includes(".") ? "." + domain.split(".").pop() : ""));
  }

  function maskPhone(phone) {
    if (!phone || typeof phone !== "string") return "-";
    const digits = phone.replace(/\D/g, "");
    if (digits.length < 4) return "***";
    return phone.slice(0, 4) + "*****" + phone.slice(-2);
  }

  async function copyToClipboard(text) {
    if (!text) return false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {}
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;opacity:0;";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  }

  window.escapeHtml = escapeHtml;
  window.formatDate = formatDate;
  window.formatCurrency = formatCurrency;
  window.maskEmail = maskEmail;
  window.maskPhone = maskPhone;
  window.copyToClipboard = copyToClipboard;
  window.parseErrorDetail = parseErrorDetail;

  function initSidebar(activePath) {
    const sidebar = document.getElementById("admin-sidebar");
    const overlay = document.getElementById("sidebar-overlay");
    const toggle = document.getElementById("sidebar-toggle");
    if (!sidebar || sidebar.dataset.inited) return;
    sidebar.dataset.inited = "1";

    if (toggle) {
      toggle.addEventListener("click", () => {
        sidebar.classList.toggle("open");
        if (overlay) overlay.classList.toggle("open");
      });
    }
    if (overlay) {
      overlay.addEventListener("click", () => {
        sidebar.classList.remove("open");
        overlay.classList.remove("open");
      });
    }

    const links = sidebar.querySelectorAll(".sidebar-nav a");
    const path = activePath || window.location.pathname;
    links.forEach((a) => {
      const href = a.getAttribute("href") || "";
      const active = href === "/admin" ? path === "/admin" : path === href || path.startsWith(href + "/");
      a.classList.toggle("active", active);
    });
  }

  window.initSidebar = initSidebar;
})();
