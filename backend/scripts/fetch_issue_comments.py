"""Fetch comments for closed issues — required for RAG corpus.

Reads the existing gql_batch_*.json cache (from fetch_issues_graphql.py)
to get candidate issue numbers, filters to (closed, not in any split),
sorts by most-recent closed_at, and uses GitHub's GraphQL API to fetch
the issue together with up to 50 comments.  Issues that come back with
zero comments are NOT written (they have nothing useful for RAG).

Output: one JSON per issue at
  data/issues/raw_with_comments/scikit-learn__scikit-learn/<issue_id>.json

Resumable: skips files that already exist.

Cost: ~1 GraphQL call per issue. GitHub allows 5000/hour authenticated.
Wall time: ~8 min for 500 issues at 1 req/sec.

Run from backend/:
    set -a; source ../.env; set +a
    uv run python scripts/fetch_issue_comments.py [--limit N]

--limit N  Maximum number of candidates to fetch (default: 500).
           Candidates are sorted most-recent-closed first so the corpus
           reflects current scikit-learn API behaviour.
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
USER_AGENT = "maintainer-copilot-comments-fetch/0.1"
GRAPHQL_URL = "https://api.github.com/graphql"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("fetch_comments")

QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      number
      databaseId
      title
      body
      state
      createdAt
      closedAt
      url
      labels(first: 30) { nodes { name } }
      comments(first: 50) {
        nodes {
          databaseId
          body
          createdAt
          author { login }
          authorAssociation
        }
      }
    }
  }
}
"""


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _candidates_from_cache(limit: int, split_ids: set[int]) -> list[dict]:
    """Return [{issue_id, number, closed_at}] for closed issues not in any split.

    The Phase 1.6 GraphQL fetch did not include comment counts, so we cannot
    pre-filter on comments.  Instead we fetch unconditionally and skip writing
    if the live response comes back with zero comments.

    Results are sorted most-recent-closed first and capped at `limit` so the
    corpus reflects current scikit-learn API behaviour without a multi-hour fetch.
    """
    raw_dir = _backend_dir() / "data" / "issues" / "raw" / f"{REPO_OWNER}__{REPO_NAME}"
    files = sorted(raw_dir.glob("gql_batch_*.json"))
    if not files:
        logger.error(f"no graphql batches found at {raw_dir}; run fetch_issues_graphql.py first")
        sys.exit(1)

    seen_numbers: set[int] = set()
    candidates: list[dict] = []
    for f in files:
        page = json.loads(f.read_text())
        items = page if isinstance(page, list) else page.get("issues", [])
        for issue in items:
            n = issue.get("number")
            if n is None or n in seen_numbers:
                continue
            seen_numbers.add(n)
            if issue.get("state", "").lower() != "closed":
                continue
            issue_id = issue.get("id") or issue.get("databaseId")
            if issue_id in split_ids:
                continue
            candidates.append(
                {
                    "issue_id": issue_id,
                    "number": n,
                    "closed_at": issue.get("closed_at") or "",
                }
            )

    # Most-recent first so we get modern API behaviour in the corpus
    candidates.sort(key=lambda c: c["closed_at"], reverse=True)
    return candidates[:limit]


def _build_client() -> httpx.Client:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token or token.startswith("ghp_placeholder"):
        logger.error("GITHUB_TOKEN not set — needed for GraphQL")
        sys.exit(1)
    return httpx.Client(
        headers={
            "Authorization": f"bearer {token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
        timeout=30.0,
    )


def _fetch_one(client: httpx.Client, number: int) -> dict | None:
    """Run the GraphQL query for one issue, return normalized dict."""
    response = client.post(
        GRAPHQL_URL,
        json={
            "query": QUERY,
            "variables": {"owner": REPO_OWNER, "name": REPO_NAME, "number": number},
        },
    )
    if response.status_code == 200:
        data = response.json()
        if "errors" in data:
            logger.warning(f"graphql errors for #{number}: {data['errors']}")
            return None
        issue = data["data"]["repository"]["issue"]
        if issue is None:
            return None

        comments = [
            {
                "id": c["databaseId"],
                "body": c.get("body") or "",
                "created_at": c["createdAt"],
                "author": (c.get("author") or {}).get("login"),
                "association": c.get("authorAssociation"),
            }
            for c in issue["comments"]["nodes"]
        ]

        return {
            "issue_id": issue["databaseId"],
            "number": issue["number"],
            "title": issue["title"],
            "body": issue.get("body") or "",
            "state": issue["state"].lower(),
            "created_at": issue["createdAt"],
            "closed_at": issue.get("closedAt"),
            "html_url": issue["url"],
            "labels": [lab["name"] for lab in issue["labels"]["nodes"]],
            "comments": comments,
        }

    # Rate limit handling
    if response.status_code == 403:
        remaining = int(response.headers.get("X-RateLimit-Remaining", "0"))
        reset_at = int(response.headers.get("X-RateLimit-Reset", "0"))
        wait_s = max(1, reset_at - int(time.time())) if reset_at else 60
        logger.warning(f"rate limited (remaining={remaining}); sleeping {wait_s}s")
        time.sleep(wait_s + 1)
        return _fetch_one(client, number)

    logger.warning(f"unexpected {response.status_code} for #{number}: {response.text[:200]}")
    return None


def _all_split_ids() -> set[int]:
    """Return issue_ids from train + val + test splits (contamination guard)."""
    splits_dir = _backend_dir() / "data" / "issues" / "splits"
    ids: set[int] = set()
    for name in ("train.jsonl", "val.jsonl", "test.jsonl"):
        p = splits_dir / name
        if p.exists():
            with p.open() as f:
                ids.update(json.loads(line)["issue_id"] for line in f)
        else:
            logger.warning(f"{p} missing — split not excluded from candidates")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of issues to fetch, sorted most-recent-closed first (default: 500)",
    )
    args = parser.parse_args()

    out_dir = (
        _backend_dir() / "data" / "issues" / "raw_with_comments" / f"{REPO_OWNER}__{REPO_NAME}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    split_ids = _all_split_ids()
    logger.info(
        f"loaded {len(split_ids)} split issue_ids (train+val+test) for contamination filter"
    )

    candidates = _candidates_from_cache(limit=args.limit, split_ids=split_ids)
    logger.info(
        f"selected {len(candidates)} candidate issues (most-recent {args.limit} closed, not in splits)"
    )

    # Skip already-fetched files (resumable)
    todo = []
    for c in candidates:
        out_path = out_dir / f"{c['issue_id']}.json"
        if out_path.exists():
            continue
        todo.append(c)
    logger.info(f"{len(todo)} issues to fetch (after already-cached filter)")

    if not todo:
        logger.info("nothing to do")
        return

    client = _build_client()
    success = 0
    skipped = 0
    try:
        for c in tqdm(todo, desc="fetching"):
            issue = _fetch_one(client, c["number"])
            if issue is None:
                skipped += 1
                continue
            # Even though we filtered, double-check after fetch (might have been deleted/transferred)
            if not issue.get("comments"):
                skipped += 1
                continue
            out_path = out_dir / f"{issue['issue_id']}.json"
            out_path.write_text(json.dumps(issue, indent=2))
            success += 1
    finally:
        client.close()

    logger.info(f"done: {success} fetched, {skipped} skipped")


if __name__ == "__main__":
    main()
