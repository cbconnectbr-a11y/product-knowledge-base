"""
飞书消息格式化模块
Phase 1: 使用简单文本消息（Phase 2+ 将引入富文本卡片）
"""
from typing import List, Dict, Any
from datetime import datetime


def format_knowledge_entry(entry: Dict[str, Any]) -> str:
    """
    格式化单个知识条目为文本

    Args:
        entry: 知识条目字典，包含 title, content, source_group, created_at 等字段

    Returns:
        格式化后的文本字符串

    Example:
        >>> entry = {
        ...     'title': '加热杯不加热了怎么办？',
        ...     'content': '检查底座接触是否良好，清洁触点',
        ...     'source_group': 'CBC004群',
        ...     'created_at': '2026-04-15T10:30:00+00:00'
        ... }
        >>> print(format_knowledge_entry(entry))
        ❓ 加热杯不加热了怎么办？
        💡 检查底座接触是否良好，清洁触点
        📅 2026-04-15 | CBC004群
    """
    title = entry.get('title', '无标题')
    content = entry.get('content', '无内容')
    source_group = entry.get('source_group', '未知来源')
    created_at = entry.get('created_at', '')

    # 格式化创建时间（只显示日期）
    try:
        if created_at:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            date_str = dt.strftime('%Y-%m-%d')
        else:
            date_str = '未知日期'
    except (ValueError, AttributeError):
        date_str = '未知日期'

    # SKU 信息（如果有）
    sku = entry.get('sku')
    sku_info = f" [{sku}]" if sku else ""

    # 格式化输出
    formatted = f"❓ {title}{sku_info}\n"
    formatted += f"💡 {content}\n"
    formatted += f"📅 {date_str} | {source_group}"

    return formatted


def format_search_results(results: List[Dict[str, Any]], search_type: str, query: str) -> str:
    """
    格式化搜索结果列表

    Args:
        results: 搜索结果列表
        search_type: 搜索类型（'sku' 或 'keyword'）
        query: 原始查询字符串

    Returns:
        格式化后的搜索结果文本

    Example:
        >>> results = [{'title': '问题1', 'content': '答案1', ...}]
        >>> print(format_search_results(results, 'keyword', '加热'))
        🔍 搜索结果 (关键词搜索: "加热")
        找到 1 条相关知识

        --- 结果 1 ---
        ❓ 问题1
        💡 答案1
        ...
    """
    if not results:
        return format_no_results(search_type, query)

    # 搜索类型显示
    type_display = {
        'sku': 'SKU 精确搜索',
        'keyword': '关键词搜索',
        'fuzzy': '模糊搜索'
    }.get(search_type, '搜索')

    # 标题
    output = f"🔍 搜索结果 ({type_display}: \"{query}\")\n"
    output += f"找到 {len(results)} 条相关知识\n\n"

    # 格式化每个结果
    for i, entry in enumerate(results, 1):
        output += f"--- 结果 {i} ---\n"
        output += format_knowledge_entry(entry)
        output += "\n\n"

    # 添加提示信息
    if len(results) >= 10:
        output += "💡 提示：结果已达上限(10条)，如需更精确的结果，请尝试更具体的关键词"

    return output.strip()


def format_no_results(search_type: str, query: str) -> str:
    """
    格式化无搜索结果消息

    Args:
        search_type: 搜索类型
        query: 查询字符串

    Returns:
        友好的无结果提示消息
    """
    output = f"😔 未找到相关知识\n\n"
    output += f"查询内容: \"{query}\"\n"
    output += f"搜索类型: {search_type}\n\n"
    output += "💡 建议：\n"
    output += "• 尝试使用不同的关键词\n"
    output += "• 检查 SKU 编号是否正确\n"
    output += "• 使用 /help 查看帮助信息"

    return output


def format_help_message() -> str:
    """
    返回帮助信息

    Returns:
        帮助消息文本

    Example:
        >>> print(format_help_message())
        📖 产品知识库机器人 - 使用帮助
        ...
    """
    help_text = """📖 产品知识库机器人 - 使用帮助

🔍 支持的命令：

1️⃣ /search <关键词>
   搜索产品相关问题和解决方案
   示例：/search 加热杯不加热

2️⃣ /sku <SKU编号>
   查询指定 SKU 的相关知识
   示例：/sku CBC004-1234

3️⃣ /help
   显示此帮助信息

💡 快捷搜索：
直接发送消息即可搜索，无需输入命令
• 如果包含 SKU 编号，会自动识别并精确搜索
• 否则将进行关键词搜索

📝 示例：
• "CBC004-1234 不加热" → 自动识别为 SKU 搜索
• "加热杯漏水怎么办" → 关键词搜索

❓ 问题反馈：
如有任何问题或建议，请联系技术支持团队"""

    return help_text


def format_error_message(error_type: str = "general", details: str = "") -> str:
    """
    格式化错误消息

    Args:
        error_type: 错误类型（'general', 'database', 'permission'）
        details: 错误详情

    Returns:
        格式化后的错误消息
    """
    error_messages = {
        'general': '❌ 处理消息时出现错误',
        'database': '❌ 数据库连接错误',
        'permission': '❌ 权限不足',
        'invalid_command': '❌ 无效的命令格式'
    }

    base_message = error_messages.get(error_type, error_messages['general'])
    output = f"{base_message}\n"

    if details:
        output += f"\n详情：{details}\n"

    output += "\n请稍后重试，或使用 /help 查看帮助信息"

    return output


if __name__ == "__main__":
    # 测试格式化函数
    print("=== 测试知识条目格式化 ===")
    test_entry = {
        'id': '123',
        'sku': 'CBC004-1234',
        'title': '加热杯不加热了怎么办？',
        'content': '检查底座接触是否良好，清洁触点',
        'source_group': 'CBC004群',
        'created_at': '2026-04-15T10:30:00+00:00'
    }
    print(format_knowledge_entry(test_entry))
    print()

    print("=== 测试搜索结果格式化 ===")
    test_results = [test_entry]
    print(format_search_results(test_results, 'keyword', '加热'))
    print()

    print("=== 测试空结果格式化 ===")
    print(format_search_results([], 'sku', 'CBC999-9999'))
    print()

    print("=== 测试帮助消息 ===")
    print(format_help_message())
    print()

    print("=== 测试错误消息 ===")
    print(format_error_message('database', '连接超时'))
