#!/bin/bash
# Product Knowledge Base - Acceptance Test Suite
# Automated verification of Phase 1 MVP deployment
# Usage: bash scripts/acceptance_test.sh

set -e  # Exit on first error in test execution
set -u  # Exit on unset variable

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
PASS=0
FAIL=0

# Project root directory (dynamic detection)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Helper functions
print_test_header() {
    echo ""
    echo -e "${BLUE}Testing: $1${NC}"
    echo "----------------------------------------"
}

print_pass() {
    echo -e "${GREEN}✓ PASS: $1${NC}"
    ((PASS++))
}

print_fail() {
    echo -e "${RED}✗ FAIL: $1${NC}"
    ((FAIL++))
}

print_info() {
    echo -e "${YELLOW}ℹ INFO: $1${NC}"
}

# Load environment variables
load_env() {
    if [ -f "$PROJECT_ROOT/.env" ]; then
        set -a
        source "$PROJECT_ROOT/.env"
        set +a
        return 0
    fi
    return 1
}

# Test 1: Configuration validation
test_configuration() {
    print_test_header "Configuration Validation"

    # Check .env file exists
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        print_fail "Configuration - .env file not found"
        print_info "Create .env file based on .env.example"
        return
    fi

    # Load .env
    load_env

    # Required environment variables
    local required_vars=(
        "SUPABASE_URL"
        "SUPABASE_KEY"
        "SUPABASE_SERVICE_KEY"
        "FEISHU_APP_ID"
        "FEISHU_APP_SECRET"
        "FEISHU_VERIFICATION_TOKEN"
        "FEISHU_ENCRYPT_KEY"
        "FEISHU_PRODUCT_TABLE_APP_TOKEN"
        "FEISHU_PRODUCT_TABLE_TABLE_ID"
        "FEISHU_TECH_GROUPS"
        "FEISHU_MANAGEMENT_APP_TOKEN"
        "FEISHU_MANAGEMENT_TABLE_ID"
    )

    local missing_vars=()
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done

    if [ ${#missing_vars[@]} -eq 0 ]; then
        print_pass "All required environment variables present"
    else
        print_fail "Missing environment variables: ${missing_vars[*]}"
        print_info "Check .env.example for required variables"
    fi

    # Check for placeholder values
    if [[ "$SUPABASE_URL" == *"your-project"* ]] || [[ "$SUPABASE_KEY" == *"your-anon-key"* ]]; then
        print_fail "Supabase credentials contain placeholder values"
    fi
}

# Test 2: Database connection
test_database_connection() {
    print_test_header "Database Connection"

    # Load environment
    if ! load_env; then
        print_fail "Database connection - .env not found"
        return
    fi

    # Check environment variables
    if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_KEY" ]; then
        print_fail "Supabase credentials not configured in .env"
        return
    fi

    # Test connection with Python
    cd "$PROJECT_ROOT"
    python3 <<EOF
import sys
import os
sys.path.insert(0, "$PROJECT_ROOT")
try:
    from scripts.utils import get_supabase_client
    client = get_supabase_client()
    result = client.table('users').select('id').limit(1).execute()
    print('Database connection successful')
    sys.exit(0)
except Exception as e:
    print(f'Database connection failed: {e}')
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_pass "Database connection successful"
    else
        print_fail "Database connection failed"
        print_info "Check SUPABASE_URL and SUPABASE_KEY in .env"
    fi
}

# Test 3: Product data
test_product_data() {
    print_test_header "Product Data Verification"

    if ! load_env; then
        print_fail "Product data - .env not found"
        return
    fi

    cd "$PROJECT_ROOT"
    python3 <<EOF
import sys
sys.path.insert(0, "$PROJECT_ROOT")
try:
    from scripts.utils import get_supabase_client
    client = get_supabase_client()

    # Check products table exists and has data
    result = client.table('products').select('id, sku, name_cn').limit(1).execute()

    if result.data and len(result.data) > 0:
        print(f'Products table has data: {len(result.data)} records found')
        sys.exit(0)
    else:
        print('Products table is empty')
        sys.exit(2)  # Special exit code for empty table
except Exception as e:
    print(f'Products table check failed: {e}')
    sys.exit(1)
EOF

    exit_code=$?
    if [ $exit_code -eq 0 ]; then
        print_pass "Products table has data"
    elif [ $exit_code -eq 2 ]; then
        print_fail "Products table is empty - run scripts/sync_product_table.py"
    else
        print_fail "Products table check failed"
    fi
}

# Test 4: Knowledge entries data
test_knowledge_data() {
    print_test_header "Knowledge Entries Data Verification"

    if ! load_env; then
        print_fail "Knowledge data - .env not found"
        return
    fi

    cd "$PROJECT_ROOT"
    python3 <<EOF
import sys
sys.path.insert(0, "$PROJECT_ROOT")
try:
    from scripts.utils import get_supabase_client
    client = get_supabase_client()

    # Check knowledge_entries table exists and has data
    result = client.table('knowledge_entries').select('id, sku, title, status').limit(1).execute()

    if result.data and len(result.data) > 0:
        print(f'Knowledge entries table has data: {len(result.data)} records found')
        sys.exit(0)
    else:
        print('Knowledge entries table is empty')
        sys.exit(2)  # Special exit code for empty table
except Exception as e:
    print(f'Knowledge entries table check failed: {e}')
    sys.exit(1)
EOF

    exit_code=$?
    if [ $exit_code -eq 0 ]; then
        print_pass "Knowledge entries table has data"
    elif [ $exit_code -eq 2 ]; then
        print_fail "Knowledge entries table is empty - run scripts/sync_feishu_qa.py or scripts/import_historical_data.py"
    else
        print_fail "Knowledge entries table check failed"
    fi
}

# Test 5: Search functions
test_search_functions() {
    print_test_header "Search Functions Verification"

    if ! load_env; then
        print_fail "Search functions - .env not found"
        return
    fi

    cd "$PROJECT_ROOT"
    python3 <<EOF
import sys
sys.path.insert(0, "$PROJECT_ROOT")
try:
    from bot.search import search_by_sku_exact, search_by_keyword, smart_search

    # Test 1: search_by_sku_exact function exists and is callable
    result = search_by_sku_exact('TEST-0000')
    assert isinstance(result, list), "search_by_sku_exact should return a list"

    # Test 2: search_by_keyword function exists and is callable
    result = search_by_keyword('测试关键词')
    assert isinstance(result, list), "search_by_keyword should return a list"

    # Test 3: smart_search function exists and is callable
    result = smart_search('测试查询')
    assert isinstance(result, dict), "smart_search should return a dict"
    assert 'search_type' in result, "smart_search should include search_type"
    assert 'results' in result, "smart_search should include results"

    print('All search functions are callable and return expected types')
    sys.exit(0)
except ImportError as e:
    print(f'Search function import failed: {e}')
    sys.exit(1)
except Exception as e:
    print(f'Search function test failed: {e}')
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_pass "Search functions (SKU exact, keyword, smart search)"
    else
        print_fail "Search functions test failed"
    fi
}

# Test 6: Scheduled tasks
test_scheduled_tasks() {
    print_test_header "Scheduled Tasks (launchd) Verification"

    # Check if launchd plist files exist
    local plist_files=(
        "$PROJECT_ROOT/launchd/com.product-kb.sync-products.plist"
        "$PROJECT_ROOT/launchd/com.product-kb.sync-feishu-qa.plist"
    )

    local missing_plists=()
    for plist in "${plist_files[@]}"; do
        if [ ! -f "$plist" ]; then
            missing_plists+=("$plist")
        fi
    done

    if [ ${#missing_plists[@]} -gt 0 ]; then
        print_fail "Missing launchd plist files: ${missing_plists[*]}"
        return
    else
        print_pass "Launchd plist files exist"
    fi

    # Check if launchd jobs are loaded
    local jobs=(
        "com.product-kb.sync-products"
        "com.product-kb.sync-feishu-qa"
    )

    local loaded_jobs=0
    local not_loaded_jobs=()

    for job in "${jobs[@]}"; do
        if launchctl list | grep -q "$job"; then
            ((loaded_jobs++))
        else
            not_loaded_jobs+=("$job")
        fi
    done

    if [ $loaded_jobs -eq ${#jobs[@]} ]; then
        print_pass "All launchd jobs are loaded ($loaded_jobs/${#jobs[@]})"
    elif [ $loaded_jobs -gt 0 ]; then
        print_fail "Some launchd jobs not loaded: ${not_loaded_jobs[*]}"
        print_info "Load with: launchctl load ~/Library/LaunchAgents/<job>.plist"
    else
        print_fail "No launchd jobs are loaded"
        print_info "Load jobs with: launchctl load ~/Library/LaunchAgents/com.product-kb.*.plist"
    fi
}

# Test 7: Logging system
test_logging_system() {
    print_test_header "Logging System Verification"

    # Check logs directory exists
    if [ ! -d "$PROJECT_ROOT/logs" ]; then
        print_fail "Logs directory does not exist: $PROJECT_ROOT/logs"
        print_info "Create with: mkdir -p $PROJECT_ROOT/logs"
        return
    else
        print_pass "Logs directory exists"
    fi

    # Check log files exist or can be created
    local log_files=(
        "sync_products.log"
        "sync_feishu_qa.log"
    )

    local found_logs=0
    for log_file in "${log_files[@]}"; do
        if [ -f "$PROJECT_ROOT/logs/$log_file" ]; then
            ((found_logs++))
        fi
    done

    if [ $found_logs -gt 0 ]; then
        print_pass "Log files present ($found_logs/${#log_files[@]} found)"
    else
        print_fail "No log files found in logs/ directory"
        print_info "Log files will be created when scripts run"
    fi

    # Check logs directory is writable
    if [ -w "$PROJECT_ROOT/logs" ]; then
        print_pass "Logs directory is writable"
    else
        print_fail "Logs directory is not writable"
        print_info "Fix permissions with: chmod 755 $PROJECT_ROOT/logs"
    fi
}

# Test 8: Integration test suite
test_integration_suite() {
    print_test_header "Integration Test Suite"

    # Check if pytest is installed
    if ! python3 -m pytest --version &> /dev/null; then
        print_fail "pytest is not installed"
        print_info "Install with: pip install -r requirements.txt"
        return
    fi

    # Run the existing test suite via run_tests.sh
    cd "$PROJECT_ROOT"

    print_info "Running test suite (this may take a moment)..."
    if bash "$PROJECT_ROOT/scripts/run_tests.sh" > /tmp/test_output.log 2>&1; then
        print_pass "Integration test suite passed"
        # Show summary
        grep -E "Test Summary|passed|failed" /tmp/test_output.log || true
    else
        print_fail "Integration test suite failed"
        print_info "Last 20 lines of output:"
        echo "----------------------------------------"
        tail -20 /tmp/test_output.log
        echo "----------------------------------------"
        print_info "Full log: /tmp/test_output.log"
    fi
}

# Main execution
main() {
    echo "=========================================="
    echo "  Acceptance Test Suite - Phase 1 MVP"
    echo "=========================================="
    echo "Project: Product Knowledge Base System"
    echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="

    # Change to project root
    cd "$PROJECT_ROOT"

    # Run all tests
    test_configuration
    test_database_connection
    test_product_data
    test_knowledge_data
    test_search_functions
    test_scheduled_tasks
    test_logging_system
    test_integration_suite

    # Summary
    echo ""
    echo "=========================================="
    echo "  Test Results Summary"
    echo "=========================================="
    echo -e "PASSED: ${GREEN}$PASS${NC}"
    echo -e "FAILED: ${RED}$FAIL${NC}"
    echo "TOTAL:  $((PASS + FAIL))"
    echo "=========================================="

    if [ $FAIL -eq 0 ]; then
        echo -e "${GREEN}✓ All acceptance tests passed!${NC}"
        echo ""
        echo "System is ready for production use."
        exit 0
    else
        echo -e "${RED}✗ Some tests failed${NC}"
        echo ""
        echo "Please review the failures above and fix issues before deployment."
        exit 1
    fi
}

# Run main function
main
