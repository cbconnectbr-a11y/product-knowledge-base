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
    if ps -p $PID > /dev/null 2>&1; then
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

    # Get port
    PORT="${PORT:-5000}"

    # Check if port is in use
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${RED}Error: Port $PORT is already in use${NC}"
        exit 1
    fi

    # Start gunicorn in background
    nohup gunicorn -w 1 -b 0.0.0.0:$PORT \
        --access-logfile "$ACCESS_LOG" \
        --error-logfile "$ERROR_LOG" \
        --log-level info \
        bot.main:app > "$LOG_FILE" 2>&1 &

    # Save PID
    echo $! > "$PID_FILE"
    echo -e "${GREEN}✓ Service started (PID: $!)${NC}"

    echo ""
    echo -e "Service URL: ${GREEN}http://0.0.0.0:$PORT${NC}"
    echo -e "Health check: ${GREEN}http://localhost:$PORT/health${NC}"
    echo -e "Logs: ${YELLOW}$LOG_DIR/${NC}"
    echo ""

    # Wait and check health
    echo "Waiting for service to be ready..."
    sleep 3

    if bash "$PROJECT_ROOT/scripts/check_health.sh" 2>/dev/null; then
        echo -e "${GREEN}✓ Health check passed${NC}"
        echo ""
        echo -e "${GREEN}Service is running successfully!${NC}"
    else
        echo -e "${YELLOW}Warning: Health check failed${NC}"
        echo "Check logs at: $LOG_FILE"
    fi

else
    echo -e "${RED}Error: Invalid mode '$MODE'${NC}"
    echo "Usage: $0 [production|development]"
    exit 1
fi
