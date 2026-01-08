(() => {
  const uploadInput = document.getElementById("editorUpload");
  const exportBtn = document.getElementById("exportBtn");
  const statusEl = document.getElementById("editorStatus");

  const IS_LOCAL =
    window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  const API_BASE = IS_LOCAL ? "http://127.0.0.1:8000" : window.location.origin;

  const BLANK_IMAGE =
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAn0B9vVnO9wAAAAASUVORK5CYII=";

  const editor = new window.tui.ImageEditor("#tui-image-editor", {
    includeUI: {
      loadImage: {
        path: BLANK_IMAGE,
        name: "Blank",
      },
      menu: ["crop", "flip", "rotate", "draw", "shape", "text", "filter"],
      initMenu: "filter",
      uiSize: {
        width: "100%",
        height: "640px",
      },
      menuBarPosition: "bottom",
    },
    cssMaxWidth: 1100,
    cssMaxHeight: 900,
    selectionStyle: {
      cornerSize: 18,
      rotatingPointOffset: 70,
    },
  });

  const setStatus = (message) => {
    if (statusEl) {
      statusEl.textContent = message;
    }
  };

  const dataUrlToBlob = (dataUrl) => {
    const parts = dataUrl.split(",");
    const byteString = atob(parts[1]);
    const mimeMatch = parts[0].match(/:(.*?);/);
    const mime = mimeMatch ? mimeMatch[1] : "image/jpeg";
    const ab = new ArrayBuffer(byteString.length);
    const ia = new Uint8Array(ab);
    for (let i = 0; i < byteString.length; i += 1) {
      ia[i] = byteString.charCodeAt(i);
    }
    return new Blob([ab], { type: mime });
  };

  if (uploadInput) {
    uploadInput.addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) {
        return;
      }
      if (!/image\/(png|jpeg)/.test(file.type)) {
        setStatus("Please upload a PNG or JPG file.");
        return;
      }

      const reader = new FileReader();
      reader.onload = async () => {
        const dataUrl = reader.result;
        try {
          await editor.loadImageFromURL(dataUrl, file.name);
          editor.clearUndoStack();
          setStatus("Editing: " + file.name);
        } catch (error) {
          setStatus("Unable to load the image. Try again.");
        }
      };
      reader.readAsDataURL(file);
    });
  }

  if (exportBtn) {
    exportBtn.addEventListener("click", async () => {
      try {
        setStatus("Exporting and generating sizes...");
        const dataUrl = editor.toDataURL({ format: "jpeg", quality: 0.92 });
        const blob = dataUrlToBlob(dataUrl);
        const filename = "pixelfit_edit_" + Date.now() + ".jpeg";
        const file = new File([blob], filename, { type: "image/jpeg" });

        const formData = new FormData();
        formData.append("files", file);

        const response = await fetch(API_BASE + "/resize", {
          method: "POST",
          body: formData,
          credentials: "include",
        });

        if (!response.ok) {
          const message = await response.text();
          setStatus("Resize failed: " + message);
          return;
        }

        const zipBlob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(zipBlob);
        const link = document.createElement("a");
        link.href = downloadUrl;
        link.download = "pixelfit_resized_images.zip";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(downloadUrl);
        setStatus("Your ZIP is ready.");
      } catch (error) {
        setStatus("Something went wrong while exporting.");
      }
    });
  }
})();
