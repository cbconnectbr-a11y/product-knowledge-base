#!/usr/bin/env python3
"""
Product Knowledge Base - Database Connection Test
Created: 2026-04-26

This script tests the connection to Supabase and verifies that all tables
are created and accessible.

Requirements:
- .env file with SUPABASE_URL and SUPABASE_KEY configured
- supabase-py package installed (pip install supabase)

Usage:
    python3 database/test_connection.py
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}{text.center(70)}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text: str):
    """Print error message"""
    print(f"{RED}✗ {text}{RESET}")


def print_info(text: str):
    """Print info message"""
    print(f"{YELLOW}ℹ {text}{RESET}")


def test_connection() -> bool:
    """Test connection to Supabase and verify database setup"""

    print_header("Product Knowledge Base - Database Connection Test")
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Step 1: Check environment variables
    print("Step 1: Checking environment variables...")
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')

    if not supabase_url or not supabase_key:
        print_error("Missing Supabase credentials in .env file")
        print_info("Please set SUPABASE_URL and SUPABASE_KEY in your .env file")
        print_info("Example:")
        print("   SUPABASE_URL=https://your-project.supabase.co")
        print("   SUPABASE_KEY=your-anon-key-here")
        return False

    if supabase_url == "https://your-project.supabase.co":
        print_error("SUPABASE_URL still has default placeholder value")
        print_info("Please update .env with your actual Supabase project URL")
        return False

    print_success(f"Environment variables loaded")
    print(f"   URL: {supabase_url}")
    print(f"   Key: {supabase_key[:20]}..." if len(supabase_key) > 20 else f"   Key: {supabase_key}")

    # Step 2: Connect to Supabase
    print("\nStep 2: Connecting to Supabase...")
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        print_success("Successfully connected to Supabase")
    except Exception as e:
        print_error(f"Failed to connect to Supabase: {str(e)}")
        return False

    # Step 3: Test each table
    print("\nStep 3: Testing table access and counting records...")

    tables = {
        'users': 'User accounts',
        'products': 'Product catalog',
        'knowledge_entries': 'Knowledge base entries',
        'search_logs': 'Search query logs'
    }

    all_tests_passed = True

    for table_name, description in tables.items():
        try:
            response = supabase.table(table_name).select("*", count="exact").execute()
            count = response.count if hasattr(response, 'count') else len(response.data)
            print_success(f"{table_name.ljust(25)} {description.ljust(30)} ({count} records)")
        except Exception as e:
            print_error(f"{table_name.ljust(25)} Failed to query: {str(e)}")
            all_tests_passed = False

    # Step 4: Test specific queries
    print("\nStep 4: Testing specific queries...")

    # Test 4.1: Query admin user
    try:
        response = supabase.table('users').select("*").eq('role', 'admin').execute()
        if response.data:
            admin = response.data[0]
            print_success(f"Found admin user: {admin['name']} ({admin['email']})")
        else:
            print_info("No admin users found (this might be expected if seed data not loaded)")
    except Exception as e:
        print_error(f"Failed to query admin user: {str(e)}")
        all_tests_passed = False

    # Test 4.2: Query products with SKU
    try:
        response = supabase.table('products').select("*").limit(1).execute()
        if response.data:
            product = response.data[0]
            print_success(f"Found product: {product['sku']} - {product['name'][:50]}...")
        else:
            print_info("No products found (seed data may not be loaded yet)")
    except Exception as e:
        print_error(f"Failed to query products: {str(e)}")
        all_tests_passed = False

    # Test 4.3: Query knowledge entries with joins
    try:
        response = supabase.table('knowledge_entries').select(
            "id, category, question, verified, products(sku, name)"
        ).limit(1).execute()
        if response.data:
            entry = response.data[0]
            print_success(f"Found knowledge entry: {entry['category']} - {entry['question'][:50]}...")
        else:
            print_info("No knowledge entries found (seed data may not be loaded yet)")
    except Exception as e:
        print_error(f"Failed to query knowledge entries: {str(e)}")
        all_tests_passed = False

    # Step 5: Final summary
    print_header("Test Summary")

    if all_tests_passed:
        print_success("All database connection tests passed!")
        print_info("Your Supabase database is properly configured and accessible.")
        print_info("\nNext steps:")
        print("   1. If you see 0 records, run database/seed.sql to load test data")
        print("   2. Start developing the Flask API and Feishu bot")
        return True
    else:
        print_error("Some tests failed!")
        print_info("\nTroubleshooting:")
        print("   1. Verify your Supabase credentials in .env")
        print("   2. Check if database/schema.sql has been executed in Supabase SQL Editor")
        print("   3. Review error messages above for specific issues")
        return False


if __name__ == "__main__":
    try:
        success = test_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print_info("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
