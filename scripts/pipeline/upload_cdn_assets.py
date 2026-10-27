#!/usr/bin/env python3
"""Upload static artifacts and GeoJSON to Cloudflare R2 CDN with content-addressable filenames.

Each file is uploaded to:
    cdn/{stem}--{sha256[:16]}{suffix}

with Cache-Control: public, max-age=31536000, immutable set as object metadata.
Because the URL changes only when content changes, browsers can cache the
response indefinitely and never receive stale data.

A cdn-manifest.json is written to the static artifacts directory mapping each
logical artifact name → CDN URL. Next.js API routes read this manifest and
return 302 redirects to the CDN URL instead of streaming the file through the
Vercel server, offloading 3MB+ of bandwidth per map load.

Required environment variables:
    CLOUDFLARE_R2_ACCOUNT_ID
    CLOUDFLARE_R2_ACCESS_KEY_ID
    CLOUDFLARE_R2_SECRET_ACCESS_KEY
    POWERVOTE_CDN_BASE_URL — public base URL for the R2 bucket
                             e.g. https://pub-abc123.r2.dev
                             or a Cloudflare custom domain https://cdn.powervote.com

If any credential or CDN_BASE_URL is absent, the script exits cleanly (safe for local dev).

Cloudflare R2 setup:
    Run scripts/pipeline/setup_r2.py once to create the powervote-cdn bucket and enable
    public access. Without public access, 302 redirects will return 403 to browsers.
    CORS is not required — R2 public buckets serve with permissive CORS by default.

Skip-if-exists:
    Before uploading, the script calls HeadObject to check whether a key already exists.
    If so, it skips the upload (idempotent — unchanged files are never re-uploaded).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "apps" / "web" / "data"
STATIC_ARTIFACTS_DIR = REPO_ROOT / "apps" / "web-next" / "public" / "data"

CDN_PREFIX = "cdn"
CDN_MANIFEST_FILENAME = "cdn-manifest.json"


def sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cdn_object_key(logical_name: str, content_hash: str) -> str:
    """Return the content-addressable R2 key for a logical filename.

    Example:
        'map-districts--us_house--general--incumbent.json', 'abc123...'
        → 'cdn/map-districts--us_house--general--incumbent--abc1234567890abc.json'
    """
    p = Path(logical_name)
    short_hash = content_hash[:16]
    return f"{CDN_PREFIX}/{p.stem}--{short_hash}{p.suffix}"


def _r2_client():
    """Return a boto3 S3 client for Cloudflare R2, or None if credentials are absent."""
    account_id = os.environ.get("CLOUDFLARE_R2_ACCOUNT_ID", "").strip()
    access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "").strip()
    if not (account_id and access_key and secret_key):
        return None
    try:
        import boto3  # noqa: PLC0415
    except ImportError:
        logger.warning("boto3 not installed — skipping CDN upload (pip install boto3)")
        return None
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def _object_exists(client, bucket: str, key: str) -> bool:
    """Return True if the R2 object already exists (content-addressable skip)."""
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def collect_assets(static_dir: Path, data_dir: Path) -> list[tuple[Path, str]]:
    """Return (local_path, logical_filename) pairs to upload.

    Includes:
    - All *.json files in static_dir (map-districts--*.json, mobile-bootstrap.json)
      except cdn-manifest.json itself
    - congressional-districts.geojson from data_dir
    """
    assets: list[tuple[Path, str]] = []

    for p in sorted(static_dir.glob("*.json")):
        if p.name != CDN_MANIFEST_FILENAME:
            assets.append((p, p.name))

    geojson = data_dir / "congressional-districts.geojson"
    if geojson.exists():
        assets.append((geojson, "congressional-districts.geojson"))
    else:
        logger.warning("congressional-districts.geojson not found in %s — skipping", data_dir)

    return assets


def upload_cdn_assets(
    client,
    bucket: str,
    cdn_base_url: str,
    static_dir: Path,
    data_dir: Path,
) -> tuple[dict[str, str], int, int]:
    """Upload assets to R2 and return (cdn_urls_map, uploaded_count, skipped_count)."""
    assets = collect_assets(static_dir, data_dir)
    cdn_urls: dict[str, str] = {}
    uploaded = 0
    skipped = 0

    for local_path, logical_name in assets:
        content_hash = sha256_hex(local_path)
        key = cdn_object_key(logical_name, content_hash)
        cdn_url = f"{cdn_base_url.rstrip('/')}/{key}"

        suffix = Path(logical_name).suffix.lower()
        content_type = "application/geo+json" if suffix == ".geojson" else "application/json"

        if _object_exists(client, bucket, key):
            logger.info("Skip (already exists): %s", key)
            skipped += 1
        else:
            logger.info("Uploading %s → s3://%s/%s", logical_name, bucket, key)
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=local_path.read_bytes(),
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
            uploaded += 1

        cdn_urls[logical_name] = cdn_url

    return cdn_urls, uploaded, skipped


def write_cdn_manifest(static_dir: Path, cdn_urls: dict[str, str], cdn_base_url: str) -> Path:
    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cdnBaseUrl": cdn_base_url,
        "assets": cdn_urls,
    }
    out = static_dir / CDN_MANIFEST_FILENAME
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Upload static artifacts to Cloudflare R2 CDN")
    p.add_argument("--bucket", default="powervote-cdn")
    p.add_argument("--static-dir", default=str(STATIC_ARTIFACTS_DIR))
    p.add_argument("--data-dir", default=str(DATA_DIR))
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()

    cdn_base_url = os.environ.get("POWERVOTE_CDN_BASE_URL", "").strip()
    client = _r2_client()

    if client is None:
        print("R2 credentials not set — skipping CDN asset upload")
        return 0

    if not cdn_base_url:
        print("POWERVOTE_CDN_BASE_URL not set — skipping CDN asset upload")
        return 0

    static_dir = Path(args.static_dir)
    data_dir = Path(args.data_dir)

    if not static_dir.exists():
        print(f"Static artifacts directory not found: {static_dir}")
        print("Run 'npm run generate:static' before uploading CDN assets")
        return 1

    cdn_urls, uploaded, skipped = upload_cdn_assets(
        client=client,
        bucket=args.bucket,
        cdn_base_url=cdn_base_url,
        static_dir=static_dir,
        data_dir=data_dir,
    )

    manifest_path = write_cdn_manifest(static_dir, cdn_urls, cdn_base_url)

    total = uploaded + skipped
    print(
        f"CDN upload complete: {uploaded} uploaded, {skipped} already existed "
        f"({total} total assets in s3://{args.bucket}/{CDN_PREFIX}/)"
    )
    print(f"CDN manifest written: {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
