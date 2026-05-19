"""Fetch closed issues from a GitHub repository and cache them locally.

One-shot developer script. Run from the backend/ directory:

    uv run python scripts/fetch_issues.py

Reads GITHUB_TOKEN from environment. Writes raw issue JSON files to
data/issues/raw/<owner>__<repo>/page_NNNN.json. Re-running is safe:
already-fetched pages are skipped unless --refresh is passed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx
from tqdm import tqdm

REPO_OWNER = "scikit-learn"
REPO_NAME = "scikit-learn"
PER_PAGE = 100  # max allowed by GitHub
USER_AGENT = "maintainer-copilot-dataset-fetch/0.1"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("fetch_issues")


def _output_dir() -> Path:
    """Return the cache directory for this repo's raw issues."""
    here = Path(__file__).resolve().parent.parent  # backend/
    out = here / "data" / "issues" / "raw" / f"{REPO_OWNER}__{REPO_NAME}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _build_client() -> httpx.Client:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token or token.startswith("ghp_placeholder"):
        logger.error(
            "GITHUB_TOKEN not set or still placeholder — generate one at "
            "https://github.com/settings/tokens?type=beta and put it in .env"
        )
        sys.exit(1)
    return httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        },
        timeout=30.0,
    )


def _fetch_page(client: httpx.Client, page: int) -> list[dict]:
    """Fetch one page of closed issues. Retries on 5xx; honours rate limits."""
    url = f"/repos/{REPO_OWNER}/{REPO_NAME}/issues"
    params = {
        "state": "closed",
        "per_page": PER_PAGE,
        "page": page,
        "sort": "created",
        "direction": "desc",  # newest first; we'll re-sort during build
    }
    for attempt in range(3):
        resp = client.get(url, params=params)

        # Honour rate-limit: if remaining is low, sleep until reset.
        remaining = int(resp.headers.get("X-RateLimit-Remaining", "1"))
        reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
        if remaining <= 1 and reset > 0:
            now = int(time.time())
            wait = max(reset - now, 0) + 2
            logger.info("rate limit low (%d remaining), sleeping %ds", remaining, wait)
            time.sleep(wait)

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 422:
            # GitHub deep-pagination limit (~10k items). Treat as "no more pages".
            logger.info("hit GitHub deep-pagination limit at page %d — stopping", page)
            return []
        if 500 <= resp.status_code < 600:
            logger.warning("server error %d on page %d, retrying", resp.status_code, page)
            time.sleep(2**attempt)
            continue
        logger.error("page %d failed: %d %s", page, resp.status_code, resp.text[:200])
        resp.raise_for_status()
    raise RuntimeError(f"page {page} failed after 3 retries")


def fetch_all(refresh: bool = False) -> None:
    out_dir = _output_dir()
    logger.info("output directory: %s", out_dir)

    with _build_client() as client:
        # Page 1 to learn total count (via Link header / first response).
        page = 1
        pbar = tqdm(desc="fetching pages", unit="page")
        while True:
            page_file = out_dir / f"page_{page:04d}.json"
            if page_file.exists() and not refresh:
                logger.debug("page %d already cached", page)
                with page_file.open() as f:
                    items = json.load(f)
                if len(items) < PER_PAGE:
                    pbar.update(1)
                    break
                page += 1
                pbar.update(1)
                continue

            items = _fetch_page(client, page)
            with page_file.open("w") as f:
                json.dump(items, f)

            pbar.update(1)
            if len(items) < PER_PAGE:
                # last page
                break
            page += 1

        pbar.close()
        logger.info("done — %d pages saved to %s", page, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch all pages even if they're cached.",
    )
    args = parser.parse_args()
    fetch_all(refresh=args.refresh)


if __name__ == "__main__":
    main()
