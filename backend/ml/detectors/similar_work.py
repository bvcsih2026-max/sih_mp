"""
MPLADS Guardian — Similar Work / Duplicate Detection Module
=============================================================

Detects MPLADS-sanctioned works that appear highly similar to one another,
based on a combination of independent evidence sources:

    1. Work description (TF-IDF + cosine similarity, or optionally
       sentence-transformers embeddings)
    2. Work type
    3. District
    4. Location (lat/lon proximity)
    5. Sanction amount
    6. Sanction date proximity

IMPORTANT: A "similar work" signal is NOT a fraud/duplicate/corruption
verdict. It only means two sanctioned works look alike on paper. There
are many legitimate explanations (see `_possible_explanations`), and the
signal is meant to route the pair to a human/verification workflow.

This module is self-contained and importable by the backend:

    from ml.detectors.similar_work import SimilarWorkDetector, SimilarWorkConfig

    detector = SimilarWorkDetector()
    signals = detector.detect(list_of_work_dicts)
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --------------------------------------------------------------------------
# Optional dependencies — the module degrades gracefully if these are
# not installed, per the spec ("if practical, also support").
# --------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer
    _SBERT_AVAILABLE = True
except ImportError:
    _SBERT_AVAILABLE = False

try:
    from geopy.distance import geodesic
    _GEOPY_AVAILABLE = True
except ImportError:
    _GEOPY_AVAILABLE = False


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

@dataclass
class SimilarWorkConfig:
    """All thresholds are configurable — nothing is hardcoded in the
    detection logic itself."""

    # Minimum TF-IDF/embedding cosine similarity for a pair to be
    # considered a text match at all.
    text_similarity_threshold: float = 0.60

    # Minimum *combined* weighted score (0-1) required to emit a signal.
    combined_score_threshold: float = 0.55

    # Used to normalize amount-similarity scoring; not a hard cutoff.
    amount_diff_threshold_percent: float = 20.0

    # Window (days) over which date proximity decays to 0.
    date_proximity_days: int = 365

    # Distance (km) over which location proximity decays to 0.
    location_distance_km_threshold: float = 5.0

    # Toggle sentence-transformers instead of TF-IDF for text similarity.
    use_sentence_transformers: bool = False
    sbert_model_name: str = "all-MiniLM-L6-v2"

    # How much each evidence type contributes to the combined score.
    # Only evidence types that are actually computable for a given pair
    # (i.e. both works have the relevant field) are included, and weights
    # are re-normalized over the available subset.
    weights: Dict[str, float] = field(default_factory=lambda: {
        "text_similarity": 0.45,
        "same_district": 0.15,
        "same_work_type": 0.10,
        "location_proximity": 0.15,
        "amount_similarity": 0.10,
        "date_proximity": 0.05,
    })

    # Priority bands over the 0-100 anomaly_score.
    high_priority_score: float = 80.0
    medium_priority_score: float = 60.0


# --------------------------------------------------------------------------
# Detector
# --------------------------------------------------------------------------

class SimilarWorkDetector:
    """Pairwise similar/duplicate-work detector for MPLADS sanctioned works."""

    def __init__(self, config: Optional[SimilarWorkConfig] = None):
        self.config = config or SimilarWorkConfig()
        self._sbert_model = None
        if self.config.use_sentence_transformers:
            if not _SBERT_AVAILABLE:
                raise ImportError(
                    "use_sentence_transformers=True but the 'sentence-transformers' "
                    "package is not installed. Run: pip install sentence-transformers"
                )
            self._sbert_model = SentenceTransformer(self.config.sbert_model_name)

    # ---------------------------------------------------------------- text

    @staticmethod
    def _clean_text(text: Any) -> str:
        if not isinstance(text, str):
            return ""
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _text_similarity_matrix(self, descriptions: List[str]) -> np.ndarray:
        cleaned = [self._clean_text(d) for d in descriptions]

        if self.config.use_sentence_transformers and self._sbert_model is not None:
            embeddings = self._sbert_model.encode(cleaned)
            return cosine_similarity(embeddings)

        if all(c == "" for c in cleaned):
            n = len(cleaned)
            return np.zeros((n, n))

        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        tfidf_matrix = vectorizer.fit_transform(cleaned)
        return cosine_similarity(tfidf_matrix)

    # ------------------------------------------------------------ evidence

    @staticmethod
    def _amount_evidence(a: Optional[float], b: Optional[float]) -> Optional[Tuple[float, float]]:
        """Returns (similarity 0-1, difference_percent) or None if not comparable."""
        if a is None or b is None:
            return None
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return None
        if a <= 0 or b <= 0:
            return None
        diff_pct = abs(a - b) / max(a, b) * 100
        similarity = max(0.0, 1 - diff_pct / 100)
        return similarity, diff_pct

    @staticmethod
    def _date_evidence(d1: Any, d2: Any, max_days: int) -> Optional[Tuple[float, int]]:
        """Returns (proximity 0-1, abs_delta_days) or None if not comparable."""
        if d1 is None or d2 is None:
            return None
        try:
            d1p, d2p = pd.to_datetime(d1), pd.to_datetime(d2)
        except (ValueError, TypeError):
            return None
        if pd.isna(d1p) or pd.isna(d2p):
            return None
        delta_days = abs((d1p - d2p).days)
        proximity = max(0.0, 1 - delta_days / max_days) if max_days > 0 else 0.0
        return proximity, delta_days

    def _location_distance_km(self, loc1: Any, loc2: Any) -> Optional[float]:
        """loc1/loc2 expected as (lat, lon) tuples/lists. Uses geopy if
        available, otherwise falls back to a haversine calculation."""
        if not loc1 or not loc2:
            return None
        try:
            lat1, lon1 = float(loc1[0]), float(loc1[1])
            lat2, lon2 = float(loc2[0]), float(loc2[1])
        except (TypeError, ValueError, IndexError):
            return None

        if _GEOPY_AVAILABLE:
            return geodesic((lat1, lon1), (lat2, lon2)).km

        # Haversine fallback (no external dependency required).
        r_km = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * r_km * math.asin(math.sqrt(a))

    # ------------------------------------------------------------- pairing

    def compare_pair(
        self, work_a: Dict[str, Any], work_b: Dict[str, Any], text_sim: float
    ) -> Dict[str, Any]:
        """Combine all independent evidence signals for a single pair of
        works into one weighted score, plus the raw evidence dict."""
        cfg = self.config
        evidence: Dict[str, Any] = {"text_similarity": round(float(text_sim), 4)}
        scores: Dict[str, float] = {"text_similarity": float(text_sim)}

        # District
        da, db = work_a.get("district"), work_b.get("district")
        if da and db:
            same_district = str(da).strip().lower() == str(db).strip().lower()
            evidence["same_district"] = same_district
            scores["same_district"] = 1.0 if same_district else 0.0

        # Work type
        wa, wb = work_a.get("work_type"), work_b.get("work_type")
        if wa and wb:
            same_type = str(wa).strip().lower() == str(wb).strip().lower()
            evidence["same_work_type"] = same_type
            scores["same_work_type"] = 1.0 if same_type else 0.0

        # Location
        dist_km = self._location_distance_km(work_a.get("location"), work_b.get("location"))
        if dist_km is not None:
            evidence["location_distance_km"] = round(dist_km, 3)
            proximity = 1 - (dist_km / cfg.location_distance_km_threshold) if cfg.location_distance_km_threshold > 0 else 0.0
            scores["location_proximity"] = float(min(1.0, max(0.0, proximity)))

        # Amount
        amount_result = self._amount_evidence(work_a.get("sanction_amount"), work_b.get("sanction_amount"))
        if amount_result is not None:
            amt_sim, amt_diff_pct = amount_result
            evidence["amount_difference_percent"] = round(amt_diff_pct, 2)
            scores["amount_similarity"] = amt_sim

        # Date
        date_result = self._date_evidence(
            work_a.get("sanction_date"), work_b.get("sanction_date"), cfg.date_proximity_days
        )
        if date_result is not None:
            date_prox, delta_days = date_result
            evidence["date_difference_days"] = int(delta_days)
            scores["date_proximity"] = date_prox

        # Weighted combination, re-normalized over whatever evidence is
        # actually available for this pair.
        total_weight = sum(cfg.weights.get(k, 0.0) for k in scores)
        if total_weight > 0:
            combined_score = sum(cfg.weights.get(k, 0.0) * v for k, v in scores.items()) / total_weight
        else:
            combined_score = 0.0

        return {"evidence": evidence, "combined_score": combined_score}

    # -------------------------------------------------------------- output

    def _priority(self, score_100: float) -> str:
        if score_100 >= self.config.high_priority_score:
            return "HIGH"
        if score_100 >= self.config.medium_priority_score:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _possible_explanations() -> List[str]:
        return [
            "Related phases of a single larger project",
            "Extension or continuation of an existing sanctioned work",
            "Legitimate similar infrastructure in nearby areas (e.g. a standard community hall design reused across villages)",
            "Duplicate reporting or data-entry duplication of the same underlying work",
        ]

    @staticmethod
    def _recommended_verification() -> List[str]:
        return [
            "Cross-check work orders for both entries",
            "Compare Bill of Quantities (BOQ)",
            "Verify site coordinates / conduct physical inspection",
            "Check completion certificates and utilization certificates",
            "Review MPLADS sanction records for explicit linkage or phase numbering",
        ]

    def detect(self, works: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run pairwise similar-work detection over a list of sanctioned works.

        Each work dict may contain:
            work_id (str)            — required for useful output, else an
                                        index-based placeholder is used
            description (str)
            work_type (str)
            district (str)
            location (tuple[float,float])   — (lat, lon)
            sanction_amount (float)
            sanction_date (str | datetime)

        Returns a list of signal dicts (common schema), sorted by
        anomaly_score descending, for every pair whose combined evidence
        score clears `combined_score_threshold`.
        """
        n = len(works)
        if n < 2:
            return []

        descriptions = [w.get("description", "") or "" for w in works]
        sim_matrix = self._text_similarity_matrix(descriptions)

        signals: List[Dict[str, Any]] = []
        signal_counter = 1

        for i in range(n):
            for j in range(i + 1, n):
                text_sim = float(sim_matrix[i, j])

                # Cheap pre-filter: skip pairs with negligible text overlap
                # to keep the candidate set manageable on large datasets.
                # (Non-text evidence alone won't rescue a near-zero text
                # match — tune/remove this if your data needs it.)
                if text_sim < self.config.text_similarity_threshold * 0.5:
                    continue

                work_a, work_b = works[i], works[j]
                result = self.compare_pair(work_a, work_b, text_sim)
                combined_score = result["combined_score"]

                if combined_score < self.config.combined_score_threshold:
                    continue

                score_100 = round(combined_score * 100, 2)
                work_a_id = work_a.get("work_id", f"WORK-{i}")
                work_b_id = work_b.get("work_id", f"WORK-{j}")

                signal = {
                    "signal_id": f"SIG-{signal_counter:05d}",
                    "schema_version": "1.0",
                    "work_id": work_a_id,
                    "detector_type": "similar_work",
                    "priority": self._priority(score_100),
                    "anomaly_score": score_100,
                    "title": "Similar work signal detected",
                    "observed_evidence": result["evidence"],
                    "baseline": {
                        "compared_work_id": work_b_id,
                        "text_similarity_threshold": self.config.text_similarity_threshold,
                        "combined_score_threshold": self.config.combined_score_threshold,
                    },
                    "explanation": (
                        "Similar work signal detected. This work shares significant "
                        "similarity with another sanctioned work across one or more "
                        "of: description, district, work type, location, amount, and "
                        "timing. This is not itself a finding of fraud, duplicate "
                        "work, or corruption — it flags the pair for verification."
                    ),
                    "possible_explanation": self._possible_explanations(),
                    "recommended_verification": self._recommended_verification(),
                    "status": "NEW",
                    "source": {
                        "detector": "similar_work.SimilarWorkDetector",
                        "compared_work_ids": [work_a_id, work_b_id],
                        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    },
                    "metadata": {
                        "text_similarity_method": (
                            "sentence-transformers" if self.config.use_sentence_transformers else "tfidf"
                        ),
                        "geopy_available": _GEOPY_AVAILABLE,
                    },
                }
                signals.append(signal)
                signal_counter += 1

        signals.sort(key=lambda s: s["anomaly_score"], reverse=True)
        return signals
