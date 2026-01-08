const PIXELFIT_ASSETS = {
  logoUrl: "/Image/PixelFit Logo.png",
  femaleProfileUrl: "/Image/Female Profile.png",
  maleProfileUrl: "/Image/Male Profile.png",
};

window.PIXELFIT_ASSETS = PIXELFIT_ASSETS;

document.addEventListener("DOMContentLoaded", () => {
  const logos = document.querySelectorAll(".brand__logo");
  logos.forEach((logo) => {
    if (PIXELFIT_ASSETS.logoUrl) {
      logo.src = PIXELFIT_ASSETS.logoUrl;
    }
  });

  const homeBtn = document.getElementById("homeBtn");
  const resizerBtn = document.getElementById("resizerBtn");
  if (!homeBtn && !resizerBtn) {
    return;
  }

  fetch(`${window.location.origin}/api/me`, { credentials: "include" })
    .then((response) => {
      const isLoggedIn = response.ok;
      if (homeBtn) {
        homeBtn.href = isLoggedIn ? "Landing.html" : "index.html";
      }
      if (resizerBtn) {
        resizerBtn.href = isLoggedIn ? "Landing.html" : "login.html";
      }
    })
    .catch(() => {
      if (homeBtn) {
        homeBtn.href = "index.html";
      }
      if (resizerBtn) {
        resizerBtn.href = "login.html";
      }
    });
});
