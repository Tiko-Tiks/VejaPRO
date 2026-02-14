"use strict";

(() => {
  const root = document.getElementById("loginRoot");
  const form = document.getElementById("loginForm");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const submitButton = document.getElementById("loginSubmit");
  const errorElement = document.getElementById("loginError");
  const subtitleEl = document.getElementById("loginSubtitle");
  const linksEl = document.getElementById("loginLinks");

  const supabaseUrl = (root?.dataset.supabaseUrl || "").trim();
  const supabaseAnonKey = (root?.dataset.supabaseAnonKey || "").trim();
  const isAdminLogin = window.location.pathname.startsWith("/admin");

  const ROLE_PORTAL = {
    ADMIN: { sessionKey: "vejapro_supabase_session", redirect: "/admin" },
    CLIENT: { sessionKey: "vejapro_client_session", redirect: "/client" },
    SUBCONTRACTOR: { sessionKey: "vejapro_contractor_session", redirect: "/contractor" },
    EXPERT: { sessionKey: "vejapro_expert_session", redirect: "/expert" },
  };
  const ALL_SESSION_KEYS = Object.values(ROLE_PORTAL).map((item) => item.sessionKey);

  if (isAdminLogin) {
    if (subtitleEl) subtitleEl.textContent = "Administravimo prisijungimas.";
    if (linksEl) {
      linksEl.innerHTML =
        '<a href="/login" style="color: var(--vp-ink-muted); font-weight: 400;">Prisijungti kaip klientui</a>';
    }
  } else if (linksEl) {
    linksEl.innerHTML +=
      '<br /><a href="/admin/login" style="color: var(--vp-ink-muted); font-weight: 400;">Administravimo prisijungimas</a>';
  }

  function normalizeRole(value) {
    if (typeof value !== "string") return "";
    return value.trim().toUpperCase();
  }

  function clearPortalSessions() {
    ALL_SESSION_KEYS.forEach((key) => sessionStorage.removeItem(key));
  }

  function setError(message) {
    if (!errorElement) return;
    if (message) {
      errorElement.textContent = message;
      errorElement.className = "auth-error vp-form-msg error";
    } else {
      errorElement.textContent = "";
      errorElement.className = "auth-error vp-form-msg";
    }
  }

  function setSubmitting(isSubmitting) {
    if (!submitButton) return;
    submitButton.disabled = isSubmitting;
    submitButton.textContent = isSubmitting ? "Jungiamasi..." : "Prisijungti";
  }

  function buildClient() {
    if (!window.supabase?.createClient || !supabaseUrl || !supabaseAnonKey) {
      return null;
    }
    return window.supabase.createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
        detectSessionInUrl: false,
      },
    });
  }

  function decodeTokenPayload(token) {
    if (!token || typeof token !== "string") return null;
    const parts = token.split(".");
    if (parts.length < 2) return null;
    try {
      const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
      const json = atob(padded);
      return JSON.parse(json);
    } catch {
      return null;
    }
  }

  function roleFromToken(accessToken) {
    const payload = decodeTokenPayload(accessToken);
    const role = payload?.app_metadata?.role;
    return normalizeRole(role);
  }

  async function resolveRole(accessToken) {
    if (!accessToken) return "";
    try {
      const response = await fetch("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        return normalizeRole(data?.role);
      }
    } catch {
      // Fallback below.
    }
    return roleFromToken(accessToken);
  }

  function persistSession(sessionKey, session) {
    sessionStorage.setItem(
      sessionKey,
      JSON.stringify({
        access_token: session.access_token,
        refresh_token: session.refresh_token || "",
        expires_at: Number(session.expires_at || 0),
      }),
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    const client = buildClient();
    if (!client) {
      setError("Prisijungimo paslauga siuo metu neprieinama.");
      return;
    }

    const email = (emailInput?.value || "").trim();
    const password = passwordInput?.value || "";
    if (!email || !password) {
      setError("Iveskite el. pasta ir slaptazodi.");
      return;
    }

    setSubmitting(true);
    try {
      const { data, error } = await client.auth.signInWithPassword({
        email,
        password,
      });
      const session = data?.session;
      const accessToken = String(session?.access_token || "").trim();
      if (error || !accessToken) {
        setError("Neteisingi prisijungimo duomenys.");
        return;
      }

      const role = await resolveRole(accessToken);
      if (!role || !ROLE_PORTAL[role]) {
        clearPortalSessions();
        setError("Paskyros role neatpazinta arba siame portale nepalaikoma.");
        return;
      }

      if (isAdminLogin && role !== "ADMIN") {
        clearPortalSessions();
        setError("Prie admin zonos gali jungtis tik ADMIN role.");
        return;
      }

      const portal = ROLE_PORTAL[role];
      clearPortalSessions();
      persistSession(portal.sessionKey, session);
      window.location.href = portal.redirect;
    } catch {
      setError("Neteisingi prisijungimo duomenys.");
    } finally {
      setSubmitting(false);
    }
  }

  form?.addEventListener("submit", handleSubmit);
})();
