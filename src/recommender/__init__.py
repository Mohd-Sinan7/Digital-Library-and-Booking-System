"""Recommendation Engine module.

Provides personalized and cold-start book recommendations behind a common
interface (NFR-R2), along with hybrid scoring utilities (DLBS-12),
evaluation metrics (DLBS-13), caching, and admin model refresh (DLBS-14).
"""

from src.recommender.base import Recommendation, Recommender
from src.recommender.cache import RecommendationCache, recommendation_cache
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
from src.recommender.scoring import blend_scores, build_reason, ensure_reason
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
    "RecommendationCache",
    "Recommender",
    "blend_scores",
    "build_reason",
    "compare_recommenders",
    "ensure_reason",
    "evaluate_recommender",
    "f1_at_k",
    "format_evaluation_markdown",
    "get_recommendations",
    "get_recommender",
    "precision_at_k",
    "recall_at_k",
    "recommendation_cache",
    "refresh_recommendations",
    "set_recommender",
    "split_user_history",
]
