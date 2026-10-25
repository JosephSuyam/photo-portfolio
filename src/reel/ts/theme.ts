// Light/dark toggle in the header. The choice is stored; until then the OS setting applies.
// The inline script in base.html applies a stored choice before first paint.

// A block keeps these names out of the global scope shared with the other site scripts.
{
  type Theme = "light" | "dark";

  const STORAGE_KEY = "reel-theme";
  const root = document.documentElement;
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

  const currentTheme = (): Theme => {
    const chosen = root.dataset.theme;
    if (chosen === "light" || chosen === "dark") return chosen;
    return prefersDark.matches ? "dark" : "light";
  };

  const setUpToggle = (button: HTMLButtonElement): void => {
    const updateLabel = (): void => {
      const other = currentTheme() === "dark" ? "light" : "dark";
      button.setAttribute("aria-label", `Switch to ${other} mode`);
    };

    button.addEventListener("click", () => {
      const next: Theme = currentTheme() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Storage can be blocked (private windows, site settings); the choice lasts this page.
      }
      updateLabel();
    });

    prefersDark.addEventListener("change", updateLabel);
    updateLabel();
    button.hidden = false;
  };

  const toggle = document.querySelector<HTMLButtonElement>(".theme-toggle");
  if (toggle) setUpToggle(toggle);
}
