# tests

Unit and integration tests, run with `pytest` from the repository root.

- Mirror the `src` layout: tests for `src/users/` go in `tests/users/`.
- Name files `test_<what>.py` and functions `test_<behaviour>`.
- Each module needs at least 70% unit-test coverage. Check it with
  `pytest --cov=src --cov-report=term-missing`.
- Use FastAPI's `TestClient` for endpoint tests. Until real login is merged (31 Oct),
  send the stub tokens listed in `docs/api-contract.md`.
