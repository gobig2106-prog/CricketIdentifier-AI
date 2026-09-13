import math
import re
from collections import Counter
from typing import Any

WEIGHTS = {
    "required_skill": 0.40,
    "preferred_skill": 0.10,
    "experience": 0.20,
    "education": 0.10,
    "similarity": 0.20,
}

SENSITIVE_MARKERS = {
    "woman", "man", "female", "male", "nonbinary", "non-binary", "gender",
    "age", "years old", "nationality", "ethnicity", "race", "religion",
    "married", "single", "pregnant", "disability", "citizenship",
}


def _screening_text(text: str) -> str:
    """Remove obvious personal-attribute phrases before text similarity.

    The matcher should compare job evidence, not identity clues accidentally
    copied into a resume. This is intentionally conservative: it is a useful
    baseline safeguard, not a substitute for a production fairness review.
    """
    cleaned = re.sub(
        r"\b(?:age|years old|nationality|ethnicity|race|religion|gender|citizenship)"
        r"\s*[:\-]?\s*[a-z0-9+#.\- ]{0,35}",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:woman|man|female|male|nonbinary|non-binary|married|single|pregnant|"
        r"disability|canadian|american|indian|british)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.-]+", text.lower())


def tfidf_similarity(left: str, right: str) -> float:
    documents = [_tokens(_screening_text(left)), _tokens(_screening_text(right))]
    if not documents[0] or not documents[1]:
        return 0.0
    vocabulary = set(documents[0] + documents[1])
    vectors = []
    for document in documents:
        counts = Counter(document)
        total = len(document)
        vector = {}
        for term in vocabulary:
            tf = counts[term] / total
            document_frequency = sum(term in item for item in documents)
            idf = math.log((1 + len(documents)) / (1 + document_frequency)) + 1
            vector[term] = tf * idf
        vectors.append(vector)
    numerator = sum(vectors[0][term] * vectors[1][term] for term in vocabulary)
    left_norm = math.sqrt(sum(value * value for value in vectors[0].values()))
    right_norm = math.sqrt(sum(value * value for value in vectors[1].values()))
    return round(numerator / (left_norm * right_norm), 4) if left_norm and right_norm else 0.0


def _coverage(expected: list[str], actual: list[str]) -> tuple[float, list[str], list[str]]:
    expected_set = set(expected)
    actual_set = set(actual)
    if not expected_set:
        return 1.0, sorted(actual_set), []
    matched = sorted(expected_set & actual_set)
    missing = sorted(expected_set - actual_set)
    return len(matched) / len(expected_set), matched, missing


def _experience_signal(required: float | None, actual: float | None) -> float:
    if required is None:
        return 1.0
    if actual is None:
        return 0.35
    return min(actual / required, 1.0) if required else 1.0


def _education_signal(required: list[str], actual: list[str]) -> float:
    if not required:
        return 1.0
    required_text = " ".join(required).lower()
    actual_text = " ".join(actual).lower()
    return 1.0 if any(term in actual_text for term in required_text.split()) else 0.35


def normalized_weights(custom_weights: dict[str, Any] | None = None) -> dict[str, float]:
    weights = {**WEIGHTS, **(custom_weights or {})}
    clean = {key: max(float(value), 0.0) for key, value in weights.items() if key in WEIGHTS}
    total = sum(clean.values()) or 1.0
    return {key: value / total for key, value in clean.items()}


def score_candidate(
    job_description: str,
    requirements: dict[str, Any],
    candidate: dict[str, Any],
    weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_weights = normalized_weights(weights)
    required_score, matched_required, missing_required = _coverage(
        requirements.get("required_skills", []), candidate.get("skills", [])
    )
    preferred_score, matched_preferred, missing_preferred = _coverage(
        requirements.get("preferred_skills", []), candidate.get("skills", [])
    )
    experience_score = _experience_signal(
        requirements.get("experience_years"), candidate.get("experience_years")
    )
    education_score = _education_signal(
        requirements.get("education", []), candidate.get("education", [])
    )
    similarity_score = tfidf_similarity(job_description, candidate.get("raw_text", ""))
    overall = (
        required_score * active_weights["required_skill"]
        + preferred_score * active_weights["preferred_skill"]
        + experience_score * active_weights["experience"]
        + education_score * active_weights["education"]
        + similarity_score * active_weights["similarity"]
    )
    review_notes = []
    if not candidate.get("email"):
        review_notes.append("Verify contact email manually.")
    if candidate.get("experience_years") is None:
        review_notes.append("Experience duration was not confidently extracted.")
    if missing_required:
        review_notes.append("Review missing required skills against project evidence.")
    if not review_notes:
        review_notes.append("No extraction warnings; verify claims during recruiter review.")
    strengths = matched_required[:3] or matched_preferred[:3] or ["Relevant text overlap"]
    return {
        **{key: value for key, value in candidate.items() if key != "raw_text"},
        "score": round(overall * 100, 1),
        "breakdown": {
            "required_skills": round(required_score * 100, 1),
            "preferred_skills": round(preferred_score * 100, 1),
            "experience": round(experience_score * 100, 1),
            "education": round(education_score * 100, 1),
            "similarity": round(similarity_score * 100, 1),
        },
        "matching_skills": sorted(set(matched_required + matched_preferred)),
        "missing_skills": sorted(set(missing_required + missing_preferred)),
        "strengths": strengths,
        "review_notes": review_notes,
        "decision_note": "Strong signal against the configured criteria; human review required.",
    }


def rank_candidates(
    job_description: str,
    requirements: dict[str, Any],
    candidates: list[dict[str, Any]],
    weights: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ranked = [score_candidate(job_description, requirements, candidate, weights) for candidate in candidates]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    return ranked
