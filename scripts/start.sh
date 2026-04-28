#!/bin/bash
# Product Knowledge Base - Start Service Script
#
# Usage:
#   ./scripts/start.sh                 # Start in production mode (background)
#   ./scripts/start.sh production      # Start in production mode (background)
#   ./scripts/start.sh development     # Start in development mode (foreground)

set -e

# Project root detection
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# PID file location
PID_FILE="$PROJECT_ROOT/bot.pid"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/bot.log"
ACCESS_LOG="$LOG_DIR/access.log"
ERROR_LOG="$LOG_DIR/error.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}===================================${NC}"
echo -e "${GREEN}Product Knowledge Base - Start${NC}"
echo -e "${GREEN}===================================${NC}"
echo ""

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${RED}Error: Service already running (PID: $PID)${NC}"
        echo "Use './scripts/stop.sh' to stop it first"
        exit 1
    else
        echo -e "${YELLOW}Removing stale PID file${NC}"
        rm "$PID_FILE"
    fi
fi

# Load environment
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo -e "${YELLOW}Hint: Copy and configure environment variables${NC}"
    echo "  cp .env.example .env"
    echo "  # Edit .env file with your credentials"
    exit 1
fi

# Check Python
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    PYTHON_CMD="python"
    if ! command -v $PYTHON_CMD &> /dev/null; then
        echo -e "${RED}Error: Python not found${NC}"
        exit 1
    fi
fi

# Validate configuration
echo "Validating configuration..."
if ! $PYTHON_CMD -m bot.config >/dev/null 2>&1; then
    echo -e "${RED}Error: Configuration validation failed${NC}"
    echo -e "${YELLOW}Please check your .env file${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Configuration validated${NC}"
echo ""

# Create logs directory
mkdir -p "$LOG_DIR"

# Get mode (default: production)
MODE="${1:-production}"

if [ "$MODE" = "development" ]; then
    # Development mode (foreground, debug enabled)
    echo -e "${YELLOW}Starting in DEVELOPMENT mode...${NC}"
    echo "Server will run in foreground with debug output"
    echo "Press Ctrl+C to stop"
    echo ""

    # Get port
    PORT="${PORT:-5000}"
    export PORT=$PORT
    export DEBUG=true

    echo -e "Service URL: ${GREEN}http://0.0.0.0:$PORT${NC}"
    echo -e "Health check: ${GREEN}http://localhost:$PORT/health${NC}"
    echo ""

    # Setup signal handlers for graceful shutdown
    trap 'echo ""; echo "Shutting down..."; exit 0' SIGINT SIGTERM

    # Run in foreground
    exec $PYTHON_CMD -m bot.main

elif [ "$MODE" = "production" ]; then
    # Production mode (background, gunicorn)
    echo "Starting in PRODUCTION mode..."

    # Check gunicorn
    if ! $PYTHON_CMD -c "import gunicorn" 2>/dev/null; then
        echo -e "${RED}Error: gunicorn not installed${NC}"
        echo "Install it with: pip3 install -r requirements.txt"
        exit 1
    fi

    # Get port and workers
    PORT="${PORT:-5000}"
    WORKERS="${WORKERS:-1}"

    # Check if port is in use (if lsof is available)
    if command -v lsof &> /dev/null; then
        if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo -e "${RED}Error: Port $PORT is already in use${NC}"
            echo "Run: lsof -ti:$PORT | xargs kill -9  # to kill the process"
            exit 1
        fi
    fi

    # Start gunicorn in background
    nohup gunicorn -w "$WORKERS" -b 0.0.0.0:$PORT \
        --access-logfile "$ACCESS_LOG" \
        --error-logfile "$ERROR_LOG" \
        --log-level info \
        bot.main:app > "$LOG_FILE" 2>&1 &

    # Save PID
    SERVICE_PID=$!
    echo $SERVICE_PID > "$PID_FILE"

    # Verify process started
    sleep 0.5
    if ! ps -p "$SERVICE_PID" > /dev/null 2>&1; then
        echo -e "${RED}Error: Service failed to start${NC}"
        echo "Check logs at: $LOG_FILE"
        rm "$PID_FILE"
        exit 1
    fi

    echo -e "${GREEN}✓ Service started (PID: $SERVICE_PID)${NC}"

    echo ""
    echo -e "Service URL: ${GREEN}http://0.0.0.0:$PORT${NC}"
    echo -e "Health check: ${GREEN}http://localhost:$PORT/health${NC}"
    echo -e "Logs: ${YELLOW}$LOG_DIR/${NC}"
    echo ""

    # Health check with retry logic
    echo "Waiting for service to be ready..."
    MAX_ATTEMPTS=5
    ATTEMPT=1
    SLEEP_TIME=1

    while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
        if bash "$PROJECT_ROOT/scripts/check_health.sh" 2>/dev/null; then
            echo -e "${GREEN}✓ Health check passed (attempt $ATTEMPT/$MAX_ATTEMPTS)${NC}"
            echo ""
            echo -e "${GREEN}Service is running successfully!${NC}"
            exit 0
        fi

        if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
            echo "Health check failed, retrying in ${SLEEP_TIME}s... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
            sleep $SLEEP_TIME
            SLEEP_TIME=$((SLEEP_TIME * 2))  # Exponential backoff
        fi

        ATTEMPT=$((ATTEMPT + 1))
    done

    echo -e "${YELLOW}Warning: Health check failed after $MAX_ATTEMPTS attempts${NC}"
    echo "Service may still be starting up. Check logs at: $LOG_FILE"

else
    echo -e "${RED}Error: Invalid mode '$MODE'${NC}"
    echo "Usage: $0 [production|development]"
    exit 1
fi
