import argparse
import json
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from common import DATASET_CONFIG, PARQUET, SOURCE, preview


def clean(value):
    return " ".join(value.replace("\\n", " ").split()) if isinstance(value, str) else ""


def publication_year(paper):
    try:
        return parsedate_to_datetime(paper["versions"][0]["created"]).year
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        try:
            return date.fromisoformat(paper.get("update_date", "")).year
        except (TypeError, ValueError):
            return None


def normalize(paper):
    arxiv_id = clean(paper.get("id"))
    title = clean(paper.get("title"))
    abstract = clean(paper.get("abstract"))
    year = publication_year(paper)
    if not (arxiv_id and title and abstract and year):
        return None
    authors = ", ".join(
        " ".join(filter(None, (clean(parts[0]), clean(parts[1]) if len(parts) > 1 else "")))
        for parts in (paper.get("authors_parsed") or [])[:10]
        if isinstance(parts, list) and parts and clean(parts[0])
    ) or clean(paper.get("authors"))
    categories = clean(paper.get("categories")).split()
    return dict(id=arxiv_id, title=title, abstract=abstract, authors=authors,
                year=year, category=categories[0] if categories else "unknown")


def select_records(source, limit, as_of_year):
    # Preserve the snapshot's initial sample, but reserve up to 10% for filter A.
    reserve = limit // 10
    first, recent, ids = [], [], set()
    invalid = 0
    with source.open(encoding="utf-8") as stream:
        for line in tqdm(stream, desc="Read JSONL", unit=" lines"):
            if not line.strip():
                continue
            try:
                paper = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if not isinstance(paper, dict):
                invalid += 1
                continue
            if (len(first) >= limit
                    and (clean(paper.get("categories")).split() or [""])[0] != "cs.LG"):
                continue
            record = normalize(paper)
            if record is None:
                invalid += 1
                continue
            if record["id"] in ids:
                continue
            if len(first) < limit:
                first.append(record)
                ids.add(record["id"])
            elif as_of_year - 4 <= record["year"] <= as_of_year:
                recent.append(record)
                ids.add(record["id"])
            if len(first) == limit and len(recent) == reserve:
                break
    return first[:limit - len(recent)] + recent, len(recent), invalid


def main():
    parser = argparse.ArgumentParser(description="Read an arXiv JSONL snapshot and save a Parquet subset.")
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--as-of-year", type=int, default=date.today().year)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"Snapshot not found: {args.input}. See README for the Kaggle download.")
    if args.limit < 1:
        parser.error("--limit must be positive.")
    records, reserved, invalid = select_records(args.input, args.limit, args.as_of_year)
    if not records:
        raise SystemExit("No usable records in the snapshot.")
    frame = pd.DataFrame.from_records(records)
    eligible = frame["year"].between(args.as_of_year - 4, args.as_of_year) & frame["category"].eq("cs.LG")
    print(f"Articles: {len(frame):,}; invalid records encountered: {invalid:,}")
    print(f"Extra recent cs.LG articles: {reserved:,}; eligible for filter A: {eligible.sum():,}; "
          f"eligible for filter B: {(frame['year'] < 2015).sum():,}")
    print("\nTop categories:\n" + frame["category"].value_counts().head(10).to_string())
    print("\nYears:\n" + frame["year"].value_counts().sort_index().to_string())
    example = dict(records[0])
    example["abstract"] = preview(example["abstract"])
    print(f"\nExample: {example}")
    PARQUET.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(PARQUET, index=False)
    DATASET_CONFIG.write_text(json.dumps({"as_of_year": args.as_of_year}) + "\n", encoding="utf-8")
    print(f"Saved {PARQUET}")


if __name__ == "__main__":
    main()
