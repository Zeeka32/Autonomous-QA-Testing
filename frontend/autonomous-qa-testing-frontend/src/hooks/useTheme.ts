import { useLayoutEffect, useState } from "react";

export type Theme = "dark" | "light";

const THEME_STORAGE_KEY = "autonomous-qa-theme";

function savedTheme(): Theme {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(savedTheme);

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      "content",
      theme === "dark" ? "#0b0f14" : "#f5f7f8",
    );
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // The switch still works when browser storage is unavailable.
    }
  }, [theme]);

  return {
    theme,
    toggleTheme: () => setTheme((current) => current === "dark" ? "light" : "dark"),
  };
}
