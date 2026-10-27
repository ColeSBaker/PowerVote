"use client";

import { useSearchParams } from "next/navigation";
import { PowerVoteLayout } from "@/components/powervote-layout";

export function PowerVotePageInner() {
  const searchParams = useSearchParams();
  const initialAddress = searchParams.get("address") ?? undefined;
  const initialZipcode = searchParams.get("zipcode") ?? undefined;
  return <PowerVoteLayout initialAddress={initialAddress} initialZipcode={initialZipcode} />;
}
