"""
Bot 集成测试 - 无需数据库连接
测试命令解析、消息格式化等基础功能
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bot.formatters import (
    format_knowledge_entry,
    format_search_results,
    format_help_message,
    format_error_message
)
from bot.handlers import parse_command


def test_parse_command():
    """测试命令解析"""
    print("=== 测试命令解析 ===")

    test_cases = [
        ("/help", ("help", "")),
        ("/search 加热杯", ("search", "加热杯")),
        ("/sku CBC004-1234", ("sku", "CBC004-1234")),
        ("加热杯不加热", ("search", "加热杯不加热")),
        ("/unknown test", ("unknown", "/unknown test")),
    ]

    passed = 0
    failed = 0

    for input_text, expected in test_cases:
        result = parse_command(input_text)
        if result == expected:
            print(f"✅ '{input_text}' → {result}")
            passed += 1
        else:
            print(f"❌ '{input_text}' → {result} (expected {expected})")
            failed += 1

    print(f"\n结果: {passed} passed, {failed} failed\n")
    return failed == 0


def test_formatters():
    """测试消息格式化"""
    print("=== 测试消息格式化 ===")

    # 测试知识条目格式化
    entry = {
        'title': '加热杯不加热',
        'content': '检查底座接触',
        'source_group': 'CBC004群',
        'created_at': '2026-04-15T10:30:00+00:00',
        'sku': 'CBC004-1234'
    }

    result = format_knowledge_entry(entry)
    assert '❓' in result
    assert '💡' in result
    assert '📅' in result
    assert 'CBC004-1234' in result
    print("✅ format_knowledge_entry() 通过")

    # 测试搜索结果格式化
    results = [entry]
    formatted = format_search_results(results, 'keyword', '加热')
    assert '找到 1 条相关知识' in formatted
    assert '🔍' in formatted
    print("✅ format_search_results() 通过")

    # 测试空结果
    empty_result = format_search_results([], 'sku', 'CBC999-9999')
    assert '未找到相关知识' in empty_result
    print("✅ format_search_results() 空结果通过")

    # 测试帮助消息
    help_msg = format_help_message()
    assert '/search' in help_msg
    assert '/sku' in help_msg
    assert '/help' in help_msg
    print("✅ format_help_message() 通过")

    # 测试错误消息
    error_msg = format_error_message('general', '测试错误')
    assert '❌' in error_msg
    assert '测试错误' in error_msg
    print("✅ format_error_message() 通过")

    print("\n✅ 所有格式化测试通过\n")
    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Bot 集成测试")
    print("=" * 60 + "\n")

    tests = [
        ("命令解析", test_parse_command),
        ("消息格式化", test_formatters),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} 测试失败: {e}")
            results.append((name, False))

    # 总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(r for _, r in results)

    if all_passed:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
