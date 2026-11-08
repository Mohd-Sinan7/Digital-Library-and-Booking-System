"""Recommendation result caching module (FR-R6, NFR-R1).

Provides an in-memory, thread-safe cache with time-to-live (TTL) expiration,
hit/miss metric tracking, user-level invalidation, and complete cache purging
on admin model refresh.

Acceptance criteria:
  - FR-R6: POST /api/recommendations/refresh clears the cache and rebuilds the model.
  - NFR-R1: Response times remain sub-2s for uncached requests and sub-millisecond
    for cached requests.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any


class RecommendationCache:
    """Thread-safe in-memory cache for recommendation responses."""

    def __init__(self, default_ttl: float = 300.0, max_size: int = 1000) -> None:
        """Initialize recommendation cache.

        Args:
            default_ttl: Expiration duration in seconds (default 300s = 5 minutes).
            max_size: Maximum number of entries before evicting the oldest entries.
        """
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._lock = threading.RLock()
        self._store: dict[tuple[int, int, str | None], tuple[list[dict[str, Any]], float]] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(
        self, user_id: int, limit: int = 10, genre: str | None = None
    ) -> tuple[int, int, str | None]:
        norm_genre = genre.strip().lower() if genre else None
        return (user_id, limit, norm_genre)

    def get(
        self, user_id: int, limit: int = 10, genre: str | None = None
    ) -> list[dict[str, Any]] | None:
        """Retrieve cached recommendations if present and unexpired.

        Args:
            user_id: ID of the user requesting recommendations.
            limit: Number of items requested.
            genre: Optional genre filter.

        Returns:
            A deep copy of the cached recommendation list, or None on miss/expiry.
        """
        key = self._make_key(user_id, limit, genre)
        now = time.time()

        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None

            items, expires_at = self._store[key]
            if now >= expires_at:
                # Expired entry: evict and treat as miss
                del self._store[key]
                self._misses += 1
                return None

            self._hits += 1
            return copy.deepcopy(items)

    def set(
        self,
        user_id: int,
        limit: int,
        genre: str | None,
        value: list[dict[str, Any]],
        ttl: float | None = None,
    ) -> None:
        """Store recommendations in cache with a TTL.

        Args:
            user_id: ID of the user.
            limit: Number of items requested.
            genre: Optional genre filter.
            value: Recommendation dictionaries to cache.
            ttl: Custom TTL in seconds, or default if None.
        """
        key = self._make_key(user_id, limit, genre)
        effective_ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.time() + effective_ttl

        with self._lock:
            # Enforce max size limit: evict oldest entry if at capacity
            if len(self._store) >= self.max_size and key not in self._store:
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]

            self._store[key] = (copy.deepcopy(value), expires_at)

    def clear(self) -> int:
        """Evict all entries from the cache (FR-R6).

        Returns:
            The number of entries that were cleared.
        """
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    def invalidate_user(self, user_id: int) -> int:
        """Evict all cached entries for a specific user.

        Args:
            user_id: The user ID whose cached recommendations to purge.

        Returns:
            The number of entries removed for this user.
        """
        with self._lock:
            matching_keys = [k for k in self._store if k[0] == user_id]
            for k in matching_keys:
                del self._store[k]
            return len(matching_keys)

    def stats(self) -> dict[str, Any]:
        """Return operational metrics for the cache."""
        with self._lock:
            total = self._hits + self._misses
            ratio = round(self._hits / total, 4) if total > 0 else 0.0
            return {
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": ratio,
                "default_ttl_seconds": self.default_ttl,
                "max_size": self.max_size,
            }

    def reset_stats(self) -> None:
        """Reset hit and miss counters."""
        with self._lock:
            self._hits = 0
            self._misses = 0


# Global singleton instance used by the recommendation service
recommendation_cache = RecommendationCache()
