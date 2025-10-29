"""FastAPI main application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import init_db, close_db
from app.api.v1 import users, operations, support
from app.services.kafka_service import kafka_service
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def consume_kafka_messages():
    """Background task to continuously consume Kafka messages."""
    while True:
        try:
            await kafka_service.consume_messages(batch_size=50)
            await asyncio.sleep(5)  # Poll every 5 seconds
        except Exception as e:
            logger.error(f"Error in Kafka consumer loop: {e}")
            await asyncio.sleep(10)  # Wait before retry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting up application...")
    await init_db()
    logger.info("Database initialized")

    # Start Kafka consumer and producer
    try:
        await kafka_service.start_consumer()
        await kafka_service.start_producer()
        logger.info("Kafka consumer and producer started")

        # Start background task for consuming messages
        kafka_task = asyncio.create_task(consume_kafka_messages())
        logger.info("Kafka consumer background task started")

    except Exception as e:
        logger.error(f"Failed to start Kafka services: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Stop Kafka background task
    if 'kafka_task' in locals():
        kafka_task.cancel()
        try:
            await kafka_task
        except asyncio.CancelledError:
            pass

    # Stop Kafka services
    await kafka_service.stop_consumer()
    await kafka_service.stop_producer()
    logger.info("Kafka services stopped")

    await close_db()
    logger.info("Database connections closed")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "Internal server error",
            "detail": str(exc) if settings.DEBUG else None
        }
    )


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": settings.APP_VERSION}


# Include routers
app.include_router(users.router, prefix="/api/v1", tags=["Users"])
app.include_router(operations.router, prefix="/api/v1/operations", tags=["Operations"])
app.include_router(support.router, prefix="/api/v1/support", tags=["Support"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
