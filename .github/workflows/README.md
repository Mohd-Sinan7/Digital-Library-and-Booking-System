# .github/workflows

GitHub Actions pipelines. Owner: Member 3.

`ci.yml` runs on every push and every pull request:

1. Check out the code
2. Set up Python 3.11 and cache pip downloads
3. Install dependencies from `requirements.txt`
4. Build: byte-compile everything in `src`
5. Lint: `ruff check --line-length 100 --select E,F,W,I .`
6. Test: run every test in `tests/` with coverage of `src/`. The job fails if a test
   fails or if total coverage is below the gate (`COVERAGE_GATE` at the top of the job).
7. Coverage report: a table per file on the run's **Summary** page, and `coverage.xml`
   under **Artifacts** (kept 14 days)

The result shows on each pull request as the `ci` check. It is a required status check
in the branch protection rule for `main`, so a pull request with failing tests or low
coverage cannot be merged.

## Coverage gate

| From | Gate |
|---|---|
| 5 Nov | 50% |
| 7 Nov | 70% |

To check your branch before pushing, from the repository root:

```bash
pytest --cov=src --cov-report=term-missing --cov-fail-under=50
```

`term-missing` lists the line numbers your tests do not reach.

## Still to come (Sprint 2)

A Docker build, deployment on merge to `main`, and a `/health` smoke test after
deployment.
