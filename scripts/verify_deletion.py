#!/usr/bin/env python3
"""
第 4 步：验证 DELETE 结果

在 Supabase SQL Editor 执行 DELETE 后，运行此脚本验证结果

期望结果：
① 总记录数: 103 条
② 只剩 3 个历史数据导入 source_group
③ 没有任何 多客 残留
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_supabase_client

def main():
    print("=" * 70)
    print("第 4 步：验证 DELETE 结果")
    print("=" * 70)

    client = get_supabase_client()

    # ① 验证总记录数
    print("\n① 验证总记录数...")
    response = client.table('knowledge_entries').select('id', count='exact').execute()
    total = response.count if response.count else 0

    print(f"   当前总数: {total}")
    print(f"   期望总数: 103")

    if total == 103:
        print("   ✅ 总数正确")
    else:
        print(f"   ❌ 总数不匹配! 差异: {total - 103}")

    # ② 验证剩余 source_group
    print("\n② 验证剩余 source_group 分布...")

    all_records = []
    batch_size = 1000
    offset = 0

    while offset < total:
        response = client.table('knowledge_entries') \
            .select('source_group') \
            .range(offset, offset + batch_size - 1) \
            .execute()
        all_records.extend(response.data)
        offset += batch_size

    from collections import Counter
    distribution = Counter([r['source_group'] for r in all_records])

    print(f"\n   source_group 分布:")
    for group, count in sorted(distribution.items(), key=lambda x: -x[1]):
        print(f"   - {group}: {count} 条")

    expected_groups = 3
    if len(distribution) == expected_groups:
        print(f"\n   ✅ source_group 数量正确 ({expected_groups} 个)")
    else:
        print(f"\n   ❌ source_group 数量不匹配! 期望 {expected_groups} 个，实际 {len(distribution)} 个")

    # 检查是否都是历史数据导入
    non_historical = [g for g in distribution.keys() if not g.startswith('历史数据导入')]
    if non_historical:
        print(f"   ❌ 发现非历史数据导入的 group: {non_historical}")
    else:
        print("   ✅ 所有 group 都是历史数据导入")

    # ③ 验证没有多客残留
    print("\n③ 验证没有多客客服残留...")
    response = client.table('knowledge_entries') \
        .select('id', count='exact') \
        .like('source_group', '%多客%') \
        .execute()

    duoke_count = response.count if response.count else 0

    print(f"   多客客服残留: {duoke_count} 条")
    print(f"   期望残留: 0 条")

    if duoke_count == 0:
        print("   ✅ 没有多客客服残留")
    else:
        print(f"   ❌ 发现 {duoke_count} 条多客客服残留!")

        # 显示残留记录
        response = client.table('knowledge_entries') \
            .select('source_group') \
            .like('source_group', '%多客%') \
            .execute()

        print("\n   残留的 source_group:")
        residual = Counter([r['source_group'] for r in response.data])
        for group, count in residual.items():
            print(f"   - {group}: {count} 条")

    # 总结
    print("\n" + "=" * 70)
    print("验证总结")
    print("=" * 70)

    all_pass = (total == 103 and len(distribution) == expected_groups and duoke_count == 0)

    if all_pass:
        print("✅ 所有验证通过！可以继续第 5 步：添加唯一约束")
    else:
        print("❌ 验证未通过，请检查上面的详细信息")
        print("\n如需恢复备份:")
        print("python3 scripts/restore_backup.py backups/knowledge_entries_backup_2026-05-05_before_cleanup.json")

    print("=" * 70)

if __name__ == '__main__':
    main()
