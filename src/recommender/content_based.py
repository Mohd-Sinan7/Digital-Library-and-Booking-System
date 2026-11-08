"""Content-based recommendation engine using TF-IDF and cosine similarity (FR-R2, NFR-R1)."""

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.catalog import service as catalog_service
from src.recommender.base import Recommendation, Recommender
from src.recommender.popularity import PopularityRecommender
from src.users import reading as reading_service
from src.users.models import FINISHED, ReadingRecordRow


class ContentBasedRecommender(Recommender):
    """Content-based recommender using TF-IDF vectors of book metadata (FR-R2, NFR-R2).

    - Text representation: constructed from book title, genre, author, and description.
    - Vectorization: TF-IDF vectorizer using scikit-learn.
    - User Profile: weighted average of TF-IDF vectors of books in user reading history,
      weighted by reading progress.
    - Ranking: unread catalog books ranked by cosine similarity to the user profile.
    - Cold-start fallback (FR-R3): users with no reading records automatically fall back
      to popularity recommendations.
    - Exclusions (FR-R4): finished and soft-deleted books are never recommended.
    - Model precomputation / caching (NFR-R1, FR-R6): TF-IDF matrix is fitted once and
      reused across requests, rebuilt on admin refresh.
    """

    def __init__(self, db: Session | None = None):
        self.db = db
        self._popularity_fallback = PopularityRecommender(db=db)
        self._all_books: list[dict] | None = None
        self._book_by_id: dict[int, dict] | None = None
        self._vectorizer: TfidfVectorizer | None = None
        self._tfidf_matrix: np.ndarray | None = None
        self._book_id_to_vec: dict[int, np.ndarray] | None = None

    def fit(self, db: Session | None = None) -> None:
        """Precompute and cache TF-IDF vectors for all catalog books (NFR-R1, FR-R6)."""
        active_db = db if db is not None else self.db
        catalog_res = catalog_service.get_books(
            page=1,
            page_size=None,
            db=active_db,
        )
        all_books: list[dict] = catalog_res.get("items", [])
        if not all_books:
            self._all_books = []
            self._book_by_id = {}
            self._vectorizer = None
            self._tfidf_matrix = None
            self._book_id_to_vec = {}
            return

        book_texts = [self._build_book_text(b) for b in all_books]
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(book_texts).toarray()

        self._all_books = all_books
        self._book_by_id = {b["id"]: b for b in all_books}
        self._vectorizer = vectorizer
        self._tfidf_matrix = tfidf_matrix
        self._book_id_to_vec = {b["id"]: tfidf_matrix[idx] for idx, b in enumerate(all_books)}

    @staticmethod
    def _build_book_text(book: dict) -> str:
        """Construct composite textual feature representation from book metadata."""
        parts: list[str] = []
        if book.get("title"):
            parts.append(str(book["title"]))
        if book.get("author"):
            parts.append(str(book["author"]))
        if book.get("genre"):
            genre = str(book["genre"])
            # Give genre extra weight so genre affinity is preserved
            parts.extend([genre, genre])
        if book.get("description"):
            parts.append(str(book["description"]))
        return " ".join(parts).strip()

    def recommend(
        self,
        user_id: int,
        n: int = 10,
        genre: str | None = None,
        db: Session | None = None,
    ) -> list[Recommendation]:
        """Generate top-n content-based recommendations for a user.

        Args:
            user_id: ID of the user requesting recommendations.
            n: Maximum number of recommendations to return.
            genre: Optional genre filter.
            db: Optional database session to reuse.

        Returns:
            A list of Recommendation objects ranked by relevance.
        """
        if n <= 0:
            return []

        active_db = db if db is not None else self.db

        # 1. Fetch user reading history
        user_history = []
        try:
            user_history = reading_service.get_history(user_id, db=active_db)
        except Exception:
            pass

        # Exclude finished books (FR-R4)
        finished_book_ids: set[int] = {
            rec.book_id
            for rec in user_history
            if rec.status == FINISHED or rec.status == "finished"
        }

        # 2. Cold-start fallback if user has no reading history (FR-R3)
        if not user_history:
            return self._popularity_fallback.recommend(
                user_id=user_id, n=n, genre=genre, db=active_db
            )

        # 3. Ensure TF-IDF model is fitted on catalog books (NFR-R1)
        if (
            self._all_books is None
            or self._tfidf_matrix is None
            or (active_db is not None and self.db is not None and active_db is not self.db)
        ):
            self.fit(active_db)
            self.db = active_db

        all_books = self._all_books or []
        if not all_books or self._tfidf_matrix is None or self._book_id_to_vec is None:
            return []

        book_by_id = self._book_by_id or {}
        book_id_to_vec = self._book_id_to_vec
        tfidf_matrix = self._tfidf_matrix

        # Determine candidates: not finished, not deleted, matching optional genre
        candidates: list[dict] = []
        for b in all_books:
            if b["id"] in finished_book_ids:
                continue
            if b.get("is_deleted", False):
                continue
            if genre and (b.get("genre") or "").strip().lower() != genre.strip().lower():
                continue
            candidates.append(b)

        if not candidates:
            return []

        # 4. Build user profile: average of read book vectors weighted by progress
        profile_sum = np.zeros(tfidf_matrix.shape[1], dtype=float)
        total_weight = 0.0
        read_genres: set[str] = set()

        for rec in user_history:
            if rec.book_id not in book_id_to_vec:
                continue

            b_info = book_by_id.get(rec.book_id, {})
            if b_info.get("genre"):
                read_genres.add(b_info["genre"])

            # Weight calculation: finished is 1.0; in-progress weighted by percent
            if rec.status == FINISHED or rec.status == "finished":
                weight = max(rec.percent / 100.0, 1.0)
            elif rec.percent > 0:
                weight = rec.percent / 100.0
            else:
                weight = 0.1

            profile_sum += weight * book_id_to_vec[rec.book_id]
            total_weight += weight

        if total_weight <= 0.0 or np.all(profile_sum == 0.0):
            # No informative history -> fall back to popularity
            return self._popularity_fallback.recommend(
                user_id=user_id, n=n, genre=genre, db=active_db
            )

        user_profile = (profile_sum / total_weight).reshape(1, -1)

        # 5. Compute reader counts for secondary popularity tie-breaking
        reader_counts: dict[int, int] = {}
        if active_db is not None:
            try:
                stmt = (
                    select(
                        ReadingRecordRow.book_id,
                        func.count(ReadingRecordRow.user_id).label("cnt"),
                    )
                    .group_by(ReadingRecordRow.book_id)
                    .order_by(desc("cnt"))
                )
                for bid, cnt in active_db.execute(stmt):
                    reader_counts[bid] = cnt
            except Exception:
                pass

        # 6. Compute cosine similarities for candidates
        candidate_vectors = np.array([book_id_to_vec[b["id"]] for b in candidates])
        sims = cosine_similarity(user_profile, candidate_vectors)[0]

        # Pair each candidate with similarity and sort descending
        scored_candidates: list[tuple[float, dict]] = []
        for idx, book in enumerate(candidates):
            sim = float(sims[idx])
            scored_candidates.append((sim, book))

        def sort_key(item: tuple[float, dict]):
            sim_val, b = item
            bid = b["id"]
            return (-sim_val, -reader_counts.get(bid, 0), bid)

        scored_candidates.sort(key=sort_key)
        top_scored = scored_candidates[:n]

        # 7. Create Recommendation objects with scores and reasons
        recommendations: list[Recommendation] = []
        for sim_val, book in top_scored:
            bid = book["id"]
            book_genre = book.get("genre")
            score = round(max(0.0, sim_val), 4)

            # Determine human-readable explanation (FR-R2, FR-R5)
            if sim_val > 0.01 and book_genre and book_genre in read_genres:
                reason = f"Based on your interest in {book_genre}"
            elif sim_val > 0.01 and book_genre:
                reason = f"Similar to books you read ({book_genre})"
            elif sim_val > 0.01:
                reason = "Recommended based on your reading history"
            elif genre:
                reason = f"Popular in {genre}"
            else:
                reason = "Popular among library readers"

            recommendations.append(
                Recommendation(
                    book_id=bid,
                    score=score,
                    reason=reason,
                )
            )

        return recommendations
