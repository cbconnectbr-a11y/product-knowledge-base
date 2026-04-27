"""
飞书机器人消息处理模块
"""
import logging
from typing import Tuple, Optional
from datetime import datetime
from bot.search import smart_search
from bot.formatters import (
    format_search_results,
    format_help_message,
    format_error_message
)
from scripts.utils import get_supabase_client

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_command(text: str) -> Tuple[str, str]:
    """
    解析用户输入，识别命令

    支持的命令：
    - /search <关键词>: 关键词搜索
    - /sku <SKU>: SKU 精确搜索
    - /help: 帮助信息

    Args:
        text: 用户输入的文本

    Returns:
        (command, argument) 元组
        - command: 命令类型 ('search', 'sku', 'help', 'unknown')
        - argument: 命令参数（可能为空字符串）

    Examples:
        >>> parse_command("/search 加热杯")
        ('search', '加热杯')
        >>> parse_command("/sku CBC004-1234")
        ('sku', 'CBC004-1234')
        >>> parse_command("/help")
        ('help', '')
        >>> parse_command("加热杯不加热")
        ('search', '加热杯不加热')
    """
    if not text or not text.strip():
        return ('unknown', '')

    text = text.strip()

    # 检查是否以命令开头
    if text.startswith('/'):
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        argument = parts[1] if len(parts) > 1 else ''

        # 映射命令
        command_map = {
            '/search': 'search',
            '/sku': 'sku',
            '/help': 'help'
        }

        if command in command_map:
            return (command_map[command], argument.strip())
        else:
            # 未知命令
            return ('unknown', text)
    else:
        # 没有命令前缀，默认为搜索
        return ('search', text)


def handle_message(message_text: str, user_id: Optional[str] = None) -> str:
    """
    主处理函数，协调命令解析和搜索

    Args:
        message_text: 用户消息文本
        user_id: 飞书用户 ID（可选，用于记录日志）

    Returns:
        格式化后的回复消息

    Raises:
        Exception: 当处理失败时抛出异常
    """
    try:
        # 解析命令
        command, argument = parse_command(message_text)
        logger.info(f"Parsed command: {command}, argument: {argument}, user: {user_id}")

        # 处理命令
        if command == 'help':
            return format_help_message()

        elif command == 'unknown':
            return format_error_message('invalid_command', f'未知命令: {argument}')

        elif command in ['search', 'sku']:
            # 检查参数
            if not argument:
                return format_error_message(
                    'invalid_command',
                    f'命令 /{command} 需要提供参数\n使用 /help 查看帮助'
                )

            # 执行搜索
            search_result = smart_search(argument)
            results = search_result.get('results', [])
            search_type = search_result.get('search_type', 'keyword')
            query = search_result.get('query', argument)

            # 记录搜索日志
            log_search(
                user_id=user_id,
                query=query,
                search_type=search_type,
                result_count=len(results)
            )

            # 格式化并返回结果
            return format_search_results(results, search_type, query)

        else:
            # 理论上不会到达这里
            return format_error_message('general', '未知的命令类型')

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        return format_error_message('general', str(e))


def log_search(
    user_id: Optional[str],
    query: str,
    search_type: str,
    result_count: int
) -> None:
    """
    记录搜索日志到 Supabase search_logs 表

    Args:
        user_id: 用户 ID（飞书 user_id，可能为 None）
        query: 搜索查询文本
        search_type: 搜索类型 ('sku', 'keyword', 'fuzzy')
        result_count: 结果数量

    Note:
        - Phase 1 中，user_id 是飞书 user_id（字符串），而非 users 表的 UUID
        - 为了兼容 schema，我们将 user_id 存储为 NULL（Phase 2+ 可以改进）
        - 或者可以创建一个临时的 user 记录
    """
    try:
        client = get_supabase_client()

        # Phase 1: 由于 user_id 是飞书 ID (字符串)，而数据库要求 UUID
        # 我们暂时将 user_id 设为 NULL，或者可以查找/创建对应的 user
        # 这里选择记录为 NULL，Phase 2 再改进用户关联

        log_data = {
            'user_id': None,  # Phase 1 暂时为 NULL
            'query': query,
            'search_type': search_type,
            'result_count': result_count,
            'created_at': datetime.now().isoformat()
        }

        # 插入日志
        response = client.table('search_logs').insert(log_data).execute()

        logger.info(
            f"Search logged: query='{query}', type={search_type}, "
            f"results={result_count}, feishu_user={user_id}"
        )

    except Exception as e:
        # 记录日志失败不应该影响主流程
        logger.error(f"Failed to log search: {e}", exc_info=True)


if __name__ == "__main__":
    # 测试处理函数
    import sys

    print("=== 产品知识库机器人 - 消息处理测试 ===\n")

    # 测试用例
    test_cases = [
        "/help",
        "/search 加热杯",
        "/sku CBC004-1234",
        "加热杯不加热怎么办",
        "/unknown 测试",
        "/search",  # 缺少参数
    ]

    for test_input in test_cases:
        print(f"输入: {test_input}")
        print("-" * 60)

        try:
            response = handle_message(test_input, user_id="test_user_123")
            print(response)
        except Exception as e:
            print(f"错误: {e}")

        print("\n" + "=" * 60 + "\n")
