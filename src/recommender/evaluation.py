"""Recommendation system evaluation metrics and holdout validation (DLBS-13).

Provides implementations for:
- Precision@K
- Recall@K
- F1@K
- Train/Test holdout split on user reading histories
- Benchmark comparison across baseline, content-based, and hybrid algorithms
"""

from typing import Any, Sequence

from sqlalchemy.orm import Session

from src.recommender.base import Recommender


def precision_at_k(
    recommended_ids: Sequence[int],
    ground_truth_ids: set[int] | Sequence[int],
    k: int = 5,
) -> float:
    """Calculate Precision@K for a single user's recommendations.

    Precision@K = (Number of recommended items in top-K that are relevant) / K

    Args:
        recommended_ids: Ordered list of recommended book IDs.
        ground_truth_ids: Set or sequence of relevant (ground-truth) book IDs.
        k: Cut-off rank (default 5).

    Returns:
        Precision score between 0.0 and 1.0.
    """
    if k <= 0:
        return 0.0
    gt = set(ground_truth_ids)
    if not gt or not recommended_ids:
        return 0.0

    top_k = recommended_ids[:k]
    hits = sum(1 for bid in top_k if bid in gt)
    return round(hits / k, 4)


def recall_at_k(
    recommended_ids: Sequence[int],
    ground_truth_ids: set[int] | Sequence[int],
    k: int = 5,
) -> float:
    """Calculate Recall@K for a single user's recommendations.

    Recall@K = (Number of recommended items in top-K that are relevant) / |Ground Truth|

    Args:
        recommended_ids: Ordered list of recommended book IDs.
        ground_truth_ids: Set or sequence of relevant (ground-truth) book IDs.
        k: Cut-off rank (default 5).

    Returns:
        Recall score between 0.0 and 1.0.
    """
    if k <= 0:
        return 0.0
    gt = set(ground_truth_ids)
    if not gt:
        return 0.0
    if not recommended_ids:
        return 0.0

    top_k = recommended_ids[:k]
    hits = sum(1 for bid in top_k if bid in gt)
    return round(hits / len(gt), 4)


def f1_at_k(precision: float, recall: float) -> float:
    """Compute harmonic mean F1@K from precision and recall."""
    if precision + recall <= 0.0:
        return 0.0
    return round(2.0 * (precision * recall) / (precision + recall), 4)


def split_user_history(
    records: list[Any],
    holdout_ratio: float = 0.2,
    min_records: int = 3,
) -> tuple[list[Any], list[Any]]:
    """Split a user's reading records into training and holdout test sets.

    Holds out the most recent `holdout_ratio` proportion of records (at least 1)
    for evaluation.

    Args:
        records: List of reading records for a user.
        holdout_ratio: Proportion of history to hold out (default 0.2 / 20%).
        min_records: Minimum records required to perform a split.

    Returns:
        Tuple of (train_records, test_records).
    """
    if len(records) < min_records:
        return list(records), []

    n_holdout = max(1, int(len(records) * holdout_ratio))
    # Keep the split bounded so training history is never empty
    if n_holdout >= len(records):
        n_holdout = 1

    train = records[:-n_holdout]
    test = records[-n_holdout:]
    return train, test


def evaluate_recommender(
    recommender: Recommender,
    test_set: dict[int, set[int]],
    k: int = 5,
    db: Session | None = None,
) -> dict[str, float]:
    """Evaluate a recommender algorithm across a population of test users.

    Computes macro-averaged Precision@K, Recall@K, and F1@K.

    Args:
        recommender: Algorithm implementing the Recommender interface.
        test_set: Mapping of {user_id: set_of_ground_truth_book_ids}.
        k: Cut-off rank (default 5).
        db: Optional database session to reuse.

    Returns:
        Dictionary with macro-averaged metrics and user count.
    """
    valid_users = [uid for uid, gt in test_set.items() if gt]
    if not valid_users:
        return {
            f"precision@{k}": 0.0,
            f"recall@{k}": 0.0,
            f"f1@{k}": 0.0,
            "users_evaluated": 0,
        }

    total_precision = 0.0
    total_recall = 0.0

    for uid in valid_users:
        gt = test_set[uid]
        recs = recommender.recommend(user_id=uid, n=k, db=db)
        rec_ids = [r.book_id for r in recs]

        p = precision_at_k(rec_ids, gt, k=k)
        r = recall_at_k(rec_ids, gt, k=k)

        total_precision += p
        total_recall += r

    n_users = len(valid_users)
    mean_p = round(total_precision / n_users, 4)
    mean_r = round(total_recall / n_users, 4)
    mean_f1 = f1_at_k(mean_p, mean_r)

    return {
        f"precision@{k}": mean_p,
        f"recall@{k}": mean_r,
        f"f1@{k}": mean_f1,
        "users_evaluated": n_users,
    }


def compare_recommenders(
    recommenders: dict[str, Recommender],
    test_set: dict[int, set[int]],
    k_list: list[int] | None = None,
    db: Session | None = None,
) -> dict[str, dict[str, float]]:
    """Compare multiple recommenders across different cut-off thresholds K.

    Args:
        recommenders: Mapping of {name: RecommenderInstance}.
        test_set: Mapping of {user_id: set_of_ground_truth_book_ids}.
        k_list: List of K thresholds (default [5, 10]).
        db: Optional database session.

    Returns:
        Nested dictionary {name: {metric_name: value}}.
    """
    if k_list is None:
        k_list = [5, 10]

    comparison: dict[str, dict[str, float]] = {}

    for name, algo in recommenders.items():
        algo_results: dict[str, float] = {}
        for k in k_list:
            res = evaluate_recommender(algo, test_set=test_set, k=k, db=db)
            algo_results[f"precision@{k}"] = res[f"precision@{k}"]
            algo_results[f"recall@{k}"] = res[f"recall@{k}"]
            algo_results[f"f1@{k}"] = res[f"f1@{k}"]
            algo_results["users_evaluated"] = res["users_evaluated"]
        comparison[name] = algo_results

    return comparison


def format_evaluation_markdown(
    comparison: dict[str, dict[str, float]],
    k_list: list[int] | None = None,
) -> str:
    """Format comparison dictionary into a clean GitHub Flavored Markdown table."""
    if k_list is None:
        k_list = [5, 10]

    header_cols = ["Algorithm"]
    for k in k_list:
        header_cols.extend([f"Precision@{k}", f"Recall@{k}", f"F1@{k}"])
    header_cols.append("Users Evaluated")

    lines = [
        "| " + " | ".join(header_cols) + " |",
        "| " + " | ".join(["---"] * len(header_cols)) + " |",
    ]

    for name, metrics in comparison.items():
        row = [f"**{name}**"]
        for k in k_list:
            p = metrics.get(f"precision@{k}", 0.0)
            r = metrics.get(f"recall@{k}", 0.0)
            f1 = metrics.get(f"f1@{k}", 0.0)
            row.extend([f"{p:.4f}", f"{r:.4f}", f"{f1:.4f}"])
        row.append(str(int(metrics.get("users_evaluated", 0))))
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)
