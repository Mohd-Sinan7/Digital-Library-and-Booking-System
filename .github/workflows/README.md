# .github/workflows

GitHub Actions pipelines. Owner: Member 3.

Sprint 1: `ci.yml` (CI pipeline v1) runs on every push and every pull request:

1. Check out the code
2. Set up Python and cache dependencies
3. Install dependencies
4. Build
5. Lint
6. Report the result on the pull request

Sprint 2: a test stage with a 70% coverage gate, a Docker build, deployment on
merge to `main`, and a `/health` smoke test after deployment.
