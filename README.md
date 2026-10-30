# Digital Library and Booking System

A standalone application for managing a digital book collection. It covers book
cataloging, borrowing and reservations, user reading history and progress
tracking, and personalised book recommendations using machine learning.

Software Engineering mini-project. Sprint 1 runs from 29 Oct to 2 Nov 2026 (midday),
Sprint 2 from 2 Nov (afternoon) to 7 Nov 2026, and the presentation slot is 9, 11 or
12 Nov 2026.

## Features

| Module | What it does |
|---|---|
| Book Catalog | Add, edit and soft-delete books (admin); search by title, author or ISBN; filter by genre and availability; paginated lists; book detail page |
| Users and Reading Tracking | Register, log in and out, member and admin roles, profile, reading status (want to read, reading, finished), reading progress, history and statistics |
| Booking and Borrowing | Reserve, borrow (14-day due date), return and cancel; overdue flag; at most 5 active bookings; no double booking |
| Recommendation Engine | Top-N personalised recommendations from reading history (TF-IDF content-based plus popularity), cold-start fallback, a reason for each suggestion |

## Team

| Member | Name | Module | Cross-cutting role |
|---|---|---|---|
| Member 1 | _name_ | Recommendation Engine | Architecture owner, presentation lead |
| Member 2 | _name_ | Book Catalog, app shell and home page | Scrum Master |
| Member 3 | Nagalapuram Sai Mukesh Reddy (PES1UG24AM170) | Users and Reading Tracking | DevOps (repo, CI/CD, deployment) |
| Member 4 | _name_ | Booking and Borrowing | QA Lead |

## Repository layout

```
Lab1/                 Lab 1 deliverables: requirements and use-case diagrams
Lab2/                 Lab 2 deliverables: Jira backlog, sprint board, burndown
Lab3/                 Lab 3 deliverables: component diagram and justification
src/                  Application code, one package per module
tests/                Unit and integration tests
data/                 Shared book list and demo data
docs/                 API contract, CI/CD notes, QA documents, sprint reports
.github/workflows/    GitHub Actions pipeline
```

## Tech stack

- Python 3.11 with FastAPI (REST API and auto-generated docs at `/docs`)
- SQLite for local development, PostgreSQL in Docker and on the deployed host
- scikit-learn for the recommendation engine
- pytest and pytest-cov for tests, ruff for linting
- GitHub Actions for CI/CD

## How to run

You need Python 3.11 or newer.

1. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Windows: `.venv\Scripts\activate`. macOS and Linux: `source .venv/bin/activate`.

2. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your own local values. Never commit `.env`.

4. Start the server (the app entry point `src/main.py` is added in Sprint 1):

   ```bash
   uvicorn src.main:app --reload
   ```

5. Open http://127.0.0.1:8000/docs to try the API.

## How to test

From the repository root:

```bash
pip install -r requirements-dev.txt
ruff check .
```

GitHub Actions (`.github/workflows/ci.yml`) builds and lints every push and pull
request. Unit tests join the pipeline in Sprint 2.

## Contributing

- Never push to `main`. It is protected, and changes reach it only through pull requests.
- Branch as `feature/<JIRA-KEY>-short-name`.
- Start every commit message with the Jira key, for example `DL-21: add login endpoint`.
- Every pull request links its Jira card, needs one reviewer, and needs a green CI run.
- Never commit secrets. Put placeholder values in `.env.example`.

The JSON shapes that modules use to talk to each other are in
[docs/api-contract.md](docs/api-contract.md).
