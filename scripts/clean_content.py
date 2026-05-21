#!/usr/bin/env python3
"""
清洗客服对话内容 - 移除系统元数据和无用信息

用途:
1. 清洗现有数据库中的 content 字段
2. 在导入脚本中调用,清洗新数据
"""

import re


def clean_customer_service_content(content: str) -> str:
    """
    清洗客服对话内容,移除系统元数据

    清洗规则:
    1. 保留: 买家/平台/客户意图/关键问题等元数据
    2. 保留: 正常对话 ([时间] 客服/买家: 消息内容)
    3. 移除: JSON 系统消息 (退货通知/评价提醒等)
    4. 转换: 图片 URL 为 [图片]
    5. 移除: 连续空行

    Args:
        content: 原始对话内容

    Returns:
        清洗后的内容

    Example:
        >>> original = "[18:13] 客服: {'unknownData': '{\"message\":...}'"
        >>> clean_customer_service_content(original)
        ""  # 系统消息被移除

        >>> original = "[02:01] 客户: {'imageUrl': 'https://...'}"
        >>> clean_customer_service_content(original)
        "[02:01] 客户: [图片]"
    """
    if not content or not content.strip():
        return ''

    lines = content.split('\n')
    cleaned_lines = []

    for line in lines:
        # 1. 保留元数据字段
        if line.startswith(('买家:', '平台:', '客户意图:', '关键问题:', '##')):
            cleaned_lines.append(line)
            continue

        # 2. 处理时间戳开头的对话
        if re.match(r'\[\d{2}:\d{2}\]', line):
            # 提取时间戳和角色
            match = re.match(r'(\[\d{2}:\d{2}\]\s*(?:客服|买家|客户):)\s*(.*)$', line)
            if not match:
                cleaned_lines.append(line)
                continue

            prefix = match.group(1)  # [时间] 角色:
            content = match.group(2)  # 消息内容

            # 检查是否是图片 URL
            if "{'imageUrl':" in content or '{"imageUrl":' in content:
                cleaned_lines.append(f"{prefix} [图片]")
                continue

            # 检查是否是商品分享 JSON
            if "{'itemId':" in content or '{"itemId":' in content:
                cleaned_lines.append(f"{prefix} [商品链接]")
                continue

            # 检查是否是系统消息 JSON (完整的 JSON 结构)
            json_system_indicators = [
                "{'unknownData':",
                '{"shop_id":',
                '{"message":',
                '\\"user_id\\"',
                '\\"language\\"',
                '\\"translated_with_lang\\"',
                '{"unrated_order_reminder"',
                '{"rated_order_reminder"',
                '{"messageType":',
                "{'messageType':"
            ]

            if any(indicator in content for indicator in json_system_indicators):
                # 系统消息,完全跳过
                continue

            # 正常对话,保留
            cleaned_lines.append(line)
            continue

        # 3. 保留空行 (但避免连续空行)
        if not line.strip():
            if cleaned_lines and cleaned_lines[-1].strip():
                cleaned_lines.append('')
            continue

        # 4. 其他非 JSON 的内容行也保留
        # 判断是否是 JSON 行 (包含大量转义字符和特殊结构)
        if '{' in line and '\\' in line and '"' in line:
            # 可能是 JSON,跳过
            continue

        # 保留普通文本行
        cleaned_lines.append(line)

    # 去除首尾空行
    result = '\n'.join(cleaned_lines).strip()

    # 压缩连续空行为单个空行
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result


if __name__ == '__main__':
    # 测试
    test_cases = [
        # 测试1: 正常对话
        "[19:25] 客服: Olá bom dia, temos somente o botão.",

        # 测试2: 图片 URL
        "[02:01] 客户: {'imageUrl': 'https://img.sp.mms.shopee.sg/br-11134231-820lg-mnhhxu09il1eab'}",

        # 测试3: 系统消息
        "[18:13] 客服: {'unknownData': '{\"message\":\"{\\\"user_id\\\":1550309778}'}",

        # 测试4: 元数据
        "买家: f6g8h8rh2f",
        "客户意图: 咨询退货",
    ]

    print("清洗规则测试:")
    print("=" * 60)
    for i, test in enumerate(test_cases, 1):
        result = clean_customer_service_content(test)
        print(f"\n测试 {i}:")
        print(f"原始: {test[:80]}")
        print(f"结果: {result if result else '(已移除)'}")
    print("\n" + "=" * 60)
