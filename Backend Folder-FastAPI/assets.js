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
});
