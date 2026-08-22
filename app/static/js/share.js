document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const input = document.getElementById(button.dataset.copyTarget);
    if (!input) return;
    try {
      await navigator.clipboard.writeText(input.value);
      button.textContent = "Copied";
    } catch (_error) {
      input.select();
    }
  });
});
