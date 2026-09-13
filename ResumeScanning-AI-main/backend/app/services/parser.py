import re
from pathlib import Path
from typing import Any

from docx import Document
from pypdf import PdfReader

SKILL_ALIASES = {
    "python": ["python"],
    "sql": ["sql", "mysql", "postgresql", "postgres"],
    "fastapi": ["fastapi"],
    "django": ["django"],
    "flask": ["flask"],
    "javascript": ["javascript", "js", "ecmascript"],
    "typescript": ["typescript", "ts"],
    "react": ["react", "react.js", "reactjs"],
    "node.js": ["node.js", "nodejs", "node"],
    "rest api": ["rest api", "restful api", "rest"],
    "git": ["git", "github", "gitlab"],
    "docker": ["docker", "containerization", "containers"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "machine learning": ["machine learning", "ml"],
    "nlp": ["nlp", "natural language processing"],
    "pandas": ["pandas"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "tableau": ["tableau"],
    "power bi": ["power bi", "powerbi"],
    "figma": ["figma"],
    "pytest": ["pytest"],
}

DEGREE_TERMS = [
    "bachelor",
    "master",
    "mca",
    "b.tech",
    "btech",
    "m.tech",
    "mba",
    "computer science",
    "information technology",
]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _preserve_lines(text: str) -> str:
    return "\n".join(clean_text(line) for line in text.splitlines() if clean_text(line))


def extract_text(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        import io

        reader = PdfReader(io.BytesIO(content))
        return _preserve_lines("\n".join(page.extract_text() or "" for page in reader.pages))
    if extension == ".docx":
        import io

        document = Document(io.BytesIO(content))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        return _preserve_lines("\n".join(paragraphs))
    return _preserve_lines(content.decode("utf-8", errors="ignore"))


def _contains_term(text: str, term: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for canonical, aliases in SKILL_ALIASES.items():
        if any(_contains_term(lowered, alias) for alias in aliases):
            found.append(canonical)
    return found


def extract_contact(text: str) -> dict[str, str]:
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(?:\+?\d[\d\s().-]{8,}\d)", text)
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    name = lines[0] if lines and "@" not in lines[0] else "Candidate"
    return {
        "name": name[:80],
        "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
    }


def extract_education(text: str) -> list[str]:
    return [term.title() for term in DEGREE_TERMS if _contains_term(text, term)]


def extract_experience_years(text: str) -> float | None:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", text.lower())
    if not matches:
        return None
    return max(float(value) for value in matches)


def extract_certifications(text: str) -> list[str]:
    results = []
    for line in text.splitlines():
        if re.search(r"certif|aws certified|scrum|pmp", line, re.I):
            cleaned = clean_text(line)
            if cleaned and cleaned not in results:
                results.append(cleaned[:120])
    return results[:6]


def parse_resume(filename: str, raw_text: str) -> dict[str, Any]:
    contact = extract_contact(raw_text)
    return {
        **contact,
        "skills": extract_skills(raw_text),
        "education": extract_education(raw_text),
        "experience_years": extract_experience_years(raw_text),
        "certifications": extract_certifications(raw_text),
        "raw_text": raw_text,
        "filename": filename,
    }


def extract_job_requirements(text: str) -> dict[str, Any]:
    required = extract_skills(text)
    preferred = []
    preferred_markers = r"preferred|nice to have|bonus|plus|desirable"
    for line in text.splitlines():
        if re.search(preferred_markers, line, re.I):
            preferred.extend(extract_skills(line))
    preferred = list(dict.fromkeys(preferred))
    required = [skill for skill in required if skill not in preferred]
    experience = extract_experience_years(text)
    education = extract_education(text)
    return {
        "required_skills": required,
        "preferred_skills": preferred,
        "experience_years": experience,
        "education": education,
        "keywords": list(dict.fromkeys(required + preferred)),
    }
