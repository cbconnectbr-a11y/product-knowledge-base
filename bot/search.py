"""
搜索逻辑实现
Phase 1: 使用传统搜索技术（SKU 精确匹配、全文搜索、模糊匹配）
Phase 2+: 将引入 AI 语义搜索和向量搜索
"""
from typing import List, Dict, Any, Optional
from scripts.utils import get_supabase_client, extract_sku


def search_by_sku_exact(sku: str) -> List[Dict[str, Any]]:
    """
    SKU 精确匹配搜索

    Args:
        sku: SKU 编号（如 CBC004-1234）

    Returns:
        匹配的知识条目列表
    """
    if not sku or not sku.strip():
        return []

    client = get_supabase_client()

    # 查询条件：SKU 精确匹配且状态为 approved
    response = client.table('knowledge_entries') \
        .select('id, sku, title, content, source_group, keywords, created_at') \
        .eq('sku', sku.strip().upper()) \
        .eq('status', 'approved') \
        .order('created_at', desc=True) \
        .execute()

    return response.data if response.data else []


def search_by_keyword(keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    全文搜索（使用 PostgreSQL 的文本搜索功能）

    Args:
        keyword: 搜索关键词
        limit: 最大返回结果数量

    Returns:
        匹配的知识条目列表
    """
    if not keyword or not keyword.strip():
        return []

    client = get_supabase_client()

    # 使用 textSearch 进行全文搜索
    # Supabase 的 textSearch 会自动使用 to_tsquery 和 tsvector
    # 搜索 title 和 content 字段
    response = client.table('knowledge_entries') \
        .select('id, sku, title, content, source_group, keywords, created_at') \
        .eq('status', 'approved') \
        .or_(f'title.ilike.%{keyword.strip()}%,content.ilike.%{keyword.strip()}%') \
        .order('created_at', desc=True) \
        .limit(limit) \
        .execute()

    return response.data if response.data else []


def search_by_fuzzy_similarity(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    模糊匹配搜索（使用 ILIKE）

    Args:
        query: 搜索查询
        limit: 最大返回结果数量

    Returns:
        匹配的知识条目列表
    """
    if not query or not query.strip():
        return []

    client = get_supabase_client()

    # 使用 ILIKE 进行模糊匹配
    search_pattern = f'%{query.strip()}%'
    response = client.table('knowledge_entries') \
        .select('id, sku, title, content, source_group, keywords, created_at') \
        .eq('status', 'approved') \
        .or_(f'title.ilike.{search_pattern},content.ilike.{search_pattern}') \
        .order('created_at', desc=True) \
        .limit(limit) \
        .execute()

    return response.data if response.data else []


def smart_search(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    智能搜索：自动判断查询类型并选择最佳搜索策略

    逻辑：
    1. 先尝试从查询中提取 SKU
    2. 如果找到 SKU，使用 SKU 精确匹配
    3. 否则使用关键词搜索

    Args:
        query: 搜索查询
        limit: 最大返回结果数量（仅用于关键词搜索）

    Returns:
        包含搜索结果和元数据的字典：
        {
            'results': [...],
            'search_type': 'sku' | 'keyword',
            'query': original_query,
            'extracted_sku': sku_if_found (optional)
        }
    """
    if not query or not query.strip():
        return {
            'results': [],
            'search_type': 'keyword',
            'query': query
        }

    # 尝试提取 SKU
    extracted_sku = extract_sku(query)

    if extracted_sku:
        # 如果找到 SKU，使用 SKU 精确搜索
        results = search_by_sku_exact(extracted_sku)
        return {
            'results': results,
            'search_type': 'sku',
            'query': query,
            'extracted_sku': extracted_sku
        }
    else:
        # 否则使用关键词搜索
        results = search_by_keyword(query, limit=limit)
        return {
            'results': results,
            'search_type': 'keyword',
            'query': query
        }


if __name__ == "__main__":
    # 测试搜索功能
    import sys

    if len(sys.argv) < 2:
        print("用法: python -m bot.search <查询内容>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"搜索查询: {query}\n")

    # 执行智能搜索
    result = smart_search(query)

    print(f"搜索类型: {result['search_type']}")
    if 'extracted_sku' in result:
        print(f"提取的 SKU: {result['extracted_sku']}")
    print(f"结果数量: {len(result['results'])}\n")

    # 显示结果
    for i, entry in enumerate(result['results'], 1):
        print(f"--- 结果 {i} ---")
        print(f"ID: {entry['id']}")
        print(f"SKU: {entry.get('sku', 'N/A')}")
        print(f"标题: {entry['title']}")
        print(f"内容: {entry['content'][:100]}...")
        print(f"来源群组: {entry.get('source_group', 'N/A')}")
        print(f"关键词: {entry.get('keywords', [])}")
        print(f"创建时间: {entry['created_at']}")
        print()
