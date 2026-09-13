# Signalboard architecture

## Request flow

```text
Recruiter
   │
   ▼
Signalboard frontend (HTML / CSS / JS)
   │  multipart/form-data
   ▼
FastAPI route: POST /api/screenings
   │
   ├── validates files and job description
   ├── extracts PDF / DOCX / TXT text
   ├── parses candidate contact, skills, education and experience
   ├── extracts job requirements
   ├── calculates explainable weighted scores
   └── persists the screening through SQLAlchemy
             │
             ├── SQLite by default
             └── MySQL when DATABASE_URL is configured
```

## Why this architecture

The system separates parsing from matching. That keeps the scoring engine testable without uploading files and makes it possible to replace the baseline parser or scoring model later without rewriting the API or frontend.

The first version uses no external AI provider. TF-IDF and cosine similarity are understandable, deterministic and appropriate for a portfolio baseline. Semantic embeddings can be introduced later behind the same matcher interface.

The frontend keeps the same HTML/CSS/JavaScript architecture while separating the recruiter experience into dashboard, jobs, screening, candidates, analytics, history and settings views. This keeps the project easy to run in VS Code and easy to explain before considering a React migration.

## Data model

The prototype uses one normalized top-level `screenings` table with candidate and result snapshots stored as JSON. This keeps local setup friction low while preserving a clear migration path:

```text
screenings
  ├── id
  ├── title
  ├── job_description
  ├── requirements_json
  ├── candidates_json
  └── created_at
```

For a multi-user production system, split the JSON snapshots into `jobs`, `candidates`, `resumes`, `skills`, `screening_results` and join tables. Snapshotting is useful for auditability: an old screening keeps the exact result it showed when it was run.

## Scoring

```text
required skill coverage  40%
preferred skill coverage 10%
experience signal         20%
education signal          10%
TF-IDF similarity         20%
```

All weights live in one configuration object. The API returns component values and evidence, not just the final percentage.

## Security boundary

This demo validates extensions, MIME hints and byte limits, uses parameterized SQL through SQLAlchemy, and avoids logging resume bodies. Before production, add authentication, role-based access, object storage with malware scanning, encryption, retention/deletion workflows and a privacy impact review.
