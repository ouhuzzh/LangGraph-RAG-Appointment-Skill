import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from api.routes import chat, documents, system


def create_app() -> FastAPI:
    app = FastAPI(title="Medical Agentic Assistant API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.API_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(chat.router)
    app.include_router(documents.router)
    return app


app = create_app()
