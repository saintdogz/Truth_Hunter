(() => {
  const storageKey = "truth-hunter-theme";
  const root = document.documentElement;
  const preferredTheme = () => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved === "light" || saved === "dark") return saved;
    } catch (_) {
      // Storage can be unavailable in privacy-restricted browser contexts.
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  };

  const applyTheme = (theme) => {
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    const toggle = document.querySelector(".theme-toggle");
    if (!toggle) return;
    const dark = theme === "dark";
    const language = root.lang === "hu" ? "hu" : "en";
    const text = toggle.querySelector(".theme-toggle-text");
    toggle.setAttribute("aria-pressed", String(dark));
    toggle.setAttribute(
      "aria-label",
      language === "hu"
        ? `${dark ? "Világos" : "Sötét"} mód bekapcsolása`
        : `Enable ${dark ? "light" : "dark"} mode`,
    );
    if (text) text.textContent = language === "hu" ? (dark ? "Világos" : "Sötét") : dark ? "Light" : "Dark";
  };

  applyTheme(preferredTheme());

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(root.dataset.theme || preferredTheme());
    document.querySelector(".theme-toggle")?.addEventListener("click", () => {
      const theme = root.dataset.theme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(storageKey, theme);
      } catch (_) {
        // The selected theme still applies for the current page.
      }
      applyTheme(theme);
    });
  });
})();
