const IS_LOCAL =
  location.hostname === "localhost" || location.hostname === "127.0.0.1";
const API_BASE = IS_LOCAL
  ? "http://127.0.0.1:8000"
  : "https://image-resizer-deao.onrender.com";

const messageEl = document.getElementById("authMessage");

const setMessage = (text, tone = "") => {
  if (!messageEl) {
    return;
  }
  messageEl.textContent = text;
  messageEl.dataset.tone = tone;
};

const handleAuth = async (endpoint, payload) => {
  setMessage("Working...", "info");
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Something went wrong.");
    }

    setMessage("Success! Redirecting...", "success");
    window.location.href = "Landing.html";
  } catch (error) {
    setMessage(error.message || "Unable to sign in.", "error");
  }
};

const loginForm = document.getElementById("loginForm");
const signupForm = document.getElementById("signupForm");

if (loginForm) {
  loginForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const email = loginForm.querySelector("#email").value;
    const password = loginForm.querySelector("#password").value;
    handleAuth("/api/login", { email, password });
  });
}

if (signupForm) {
  signupForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = signupForm.querySelector("#name").value;
    const username = signupForm.querySelector("#username").value;
    const gender = signupForm.querySelector("#gender").value;
    const email = signupForm.querySelector("#email").value;
    const password = signupForm.querySelector("#password").value;
    handleAuth("/api/signup", { name, username, gender, email, password });
  });
}

const googleButtons = document.querySelectorAll(".btn--google");
if (googleButtons.length) {
  googleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      window.location.href = `${API_BASE}/api/auth/google/start`;
    });
  });
}
