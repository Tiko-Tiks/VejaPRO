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

  // Detect whether this is admin login or client login
  const isAdminLogin = window.location.pathname.startsWith("/admin");
  const redirectTarget = isAdminLogin ? "/admin" : "/client";
  const sessionKey = isAdminLogin
    ? "vejapro_supabase_session"
    : "vejapro_client_session";

  // Adjust UI for admin login path
  if (isAdminLogin) {
    if (subtitleEl) subtitleEl.textContent = "Administravimo prisijungimas.";
    if (linksEl) {
      linksEl.innerHTML =
        '<a href="/admin" style="color: var(--vp-ink-muted); font-weight: 400;">Grįžti į admin (dev token)</a>';
    }
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

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    const client = buildClient();
    if (!client) {
      setError("Prisijungimo paslauga šiuo metu neprieinama.");
      return;
    }

    const email = (emailInput?.value || "").trim();
    const password = passwordInput?.value || "";
    if (!email || !password) {
      setError("Įveskite el. paštą ir slaptažodį.");
      return;
    }

    setSubmitting(true);
    try {
      const { data, error } = await client.auth.signInWithPassword({
        email,
        password,
      });
      const session = data?.session;
      if (error || !session?.access_token) {
        setError("Neteisingi prisijungimo duomenys.");
        return;
      }

      sessionStorage.setItem(
        sessionKey,
        JSON.stringify({
          access_token: session.access_token,
          refresh_token: session.refresh_token || "",
          expires_at: Number(session.expires_at || 0),
        }),
      );

      window.location.href = redirectTarget;
    } catch {
      setError("Neteisingi prisijungimo duomenys.");
    } finally {
      setSubmitting(false);
    }
  }

  form?.addEventListener("submit", handleSubmit);
})();
