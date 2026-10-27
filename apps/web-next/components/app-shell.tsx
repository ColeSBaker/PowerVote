import Link from "next/link";
import React, { type PropsWithChildren } from "react";

import { ThemeToggle } from "@/components/theme-toggle";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <>
      <header className="pv-topnav">
        <Link href="/" className="pv-topnav__wordmark">
          Power<span className="pv-topnav__accent">Vote</span>
          <span className="pv-topnav__year">2026</span>
        </Link>
        <nav className="pv-topnav__links" aria-label="Primary routes">
          <Link href="/">Overview</Link>
          <Link href="/map">Map</Link>
          <Link href="/powervote">PowerVote</Link>
        </nav>
        <div className="pv-topnav__actions">
          <ThemeToggle />
        </div>
      </header>
      <main className="pv-shell">
        {children}
      </main>
    </>
  );
}
