"""Build the RAG corpus: scikit-learn docs + resolved issues with maintainer comments.

Produces:
  data/rag_corpus/
    docs/      — {file_id}.json per .rst file in scikit-learn/doc/
    issues/    — {issue_id}.json per resolved issue with comments
    manifest.json — fingerprint for the whole corpus (committed to git)

The corpus is NOT committed to git (see .gitignore); the manifest is.
The manifest is the contract: anyone running the script should produce
a corpus that fingerprints identically.

Reproducibility:
  - Clones scikit-learn at the commit pinned in CLONE_REF below
  - Reads `backend/data/issues/raw/*.json` cached by Phase 1.6's fetch_issues.py
  - Filters issues NOT in train.jsonl (avoid contamination)
  - Filters for comments > 0 (only resolved issues with discussion)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAG_DIR = DATA_DIR / "rag_corpus"
DOCS_DIR = RAG_DIR / "docs"
ISSUES_DIR = RAG_DIR / "issues"

# Pin to a specific tag for reproducibility. 1.6.0 is the latest stable as of build time;
# update this when bumping sklearn version coverage.
CLONE_REF = "1.6.0"
CLONE_DIR = DATA_DIR / "scikit-learn-clone"

ISSUES_RAW_DIR = DATA_DIR / "issues" / "raw" / "scikit-learn__scikit-learn"
ISSUES_WITH_COMMENTS_DIR = DATA_DIR / "issues" / "raw_with_comments" / "scikit-learn__scikit-learn"
TRAIN_JSONL = DATA_DIR / "issues" / "splits" / "train.jsonl"


def clone_scikit_learn() -> None:
    """Clone scikit-learn at the pinned ref for docs extraction."""
    if CLONE_DIR.exists():
        print(f"  clone already at {CLONE_DIR}, skipping")
        return
    print(f"  cloning scikit-learn@{CLONE_REF} → {CLONE_DIR}")
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            CLONE_REF,
            "https://github.com/scikit-learn/scikit-learn.git",
            str(CLONE_DIR),
        ],
        check=True,
    )


def extract_docs() -> tuple[int, str]:
    """Read all .rst files in scikit-learn/doc/ into corpus/docs/."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    doc_root = CLONE_DIR / "doc"
    rst_files = sorted(doc_root.rglob("*.rst"))
    print(f"  found {len(rst_files)} .rst files")

    content_hash = hashlib.sha256()
    count = 0
    for rst_path in rst_files:
        try:
            raw = rst_path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"  skipping {rst_path}: {exc}")
            continue

        # Skip very short fragments (e.g., redirects, stubs)
        if len(raw.strip()) < 200:
            continue

        rel_path = rst_path.relative_to(doc_root).as_posix()
        # file_id is the slugified relative path
        file_id = rel_path.replace("/", "__").replace(".rst", "")

        doc = {
            "file_id": file_id,
            "source_path": rel_path,
            "raw_text": raw,
            "n_chars": len(raw),
            "scikit_learn_ref": CLONE_REF,
        }

        out_path = DOCS_DIR / f"{file_id}.json"
        out_path.write_text(json.dumps(doc, indent=2))
        content_hash.update(raw.encode("utf-8"))
        count += 1

    return count, content_hash.hexdigest()


def extract_resolved_issues() -> tuple[int, str]:
    """Filter cached issues to (closed, has comments, not in train.jsonl).

    Reads issue files that include their comments (fetched separately by
    scripts/fetch_issue_comments.py). The base GraphQL fetch did not pull
    comments — the RAG corpus needs comment text for maintainer answers.
    """
    ISSUES_DIR.mkdir(parents=True, exist_ok=True)

    train_ids: set[int] = set()
    if TRAIN_JSONL.exists():
        with TRAIN_JSONL.open() as f:
            train_ids = {json.loads(line)["issue_id"] for line in f}
    else:
        print(f"  WARNING: {TRAIN_JSONL} missing — no contamination filter")
    print(f"  loaded {len(train_ids)} training issue_ids for contamination filter")

    raw_files = sorted(ISSUES_WITH_COMMENTS_DIR.glob("*.json"))
    if not raw_files:
        print(f"  WARNING: no comment-enriched issues at {ISSUES_WITH_COMMENTS_DIR}")
        print("  run scripts/fetch_issue_comments.py first")
        return 0, hashlib.sha256().hexdigest()

    print(f"  scanning {len(raw_files)} comment-enriched issue files")

    content_hash = hashlib.sha256()
    count = 0

    for issue_file in raw_files:
        try:
            issue = json.loads(issue_file.read_text())
        except Exception as exc:
            print(f"  skipping {issue_file}: {exc}")
            continue

        issue_id = issue["issue_id"]
        if issue_id in train_ids:
            continue

        # The new fetcher only writes closed issues with comments, but defensively check.
        if issue.get("state") != "closed":
            continue
        if len(issue.get("comments", [])) < 1:
            continue

        # Write the per-issue file to RAG corpus
        record = {
            "issue_id": issue_id,
            "number": issue["number"],
            "title": issue.get("title", ""),
            "body": issue.get("body", "") or "",
            "comments": issue.get("comments", []),
            "labels": issue.get("labels", []),
            "n_comments": len(issue["comments"]),
            "created_at": issue["created_at"],
            "closed_at": issue.get("closed_at"),
            "html_url": issue.get("html_url"),
        }

        out_path = ISSUES_DIR / f"{issue_id}.json"
        out_path.write_text(json.dumps(record, indent=2))

        # Fingerprint on title + body + comment texts
        content_hash.update(record["title"].encode("utf-8"))
        content_hash.update(record["body"].encode("utf-8"))
        for c in record["comments"]:
            content_hash.update((c.get("body") or "").encode("utf-8"))

        count += 1

    return count, content_hash.hexdigest()


def write_manifest(n_docs: int, docs_hash: str, n_issues: int, issues_hash: str) -> None:
    """Write the fingerprint manifest — committed to git as the corpus contract."""
    combined = hashlib.sha256()
    combined.update(docs_hash.encode("utf-8"))
    combined.update(issues_hash.encode("utf-8"))

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scikit_learn_ref": CLONE_REF,
        "docs": {
            "count": n_docs,
            "content_sha256": docs_hash,
        },
        "issues": {
            "count": n_issues,
            "content_sha256": issues_hash,
            "filter": "state=closed AND comments>=1 AND NOT in train.jsonl",
        },
        "combined_sha256": combined.hexdigest(),
    }

    manifest_path = RAG_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\n  manifest → {manifest_path}")
    print(f"  combined sha256: {combined.hexdigest()[:16]}...")


def main() -> None:
    RAG_DIR.mkdir(parents=True, exist_ok=True)

    print("Step 1/3 — cloning scikit-learn")
    clone_scikit_learn()

    print("\nStep 2/3 — extracting docs")
    n_docs, docs_hash = extract_docs()
    print(f"  wrote {n_docs} doc files")

    print("\nStep 3/3 — extracting resolved issues")
    n_issues, issues_hash = extract_resolved_issues()
    print(f"  wrote {n_issues} issue files")

    write_manifest(n_docs, docs_hash, n_issues, issues_hash)

    print(f"\n✓ corpus ready at {RAG_DIR}")


if __name__ == "__main__":
    sys.exit(main() or 0)
