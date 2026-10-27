/** @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

import { AppShell } from "@/components/app-shell";

describe("app shell theme toggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  test("shows a theme toggle in the top nav", () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>,
    );

    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeInTheDocument();
  });

  test("toggles to light mode and persists the preference", async () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute("data-theme", "light");
    });
    expect(localStorage.getItem("pv-theme")).toBe("light");
    expect(screen.getByRole("button", { name: "Switch to dark mode" })).toBeInTheDocument();
  });

  test("uses persisted theme preference on initial render", async () => {
    localStorage.setItem("pv-theme", "light");

    render(
      <AppShell>
        <div>content</div>
      </AppShell>,
    );

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute("data-theme", "light");
    });
    expect(screen.getByRole("button", { name: "Switch to dark mode" })).toBeInTheDocument();
  });

  test("syncs theme if storage value changes in another tab", async () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>,
    );

    localStorage.setItem("pv-theme", "light");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "pv-theme", newValue: "light" }));
    });

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute("data-theme", "light");
    });
  });
});
