#!/bin/bash
# Product Knowledge Base - Health Check Script
#
# Checks if the service is running and responding
# Usage: ./scripts/check_health.sh

# Get port from environment or default to 5000
PORT="${PORT:-5000}"
HEALTH_URL="http://localhost:$PORT/health"

# Colors (only if stdout is terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    NC=''
fi

# Check if curl is available
if command -v curl &> /dev/null; then
    # Try HTTP health check
    RESPONSE=$(curl -s -w "\n%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)

    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ Service is healthy${NC}"
        exit 0
    else
        echo -e "${RED}✗ Service returned HTTP $HTTP_CODE${NC}"
        exit 1
    fi
else
    # Fallback: check if process exists
    PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    PID_FILE="$PROJECT_ROOT/bot.pid"

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Service process is running (PID: $PID)${NC}"
            exit 0
        fi
    fi

    echo -e "${RED}✗ Service is not running${NC}"
    exit 1
fi
