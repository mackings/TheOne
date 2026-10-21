"""The composition root: builds the FastAPI app and wires each layer together."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, errors
from app.assistant.api import router as assistant_router
from app.core.config import get_settings
from app.identity.api import customers, enrolment, iris, stepup, verification
from app.identity.api.schemas import HealthOut
from app.identity.application.verification import thresholds
from app.identity.infrastructure.antispoof import BaselineAntiSpoof
from app.identity.infrastructure.audio import ffmpeg_available
from app.identity.infrastructure.embedder import build_embedder
from app.infrastructure.database import engine, run_migrations
from app.network.api import router as network_router
from app.network.dev.mock_nibss import router as mock_nibss_router
from app.network.dev.mock_obn import router as mock_obn_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    logging.getLogger(__name__).info("database at migration %s", run_migrations(engine))
    app.state.embedder = build_embedder(s.embedder_backend, s.speaker_model_abspath, s.embedder_threads)
    app.state.antispoof = BaselineAntiSpoof()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="TheOne Fraud Defence API",
        version="0.1.0",
        description="Mule-network detection with real-time transfer decisions, plus voice, iris and device-biometric step-up.",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_methods=["*"], allow_headers=["*"])
    errors.install(app)
    auth.install(app, s)

    for router in (customers.router, enrolment.router, verification.router, iris.router, stepup.router, network_router,
                   assistant_router):
        app.include_router(router)
    if s.network_simulation_enabled:
        app.include_router(mock_obn_router)
        app.include_router(mock_nibss_router)

    @app.get("/health", response_model=HealthOut, tags=["system"])
    def health():
        t = thresholds(s)
        return HealthOut(
            status="ok", embedder=app.state.embedder.name, embedding_dim=app.state.embedder.dim,
            antispoof=app.state.antispoof.name,
            accepted_formats=["wav", "flac", "ogg", "m4a", "aac", "mp3", "3gp", "amr", "opus", "webm"] if ffmpeg_available()
            else ["wav", "flac", "ogg"],
            thresholds={"match_accept": t.match_accept, "match_stepup": t.match_stepup, "spoof_stepup": t.spoof_stepup,
                        "spoof_reject": t.spoof_reject, "high_risk_margin": t.high_risk_margin},
        )

    return app


app = create_app()
