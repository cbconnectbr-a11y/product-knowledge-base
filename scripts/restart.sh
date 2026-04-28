#!/bin/bash
# Product Knowledge Base - Restart Service Script
#
# Stops and starts the Flask webhook service
# Usage:
#   ./scripts/restart.sh                 # Restart in production mode
#   ./scripts/restart.sh production      # Restart in production mode
#   ./scripts/restart.sh development     # Restart in development mode

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}===================================${NC}"
echo -e "${GREEN}Product Knowledge Base - Restart${NC}"
echo -e "${GREEN}===================================${NC}"
echo ""

# Stop service
echo "Step 1/2: Stopping service..."
bash "$SCRIPT_DIR/stop.sh"

# Wait a moment for cleanup
sleep 2

echo ""
echo "Step 2/2: Starting service..."
# Start service with same arguments (mode passthrough)
bash "$SCRIPT_DIR/start.sh" "$@"
