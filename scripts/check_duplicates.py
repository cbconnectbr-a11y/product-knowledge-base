#!/usr/bin/env python3
"""
检查当前表中的重复记录

显示所有 (source_group, title) 重复的记录
"""

import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_supabase_client

def main():
    print("=" * 70)
    print("检查 knowledge_entries 表中的重复记录")
    print("=" * 70)

    client = get_supabase_client()

    # 获取总记录数
    response = client.table('knowledge_entries').select('id', count='exact').execute()
    total = response.count if response.count else 0
    print(f"\n当前总记录数: {total}")

    # 读取所有记录
    print("\n读取所有记录...")
    all_records = []
    batch_size = 1000
    offset = 0

    while offset < total:
        response = client.table('knowledge_entries') \
            .select('id, source_group, title, created_at') \
            .range(offset, offset + batch_size - 1) \
            .execute()
        all_records.extend(response.data)
        offset += batch_size

    print(f"✅ 已读取 {len(all_records)} 条记录")

    # 检查重复
    print("\n分析重复记录...")
    key_to_records = {}

    for record in all_records:
        key = (record['source_group'], record['title'])
        if key not in key_to_records:
            key_to_records[key] = []
        key_to_records[key].append(record)

    # 找出重复的
    duplicates = {k: v for k, v in key_to_records.items() if len(v) > 1}

    if not duplicates:
        print("✅ 没有发现重复记录")
        return

    print(f"\n❌ 发现 {len(duplicates)} 组重复记录\n")

    # 显示每组重复
    total_duplicate_count = 0
    for i, ((source_group, title), records) in enumerate(sorted(duplicates.items(), key=lambda x: -len(x[1])), 1):
        count = len(records)
        total_duplicate_count += count - 1  # 每组保留1条，删除 count-1 条

        print(f"{i}. source_group: {source_group}")
        print(f"   title: {title}")
        print(f"   重复次数: {count} 条")
        print(f"   记录 ID:")
        for record in sorted(records, key=lambda x: x['created_at']):
            print(f"   - {record['id']} (created_at: {record['created_at']})")
        print()

    # 总结
    print("=" * 70)
    print("重复记录总结")
    print("=" * 70)
    print(f"重复组数: {len(duplicates)}")
    print(f"需要删除的记录数: {total_duplicate_count} 条")
    print(f"删除后剩余: {total - total_duplicate_count} 条")
    print("=" * 70)

    # 按 source_group 统计
    print("\n按 source_group 统计重复:")
    duplicate_by_group = Counter([sg for (sg, _), records in duplicates.items()])
    for group, count in sorted(duplicate_by_group.items(), key=lambda x: -x[1]):
        print(f"  - {group}: {count} 组重复")

if __name__ == '__main__':
    main()
