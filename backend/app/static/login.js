"use strict";

(() => {
  const root = document.getElementById("loginRoot");
  const form = document.getElementById("loginForm");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const submitButton = document.getElementById("loginSubmit");
  const errorElement = document.getElementById("loginError");

  const supabaseUrl = (root?.dataset.supabaseUrl || "").trim();
  const supabaseAnonKey = (root?.dataset.supabaseAnonKey || "").trim();

  function setError(message) {
    if (!errorElement) return;
    errorElement.textContent = message || "";
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
      setError("Supabase konfiguracija nerasta.");
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
      if (error || !session?.access_token) {
        setError("Neteisingi prisijungimo duomenys");
        return;
      }

      sessionStorage.setItem(
        "vejapro_supabase_session",
        JSON.stringify({
          access_token: session.access_token,
          refresh_token: session.refresh_token || "",
          expires_at: Number(session.expires_at || 0),
        }),
      );

      window.location.href = "/admin";
    } catch {
      setError("Neteisingi prisijungimo duomenys");
    } finally {
      setSubmitting(false);
    }
  }

  // Detect Supabase not configured
  if (
    !supabaseUrl ||
    supabaseUrl === "__SUPABASE_URL__" ||
    !supabaseAnonKey ||
    supabaseAnonKey === "__SUPABASE_ANON_KEY__"
  ) {
    setError("Supabase prisijungimas nesukonfigūruotas. Naudokite dev token (admin > žetonas).");
    if (submitButton) submitButton.disabled = true;
  }

  form?.addEventListener("submit", handleSubmit);
})();

