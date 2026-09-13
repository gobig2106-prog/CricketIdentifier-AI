from backend.app.services.matcher import normalized_weights, rank_candidates, tfidf_similarity
from backend.app.services.parser import extract_job_requirements, extract_skills


def test_extracts_canonical_skills():
    skills = extract_skills("Python, FastAPI, RESTful API, Docker and AWS")
    assert "python" in skills
    assert "fastapi" in skills
    assert "rest api" in skills
    assert "docker" in skills


def test_similarity_is_higher_for_related_text():
    job = "Python FastAPI SQL backend APIs"
    assert tfidf_similarity(job, "Python FastAPI SQL backend APIs") > tfidf_similarity(
        job, "Graphic design illustration typography"
    )


def test_ranking_prefers_required_skill_coverage():
    job = "Python FastAPI SQL. 3 years experience."
    requirements = extract_job_requirements(job)
    candidates = [
        {
            "name": "Partial",
            "skills": ["python"],
            "education": [],
            "experience_years": 3,
            "raw_text": "Python developer",
        },
        {
            "name": "Strong",
            "skills": ["python", "fastapi", "sql"],
            "education": [],
            "experience_years": 3,
            "raw_text": "Python FastAPI SQL backend developer",
        },
    ]
    ranked = rank_candidates(job, requirements, candidates)
    assert ranked[0]["name"] == "Strong"
    assert ranked[0]["rank"] == 1
    assert ranked[0]["score"] > ranked[1]["score"]


def test_sensitive_attributes_are_not_used_by_matcher():
    job = "Python FastAPI SQL"
    requirements = extract_job_requirements(job)
    base = {
        "name": "Candidate",
        "skills": ["python", "fastapi", "sql"],
        "education": [],
        "experience_years": 2,
        "raw_text": "Python FastAPI SQL",
    }
    other = {**base, "raw_text": "Python FastAPI SQL woman age 22 nationality Canadian"}
    first = rank_candidates(job, requirements, [base])[0]["score"]
    second = rank_candidates(job, requirements, [other])[0]["score"]
    assert first == second


def test_custom_weights_are_normalized():
    weights = normalized_weights({"required_skill": 80, "preferred_skill": 0, "experience": 10, "education": 0, "similarity": 10})
    assert round(sum(weights.values()), 5) == 1
    assert weights["required_skill"] == 0.8
