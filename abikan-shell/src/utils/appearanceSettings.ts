export type AppTheme = "light" | "dark";

const THEME_KEY = "abikan.appearance.theme";
export const THEME_CHANGED_EVENT = "abikan:theme-changed";

export function readTheme(storage: Storage | null = defaultStorage()): AppTheme {
  try {
    return storage?.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: AppTheme): void {
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = theme;
  }
}

export function writeTheme(theme: AppTheme, storage: Storage | null = defaultStorage()): void {
  try {
    storage?.setItem(THEME_KEY, theme);
  } catch {
    // A restricted browser storage should not prevent theme switching.
  }
  applyTheme(theme);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(THEME_CHANGED_EVENT));
  }
}

function defaultStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
