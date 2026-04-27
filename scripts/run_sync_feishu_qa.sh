#!/bin/bash
# Wrapper script for launchd to load environment variables before running sync_feishu_qa.py

# Change to project directory
cd /Users/cindy/Projects/product-knowledge-base

# Load environment variables from .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "Error: .env file not found at /Users/cindy/Projects/product-knowledge-base/.env"
    exit 1
fi

# Run the Python script
/opt/homebrew/bin/python3 scripts/sync_feishu_qa.py
