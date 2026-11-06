"""Hybrid scoring utilities and explanation guarantees (DLBS-12, FR-R5).

This module provides:
- blend_scores(): linear interpolation between content and popularity signals.
- ensure_reason(): enforces the FR-R5 contract — every Recommendation object
  carries a non-empty, human-readable reason string.

Design rationale
----------------
FR-R5 states that every item in a recommendation response MUST carry a
non-empty reason so that the UI can always display an explanation next to
each book. Rather than relying on every individual algorithm to never miss
a path, we centralise the guarantee here: service.py calls ensure_reason()
as a final defensive pass after the recommender produces its list.
"""

from __future__ import annotations

from src.recommender.base import Recommendation

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def blend_scores(
    content_score: float,
    popularity_score: float,
    alpha: float = 0.7,
) -> float:
    """Return a linearly blended hybrid score.

    Formula (FR-R5):
        hybrid = alpha * content_score + (1 - alpha) * popularity_score

    Args:
        content_score: Cosine-similarity score from the content-based model,
            expected in [0.0, 1.0].
        popularity_score: Normalised reader-count score, expected in [0.0, 1.0].
        alpha: Content weight in [0.0, 1.0]. Default 0.7 (70 % content).

    Returns:
        Blended score rounded to 4 decimal places.

    Raises:
        ValueError: If alpha is outside [0.0, 1.0].
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be in [0.0, 1.0], got {alpha}")
    return round(alpha * content_score + (1.0 - alpha) * popularity_score, 4)


def build_reason(
    content_score: float,
    genre: str | None,
    read_genres: set[str] | None = None,
    reader_count: int = 0,
) -> str:
    """Build a human-readable explanation for a hybrid recommendation (FR-R5).

    Priority order:
      1. User has previously read a book in the same genre  → genre affinity.
      2. Content similarity is positive but genre is new    → similarity hint.
      3. Some content signal exists but no genre            → generic history.
      4. Known reader count available                       → popularity note.
      5. Fallback                                           → generic popular.

    Args:
        content_score: Cosine similarity of the book to the user profile.
        genre: Genre of the candidate book (may be None).
        read_genres: Set of genres the user has already read (may be None).
        reader_count: Number of library readers for this book.

    Returns:
        A non-empty human-readable explanation string.
    """
    effective_read_genres = read_genres or set()

    if content_score > 0.01 and genre and genre in effective_read_genres:
        return f"Based on your interest in {genre}"
    if content_score > 0.01 and genre:
        return f"Similar to books you have read ({genre})"
    if content_score > 0.01:
        return "Recommended based on your reading history"
    if genre and reader_count > 0:
        return f"Popular in {genre} ({reader_count} readers)"
    if genre:
        return f"Popular in {genre}"
    if reader_count > 0:
        return f"Popular among library readers ({reader_count} readers)"
    return "Popular among library readers"


# ---------------------------------------------------------------------------
# FR-R5 safety contract
# ---------------------------------------------------------------------------

_FALLBACK_REASON = "Recommended by the Digital Library"


def ensure_reason(recommendations: list[Recommendation]) -> list[Recommendation]:
    """Guarantee every Recommendation has a non-empty reason (FR-R5).

    This is a final defensive pass called by the service layer.  Any item
    whose reason is empty or whitespace-only is replaced with a safe fallback
    so the caller never receives an empty string.

    Args:
        recommendations: List of Recommendation objects from any algorithm.

    Returns:
        The same list with every reason guaranteed non-empty.
    """
    result: list[Recommendation] = []
    for rec in recommendations:
        if rec.reason and rec.reason.strip():
            result.append(rec)
        else:
            # Replace empty reason — Recommendation is frozen, create a new one
            result.append(
                Recommendation(
                    book_id=rec.book_id,
                    score=rec.score,
                    reason=_FALLBACK_REASON,
                )
            )
    return result
