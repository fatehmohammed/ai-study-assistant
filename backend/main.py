import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import state
from config import CORS_ORIGINS, DB_PATH
from pipeline import RAGPipeline
from routers import ask, files, index, quiz, summarize, topics


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    state.pipeline = RAGPipeline(collection_name="jawar", db_path=DB_PATH)
    print("RAG pipeline ready")
    yield
    print("Server shutting down")


app = FastAPI(
    title="Jawar API",
    description="RAG-powered study assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ask.router)
app.include_router(files.router)
app.include_router(index.router)
app.include_router(quiz.router)
app.include_router(summarize.router)
app.include_router(topics.router)
