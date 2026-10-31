# .github/workflows

GitHub Actions pipelines. Owner: Member 3.

`ci.yml` (CI pipeline v1) runs on every push and every pull request:

1. Check out the code
2. Set up Python 3.11 and cache pip downloads
3. Install dependencies from `requirements.txt`
4. Build: byte-compile everything in `src`
5. Lint: `ruff check --line-length 100 --select E,F,W,I .`

The result shows on each pull request as the `ci` check. After it has run once, it
can be added as a required status check in the branch protection rule for `main`.

Sprint 2: a test stage with a coverage gate (50% from 4 Nov, 70% by 6 Nov), a Docker
build, deployment on merge to `main`, and a `/health` smoke test after deployment.
