(() => {
  const claim = document.querySelector("#claim");
  const imageInput = document.querySelector("#claim-image");
  const preview = document.querySelector("#image-preview");
  const thumbnail = document.querySelector("#image-preview-thumbnail");
  const previewName = document.querySelector("#image-preview-name");
  const previewSize = document.querySelector("#image-preview-size");
  const removeButton = document.querySelector("#remove-image");
  let previewUrl = null;

  if (!claim || !imageInput || !preview || !thumbnail || !previewName || !previewSize || !removeButton) return;

  const clearPreviewUrl = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  };

  const showPreview = (file) => {
    clearPreviewUrl();
    previewUrl = URL.createObjectURL(file);
    thumbnail.src = previewUrl;
    previewName.textContent = file.name;
    previewSize.textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
    preview.hidden = false;
  };

  const clearImage = () => {
    imageInput.value = "";
    clearPreviewUrl();
    thumbnail.removeAttribute("src");
    preview.hidden = true;
  };

  document.querySelectorAll("[data-example]").forEach((button) => {
    button.addEventListener("click", () => {
      clearImage();
      claim.value = button.dataset.example;
      claim.focus();
    });
  });

  imageInput.addEventListener("change", () => {
    const file = imageInput.files?.[0];
    if (file) {
      claim.value = "";
      showPreview(file);
    } else {
      clearImage();
    }
  });

  document.addEventListener("paste", (event) => {
    const imageItem = Array.from(event.clipboardData?.items || []).find((item) =>
      item.type.startsWith("image/"),
    );
    if (!imageItem) return;
    const blob = imageItem.getAsFile();
    if (!blob || !["image/jpeg", "image/png", "image/webp"].includes(blob.type)) return;

    const extension = blob.type === "image/jpeg" ? "jpg" : blob.type.split("/")[1];
    const file = new File([blob], `clipboard-image.${extension}`, { type: blob.type });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    imageInput.files = transfer.files;
    claim.value = "";
    showPreview(file);
    event.preventDefault();
  });

  removeButton.addEventListener("click", clearImage);
  window.addEventListener("pagehide", clearPreviewUrl);
})();
