#!/usr/bin/env python3
"""
测试 sync_feishu_qa 功能
"""
import sys
from pathlib import Path

# 添加scripts目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import extract_sku, is_tech_question, extract_keywords


def test_extract_sku():
    """测试 SKU 提取功能"""
    print("=" * 60)
    print("测试 SKU 提取")
    print("=" * 60)

    test_cases = [
        ("客户反馈 CBC004-1234 加热杯漏水", "CBC004-1234"),
        ("BRME0341 产品描述", "BRME0341"),
        ("K004-123 故障报告", "K004-123"),
        ("YMX018 和 SUB154 对比", "YMX018"),  # 提取第一个
        ("没有SKU的文本", None),
    ]

    passed = 0
    failed = 0

    for text, expected in test_cases:
        result = extract_sku(text)
        status = "✅" if result == expected else "❌"
        print(f"{status} 输入: {text[:40]}")
        print(f"   期望: {expected}, 实际: {result}")

        if result == expected:
            passed += 1
        else:
            failed += 1

    print(f"\n通过: {passed}/{len(test_cases)}")
    return failed == 0


def test_is_tech_question():
    """测试技术问题识别"""
    print("\n" + "=" * 60)
    print("测试技术问题识别")
    print("=" * 60)

    test_cases = [
        # 正例
        ("客户反馈加热杯漏水，无法正常使用", True),
        ("CBC004-1234 故障问题如何解决？", True),
        ("产品损坏，客户投诉", True),
        ("不能加热，什么原因？", True),
        # 反例
        ("货柜入仓时间确认", False),
        ("配货异常需要处理", False),
        ("要求发100件，实际发了90件", False),
        ("正常的产品咨询", False),  # 不包含技术关键词
    ]

    passed = 0
    failed = 0

    for text, expected in test_cases:
        result = is_tech_question(text)
        status = "✅" if result == expected else "❌"
        print(f"{status} 输入: {text}")
        print(f"   期望: {expected}, 实际: {result}")

        if result == expected:
            passed += 1
        else:
            failed += 1

    print(f"\n通过: {passed}/{len(test_cases)}")
    return failed == 0


def test_extract_keywords():
    """测试关键词提取"""
    print("\n" + "=" * 60)
    print("测试关键词提取")
    print("=" * 60)

    test_cases = [
        "客户反馈加热杯漏水，无法正常使用",
        "CBC004-1234 产品故障，需要维修处理",
        "空文本测试",
    ]

    all_passed = True

    for text in test_cases:
        keywords = extract_keywords(text, max_keywords=5)
        print(f"输入: {text}")
        print(f"关键词: {keywords}")
        print(f"数量: {len(keywords)}")

        # 基本验证：应该返回列表，长度不超过5
        if not isinstance(keywords, list):
            print("❌ 返回类型错误，应为列表")
            all_passed = False
        elif len(keywords) > 5:
            print("❌ 关键词数量超过最大值")
            all_passed = False
        else:
            print("✅ 通过")

        print()

    return all_passed


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("飞书群问答同步功能测试")
    print("=" * 60)
    print()

    results = {
        "SKU提取": test_extract_sku(),
        "技术问题识别": test_is_tech_question(),
        "关键词提取": test_extract_keywords(),
    }

    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {test_name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("✅ 所有测试通过！")
        return 0
    else:
        print("❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
