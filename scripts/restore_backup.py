#!/usr/bin/env python3
"""
从备份文件恢复 knowledge_entries 表

用法: python3 scripts/restore_backup.py <backup_file.json>
示例: python3 scripts/restore_backup.py backups/knowledge_entries_backup_2026-05-05_before_cleanup.json
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_supabase_client

def restore_backup(backup_file: Path):
    """从备份文件恢复数据"""

    print("=" * 70)
    print("从备份恢复 knowledge_entries 表")
    print("=" * 70)

    # 读取备份
    print(f"\n读取备份文件: {backup_file}")
    with open(backup_file, 'r', encoding='utf-8') as f:
        backup_data = json.load(f)

    records = backup_data['records']
    total = len(records)

    print(f"✅ 读取成功")
    print(f"   备份时间: {backup_data['backup_time']}")
    print(f"   总记录数: {total}")
    print(f"   备份原因: {backup_data['backup_reason']}")

    # 确认
    print(f"\n⚠️  警告: 此操作将插入 {total} 条记录到数据库")
    print(f"         如果表中已有数据，可能导致重复或冲突")
    print(f"         建议先清空表或使用唯一约束防止重复")
    print()

    response = input("确认恢复？(输入 'YES' 继续): ")
    if response != 'YES':
        print("已取消")
        return

    # 连接数据库
    print(f"\n连接数据库...")
    client = get_supabase_client()

    # 批量插入
    batch_size = 100
    imported = 0
    errors = 0

    print(f"\n开始恢复...")
    print(f"批量大小: {batch_size}")

    for i in range(0, total, batch_size):
        batch = records[i:i+batch_size]

        try:
            response = client.table('knowledge_entries').insert(batch).execute()
            imported += len(batch)

            if (i + batch_size) % 1000 == 0:
                print(f"  已恢复: {imported}/{total} ({imported/total*100:.1f}%)")

        except Exception as e:
            errors += 1
            print(f"  ❌ 批次 {i//batch_size + 1} 失败: {e}")

            if errors >= 10:
                print(f"\n错误过多，终止恢复")
                break

    # 总结
    print(f"\n" + "=" * 70)
    print(f"恢复完成")
    print(f"=" * 70)
    print(f"成功: {imported} 条")
    print(f"失败: {total - imported} 条")
    print(f"=" * 70)

def main():
    if len(sys.argv) != 2:
        print("用法: python3 scripts/restore_backup.py <backup_file.json>")
        print("示例: python3 scripts/restore_backup.py backups/knowledge_entries_backup_2026-05-05_before_cleanup.json")
        sys.exit(1)

    backup_file = Path(sys.argv[1])

    if not backup_file.exists():
        print(f"❌ 备份文件不存在: {backup_file}")
        sys.exit(1)

    restore_backup(backup_file)

if __name__ == '__main__':
    main()
