#!/bin/bash
set -e

# Default values
SERVICE_TYPE="${SERVICE_TYPE:-api}"
APP_PORT="${APP_PORT:-8510}"
CELERY_LOGLEVEL="${CELERY_LOGLEVEL:-debug}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-4}"

case "$SERVICE_TYPE" in
  api)
    echo "Starting FastAPI server on port ${APP_PORT}..."
    exec uv run python -m uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT} --reload
    ;;
  celery)
    echo "Starting Celery worker with loglevel=${CELERY_LOGLEVEL} and concurrency=${CELERY_CONCURRENCY}..."
    exec uv run celery -A celery_worker worker --loglevel=${CELERY_LOGLEVEL} --pool=threads --concurrency=${CELERY_CONCURRENCY}
    ;;
  both)
    echo "Starting both FastAPI and Celery services..."
    # Function to handle shutdown
    cleanup() {
      echo "Shutting down services..."
      kill $CELERY_PID $UVICORN_PID 2>/dev/null || true
      wait $CELERY_PID $UVICORN_PID 2>/dev/null || true
      exit 0
    }
    trap cleanup SIGTERM SIGINT
    
    # Start Celery in background
    uv run celery -A celery_worker worker --loglevel=${CELERY_LOGLEVEL} --pool=threads --concurrency=${CELERY_CONCURRENCY} &
    CELERY_PID=$!
    
    # Start FastAPI in background
    uv run python -m uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT} --reload &
    UVICORN_PID=$!
    
    # Wait for either process to exit
    wait $CELERY_PID $UVICORN_PID
    ;;
  *)
    echo "Unknown SERVICE_TYPE: $SERVICE_TYPE"
    echo "Valid options: api, celery, both"
    exit 1
    ;;
esac

