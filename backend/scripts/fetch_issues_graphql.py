"""Fetch closed issues via GraphQL cursor pagination — bypasses the REST 10k limit.

One-shot developer script. Run from backend/:

    uv run python scripts/fetch_issues_graphql.py

Reads GITHUB_TOKEN from environment. Writes one JSON file per page to
data/issues/raw/<owner>__<repo>/gql_batch_NNNN.json with issues normalized
to look like REST API output, so the build script doesn't care which
source they came from.

Resumable: re-running picks up from the last saved cursor.
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
USER_AGENT = "maintainer-copilot-dataset-fetch/0.1"
PER_PAGE = 100  # GraphQL max

QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, after: $cursor, states: CLOSED,
           orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        databaseId
        title
        body
        state
        createdAt
        closedAt
        labels(first: 30) { nodes { name } }
      }
    }
  }
}
"""

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("fetch_issues_graphql")


def _output_dir() -> Path:
    here = Path(__file__).resolve().parent.parent  # backend/
    out = here / "data" / "issues" / "raw" / f"{REPO_OWNER}__{REPO_NAME}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _state_file() -> Path:
    return _output_dir() / "gql_state.json"


def _load_state() -> dict:
    f = _state_file()
    if f.exists():
        return json.loads(f.read_text())
    return {"cursor": None, "batch_index": 0, "complete": False}


def _save_state(state: dict) -> None:
    _state_file().write_text(json.dumps(state, indent=2))


def _normalize(node: dict) -> dict:
    """Convert a GraphQL issue node to REST-shaped issue dict."""
    return {
        "number": node["number"],
        "id": node["databaseId"],
        "title": node.get("title", ""),
        "body": node.get("body") or "",
        "state": node.get("state", "CLOSED").lower(),
        "created_at": node["createdAt"],
        "closed_at": node.get("closedAt"),
        "labels": [{"name": lbl["name"]} for lbl in node["labels"]["nodes"]],
    }


def _build_client() -> httpx.Client:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token or token.startswith("ghp_placeholder"):
        logger.error("GITHUB_TOKEN not set or still placeholder")
        sys.exit(1)
    return httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
        timeout=60.0,
    )


def fetch_all(refresh: bool = False) -> None:
    out_dir = _output_dir()
    logger.info("output directory: %s", out_dir)

    state = {"cursor": None, "batch_index": 0, "complete": False} if refresh else _load_state()

    if state["complete"]:
        logger.info("already complete (per gql_state.json). Use --refresh to re-fetch.")
        return

    pbar = tqdm(desc="fetching batches (GraphQL)", unit="batch", initial=state["batch_index"])

    with _build_client() as client:
        while True:
            variables = {
                "owner": REPO_OWNER,
                "name": REPO_NAME,
                "cursor": state["cursor"],
            }
            payload = {"query": QUERY, "variables": variables}

            for attempt in range(3):
                resp = client.post("/graphql", json=payload)

                # GraphQL secondary rate limit hint
                remaining = int(resp.headers.get("X-RateLimit-Remaining", "1"))
                reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
                if remaining <= 1 and reset > 0:
                    wait = max(reset - int(time.time()), 0) + 2
                    logger.info("rate limit low (%d remaining), sleeping %ds", remaining, wait)
                    time.sleep(wait)

                if resp.status_code == 200:
                    body = resp.json()
                    if "errors" in body:
                        logger.error("graphql errors: %s", body["errors"])
                        resp.raise_for_status()
                    break
                if 500 <= resp.status_code < 600:
                    logger.warning("server error %d, retrying", resp.status_code)
                    time.sleep(2**attempt)
                    continue
                logger.error("request failed: %d %s", resp.status_code, resp.text[:300])
                resp.raise_for_status()
            else:
                raise RuntimeError("graphql request failed after 3 retries")

            data = body["data"]["repository"]["issues"]
            nodes = data["nodes"]
            normalized = [_normalize(n) for n in nodes]

            state["batch_index"] += 1
            batch_path = out_dir / f"gql_batch_{state['batch_index']:04d}.json"
            batch_path.write_text(json.dumps(normalized))

            page_info = data["pageInfo"]
            state["cursor"] = page_info["endCursor"]
            state["complete"] = not page_info["hasNextPage"]
            _save_state(state)

            pbar.update(1)
            if state["complete"]:
                break

    pbar.close()
    logger.info("done — %d batches saved to %s", state["batch_index"], out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Start over from cursor=null.")
    args = parser.parse_args()
    fetch_all(refresh=args.refresh)


if __name__ == "__main__":
    main()
