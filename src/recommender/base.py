"""Common interface and domain models for the Recommendation Engine (NFR-R2)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Recommendation:
    """A single book recommendation produced by an algorithm."""

    book_id: int
    score: float
    reason: str


class Recommender(ABC):
    """Common interface for recommendation algorithms (NFR-R2).

    All recommendation implementations (popularity baseline, content-based TF-IDF,
    collaborative filtering, hybrid) inherit from this class and implement
    recommend(). This allows swapping algorithms without changes outside src/recommender.
    """

    @abstractmethod
    def recommend(self, user_id: int, n: int = 10) -> list[Recommendation]:
        """Generate top-n book recommendations for a given user.

        Args:
            user_id: ID of the user requesting recommendations.
            n: Number of recommendations to return (default 10).

        Returns:
            A list of Recommendation objects ranked by relevance.
        """
        pass
