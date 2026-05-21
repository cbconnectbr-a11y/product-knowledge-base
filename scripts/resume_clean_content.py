#!/usr/bin/env python3
"""
恢复清洗 - 只处理仍包含 JSON 的记录

改进:
1. 只处理未清洗的记录
2. 更小的批次 (50 条)
3. 添加重试逻辑
4. 错误后不中断
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_supabase_client
from scripts.clean_content import clean_customer_service_content


def needs_cleaning(content: str) -> bool:
    """检查记录是否需要清洗"""
    indicators = [
        'unknownData',
        '{\"imageUrl\"',
        "{'imageUrl'",
        '\\"user_id\\"',
        '\\"language\\"',
    ]
    return any(ind in content for ind in indicators)


def main():
    print("=" * 70)
    print("恢复清洗 - 只处理未清洗记录")
    print("=" * 70)

    client = get_supabase_client()

    # 获取总记录数
    total = client.table('knowledge_entries').select('id', count='exact').execute().count
    print(f"\n数据库总记录: {total:,}")

    # 估算需要清洗的记录数 (先抽样)
    print("\n抽样估算需清洗记录数...")
    sample_size = 1000
    samples = client.table('knowledge_entries').select('content').limit(sample_size).execute().data
    needs_clean_sample = sum(1 for s in samples if needs_cleaning(s['content']))
    estimated_to_clean = int((needs_clean_sample / sample_size) * total)

    print(f"抽样 {sample_size} 条: {needs_clean_sample} 条需清洗")
    print(f"估算需清洗: ~{estimated_to_clean:,} 条")

    print("\n开始处理...")

    batch_size = 50  # 减小批次以避免超时
    offset = 0
    processed = 0
    cleaned = 0
    skipped = 0
    errors = 0
    total_saved = 0

    while offset < total:
        try:
            # 读取一批记录
            response = client.table('knowledge_entries') \
                .select('id, content') \
                .range(offset, offset + batch_size - 1) \
                .execute()

            records = response.data
            if not records:
                break

            # 处理这批记录
            for record in records:
                processed += 1
                original_content = record['content']

                # 检查是否需要清洗
                if not needs_cleaning(original_content):
                    skipped += 1
                    continue

                # 清洗
                cleaned_content = clean_customer_service_content(original_content)

                # 更新 (带重试)
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        client.table('knowledge_entries').update({
                            'content': cleaned_content
                        }).eq('id', record['id']).execute()

                        cleaned += 1
                        saved = len(original_content) - len(cleaned_content)
                        total_saved += saved
                        break  # 成功,跳出重试循环

                    except Exception as e:
                        if attempt < max_retries - 1:
                            time.sleep(1)  # 等待1秒后重试
                            continue
                        else:
                            # 最后一次重试也失败
                            errors += 1
                            print(f"  ❌ 错误 (ID: {record['id'][:8]}...): {str(e)[:60]}")

                # 进度显示 (每 100 条)
                if processed % 100 == 0:
                    progress = processed / total * 100
                    print(f"  进度: {processed}/{total} ({progress:.1f}%) | "
                          f"已清洗: {cleaned} | 跳过: {skipped} | 错误: {errors}")

            offset += batch_size

        except Exception as e:
            print(f"  ❌ 批次错误 (offset {offset}): {e}")
            errors += 1
            offset += batch_size  # 跳过这批,继续下一批
            time.sleep(2)  # 等待后继续

    # 总结
    print("\n" + "=" * 70)
    print("清洗完成")
    print("=" * 70)
    print(f"处理: {processed:,} 条")
    print(f"清洗: {cleaned:,} 条")
    print(f"跳过: {skipped:,} 条 (已清洗)")
    print(f"错误: {errors} 条")
    print(f"节省: {total_saved:,} 字符 ({total_saved/1024/1024:.2f} MB)")
    if cleaned > 0:
        print(f"平均: {total_saved/cleaned:.0f} 字符/条")
    print("=" * 70)


if __name__ == '__main__':
    main()
