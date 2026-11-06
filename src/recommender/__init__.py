"""Recommendation Engine module.

Provides personalized and cold-start book recommendations behind a common
interface (NFR-R2), along with evaluation metrics (DLBS-13).
"""

from src.recommender.base import Recommendation, Recommender
from src.recommender.content_based import ContentBasedRecommender
from src.recommender.evaluation import (
    compare_recommenders,
    evaluate_recommender,
    f1_at_k,
    format_evaluation_markdown,
    precision_at_k,
    recall_at_k,
    split_user_history,
)
from src.recommender.hybrid import HybridRecommender
from src.recommender.popularity import PopularityRecommender
from src.recommender.service import (
    get_recommendations,
    get_recommender,
    refresh_recommendations,
    set_recommender,
)

__all__ = [
    "ContentBasedRecommender",
    "HybridRecommender",
    "PopularityRecommender",
    "Recommendation",
    "Recommender",
    "compare_recommenders",
    "evaluate_recommender",
    "f1_at_k",
    "format_evaluation_markdown",
    "get_recommendations",
    "get_recommender",
    "precision_at_k",
    "recall_at_k",
    "refresh_recommendations",
    "set_recommender",
    "split_user_history",
]
