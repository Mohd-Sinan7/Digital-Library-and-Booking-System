# DLBS-12: Hybrid Scoring and Explanations

**Jira:** [DLBS-12](https://pes-se.atlassian.net/browse/DLBS-12)
**Sprint:** DLBS Sprint 2 (3–8 Nov)
**Owner:** Mohammed Sinan M T (Member 1 — Recommendation Engine Lead)
**Story Points:** 5

---

## Requirement

**FR-R5:** Every item returned by `GET /api/recommendations/me` MUST carry a
non-empty `reason` string so the UI can always display a human-readable
explanation next to each recommended book.

---

## Implementation

### New File: `src/recommender/scoring.py`

Centralises the hybrid scoring formula and the FR-R5 safety contract.

#### `blend_scores(content_score, popularity_score, alpha=0.7)`

Linear blend of two normalised signals:

```
hybrid_score = alpha × content_score + (1 − alpha) × popularity_score
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `content_score` | Cosine similarity to user profile, in `[0, 1]` | — |
| `popularity_score` | Normalised reader count, in `[0, 1]` | — |
| `alpha` | Content weight, in `[0, 1]` | `0.7` |

Returns a float rounded to 4 decimal places.  
Raises `ValueError` if `alpha` is outside `[0, 1]`.

#### `build_reason(content_score, genre, read_genres, reader_count)`

Generates a human-readable explanation following this priority ladder:

| Priority | Condition | Reason template |
|----------|-----------|-----------------|
| 1 | `content_score > 0.01` and genre in user's read genres | `"Based on your interest in {genre}"` |
| 2 | `content_score > 0.01` and genre present (new) | `"Similar to books you have read ({genre})"` |
| 3 | `content_score > 0.01`, no genre | `"Recommended based on your reading history"` |
| 4 | No content signal, genre + readers | `"Popular in {genre} ({n} readers)"` |
| 5 | No content signal, genre only | `"Popular in {genre}"` |
| 6 | No content signal, readers only | `"Popular among library readers ({n} readers)"` |
| 7 | Fallback | `"Popular among library readers"` |

#### `ensure_reason(recommendations)`

A **final defensive pass** called by `service.get_recommendations()` immediately
after the recommender produces its list.  
Any item whose `reason` is empty or whitespace-only receives the module-level
fallback string `"Recommended by the Digital Library"`.

This provides a belt-and-braces guarantee: even if a future algorithm
implementation accidentally leaves a blank reason, FR-R5 is never violated.

---

### Modified File: `src/recommender/service.py`

`get_recommendations()` now calls `ensure_reason(recs)` between the raw
recommender call and the catalog enrichment loop:

```python
recs = _active_recommender.recommend(**kwargs)
recs = ensure_reason(recs)   # ← FR-R5 safety net
```

---

### How Every Algorithm Fulfils FR-R5

| Recommender | Explanation strategy |
|-------------|---------------------|
| `PopularityRecommender` | Returns `"Popular among library readers (N readers)"` or genre variant |
| `ContentBasedRecommender` | Returns genre affinity, similarity hint, or history-based message; falls back to popularity reason on cold-start |
| `HybridRecommender` | Inherits content reason when content signal is present; uses popularity reason otherwise; falls back to `PopularityRecommender` on cold-start |
| **Service layer** | `ensure_reason()` is called on every list regardless of algorithm |

---

## Tests

**File:** `tests/recommender/test_hybrid_scoring.py`

| Test class | Coverage |
|------------|---------|
| `TestBlendScores` | Formula correctness, boundary values (`alpha=0`, `alpha=1`), rounding, `ValueError` |
| `TestBuildReason` | All 7 priority branches, `None` / empty inputs, exhaustive parameter grid |
| `TestEnsureReason` | Empty reason replacement, whitespace-only replacement, mixed list, length preservation, book_id/score preservation |
| `TestPopularityRecommenderFR5` | Cold-start and genre-filter paths produce non-empty reasons |
| `TestHybridRecommenderFR5` | Cold-start path, history path, `ensure_reason` safety-net test |

---

## Running the Tests

```bash
# DLBS-12 tests only
python -m pytest tests/recommender/test_hybrid_scoring.py -v

# Full recommender suite
python -m pytest tests/recommender/ -v

# Full project suite
python -m pytest
```

---

## API Response Shape (FR-R1 + FR-R5)

```json
{
  "items": [
    {
      "book_id": 42,
      "title": "Dune",
      "author": "Frank Herbert",
      "cover_url": "https://...",
      "genre": "Sci-Fi",
      "score": 0.8341,
      "reason": "Based on your interest in Sci-Fi"
    }
  ],
  "count": 1
}
```

The `reason` field is **always non-empty** (FR-R5).
