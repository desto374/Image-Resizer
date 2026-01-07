const IS_LOCAL =
  location.hostname === "localhost" || location.hostname === "127.0.0.1";
const API_BASE = IS_LOCAL ? "http://127.0.0.1:8000" : window.location.origin;

const profile = document.getElementById("profile");
const profileUsername = document.getElementById("profileUsername");
const profileName = document.getElementById("profileName");
const profileAvatar = document.getElementById("profileAvatar");
const profileAvatarFallback = document.getElementById("profileAvatarFallback");
const authActions = document.getElementById("authActions");

const ASSETS = window.PIXELFIT_ASSETS || {
  femaleProfileUrl: "",
  maleProfileUrl: "",
};

const fileInput = document.getElementById("fileInput");
const fileList = document.getElementById("fileList");
const processBtn = document.getElementById("processBtn");
const progressFill = document.getElementById("progressFill");
const statusText = document.getElementById("statusText");
const downloadArea = document.getElementById("downloadArea");

let filesState = [];

const loadCurrentUser = async () => {
  if (document.body.dataset.authToggle === "off") {
    return;
  }
  try {
    const response = await fetch(`${API_BASE}/api/me`, { credentials: "include" });
    if (!response.ok) {
      if (
        window.location.pathname.endsWith("/app.html")
        || window.location.pathname.endsWith("/Landing.html")
      ) {
        window.location.href = "login.html";
        return;
      }
      if (profile) {
        profile.hidden = true;
      }
      if (authActions) {
        authActions.hidden = false;
      }
      return;
    }
    const data = await response.json();
    const user = data.user || {};
    if (profile) {
      profile.hidden = false;
    }
    if (authActions) {
      authActions.hidden = true;
    }
    if (profileUsername) {
      profileUsername.textContent = user.username || baseUsernameFromEmail(user.email || "");
    }
    if (profileName) {
      profileName.textContent = user.name || user.email || "";
    }
    if (profileAvatar && profileAvatarFallback) {
      if (user.avatar_url) {
        profileAvatar.src = user.avatar_url;
        profileAvatar.style.display = "block";
        profileAvatarFallback.style.display = "none";
      } else {
        if (user.gender === "female") {
          profileAvatar.src = ASSETS.femaleProfileUrl;
          profileAvatar.style.display = "block";
          profileAvatarFallback.style.display = "none";
        } else if (user.gender === "male") {
          profileAvatar.src = ASSETS.maleProfileUrl;
          profileAvatar.style.display = "block";
          profileAvatarFallback.style.display = "none";
        } else {
          profileAvatar.src = "";
          profileAvatar.style.display = "none";
          profileAvatarFallback.textContent = "👤";
          profileAvatarFallback.style.display = "block";
        }
      }
    }
  } catch (error) {
    if (profile) {
      profile.hidden = true;
    }
    if (authActions) {
      authActions.hidden = false;
    }
  }
};

const baseUsernameFromEmail = (email) => {
  if (!email) {
    return "user";
  }
  return email.split("@")[0] || "user";
};

const updateStatus = (message) => {
  statusText.textContent = message;
};

const setProgress = (value) => {
  const clamped = Math.max(0, Math.min(1, value));
  progressFill.style.width = `${clamped * 100}%`;
};

const formatFileName = (name) => {
  const base = name.replace(/\.[^/.]+$/, "");
  return base || "image";
};

const renderFiles = () => {
  fileList.innerHTML = "";

  if (!filesState.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No artwork yet. Drop files here or tap “Select artwork.”";
    fileList.appendChild(empty);
    processBtn.disabled = true;
    return;
  }

  filesState.forEach((entry, index) => {
    const card = document.createElement("div");
    card.className = "file-card";

    const title = document.createElement("div");
    title.className = "file-title";
    title.innerHTML = `<span>${entry.file.name}</span><span class="badge">${entry.file.type || "image"}</span>`;

    const inputs = document.createElement("div");
    inputs.className = "file-inputs";

    const mainField = document.createElement("div");
    mainField.className = "field";
    mainField.innerHTML = `
      <label>Main output folder name</label>
      <input type="text" value="${entry.mainFolder}" data-index="${index}" data-field="mainFolder" />
    `;

    inputs.appendChild(mainField);
    card.appendChild(title);
    card.appendChild(inputs);
    fileList.appendChild(card);
  });

  processBtn.disabled = !filesState.every((entry) => entry.mainFolder);
};

const updateStateFromInputs = (event) => {
  const target = event.target;
  if (target.tagName !== "INPUT") {
    return;
  }
  const index = Number(target.dataset.index);
  const field = target.dataset.field;
  if (!Number.isNaN(index) && field) {
    filesState[index][field] = target.value.trim();
    processBtn.disabled = !filesState.every((entry) => entry.mainFolder);
  }
};

fileList.addEventListener("input", updateStateFromInputs);

fileInput.addEventListener("change", (event) => {
  const files = Array.from(event.target.files || []);
  filesState = files.map((file) => {
    const base = formatFileName(file.name);
    return {
      file,
      mainFolder: base,
    };
  });
  downloadArea.innerHTML = "";
  setProgress(0);
  updateStatus("Files loaded. Add folder names and hit process.");
  renderFiles();
});

const createDownloadCard = (name, blob) => {
  const url = URL.createObjectURL(blob);
  const card = document.createElement("div");
  card.className = "download-card";

  const label = document.createElement("span");
  label.textContent = name;

  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.textContent = "Download zip";

  card.appendChild(label);
  card.appendChild(link);
  downloadArea.appendChild(card);
};

processBtn.addEventListener("click", async () => {
  if (!filesState.length) {
    updateStatus("Add files first.");
    return;
  }

  processBtn.disabled = true;
  downloadArea.innerHTML = "";
  updateStatus("Processing images...");
  setProgress(0);

  try {
    const formData = new FormData();
    const mainFolders = [];

    filesState.forEach((entry) => {
      formData.append("files", entry.file, entry.file.name);
      mainFolders.push(entry.mainFolder);
    });

    formData.append("base_names", JSON.stringify(mainFolders));
    formData.append("main_folder", JSON.stringify(mainFolders));

    updateStatus("Sending to server...");
    const response = await fetch(`${API_BASE}/resize`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      let detail = "Server error.";
      try {
        const errorData = await response.json();
        detail = errorData.detail || detail;
      } catch (error) {
        detail = await response.text();
      }
      throw new Error(detail);
    }

    const zipBlob = await response.blob();
    const zipName = "resized_images.zip";
    createDownloadCard(zipName, zipBlob);
    setProgress(1);
    updateStatus("All images processed and ready for download!");
  } catch (error) {
    updateStatus(`Error: ${error.message}`);
  } finally {
    processBtn.disabled = false;
  }
});

loadCurrentUser();
