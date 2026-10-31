"""Recommendation Engine module.

Provides personalized and cold-start book recommendations behind a common
interface (NFR-R2).
"""

from src.recommender.base import Recommendation, Recommender
from src.recommender.popularity import PopularityRecommender
from src.recommender.service import (
    get_recommendations,
    get_recommender,
    refresh_recommendations,
    set_recommender,
)

__all__ = [
    "PopularityRecommender",
    "Recommendation",
    "Recommender",
    "get_recommendations",
    "get_recommender",
    "refresh_recommendations",
    "set_recommender",
]
