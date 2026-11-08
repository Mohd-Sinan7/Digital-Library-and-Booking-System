# .github/workflows

GitHub Actions pipelines. Owner: Member 3.

`ci.yml` runs three jobs. Each starts only if the one before it passed.

| Job | Runs on | What it does |
|---|---|---|
| `ci` | every push and pull request | build, lint, tests with the coverage gate |
| `docker` | every push and pull request | builds the image, starts it with PostgreSQL, smoke-tests `/health` |
| `deploy` | merges to `main`, and manual runs | deploys that commit to Render, then smoke-tests the live app |

## ci

1. Check out the code
2. Set up Python 3.11 and cache pip downloads
3. Install dependencies from `requirements.txt`
4. Build: byte-compile everything in `src`
5. Lint: `ruff check --line-length 100 --select E,F,W,I .`
6. Test: run every test in `tests/` with coverage of `src/`. The job fails if a test
   fails or if total coverage is below the gate (`COVERAGE_GATE` at the top of the job).
7. Coverage report: a table per file on the run's **Summary** page, and `coverage.xml`
   under **Artifacts** (kept 14 days)

`ci` is a required status check in the branch protection rule for `main`, so a pull
request with failing tests or low coverage cannot be merged. `docker` can be added as a
second required check in the same rule.

### Coverage gate

| From | Gate |
|---|---|
| 5 Nov | 50% |
| 7 Nov | 70% |

To check your branch before pushing, from the repository root:

```bash
pytest --cov=src --cov-report=term-missing --cov-fail-under=70
```

`term-missing` lists the line numbers your tests do not reach.

## docker

Runs `docker compose up --build --wait` (the app and PostgreSQL, as in
`docker-compose.yml`), then `scripts/smoke_test.py`, which calls `GET /health` until it
answers `{"status": "ok"}` from this commit (the `X-App-Version` header). It prints the
app's log and stops the containers at the end.

## deploy

The app runs on [Render](https://render.com) (free web service and free PostgreSQL).
After `ci` and `docker` pass on `main`, the job:

1. calls Render's deploy hook with `ref=<commit>`, so Render builds exactly that commit
   from the `Dockerfile`
2. runs `scripts/smoke_test.py` against the live app until `/health` answers ok with
   that commit in `X-App-Version` (Render sets `RENDER_GIT_COMMIT`). If that has not
   happened within 20 minutes, the job fails.

The deploy hook URL is kept in GitHub Secrets, never in the code. Until the secret and
the variable below exist, the job only shows a warning and deploys nothing.

To deploy `main` again without a new merge: **Actions** → **CI** → **Run workflow** →
branch `main`.

### One-time setup

**On Render (Member 3):**

1. Create a free account at render.com.
2. **New** → **Postgres**: name `dlbs-db`, region Singapore, plan **Free**. When it is
   ready, copy its **Internal Database URL**.
3. **New** → **Web Service** → **Public Git Repository**:
   `https://github.com/Mohd-Sinan7/Digital-Library-and-Booking-System`, branch `main`,
   language **Docker**, region Singapore (the same as the database), instance type
   **Free**. Environment variables:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Internal Database URL |
   | `JWT_SECRET` | click **Generate** |
   | `ADMIN_EMAIL` | the team's admin login |
   | `ADMIN_PASSWORD` | at least 8 characters, with a letter and a digit |
   | `SEED_BOOKS` | `full` (all 10,000 books, loaded in the background on the first start) |

   Under **Advanced**: Health Check Path `/health`, Auto-Deploy **No** (the pipeline
   deploys, and only after the tests pass).
4. **Create Web Service**. The first build takes about 5 to 10 minutes. Note the app's
   address, `https://<name>.onrender.com`.
5. The service's **Settings** → **Deploy Hook** → copy it. Treat it like a password:
   anyone who has it can redeploy the app.

**On GitHub (Sinan, because only the owner of a personal repository can add secrets):**

6. **Settings** → **Secrets and variables** → **Actions** → **Secrets** →
   **New repository secret**: `RENDER_DEPLOY_HOOK_URL` = the deploy hook.
7. **Variables** tab → **New repository variable**: `APP_URL` =
   `https://<name>.onrender.com` (no `/` at the end).
8. **Actions** → **CI** → **Run workflow** on `main` for the first deploy.

### Good to know

- A free Render service sleeps after 15 minutes without visitors, and the next visit
  takes about a minute to wake it. Open the app a few minutes before a demo.
- Render deletes free databases 30 days after they are created, which is after the
  presentations.
- Bookings are kept in the app's memory for now (`src/bookings/service.py`), so they are
  lost whenever the app restarts or sleeps. Users, books and reading records are in
  PostgreSQL.
