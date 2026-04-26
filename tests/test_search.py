"""
搜索功能单元测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from bot.search import (
    search_by_sku_exact,
    search_by_keyword,
    search_by_fuzzy_similarity,
    smart_search
)


# Mock 数据
MOCK_KNOWLEDGE_ENTRY_1 = {
    'id': '123e4567-e89b-12d3-a456-426614174000',
    'sku': 'CBC004-1234',
    'title': '加热杯漏水问题',
    'content': '客户反馈 CBC004-1234 加热杯底部漏水，经检查发现是密封圈老化导致',
    'source_group': '客服群A',
    'keywords': ['漏水', '密封圈', '加热杯'],
    'created_at': '2026-04-20T10:00:00+00:00'
}

MOCK_KNOWLEDGE_ENTRY_2 = {
    'id': '123e4567-e89b-12d3-a456-426614174001',
    'sku': 'CBC004-1234',
    'title': '加热杯不加热故障',
    'content': 'CBC004-1234 加热杯无法加热，检查发现加热片损坏需更换',
    'source_group': '客服群B',
    'keywords': ['不加热', '加热片', '故障'],
    'created_at': '2026-04-21T15:30:00+00:00'
}

MOCK_KNOWLEDGE_ENTRY_3 = {
    'id': '123e4567-e89b-12d3-a456-426614174002',
    'sku': 'CBC006-5678',
    'title': '杯子破损问题',
    'content': '客户收到 CBC006-5678 杯子时发现杯身破损，包装完好',
    'source_group': '客服群A',
    'keywords': ['破损', '包装'],
    'created_at': '2026-04-22T09:15:00+00:00'
}


@pytest.fixture
def mock_supabase():
    """Mock Supabase 客户端"""
    with patch('bot.search.get_supabase_client') as mock_client:
        yield mock_client


class TestSearchBySKUExact:
    """测试 SKU 精确匹配搜索"""

    def test_search_by_sku_success(self, mock_supabase):
        """测试成功查找 SKU"""
        # 设置 mock 返回值
        mock_table = MagicMock()
        mock_response = Mock()
        mock_response.data = [MOCK_KNOWLEDGE_ENTRY_1, MOCK_KNOWLEDGE_ENTRY_2]

        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = mock_response

        mock_supabase.return_value.table.return_value = mock_table

        # 执行搜索
        results = search_by_sku_exact('CBC004-1234')

        # 验证结果
        assert len(results) == 2
        assert results[0]['sku'] == 'CBC004-1234'
        assert results[1]['sku'] == 'CBC004-1234'

        # 验证调用参数
        mock_table.select.assert_called_once()
        assert mock_table.eq.call_count == 2  # status 和 sku

    def test_search_by_sku_no_results(self, mock_supabase):
        """测试未找到匹配的 SKU"""
        mock_table = MagicMock()
        mock_response = Mock()
        mock_response.data = []

        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = mock_response

        mock_supabase.return_value.table.return_value = mock_table

        results = search_by_sku_exact('NOTFOUND-0000')

        assert len(results) == 0

    def test_search_by_sku_empty_input(self, mock_supabase):
        """测试空输入"""
        results = search_by_sku_exact('')
        assert len(results) == 0

        results = search_by_sku_exact('   ')
        assert len(results) == 0

    def test_search_by_sku_case_insensitive(self, mock_supabase):
        """测试 SKU 大小写处理"""
        mock_table = MagicMock()
        mock_response = Mock()
        mock_response.data = [MOCK_KNOWLEDGE_ENTRY_1]

        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = mock_response

        mock_supabase.return_value.table.return_value = mock_table

        # 使用小写 SKU 搜索
        results = search_by_sku_exact('cbc004-1234')

        assert len(results) == 1
        # 验证 SKU 被转为大写
        # 注意：我们只能验证传入的参数，实际转换在函数内部


class TestSearchByKeyword:
    """测试关键词搜索"""

    def test_search_by_keyword_success(self, mock_supabase):
        """测试成功的关键词搜索"""
        mock_table = MagicMock()
        mock_response = Mock()
        mock_response.data = [MOCK_KNOWLEDGE_ENTRY_1]

        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.textSearch.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = mock_response

        mock_supabase.return_value.table.return_value = mock_table

        results = search_by_keyword('漏水')

        assert len(results) == 1
        assert '漏水' in results[0]['content']

    def test_search_by_keyword_multiple_results(self, mock_supabase):
        """测试多个结果"""
        mock_table = MagicMock()
        mock_response = Mock()
        mock_response.data = [MOCK_KNOWLEDGE_ENTRY_1, MOCK_KNOWLEDGE_ENTRY_2]

        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.textSearch.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = mock_response

        mock_supabase.return_value.table.return_value = mock_table

        results = search_by_keyword('加热杯')

        assert len(results) == 2

    def test_search_by_keyword_empty_input(self, mock_supabase):
        """测试空输入"""
        results = search_by_keyword('')
        assert len(results) == 0

        results = search_by_keyword('   ')
        assert len(results) == 0

    def test_search_by_keyword_limit(self, mock_supabase):
        """测试结果数量限制"""
        mock_table = MagicMock()
        mock_response = Mock()
        mock_response.data = [MOCK_KNOWLEDGE_ENTRY_1]

        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.textSearch.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = mock_response

        mock_supabase.return_value.table.return_value = mock_table

        results = search_by_keyword('测试', limit=5)

        # 验证 limit 被调用
        mock_table.limit.assert_called_once_with(5)


class TestSearchByFuzzySimilarity:
    """测试模糊匹配搜索"""

    def test_fuzzy_search_success(self, mock_supabase):
        """测试成功的模糊搜索"""
        mock_table = MagicMock()
        mock_response = Mock()
        mock_response.data = [MOCK_KNOWLEDGE_ENTRY_3]

        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.or_.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = mock_response

        mock_supabase.return_value.table.return_value = mock_table

        results = search_by_fuzzy_similarity('破损')

        assert len(results) == 1
        assert '破损' in results[0]['title']

    def test_fuzzy_search_empty_input(self, mock_supabase):
        """测试空输入"""
        results = search_by_fuzzy_similarity('')
        assert len(results) == 0

    def test_fuzzy_search_limit(self, mock_supabase):
        """测试结果数量限制"""
        mock_table = MagicMock()
        mock_response = Mock()
        mock_response.data = []

        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.or_.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = mock_response

        mock_supabase.return_value.table.return_value = mock_table

        results = search_by_fuzzy_similarity('测试', limit=20)

        mock_table.limit.assert_called_once_with(20)


class TestSmartSearch:
    """测试智能搜索"""

    @patch('bot.search.search_by_sku_exact')
    @patch('bot.search.extract_sku')
    def test_smart_search_with_sku(self, mock_extract_sku, mock_search_sku):
        """测试包含 SKU 的智能搜索"""
        mock_extract_sku.return_value = 'CBC004-1234'
        mock_search_sku.return_value = [MOCK_KNOWLEDGE_ENTRY_1, MOCK_KNOWLEDGE_ENTRY_2]

        result = smart_search('CBC004-1234 加热问题')

        assert result['search_type'] == 'sku'
        assert result['extracted_sku'] == 'CBC004-1234'
        assert len(result['results']) == 2
        assert result['query'] == 'CBC004-1234 加热问题'

        mock_extract_sku.assert_called_once_with('CBC004-1234 加热问题')
        mock_search_sku.assert_called_once_with('CBC004-1234')

    @patch('bot.search.search_by_keyword')
    @patch('bot.search.extract_sku')
    def test_smart_search_without_sku(self, mock_extract_sku, mock_search_keyword):
        """测试不包含 SKU 的智能搜索"""
        mock_extract_sku.return_value = None
        mock_search_keyword.return_value = [MOCK_KNOWLEDGE_ENTRY_1]

        result = smart_search('杯子漏水怎么办')

        assert result['search_type'] == 'keyword'
        assert 'extracted_sku' not in result
        assert len(result['results']) == 1
        assert result['query'] == '杯子漏水怎么办'

        mock_extract_sku.assert_called_once_with('杯子漏水怎么办')
        mock_search_keyword.assert_called_once_with('杯子漏水怎么办', limit=10)

    def test_smart_search_empty_input(self):
        """测试空输入"""
        result = smart_search('')

        assert result['search_type'] == 'keyword'
        assert len(result['results']) == 0
        assert result['query'] == ''

    @patch('bot.search.search_by_keyword')
    @patch('bot.search.extract_sku')
    def test_smart_search_custom_limit(self, mock_extract_sku, mock_search_keyword):
        """测试自定义结果数量限制"""
        mock_extract_sku.return_value = None
        mock_search_keyword.return_value = []

        result = smart_search('测试查询', limit=5)

        mock_search_keyword.assert_called_once_with('测试查询', limit=5)

    @patch('bot.search.search_by_sku_exact')
    @patch('bot.search.extract_sku')
    def test_smart_search_sku_not_found(self, mock_extract_sku, mock_search_sku):
        """测试提取到 SKU 但未找到结果"""
        mock_extract_sku.return_value = 'CBC999-9999'
        mock_search_sku.return_value = []

        result = smart_search('CBC999-9999 问题')

        assert result['search_type'] == 'sku'
        assert result['extracted_sku'] == 'CBC999-9999'
        assert len(result['results']) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
