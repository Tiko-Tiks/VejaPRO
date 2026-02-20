"use strict";

(() => {
  const root = document.getElementById("registerRoot");
  const form = document.getElementById("registerForm");
  const emailInput = document.getElementById("regEmail");
  const passwordInput = document.getElementById("regPassword");
  const confirmInput = document.getElementById("regPasswordConfirm");
  const submitButton = document.getElementById("registerSubmit");
  const errorElement = document.getElementById("registerError");
  const successElement = document.getElementById("registerSuccess");

  // Ensure clean state on page load (handles BFcache restore)
  if (successElement) successElement.style.display = "none";
  if (form) form.style.display = "";

  const supabaseUrl = (root?.dataset.supabaseUrl || "").trim();
  const supabaseAnonKey = (root?.dataset.supabaseAnonKey || "").trim();

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
    submitButton.textContent = isSubmitting ? "Registruojama..." : "Registruotis";
  }

  function showSuccess() {
    if (form) form.style.display = "none";
    if (successElement) successElement.style.display = "block";
    setError("");
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
      setError("Registracijos paslauga šiuo metu neprieinama.");
      return;
    }

    const email = (emailInput?.value || "").trim();
    const password = passwordInput?.value || "";
    const confirm = confirmInput?.value || "";

    if (!email || !password) {
      setError("Įveskite el. paštą ir slaptažodį.");
      return;
    }

    if (password.length < 6) {
      setError("Slaptažodis turi būti bent 6 simbolių.");
      return;
    }

    if (password !== confirm) {
      setError("Slaptažodžiai nesutampa.");
      return;
    }

    setSubmitting(true);
    try {
      const { data, error } = await client.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: window.location.origin + "/login?confirmed=1&email=" + encodeURIComponent(email),
        },
      });

      if (error) {
        if (error.message.toLowerCase().includes("already registered")) {
          setError("Šis el. pašto adresas jau registruotas.");
        } else {
          setError(error.message || "Registracija nepavyko.");
        }
        return;
      }

      // Supabase signUp returns a user even if email confirmation is required.
      // Show success message asking to confirm email.
      showSuccess();
    } catch {
      setError("Registracija nepavyko. Bandykite vėliau.");
    } finally {
      setSubmitting(false);
    }
  }

  form?.addEventListener("submit", handleSubmit);
})();
