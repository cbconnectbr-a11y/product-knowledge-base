#!/bin/bash
# Test runner script for product knowledge base system
# Usage: ./scripts/run_tests.sh

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================="
echo "  Product Knowledge Base - Test Runner"
echo "========================================="
echo ""

# Check if we're in the project root
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Check environment
if [ ! -f .env ]; then
    echo -e "${YELLOW}Warning: .env file not found${NC}"
    echo "Integration tests will be skipped"
    echo ""
fi

# Check if pytest is installed
if ! python3 -m pytest --version &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed${NC}"
    echo "Install with: pip install -r requirements.txt"
    exit 1
fi

# Track overall status
OVERALL_STATUS=0

# Run unit tests for search functions
echo -e "${BLUE}1. Running search unit tests...${NC}"
echo "----------------------------------------"
if python3 -m pytest tests/test_search.py -v --tb=short; then
    echo -e "${GREEN}✓ Search unit tests passed${NC}"
    echo ""
else
    echo -e "${RED}✗ Search unit tests failed${NC}"
    OVERALL_STATUS=1
    echo ""
fi

# Run integration tests
echo -e "${BLUE}2. Running integration tests...${NC}"
echo "----------------------------------------"
if python3 -m pytest tests/test_integration.py -v --tb=short -m integration; then
    echo -e "${GREEN}✓ Integration tests passed${NC}"
    echo ""
else
    echo -e "${YELLOW}✗ Integration tests failed or skipped${NC}"
    echo "Note: Integration tests require .env configuration"
    # Don't set OVERALL_STATUS=1 here since tests might be skipped
    echo ""
fi

# Run import script tests
echo -e "${BLUE}3. Running import script tests...${NC}"
echo "----------------------------------------"
if python3 -m pytest tests/test_import_historical_data.py -v --tb=short; then
    echo -e "${GREEN}✓ Import script tests passed${NC}"
    echo ""
else
    echo -e "${RED}✗ Import script tests failed${NC}"
    OVERALL_STATUS=1
    echo ""
fi

# Summary
echo "========================================="
echo "  Test Summary"
echo "========================================="
if [ $OVERALL_STATUS -eq 0 ]; then
    echo -e "${GREEN}All required tests passed!${NC}"
    echo ""
    echo "Run with coverage: python3 -m pytest --cov=bot --cov=scripts tests/"
    exit 0
else
    echo -e "${RED}Some tests failed. Please review the output above.${NC}"
    exit 1
fi
