from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.router import api_router
from backend.app.config import settings
from backend.app.core.database import AsyncSessionLocal, create_database
from backend.app.services.scheduler import run_missed_weekly_batches_if_needed, start_scheduler, stop_scheduler
from backend.app.services.seed import seed_database
from backend.app.services.questionnaire import seed_questionnaire


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    await create_database()
    async with AsyncSessionLocal() as db:
        await seed_database(db, include_demo_users=settings.seed_demo_data)
    async with AsyncSessionLocal() as db:
        await seed_questionnaire(db)
    await run_missed_weekly_batches_if_needed()
    start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    description="面向高校学生的兴趣匹配与即时聊天平台",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
app.mount("/static", StaticFiles(directory=settings.upload_dir.parent / "app" / "static"), name="static")
app.include_router(api_router)


@app.get("/health", tags=["系统"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
