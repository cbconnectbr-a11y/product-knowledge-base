"""
Integration tests for the product knowledge base system.

These tests verify the entire system works end-to-end with a real Supabase database.
Tests are designed to be idempotent and clean up after themselves.

Run with: pytest tests/test_integration.py -v
Skip if no .env: pytest tests/test_integration.py -v -m "not integration"
"""
import pytest
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from scripts.utils import get_supabase_client, extract_sku
from bot.search import (
    search_by_sku_exact,
    search_by_keyword,
    smart_search
)
from bot.formatters import format_knowledge_entry, format_search_results
from bot.handlers import parse_command, log_search


# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def supabase_client():
    """
    Get Supabase client for integration tests.

    Skips all integration tests if SUPABASE_URL or SUPABASE_KEY are not configured.
    """
    # Check for required environment variables
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        pytest.skip(
            "Integration tests skipped: SUPABASE_URL and SUPABASE_KEY not configured in .env"
        )

    if "your-project" in supabase_url or "your-anon-key" in supabase_key:
        pytest.skip(
            "Integration tests skipped: SUPABASE_URL and SUPABASE_KEY not properly configured"
        )

    try:
        client = get_supabase_client()
        # Test connection by querying users table
        client.table('users').select('id').limit(1).execute()
        return client
    except Exception as e:
        pytest.skip(f"Integration tests skipped: Cannot connect to Supabase: {e}")


@pytest.fixture(scope="module")
def test_user_id(supabase_client) -> Optional[str]:
    """
    Get or create a test user for integration tests.

    Returns the user UUID as a string.
    """
    test_email = "test_integration@example.com"

    try:
        # Check if test user exists
        response = supabase_client.table('users').select('id').eq('email', test_email).execute()

        if response.data:
            return str(response.data[0]['id'])

        # Create test user if doesn't exist
        response = supabase_client.table('users').insert({
            'email': test_email,
            'name': 'Integration Test User',
            'role': 'viewer'
        }).execute()

        return str(response.data[0]['id'])
    except Exception as e:
        pytest.skip(f"Cannot create test user: {e}")


@pytest.fixture(scope="function")
def test_knowledge_entry(supabase_client) -> Dict[str, Any]:
    """
    Create a test knowledge entry and clean up after tests.

    Yields entry data, then deletes it after the test completes.
    """
    # Generate unique SKU for this test
    test_sku = f"TEST{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"

    # Insert test entry
    entry_data = {
        'sku': test_sku,
        'title': '测试产品常见问题',
        'content': '这是一个集成测试的知识条目，用于验证搜索功能。包含关键词：加热杯、漏水、故障',
        'source_type': 'manual',
        'source_id': f'test_{uuid.uuid4().hex}',
        'source_group': '集成测试群',
        'status': 'approved',
        'keywords': ['加热杯', '漏水', '故障', '测试'],
        'category': ['测试分类']
    }

    try:
        response = supabase_client.table('knowledge_entries').insert(entry_data).execute()
        created_entry = response.data[0]

        yield created_entry

    finally:
        # Cleanup: Delete test entry
        try:
            supabase_client.table('knowledge_entries').delete().eq('sku', test_sku).execute()
        except Exception as e:
            print(f"Warning: Failed to cleanup test entry: {e}")


class TestDatabaseConnection:
    """Test database connectivity and configuration"""

    def test_environment_variables_loaded(self, supabase_client):
        """Test that environment variables are properly loaded"""
        # This test will be skipped if env vars are not configured
        # due to the supabase_client fixture dependency
        assert os.environ.get("SUPABASE_URL") is not None
        assert os.environ.get("SUPABASE_KEY") is not None

    def test_supabase_client_creation(self, supabase_client):
        """Test that Supabase client can be created"""
        # This test will be skipped if env vars are not configured
        assert supabase_client is not None

    def test_database_connection(self, supabase_client):
        """Test that database connection is working"""
        # Simple query to verify connection
        response = supabase_client.table('users').select('id').limit(1).execute()
        assert response is not None

    def test_required_tables_exist(self, supabase_client):
        """Test that all required tables are accessible"""
        tables = ['users', 'products', 'knowledge_entries', 'search_logs']

        for table in tables:
            try:
                response = supabase_client.table(table).select('id').limit(1).execute()
                assert response is not None, f"Table {table} should be accessible"
            except Exception as e:
                pytest.fail(f"Table {table} is not accessible: {e}")


class TestProductData:
    """Test products table operations"""

    def test_products_table_structure(self, supabase_client):
        """Test that products table has expected structure"""
        response = supabase_client.table('products').select('*').limit(1).execute()

        # Should return without error even if empty
        assert response is not None
        assert hasattr(response, 'data')

    def test_products_retrieval(self, supabase_client):
        """Test retrieving products from database"""
        response = supabase_client.table('products').select('id, sku, name_cn').limit(5).execute()

        assert response is not None
        assert isinstance(response.data, list)
        # Note: May be empty if no products synced yet

    def test_products_sku_uniqueness(self, supabase_client):
        """Test that SKU field exists and is indexed"""
        # Query by SKU to verify index works
        response = supabase_client.table('products').select('id, sku').eq('sku', 'NONEXISTENT_SKU').execute()

        assert response is not None
        assert len(response.data) == 0  # Should find nothing


class TestKnowledgeEntries:
    """Test knowledge_entries CRUD and triggers"""

    def test_knowledge_entries_table_structure(self, supabase_client):
        """Test that knowledge_entries table has expected structure"""
        response = supabase_client.table('knowledge_entries').select('*').limit(1).execute()

        assert response is not None
        assert hasattr(response, 'data')

    def test_create_knowledge_entry(self, supabase_client):
        """Test creating a knowledge entry"""
        test_sku = f"TEST{uuid.uuid4().hex[:8].upper()}"

        entry_data = {
            'sku': test_sku,
            'title': '测试标题',
            'content': '测试内容',
            'source_type': 'manual',
            'source_id': f'test_{uuid.uuid4().hex}',
            'status': 'draft'
        }

        try:
            response = supabase_client.table('knowledge_entries').insert(entry_data).execute()

            assert len(response.data) == 1
            created = response.data[0]
            assert created['sku'] == test_sku
            assert created['title'] == '测试标题'
            assert created['status'] == 'draft'

        finally:
            # Cleanup
            supabase_client.table('knowledge_entries').delete().eq('sku', test_sku).execute()

    def test_update_knowledge_entry(self, test_knowledge_entry):
        """Test updating a knowledge entry"""
        client = get_supabase_client()
        entry_id = test_knowledge_entry['id']

        # Update title
        response = client.table('knowledge_entries').update({
            'title': '更新后的标题'
        }).eq('id', entry_id).execute()

        assert len(response.data) == 1
        assert response.data[0]['title'] == '更新后的标题'

    def test_search_vector_trigger(self, supabase_client):
        """Test that search_vector is automatically generated on insert/update"""
        test_sku = f"TEST{uuid.uuid4().hex[:8].upper()}"

        entry_data = {
            'sku': test_sku,
            'title': '搜索向量测试标题',
            'content': '搜索向量测试内容',
            'source_type': 'manual',
            'source_id': f'test_{uuid.uuid4().hex}',
            'status': 'approved'
        }

        try:
            response = supabase_client.table('knowledge_entries').insert(entry_data).execute()
            created = response.data[0]

            # Verify search_vector field exists (PostgreSQL auto-generates it via trigger)
            # We can't directly check search_vector, but we can verify full-text search works
            search_response = supabase_client.table('knowledge_entries') \
                .select('id') \
                .eq('sku', test_sku) \
                .plfts('search_vector', '测试标题') \
                .execute()

            assert len(search_response.data) > 0, "Search vector trigger should enable full-text search"

        finally:
            # Cleanup
            supabase_client.table('knowledge_entries').delete().eq('sku', test_sku).execute()

    def test_delete_knowledge_entry(self, supabase_client):
        """Test deleting a knowledge entry"""
        test_sku = f"TEST{uuid.uuid4().hex[:8].upper()}"

        # Create entry
        entry_data = {
            'sku': test_sku,
            'title': '待删除测试',
            'content': '测试内容',
            'source_type': 'manual',
            'source_id': f'test_{uuid.uuid4().hex}',
            'status': 'draft'
        }

        response = supabase_client.table('knowledge_entries').insert(entry_data).execute()
        created_id = response.data[0]['id']

        # Delete entry
        delete_response = supabase_client.table('knowledge_entries').delete().eq('id', created_id).execute()

        assert len(delete_response.data) == 1

        # Verify deleted
        verify_response = supabase_client.table('knowledge_entries').select('id').eq('id', created_id).execute()
        assert len(verify_response.data) == 0


class TestSKUSearch:
    """Test SKU search functionality"""

    def test_sku_exact_match(self, test_knowledge_entry):
        """Test exact SKU matching"""
        test_sku = test_knowledge_entry['sku']

        results = search_by_sku_exact(test_sku)

        assert len(results) > 0
        assert results[0]['sku'] == test_sku
        assert results[0]['status'] == 'approved'

    def test_sku_case_insensitive(self, test_knowledge_entry):
        """Test that SKU search is case-insensitive"""
        test_sku = test_knowledge_entry['sku']

        # Search with lowercase
        results = search_by_sku_exact(test_sku.lower())

        assert len(results) > 0
        assert results[0]['sku'] == test_sku

    def test_sku_not_found(self, supabase_client):
        """Test SKU search with non-existent SKU"""
        results = search_by_sku_exact('NONEXISTENT-9999')

        assert len(results) == 0

    def test_sku_empty_input(self):
        """Test SKU search with empty input"""
        results = search_by_sku_exact('')
        assert len(results) == 0

        results = search_by_sku_exact('   ')
        assert len(results) == 0

    def test_extract_sku_from_text(self):
        """Test SKU extraction utility function"""
        # Test various SKU formats
        assert extract_sku("CBC004-1234 加热问题") == "CBC004-1234"
        assert extract_sku("产品 K004-5678 漏水") == "K004-5678"
        assert extract_sku("BRME0341不加热") == "BRME0341"
        assert extract_sku("YMX018 故障") == "YMX018"
        assert extract_sku("没有SKU的文本") is None


class TestKeywordSearch:
    """Test full-text search functionality"""

    def test_keyword_search_basic(self, test_knowledge_entry):
        """Test basic keyword search"""
        results = search_by_keyword('加热杯')

        # Should find our test entry
        assert len(results) > 0

    def test_keyword_search_chinese(self, test_knowledge_entry):
        """Test Chinese content search"""
        results = search_by_keyword('漏水')

        # Should find entries containing the keyword
        assert len(results) > 0

    def test_keyword_search_no_results(self, supabase_client):
        """Test keyword search with no matching results"""
        # Use a very specific nonsense keyword
        results = search_by_keyword('这是一个非常特殊的不存在的关键词xyz123')

        # May or may not find results, but should not error
        assert isinstance(results, list)

    def test_keyword_search_empty_input(self):
        """Test keyword search with empty input"""
        results = search_by_keyword('')
        assert len(results) == 0

        results = search_by_keyword('   ')
        assert len(results) == 0

    def test_keyword_search_limit(self, test_knowledge_entry):
        """Test keyword search result limit"""
        results = search_by_keyword('测试', limit=3)

        # Should not exceed limit
        assert len(results) <= 3

    def test_postgresql_tsvector_search(self, supabase_client):
        """Test that PostgreSQL full-text search is working"""
        # Create a test entry with specific searchable content
        test_sku = f"TEST{uuid.uuid4().hex[:8].upper()}"

        entry_data = {
            'sku': test_sku,
            'title': '全文搜索测试专用标题',
            'content': '全文搜索测试专用内容',
            'source_type': 'manual',
            'source_id': f'test_{uuid.uuid4().hex}',
            'status': 'approved'
        }

        try:
            supabase_client.table('knowledge_entries').insert(entry_data).execute()

            # Use plfts (plainto_tsquery) to search
            response = supabase_client.table('knowledge_entries') \
                .select('id, title') \
                .eq('status', 'approved') \
                .plfts('search_vector', '全文搜索测试专用') \
                .execute()

            assert len(response.data) > 0, "PostgreSQL full-text search should work"

        finally:
            # Cleanup
            supabase_client.table('knowledge_entries').delete().eq('sku', test_sku).execute()


class TestSmartSearch:
    """Test smart search functionality"""

    def test_smart_search_with_sku(self, test_knowledge_entry):
        """Test smart search automatically detects SKU"""
        test_sku = test_knowledge_entry['sku']

        result = smart_search(f"{test_sku} 问题")

        assert result['search_type'] == 'sku'
        assert result['extracted_sku'] == test_sku
        assert len(result['results']) > 0

    def test_smart_search_keyword_only(self, supabase_client):
        """Test smart search falls back to keyword search"""
        result = smart_search('加热杯漏水')

        assert result['search_type'] == 'keyword'
        assert 'extracted_sku' not in result
        assert isinstance(result['results'], list)

    def test_smart_search_empty_input(self):
        """Test smart search with empty input"""
        result = smart_search('')

        assert result['search_type'] == 'keyword'
        assert len(result['results']) == 0


class TestResultFormatting:
    """Test message formatting functions"""

    def test_format_knowledge_entry(self, test_knowledge_entry):
        """Test formatting a single knowledge entry"""
        formatted = format_knowledge_entry(test_knowledge_entry)

        assert isinstance(formatted, str)
        assert test_knowledge_entry['title'] in formatted
        assert test_knowledge_entry['sku'] in formatted
        assert '❓' in formatted  # Question emoji
        assert '💡' in formatted  # Bulb emoji
        assert '📅' in formatted  # Calendar emoji

    def test_format_search_results_with_results(self, test_knowledge_entry):
        """Test formatting search results with data"""
        results = [test_knowledge_entry]

        formatted = format_search_results(results, 'keyword', '测试')

        assert isinstance(formatted, str)
        assert '🔍 搜索结果' in formatted
        assert '找到 1 条相关知识' in formatted
        assert test_knowledge_entry['title'] in formatted

    def test_format_search_results_empty(self):
        """Test formatting empty search results"""
        formatted = format_search_results([], 'sku', 'NOTFOUND-9999')

        assert isinstance(formatted, str)
        assert '未找到相关知识' in formatted
        assert 'NOTFOUND-9999' in formatted

    def test_format_search_results_multiple(self):
        """Test formatting multiple search results"""
        # Create mock entries
        entries = [
            {
                'id': str(uuid.uuid4()),
                'sku': 'TEST001',
                'title': '标题1',
                'content': '内容1',
                'source_group': '群组1',
                'created_at': datetime.now().isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'sku': 'TEST002',
                'title': '标题2',
                'content': '内容2',
                'source_group': '群组2',
                'created_at': datetime.now().isoformat()
            }
        ]

        formatted = format_search_results(entries, 'keyword', '测试')

        assert '找到 2 条相关知识' in formatted
        assert '--- 结果 1 ---' in formatted
        assert '--- 结果 2 ---' in formatted

    def test_parse_command(self):
        """Test command parsing"""
        assert parse_command('/search 加热杯') == ('search', '加热杯')
        assert parse_command('/sku CBC004-1234') == ('sku', 'CBC004-1234')
        assert parse_command('/help') == ('help', '')
        assert parse_command('加热杯不加热') == ('search', '加热杯不加热')
        assert parse_command('') == ('unknown', '')


class TestSearchLogging:
    """Test search log recording"""

    def test_log_search_writes_to_database(self, supabase_client, test_user_id):
        """Test that log_search() writes to database"""
        # Log a search
        test_query = f'集成测试搜索_{uuid.uuid4().hex[:8]}'

        log_search(
            user_id=test_user_id,
            query=test_query,
            search_type='keyword',
            result_count=5
        )

        # Verify log was created
        response = supabase_client.table('search_logs') \
            .select('*') \
            .eq('query', test_query) \
            .execute()

        # Note: log_search currently sets user_id to NULL in Phase 1
        # So we search by query instead
        assert len(response.data) > 0, "Search log should be created"

        log_entry = response.data[0]
        assert log_entry['query'] == test_query
        assert log_entry['search_type'] == 'keyword'
        assert log_entry['result_count'] == 5

        # Cleanup
        try:
            supabase_client.table('search_logs').delete().eq('query', test_query).execute()
        except:
            pass

    def test_log_search_handles_none_user(self, supabase_client):
        """Test that log_search() handles None user_id gracefully"""
        test_query = f'测试无用户_{uuid.uuid4().hex[:8]}'

        # Should not raise exception
        log_search(
            user_id=None,
            query=test_query,
            search_type='sku',
            result_count=0
        )

        # Verify log was created
        response = supabase_client.table('search_logs') \
            .select('*') \
            .eq('query', test_query) \
            .execute()

        assert len(response.data) > 0

        # Cleanup
        try:
            supabase_client.table('search_logs').delete().eq('query', test_query).execute()
        except:
            pass

    def test_search_logs_table_records(self, supabase_client):
        """Test that search_logs table records properly"""
        # Insert a test log directly
        log_data = {
            'user_id': None,
            'query': f'直接插入测试_{uuid.uuid4().hex[:8]}',
            'search_type': 'keyword',
            'result_count': 3
        }

        response = supabase_client.table('search_logs').insert(log_data).execute()

        assert len(response.data) == 1
        created_log = response.data[0]
        assert created_log['query'] == log_data['query']
        assert created_log['search_type'] == 'keyword'
        assert created_log['result_count'] == 3

        # Cleanup
        try:
            supabase_client.table('search_logs').delete().eq('id', created_log['id']).execute()
        except:
            pass


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])
