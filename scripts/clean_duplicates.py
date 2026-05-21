#!/usr/bin/env python3
"""
清理重复记录

策略: 对于每组 (source_group, title) 重复记录
     保留 created_at 最早的一条，删除其余的
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_supabase_client

def main():
    print("=" * 70)
    print("清理 knowledge_entries 表中的重复记录")
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

    print(f"\n发现 {len(duplicates)} 组重复记录")

    # 收集要删除的 ID
    ids_to_delete = []

    for (source_group, title), records in duplicates.items():
        # 按 created_at 排序，保留最早的，删除其余的
        sorted_records = sorted(records, key=lambda x: x['created_at'])
        keep = sorted_records[0]
        to_delete = sorted_records[1:]

        print(f"\n组: {title[:60]}...")
        print(f"  保留: {keep['id']} (created_at: {keep['created_at']})")
        for record in to_delete:
            print(f"  删除: {record['id']} (created_at: {record['created_at']})")
            ids_to_delete.append(record['id'])

    print(f"\n" + "=" * 70)
    print(f"将删除 {len(ids_to_delete)} 条重复记录")
    print(f"删除后剩余: {total - len(ids_to_delete)} 条")
    print("=" * 70)

    # 确认
    print("\n⚠️  确认删除这些重复记录？")
    response = input("输入 'YES' 继续: ")
    if response != 'YES':
        print("已取消")
        return

    # 逐个删除
    print("\n开始删除...")
    deleted = 0
    failed = 0

    for record_id in ids_to_delete:
        try:
            client.table('knowledge_entries').delete().eq('id', record_id).execute()
            deleted += 1
            print(f"  ✅ 已删除: {record_id}")
        except Exception as e:
            failed += 1
            print(f"  ❌ 删除失败: {record_id} - {e}")

    # 总结
    print("\n" + "=" * 70)
    print("清理完成")
    print("=" * 70)
    print(f"成功删除: {deleted} 条")
    print(f"失败: {failed} 条")
    print("=" * 70)

    # 验证
    print("\n验证清理结果...")
    response = client.table('knowledge_entries').select('id', count='exact').execute()
    new_total = response.count if response.count else 0
    print(f"当前总记录数: {new_total}")
    print(f"期望记录数: {total - len(ids_to_delete)}")

    if new_total == total - len(ids_to_delete):
        print("✅ 清理成功！")
    else:
        print(f"❌ 记录数不匹配，差异: {new_total - (total - len(ids_to_delete))}")

if __name__ == '__main__':
    main()
