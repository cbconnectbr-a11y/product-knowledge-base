#!/usr/bin/env python3
"""
批量清洗数据库中的 content 字段

清洗 knowledge_entries 表中所有记录的 content,移除系统元数据
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_supabase_client
from scripts.clean_content import clean_customer_service_content


def main(auto_confirm=False):
    print("=" * 70)
    print("批量清洗 knowledge_entries.content 字段")
    print("=" * 70)

    client = get_supabase_client()

    # 获取总记录数
    response = client.table('knowledge_entries').select('id', count='exact').execute()
    total = response.count if response.count else 0
    print(f"\n总记录数: {total:,}")

    # 确认
    print(f"\n⚠️  将清洗所有 {total:,} 条记录的 content 字段")
    print("   - 移除系统 JSON 消息")
    print("   - 转换图片 URL 为 [图片]")
    print("   - 保留正常对话和元数据")
    print()

    if not auto_confirm:
        confirm = input("确认继续? 输入 'YES' 继续: ")
        if confirm != 'YES':
            print("已取消")
            return
    else:
        print("自动确认模式: 开始清洗...")

    # 分批处理
    print("\n开始清洗...")
    batch_size = 100
    offset = 0
    updated = 0
    errors = 0
    total_saved = 0  # 总共节省的字符数

    while offset < total:
        # 读取一批记录
        response = client.table('knowledge_entries') \
            .select('id, content') \
            .range(offset, offset + batch_size - 1) \
            .execute()

        records = response.data
        if not records:
            break

        # 逐条清洗并更新
        for record in records:
            try:
                original_content = record['content']
                cleaned_content = clean_customer_service_content(original_content)

                # 更新数据库
                client.table('knowledge_entries').update({
                    'content': cleaned_content
                }).eq('id', record['id']).execute()

                updated += 1
                saved = len(original_content) - len(cleaned_content)
                total_saved += saved

                # 每 100 条显示进度
                if updated % 100 == 0:
                    progress = updated / total * 100
                    avg_compression = total_saved / updated
                    print(f"  进度: {updated}/{total} ({progress:.1f}%) | "
                          f"平均压缩: {avg_compression:.0f} 字符/条")

            except Exception as e:
                errors += 1
                print(f"  ❌ 错误 (ID: {record['id']}): {e}")
                if errors >= 10:
                    print("  错误过多,终止")
                    return

        offset += batch_size

    # 总结
    print("\n" + "=" * 70)
    print("清洗完成")
    print("=" * 70)
    print(f"成功: {updated:,} 条")
    print(f"失败: {errors} 条")
    print(f"总节省: {total_saved:,} 字符 ({total_saved/1024/1024:.2f} MB)")
    print(f"平均压缩: {total_saved/updated if updated > 0 else 0:.0f} 字符/条")
    print("=" * 70)


if __name__ == '__main__':
    import sys
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    main(auto_confirm=auto_confirm)
