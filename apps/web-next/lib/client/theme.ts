export const THEME_STORAGE_KEY = "pv-theme";

export type Theme = "dark" | "light";

export function isTheme(value: string | null | undefined): value is Theme {
  return value === "dark" || value === "light";
}

export const THEME_INIT_SCRIPT = `
(() => {
  try {
    const storageKey = "${THEME_STORAGE_KEY}";
    const saved = window.localStorage.getItem(storageKey);
    const theme = (saved === "light" || saved === "dark")
      ? saved
      : (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (_) {
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();
`;
