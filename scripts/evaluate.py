"""Evaluation script for recommendation algorithms (DLBS-13).

Calculates Precision@K and Recall@K across algorithms using a holdout split
of user reading histories, and outputs results in console and docs/evaluation.md.

Usage:
    python -m scripts.evaluate
    python -m scripts.evaluate --k 5 10 --output docs/evaluation.md
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.catalog.models import Book
from src.db import create_tables
from src.recommender.content_based import ContentBasedRecommender
from src.recommender.evaluation import (
    compare_recommenders,
    format_evaluation_markdown,
    split_user_history,
)
from src.recommender.hybrid import HybridRecommender
from src.recommender.popularity import PopularityRecommender
from src.users.models import FINISHED, ReadingRecordRow

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_evaluation(
    books_csv: Path,
    records_csv: Path,
    k_list: list[int],
    max_books: int = 500,
    holdout_ratio: float = 0.25,
    min_records: int = 3,
) -> tuple[dict[str, dict[str, float]], str]:
    """Run holdout evaluation and return comparison dict and Markdown table."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)

    with Session(engine) as session:
        # 1. Load books into evaluation session
        book_ids: set[int] = set()
        with open(books_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if max_books and i >= max_books:
                    break
                bid = int(row.get("book_id") or row["id"])
                book_ids.add(bid)
                raw_year = row.get("year")
                year = int(raw_year) if raw_year and str(raw_year).strip() else None
                b = Book(
                    id=bid,
                    title=row["title"].strip(),
                    author=row["author"].strip(),
                    isbn=row["isbn"].strip(),
                    genre=row["genre"].strip(),
                    description=row.get("description", "").strip(),
                    year=year,
                    page_count=int(row["page_count"]),
                    total_copies=int(row.get("total_copies", 3)),
                    available_copies=int(row.get("total_copies", 3)),
                    cover_url=row.get("cover_url", "").strip() or None,
                )
                session.add(b)
        session.commit()

        # 2. Group reading records by user
        user_records: dict[int, list[dict]] = defaultdict(list)
        with open(records_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bid = int(row.get("book_id") or row["id"])
                if bid in book_ids:
                    user_records[int(row["user_id"])].append(row)

        # 3. Perform holdout split for qualifying users
        test_set: dict[int, set[int]] = {}
        for uid, recs in user_records.items():
            if len(recs) >= min_records:
                train, test = split_user_history(
                    recs, holdout_ratio=holdout_ratio, min_records=min_records
                )
                if test:
                    for r in train:
                        row = ReadingRecordRow(
                            user_id=uid,
                            book_id=int(r["book_id"]),
                            status=r.get("status", FINISHED),
                            current_page=int(r.get("current_page", 100)),
                            percent=float(r.get("percent", 100.0)),
                        )
                        session.add(row)
                    test_set[uid] = {int(r["book_id"]) for r in test}

        session.commit()

        # 4. Initialize algorithms
        recommenders = {
            "Popularity Baseline": PopularityRecommender(db=session),
            "Content-Based (TF-IDF)": ContentBasedRecommender(db=session),
            "Hybrid (Content + Popularity)": HybridRecommender(alpha=0.7, db=session),
        }

        # 5. Compute metrics
        comparison = compare_recommenders(
            recommenders, test_set=test_set, k_list=k_list, db=session
        )
        md_table = format_evaluation_markdown(comparison, k_list=k_list)
        return comparison, md_table


def main():
    parser = argparse.ArgumentParser(description="Evaluate recommendation algorithms (DLBS-13)")
    parser.add_argument(
        "--books",
        type=Path,
        default=PROJECT_ROOT / "data" / "books.csv",
        help="Path to books CSV",
    )
    parser.add_argument(
        "--records",
        type=Path,
        default=PROJECT_ROOT / "data" / "reading_records.csv",
        help="Path to reading records CSV",
    )
    parser.add_argument(
        "--k",
        nargs="+",
        type=int,
        default=[5, 10],
        help="List of K cut-offs to evaluate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evaluation.md",
        help="Path to save evaluation markdown report",
    )
    parser.add_argument(
        "--max-books",
        type=int,
        default=500,
        help="Max books to load into benchmark session",
    )
    args = parser.parse_args()

    print("Running recommendation algorithm evaluation...")
    comparison, table = run_evaluation(
        books_csv=args.books,
        records_csv=args.records,
        k_list=args.k,
        max_books=args.max_books,
    )

    print("\n" + table + "\n")

    report_lines = [
        "# Recommendation Engine Evaluation (DLBS-13)",
        "",
        "**Author:** Mohammed Sinan M T (Member 1, Recommendation Engine Lead)",
        "**Date:** November 2026",
        "**Sprint:** DLBS Sprint 2 (3 – 8 Nov)",
        "**Requirement Reference:** FR-R2, FR-R3, FR-R5, NFR-R2",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        "This report evaluates and compares the ranking effectiveness of the three recommendation",
        "algorithms developed for the Digital Library and Booking System (DLBS):",
        "1. **Popularity Baseline (`PopularityRecommender`)**: Global popularity based on reader",
        "   activity counts across users with cold-start fallback (FR-R3).",
        "2. **Content-Based Filtering (`ContentBasedRecommender`)**: TF-IDF vectorization of book",
        "   features (title, author, genre, description) with progress weighting (FR-R2).",
        "3. **Hybrid Recommender (`HybridRecommender`)**: Linear blend (70% content + 30%",
        "   popularity) with human-readable explanations (FR-R5).",
        "",
        "---",
        "",
        "## 2. Evaluation Methodology",
        "",
        "### Metrics",
        "- **Precision@K**: The proportion of recommended books in the top-K list that the user",
        "  actually read in the held-out test set:",
        "  $$\\text{Precision@K} = \\frac{|\\text{Top-K} \\cap \\text{GroundTruth}|}{K}$$",
        "- **Recall@K**: The proportion of the user's held-out relevant books retrieved in top-K:",
        "  Recall@K = |Top-K ∩ GroundTruth| / |GroundTruth|",
        "- **F1@K**: The harmonic mean of Precision@K and Recall@K:",
        "  $$\\text{F1@K} = 2 \\cdot \\frac{\\text{Precision@K} \\cdot \\text{Recall@K}}"
        "{\\text{Precision@K} + \\text{Recall@K}}$$",
        "",
        "### Holdout Protocol",
        "- Users with at least 3 reading records are evaluated.",
        "- A temporal holdout split partitions each user's history into 75% training records and",
        "  25% holdout ground truth records.",
        "- Algorithms generate recommendations without access to held-out test records.",
        "- Per **FR-R4**, books finished in the training set are excluded from recommendations.",
        "",
        "---",
        "",
        "## 3. Benchmark Results",
        "",
        table,
        "",
        "---",
        "",
        "## 4. Key Findings & Discussion",
        "",
        "1. **Personalization & Genre Affinity**:",
        "   - Content-Based Recommender achieves genre affinity, fulfilling **FR-R2**.",
        "     user's specific reading history, fulfilling **FR-R2**.",
        "2. **Hybrid Advantage**:",
        "   - The Hybrid Recommender blends content similarity with library popularity.",
        "     reader consensus. For cold-start users or users with sparse history, it falls back",
        "     smoothly to popular books, preventing the cold-start penalty.",
        "3. **Extensibility & Common Interface**:",
        "   - All algorithms use the common `Recommender` interface (NFR-R2).",
        "     Hot-swap via `set_recommender()` with zero caller changes.",
        "",
    ]
    report_content = "\n".join(report_lines)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"Saved evaluation report to {args.output}")


if __name__ == "__main__":
    main()
