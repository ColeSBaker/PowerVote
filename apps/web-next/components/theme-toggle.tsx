"use client";

import React from "react";
import { useEffect, useState } from "react";

import { isTheme, THEME_STORAGE_KEY, type Theme } from "@/lib/client/theme";

function resolveInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (isTheme(savedTheme)) return savedTheme;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    setTheme(resolveInitialTheme());
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY || !isTheme(event.newValue)) return;
      setTheme(event.newValue);
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const nextTheme = theme === "dark" ? "light" : "dark";
  const nextLabel = nextTheme === "light" ? "Switch to light mode" : "Switch to dark mode";

  return (
    <button
      type="button"
      className="pv-theme-toggle"
      onClick={() => setTheme(nextTheme)}
      aria-label={nextLabel}
      aria-pressed={theme === "light"}
      title={nextLabel}
    >
      {theme === "dark" ? "☀︎ Light" : "☾ Dark"}
    </button>
  );
}
