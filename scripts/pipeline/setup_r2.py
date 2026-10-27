#!/usr/bin/env python3
"""One-time Cloudflare R2 provisioning for PowerVote.

Creates two R2 buckets and enables public access on the CDN bucket:

    powervote-snapshots  — private; daily snapshot CSV archive (existing)
    powervote-cdn        — public; content-addressable static artifacts + GeoJSON

After this script runs, add the printed POWERVOTE_CDN_BASE_URL value as a
GitHub Actions secret so the daily ETL workflow can upload and redirect to CDN.

Required environment variables:
    CLOUDFLARE_R2_ACCOUNT_ID  — shown in Cloudflare dashboard → top-right account menu
    CLOUDFLARE_API_TOKEN      — API token with Workers R2 Storage:Edit permission
                                Create at: dashboard → My Profile → API Tokens →
                                Create Token → use "Edit Cloudflare Workers" template,
                                then add Workers R2 Storage:Edit to the permissions.

Optional S3 credentials (to verify bucket write access after creation):
    CLOUDFLARE_R2_ACCESS_KEY_ID
    CLOUDFLARE_R2_SECRET_ACCESS_KEY

Idempotent — safe to run multiple times. Already-existing buckets are
reported as such rather than treated as errors.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
SNAPSHOT_BUCKET = "powervote-snapshots"
CDN_BUCKET = "powervote-cdn"


# ---------------------------------------------------------------------------
# Cloudflare REST API helpers
# ---------------------------------------------------------------------------

def _cf_request(
    method: str,
    path: str,
    account_id: str,
    api_token: str,
    body: dict | None = None,
) -> dict:
    """Make an authenticated Cloudflare REST API call and return parsed JSON."""
    url = f"{CLOUDFLARE_API_BASE}/accounts/{account_id}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        raise RuntimeError(
            f"Cloudflare API {method} {url} → HTTP {exc.code}: {json.dumps(parsed)}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Network error calling Cloudflare API: {exc.reason}") from exc


def list_buckets(account_id: str, api_token: str) -> list[str]:
    result = _cf_request("GET", "/r2/buckets", account_id, api_token)
    return [b["name"] for b in result.get("result", {}).get("buckets", [])]


def create_bucket(name: str, account_id: str, api_token: str) -> bool:
    """Create an R2 bucket. Returns True if created, False if already existed."""
    try:
        _cf_request("POST", "/r2/buckets", account_id, api_token, body={"name": name})
        return True
    except RuntimeError as exc:
        msg = str(exc)
        # R2 returns 409 when bucket already exists
        if "10006" in msg or "already exists" in msg.lower() or "HTTP 409" in msg:
            return False
        raise


def enable_public_access(bucket_name: str, account_id: str, api_token: str) -> str:
    """Enable the managed r2.dev public domain. Returns the public domain string."""
    result = _cf_request(
        "PUT",
        f"/r2/buckets/{bucket_name}/domains/managed",
        account_id,
        api_token,
        body={"enabled": True},
    )
    domain: str = result["result"]["domain"]
    return domain


def get_public_domain(bucket_name: str, account_id: str, api_token: str) -> str | None:
    """Return the r2.dev domain if public access is already enabled, else None."""
    try:
        result = _cf_request(
            "GET",
            f"/r2/buckets/{bucket_name}/domains/managed",
            account_id,
            api_token,
        )
        r = result.get("result", {})
        return r["domain"] if r.get("enabled") else None
    except RuntimeError:
        return None


# ---------------------------------------------------------------------------
# S3-compatible write-access verification (optional)
# ---------------------------------------------------------------------------

def verify_s3_write(bucket: str, account_id: str, access_key: str, secret_key: str) -> bool:
    """Upload a tiny probe object to confirm S3 write access. Returns True on success."""
    try:
        import boto3  # noqa: PLC0415
        from botocore.exceptions import ClientError  # noqa: PLC0415
    except ImportError:
        logger.warning("boto3 not installed — skipping S3 write-access verification")
        return False

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )
    probe_key = "_setup_probe.txt"
    try:
        client.put_object(Bucket=bucket, Key=probe_key, Body=b"ok", ContentType="text/plain")
        client.delete_object(Bucket=bucket, Key=probe_key)
        return True
    except ClientError as exc:
        logger.warning("S3 write-access check failed for %s: %s", bucket, exc)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    account_id = os.environ.get("CLOUDFLARE_R2_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

    if not account_id or not api_token:
        print(
            "ERROR: CLOUDFLARE_R2_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set.\n"
            "\n"
            "  CLOUDFLARE_R2_ACCOUNT_ID  — Cloudflare dashboard → top-right account menu\n"
            "  CLOUDFLARE_API_TOKEN      — dashboard → My Profile → API Tokens → Create Token\n"
            "                             Use 'Edit Cloudflare Workers' template and add\n"
            "                             Workers R2 Storage:Edit to the permissions.\n",
            file=sys.stderr,
        )
        return 1

    access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "").strip()

    print(f"Account ID : {account_id}")
    print()

    # ------------------------------------------------------------------
    # 1. Snapshot archive bucket (private, existing)
    # ------------------------------------------------------------------
    print(f"[1/3] Snapshot archive bucket: {SNAPSHOT_BUCKET}")
    created = create_bucket(SNAPSHOT_BUCKET, account_id, api_token)
    if created:
        print(f"      Created ✓")
    else:
        print(f"      Already exists ✓")

    if access_key and secret_key:
        ok = verify_s3_write(SNAPSHOT_BUCKET, account_id, access_key, secret_key)
        print(f"      S3 write access: {'✓' if ok else '✗ (check R2 API token permissions)'}")

    # ------------------------------------------------------------------
    # 2. CDN bucket (public)
    # ------------------------------------------------------------------
    print(f"\n[2/3] CDN bucket: {CDN_BUCKET}")
    created = create_bucket(CDN_BUCKET, account_id, api_token)
    if created:
        print(f"      Created ✓")
    else:
        print(f"      Already exists ✓")

    if access_key and secret_key:
        ok = verify_s3_write(CDN_BUCKET, account_id, access_key, secret_key)
        print(f"      S3 write access: {'✓' if ok else '✗ (check R2 API token permissions)'}")

    # ------------------------------------------------------------------
    # 3. Enable public access on CDN bucket
    # ------------------------------------------------------------------
    print(f"\n[3/3] Enabling public access on {CDN_BUCKET}")

    # Check if already enabled
    existing_domain = get_public_domain(CDN_BUCKET, account_id, api_token)
    if existing_domain:
        print(f"      Already enabled ✓")
        cdn_domain = existing_domain
    else:
        cdn_domain = enable_public_access(CDN_BUCKET, account_id, api_token)
        print(f"      Enabled ✓")

    cdn_base_url = f"https://{cdn_domain}"
    print(f"      Public URL: {cdn_base_url}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("R2 setup complete. Add these GitHub Actions secrets:")
    print()
    print(f"  POWERVOTE_CDN_BASE_URL = {cdn_base_url}")
    print()
    print("  (CLOUDFLARE_R2_ACCOUNT_ID, CLOUDFLARE_R2_ACCESS_KEY_ID,")
    print("   CLOUDFLARE_R2_SECRET_ACCESS_KEY should already be set)")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
