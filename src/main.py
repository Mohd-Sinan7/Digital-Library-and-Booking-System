"""The FastAPI app: mounts every module's router and adds GET /health.

Run from the repository root:

    uvicorn src.main:app --reload

Settings come from the environment or from a .env file in the repository root (see
.env.example). On startup the app creates any missing tables and the first admin
account from ADMIN_EMAIL and ADMIN_PASSWORD (FR-U3).
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

load_dotenv()  # before the modules below read settings such as DATABASE_URL and JWT_SECRET

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build the app with every module's router mounted."""
    # Imported here so that .env is loaded before any module reads its settings.
    from src import db
    from src.bookings.routes import router as bookings_router
    from src.catalog.routes import router as catalog_router
    from src.recommender.routes import router as recommender_router
    from src.users.reading_routes import router as reading_router
    from src.users.routes import profile_router
    from src.users.routes import router as users_router
    from src.users.service import ensure_admin_account

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.create_tables()
        with db.SessionLocal() as session:
            try:
                ensure_admin_account(session)
            except ValueError as error:
                logger.warning("Admin account not created: %s", error)
        yield

    app = FastAPI(title="Digital Library and Booking System", lifespan=lifespan)
    routers = (
        users_router,
        profile_router,
        reading_router,
        catalog_router,
        bookings_router,
        recommender_router,
    )
    for router in routers:
        app.include_router(router)

    @app.get("/health")
    def health(response: Response):
        """Liveness check used by the deployment smoke test.

        The X-App-Version header names the running commit, so after a deploy the smoke
        test can wait until the new version answers. Render sets RENDER_GIT_COMMIT;
        other hosts can set APP_VERSION.
        """
        response.headers["X-App-Version"] = (
            os.getenv("APP_VERSION") or os.getenv("RENDER_GIT_COMMIT") or "dev"
        )
        return {"status": "ok"}

    # Web pages (DLBS-23). Mounted last so every /api route and /health is matched first.
    web = Path(__file__).parent / "web"
    app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


app = create_app()
