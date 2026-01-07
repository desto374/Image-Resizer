const IS_LOCAL =
  location.hostname === "localhost" || location.hostname === "127.0.0.1";
const API_BASE = IS_LOCAL
  ? "http://127.0.0.1:8000"
  : "https://image-resizer-rxnr.onrender.com";

const userPanel = document.getElementById("userPanel");
const userGreeting = document.getElementById("userGreeting");
const usernameForm = document.getElementById("usernameForm");
const usernameInput = document.getElementById("usernameInput");
const usernameMessage = document.getElementById("usernameMessage");
const signOutBtn = document.getElementById("signOutBtn");

const setUsernameMessage = (text, tone = "") => {
  usernameMessage.textContent = text;
  usernameMessage.dataset.tone = tone;
};

const loadCurrentUser = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/me`, { credentials: "include" });
    if (!response.ok) {
      window.location.href = "login.html";
      return;
    }
    const data = await response.json();
    const user = data.user || {};
    userPanel.hidden = false;
    userGreeting.textContent = `Signed in as ${user.name || user.email}.`;
    usernameInput.value = user.username || "";
  } catch (error) {
    window.location.href = "login.html";
  }
};

usernameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = usernameInput.value.trim();
  if (!username) {
    setUsernameMessage("Username is required.", "error");
    return;
  }
  setUsernameMessage("Updating...", "info");
  try {
    const response = await fetch(`${API_BASE}/api/username`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Unable to update username.");
    }
    setUsernameMessage("Username updated.", "success");
  } catch (error) {
    setUsernameMessage(error.message, "error");
  }
});

loadCurrentUser();

if (signOutBtn) {
  signOutBtn.addEventListener("click", async () => {
    const confirmed = window.confirm("Are You Sure You Want To Sign Out");
    if (!confirmed) {
      return;
    }
    await fetch(`${API_BASE}/api/logout`, { method: "POST", credentials: "include" });
    window.location.href = "index.html";
  });
}
