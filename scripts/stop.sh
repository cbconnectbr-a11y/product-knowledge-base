#!/bin/bash
# Product Knowledge Base - Stop Service Script
#
# Gracefully stops the Flask webhook service
# Usage: ./scripts/stop.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$PROJECT_ROOT/bot.pid"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}===================================${NC}"
echo -e "${GREEN}Product Knowledge Base - Stop${NC}"
echo -e "${GREEN}===================================${NC}"
echo ""

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo -e "${YELLOW}Service is not running (no PID file)${NC}"
    exit 0
fi

# Read PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${YELLOW}Service is not running (stale PID: $PID)${NC}"
    rm "$PID_FILE"
    exit 0
fi

echo "Stopping service (PID: $PID)..."

# Try graceful shutdown first (SIGTERM)
kill "$PID" 2>/dev/null || true

# Wait up to 10 seconds for graceful shutdown
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Service stopped gracefully${NC}"
        rm "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill if still running (SIGKILL)
echo -e "${YELLOW}Forcing shutdown...${NC}"
kill -9 $PID 2>/dev/null || true

# Wait a moment
sleep 1

# Verify stopped
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Service stopped (forced)${NC}"
    rm "$PID_FILE"
    exit 0
else
    echo -e "${RED}Error: Failed to stop service${NC}"
    exit 1
fi
