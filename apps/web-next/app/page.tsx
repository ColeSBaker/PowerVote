"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AddressAutocomplete } from "@/components/address-autocomplete";

export default function HomePage() {
  const router = useRouter();
  const [address, setAddress] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = address.trim();
    if (!q) return;
    const param = /^\d{5}$/.test(q) ? "zipcode" : "address";
    router.push(`/powervote?${param}=${encodeURIComponent(q)}`);
  }

  function handleSelect(selectedAddress: string) {
    const param = /^\d{5}$/.test(selectedAddress) ? "zipcode" : "address";
    router.push(`/powervote?${param}=${encodeURIComponent(selectedAddress)}`);
  }

  return (
    <AppShell>
      <div className="pv-home-hero">
        <div className="pv-home-hero__inner">
          <p className="pv-home-hero__eyebrow">2026 U.S. Elections</p>
          <h1 className="pv-home-hero__headline">
            See what&rsquo;s at stake<br />where you live.
          </h1>
          <p className="pv-home-hero__sub">
            Enter your address to see every competitive race on your 2026 ballot — House, Senate, Governor, and more — with live market odds and competitiveness signals.
          </p>
          <form onSubmit={handleSubmit} className="pv-home-hero__form">
            <div className="pv-home-hero__input-wrap">
              <AddressAutocomplete
                value={address}
                onChange={setAddress}
                onSelect={handleSelect}
                placeholder="Enter address or zip code"
              />
            </div>
            <button type="submit" className="pv-home-hero__cta" disabled={!address.trim()}>
              See My Races
            </button>
          </form>
          <p className="pv-home-hero__secondary-links">
            <Link href="/powervote">Or see previously saved races →</Link>
            <Link href="/map">Or explore all races on the national map →</Link>
          </p>
        </div>
        <div className="pv-home-hero__glow" aria-hidden="true" />
      </div>
    </AppShell>
  );
}
