"""
搜索逻辑实现
Phase 1: 使用传统搜索技术（SKU 精确匹配、全文搜索、模糊匹配）
Phase 2+: 将引入 AI 语义搜索和向量搜索
"""
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from scripts.utils import get_supabase_client, extract_sku

logger = logging.getLogger(__name__)


def search_products_by_sku(sku: str) -> List[Dict[str, Any]]:
    """
    在产品表中搜索 SKU

    Args:
        sku: SKU 编号

    Returns:
        匹配的产品列表
    """
    if not sku or not sku.strip():
        return []

    client = get_supabase_client()

    response = client.table('products') \
        .select('sku, name_cn, name_en, features, description, searchable_content, images, package_images, manual_files') \
        .eq('sku', sku.strip().upper()) \
        .execute()

    # 转换为统一格式（与 knowledge_entries 兼容）
    results = []
    for item in (response.data or []):
        results.append({
            'id': item.get('sku'),  # 使用 SKU 作为 ID
            'sku': item.get('sku'),
            'title': f"{item.get('name_cn') or item.get('name_en')} [{item.get('sku')}]",
            'content': item.get('searchable_content') or item.get('features') or item.get('description') or '',
            'source_group': '产品信息',
            'source_type': 'product',
            'images': item.get('images'),
            'package_images': item.get('package_images'),
            'manual_files': item.get('manual_files'),
        })

    return results


def search_products_by_keyword(keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    在产品表中搜索关键词（全文搜索）

    Args:
        keyword: 搜索关键词
        limit: 最大返回结果数量

    Returns:
        匹配的产品列表
    """
    if not keyword or not keyword.strip():
        return []

    client = get_supabase_client()

    response = client.table('products') \
        .select('sku, name_cn, name_en, features, description, searchable_content, images, package_images, manual_files') \
        .plfts('search_vector', keyword.strip()) \
        .limit(limit) \
        .execute()

    # 转换为统一格式
    results = []
    for item in (response.data or []):
        results.append({
            'id': item.get('sku'),
            'sku': item.get('sku'),
            'title': f"{item.get('name_cn') or item.get('name_en')} [{item.get('sku')}]",
            'content': item.get('searchable_content') or item.get('features') or item.get('description') or '',
            'source_group': '产品信息',
            'source_type': 'product',
            'images': item.get('images'),
            'package_images': item.get('package_images'),
            'manual_files': item.get('manual_files'),
        })

    return results


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

    # 使用 PostgreSQL 全文搜索（tsvector/tsquery）
    # Supabase Python SDK 使用 plfts() 方法（plainto_tsquery）
    # 搜索 search_vector 字段（由 title + content 自动生成）
    response = client.table('knowledge_entries') \
        .select('id, sku, title, content, source_group, keywords, created_at') \
        .eq('status', 'approved') \
        .plfts('search_vector', keyword.strip()) \
        .order('created_at', desc=True) \
        .limit(limit) \
        .execute()

    return response.data if response.data else []


def search_by_keyword_like(keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    LIKE 模糊搜索（使用 pg_trgm 索引优化，适合中文搜索）

    策略（多词查询优先级）：
    1. 优先：标题同时包含所有词（最相关）
    2. 其次：内容同时包含所有词
    3. 最后：标题或内容包含任意词（降级）

    Args:
        keyword: 搜索关键词（支持多词，如"水龙头 漏水"）
        limit: 最大返回结果数量

    Returns:
        匹配的知识条目列表
    """
    if not keyword or not keyword.strip():
        return []

    client = get_supabase_client()
    keyword = keyword.strip()
    results = []
    seen_ids = set()

    # 检测多词查询：如果有空格，使用多词策略
    words = [w.strip() for w in keyword.split() if w.strip()]
    if len(words) > 1:
        # 优先级1: 标题同时包含所有词
        try:
            query = client.table('knowledge_entries') \
                .select('id, sku, title, content, source_group, keywords, created_at') \
                .eq('status', 'approved')

            # 链式调用 ilike，实现 AND 逻辑
            for word in words:
                query = query.ilike('title', f'%{word}%')

            response = query.order('created_at', desc=True).limit(limit).execute()

            if response.data:
                for item in response.data:
                    if item['id'] not in seen_ids:
                        results.append(item)
                        seen_ids.add(item['id'])
        except Exception as e:
            import logging
            logging.error(f"Multi-word title search failed: {e}")

        # 优先级2: 如果结果不够，搜索内容同时包含所有词
        if len(results) < limit:
            try:
                query = client.table('knowledge_entries') \
                    .select('id, sku, title, content, source_group, keywords, created_at') \
                    .eq('status', 'approved')

                for word in words:
                    query = query.ilike('content', f'%{word}%')

                response = query.order('created_at', desc=True).limit(limit - len(results) + 5).execute()

                if response.data:
                    for item in response.data:
                        if item['id'] not in seen_ids:
                            results.append(item)
                            seen_ids.add(item['id'])
                            if len(results) >= limit:
                                break
            except Exception as e:
                import logging
                logging.error(f"Multi-word content search failed: {e}")

        # 优先级3: 如果还不够，降级为搜索包含任意词的记录
        if len(results) < limit:
            for word in words:
                if len(results) >= limit:
                    break
                word_results = _search_single_keyword_like(client, word, limit - len(results))
                for item in word_results:
                    if item['id'] not in seen_ids:
                        results.append(item)
                        seen_ids.add(item['id'])
                        if len(results) >= limit:
                            break

        return results[:limit]

    # 单词查询：使用原有逻辑
    return _search_single_keyword_like(client, keyword, limit)


def _search_single_keyword_like(client, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    单个关键词的 LIKE 搜索（内部函数）

    分步搜索：先 title 后 content

    Args:
        client: Supabase 客户端
        keyword: 单个搜索关键词
        limit: 最大返回结果数量

    Returns:
        匹配的知识条目列表
    """
    results = []
    seen_ids = set()

    # 步骤1: 搜索 title (优先级高，速度快)
    try:
        response = client.table('knowledge_entries') \
            .select('id, sku, title, content, source_group, keywords, created_at') \
            .eq('status', 'approved') \
            .ilike('title', f'%{keyword}%') \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()

        if response.data:
            for item in response.data:
                if item['id'] not in seen_ids:
                    results.append(item)
                    seen_ids.add(item['id'])
    except Exception as e:
        # title 搜索失败，记录日志但继续
        import logging
        logging.error(f"Title LIKE search failed for '{keyword}': {e}")

    # 步骤2: 如果 title 结果不够，搜索 content 补充
    if len(results) < limit:
        remaining = limit - len(results)
        try:
            response = client.table('knowledge_entries') \
                .select('id, sku, title, content, source_group, keywords, created_at') \
                .eq('status', 'approved') \
                .ilike('content', f'%{keyword}%') \
                .order('created_at', desc=True) \
                .limit(remaining + 5) \
                .execute()

            if response.data:
                for item in response.data:
                    if item['id'] not in seen_ids:
                        results.append(item)
                        seen_ids.add(item['id'])
                        if len(results) >= limit:
                            break
        except Exception as e:
            # content 搜索失败，记录日志
            import logging
            logging.error(f"Content LIKE search failed for '{keyword}': {e}")

    return results[:limit]


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


def filter_sensitive_content(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    过滤包含敏感信息的记录（价格、供应商等）

    Args:
        results: 搜索结果列表

    Returns:
        过滤后的结果列表
    """
    # 敏感关键词列表
    SENSITIVE_KEYWORDS = [
        # 价格相关
        '价格', '采购价', '成本价', '进价', '售价', '报价', '单价', '总价',
        '成本', '费用', '金额', '人民币', '美元', '雷亚尔',
        'USD', 'BRL', 'CNY', 'R$', '$', '¥', '元',
        # 供应商相关
        '供应商', '供货商', '厂家', '生产商', '工厂', '制造商',
        'supplier', 'vendor', 'factory', 'manufacturer'
    ]

    filtered_results = []
    filtered_count = 0

    for result in results:
        # 检查标题和内容
        title = result.get('title', '').lower()
        content = result.get('content', '').lower()
        combined_text = title + ' ' + content

        # 检查是否包含敏感关键词
        is_sensitive = any(keyword.lower() in combined_text for keyword in SENSITIVE_KEYWORDS)

        if not is_sensitive:
            filtered_results.append(result)
        else:
            filtered_count += 1
            logger.info(f"Filtered sensitive content: SKU={result.get('sku')}, title={result.get('title', '')[:50]}...")

    if filtered_count > 0:
        logger.info(f"Filtered {filtered_count} sensitive records out of {len(results)} total results")

    return filtered_results


def smart_search(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    智能搜索：自动判断查询类型并选择最佳搜索策略

    逻辑：
    1. 先尝试从查询中提取 SKU
    2. 如果找到 SKU，使用 SKU 精确匹配
    3. 否则使用关键词搜索

    优化：使用并行查询（ThreadPoolExecutor）同时查询 products 和 knowledge_entries 表

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

    # 使用线程池并行查询（2个查询同时执行）
    product_results = []
    knowledge_results = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        if extracted_sku:
            # SKU 精确搜索路径
            future_product = executor.submit(search_products_by_sku, extracted_sku)
            future_knowledge = executor.submit(search_by_sku_exact, extracted_sku)
            search_type = 'sku'
        else:
            # 关键词搜索路径
            future_product = executor.submit(search_products_by_keyword, query, limit)
            future_knowledge = executor.submit(search_by_keyword_like, query, limit)
            search_type = 'keyword'

        # 收集结果（带超时和异常处理）
        for future, name in [(future_product, 'products'), (future_knowledge, 'knowledge_entries')]:
            try:
                result = future.result(timeout=10)  # 10秒超时
                if name == 'products':
                    product_results = result or []
                else:
                    knowledge_results = result or []
            except Exception as e:
                logger.warning(f"Search failed for {name}: {e}", exc_info=True)
                # 失败的查询返回空列表，不影响另一个查询

    # 合并结果：产品信息优先
    results = product_results + knowledge_results

    # 过滤敏感信息（价格、供应商等）
    filtered_results = filter_sensitive_content(results)

    result_dict = {
        'results': filtered_results,
        'search_type': search_type,
        'query': query,
        'total_before_filter': len(results),
        'filtered_count': len(results) - len(filtered_results)
    }

    if extracted_sku:
        result_dict['extracted_sku'] = extracted_sku

    return result_dict


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
        print(f"来源类型: {entry.get('source_type', 'knowledge')}")
        if 'created_at' in entry:
            print(f"创建时间: {entry['created_at']}")
        print()
