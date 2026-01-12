from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.routes import jobs, compare, health, debug
from app.core.config import settings
from app.core.logging import setup_logging
from app.orchestrator.context import ExecutionContext

# Setup logging
setup_logging()

# Global context
context = ExecutionContext()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await context.initialize()
    yield
    # Shutdown
    await context.cleanup()

app = FastAPI(
    title="Prompt Evaluation API",
    description="프롬프트 품질 평가 시스템",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(compare.router, prefix="/api/v1")
app.include_router(debug.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)