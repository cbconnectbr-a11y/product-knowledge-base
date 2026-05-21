#!/usr/bin/env python3
"""
最小化单文件导入脚本 - 用于诊断
不走队列、不异步、同步运行、详细日志

用法: python3 scripts/import_one.py <excel_file>
示例: python3 scripts/import_one.py data/duoke/汇总_20260312_0600.xlsx
"""

import sys
import pandas as pd
import logging
import hashlib
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_supabase_client, extract_sku

# 配置日志 - 详细输出
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def record_import_start(client, filename: str):
    """记录导入开始"""
    try:
        client.table('import_log').insert({
            'filename': filename,
            'started_at': datetime.now().isoformat(),
            'status': 'running'
        }).execute()
        logger.info(f"✅ 已记录导入开始: {filename}")
    except Exception as e:
        logger.warning(f"⚠️  记录导入开始失败: {e}")

def record_import_complete(client, filename: str, stats: dict):
    """记录导入成功"""
    try:
        client.table('import_log').update({
            'status': 'completed',
            'completed_at': datetime.now().isoformat(),
            'total_rows': stats.get('total_rows', 0),
            'imported_rows': stats.get('imported', 0),
            'skipped_rows': stats.get('skipped', 0),
            'error_rows': stats.get('errors', 0),
            'error_msg': None  # 清除之前的错误信息
        }).eq('filename', filename).execute()  # 去掉 .eq('status', 'running')
        logger.info(f"✅ 已记录导入完成: {filename}")
    except Exception as e:
        logger.warning(f"⚠️  记录导入完成失败: {e}")

def record_import_failed(client, filename: str, error_msg: str, stats: dict = None):
    """记录导入失败"""
    try:
        update_data = {
            'status': 'failed',
            'completed_at': datetime.now().isoformat(),
            'error_msg': error_msg[:500]  # 限制错误信息长度
        }

        # 即使失败，也记录已经处理了多少
        if stats:
            update_data.update({
                'total_rows': stats.get('total_rows', 0),
                'imported_rows': stats.get('imported', 0),
                'skipped_rows': stats.get('skipped', 0),
                'error_rows': stats.get('errors', 0)
            })

        client.table('import_log').update(update_data) \
            .eq('filename', filename).eq('status', 'running').execute()
        logger.info(f"✅ 已记录导入失败: {filename}")
    except Exception as e:
        logger.warning(f"⚠️  记录导入失败失败: {e}")

def diagnose_file(file_path: Path):
    """诊断文件基本信息"""
    logger.info(f"=" * 70)
    logger.info(f"诊断文件: {file_path.name}")
    logger.info(f"=" * 70)

    # 文件大小
    file_size_mb = file_path.stat().st_size / 1024 / 1024
    logger.info(f"文件大小: {file_size_mb:.2f} MB")

    # 读取 Excel
    logger.info(f"开始读取 Excel...")
    try:
        df = pd.read_excel(file_path, header=2)
        logger.info(f"✅ Excel 读取成功")
        logger.info(f"总行数: {len(df)} 行")
        logger.info(f"总列数: {len(df.columns)} 列")

        # 列名
        logger.info(f"\n列名列表:")
        for i, col in enumerate(df.columns, 1):
            logger.info(f"  {i}. {col}")

        # 检查关键列
        required_cols = ['与买家沟通消息', 'productSku', 'variationSku']
        logger.info(f"\n关键列检查:")
        for col in required_cols:
            exists = col in df.columns
            logger.info(f"  {col}: {'✅ 存在' if exists else '❌ 缺失'}")

        return df

    except Exception as e:
        logger.error(f"❌ Excel 读取失败: {e}")
        raise

def import_with_progress(file_path: Path):
    """带进度的导入"""
    logger.info(f"\n{'='*70}")
    logger.info(f"开始导入: {file_path.name}")
    logger.info(f"{'='*70}\n")

    # 获取数据库客户端（提前，用于检查 import_log）
    logger.info(f"连接数据库...")
    try:
        client = get_supabase_client()
        logger.info(f"✅ 数据库连接成功")
    except Exception as e:
        logger.error(f"❌ 数据库连接失败: {e}")
        raise

    # 检查 import_log 避免重复和并发
    logger.info(f"\n检查 import_log 状态...")
    try:
        response = client.table('import_log') \
            .select('status, completed_at') \
            .eq('filename', file_path.name) \
            .order('started_at', desc=True) \
            .limit(1) \
            .execute()

        if response.data:
            last_record = response.data[0]
            status = last_record['status']

            if status == 'completed':
                logger.warning(f"⏭️  文件已导入完成，跳过: {file_path.name}")
                logger.info(f"   完成时间: {last_record.get('completed_at', 'N/A')}")
                return
            elif status == 'running':
                logger.warning(f"⚠️  文件正在被其他进程导入，跳过避免并发: {file_path.name}")
                return
            elif status == 'failed':
                logger.info(f"✅ 上次导入失败，允许重试")
        else:
            logger.info(f"✅ 首次导入此文件")
    except Exception as e:
        logger.warning(f"⚠️  检查 import_log 失败: {e}，继续执行")

    # 诊断文件
    df = diagnose_file(file_path)

    # 提取文件日期 - 修复: 使用正则提取8位日期而不是最后一个下划线分隔符
    import re
    match = re.search(r'(\d{8})', file_path.stem)
    if match:
        file_date = match.group(1)
        logger.info(f"\n文件日期: {file_date} (从文件名提取)")
    else:
        file_date = datetime.now().strftime('%Y%m%d')
        logger.warning(f"\n⚠️  无法从文件名提取日期，使用当前日期: {file_date}")

    # 记录导入开始
    record_import_start(client, file_path.name)

    # 统计
    total_rows = len(df)
    imported = 0
    skipped = 0
    errors = 0

    logger.info(f"\n开始处理 {total_rows} 行数据...")
    logger.info(f"进度报告频率: 每 100 行\n")

    start_time = datetime.now()

    for idx, row in df.iterrows():
        try:
            # Excel 实际行号（仅用于日志，不用于 idempotency_key）
            excel_row = idx + 3

            # 进度报告
            if (idx + 1) % 100 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                speed = (idx + 1) / elapsed * 60
                logger.info(f"📊 进度: {idx+1}/{total_rows} ({(idx+1)/total_rows*100:.1f}%) | "
                          f"速度: {speed:.1f} 条/分钟 | "
                          f"新增: {imported} | 跳过: {skipped} | 错误: {errors}")

            # 跳过空行
            messages = row.get('与买家沟通消息')
            if pd.isna(messages) or not str(messages).strip():
                skipped += 1
                if idx < 10:  # 前10行详细日志
                    logger.debug(f"第 {excel_row} 行: 跳过（空内容）")
                continue

            # 提取 SKU
            product_sku = row.get('productSku', '')
            variation_sku = row.get('variationSku', '')

            all_skus = set()
            for field in [product_sku, variation_sku, str(messages)]:
                sku = extract_sku(str(field))
                if sku:
                    all_skus.add(sku)

            main_sku = list(all_skus)[0] if all_skus else None

            # 提取问题和对话
            intent = row.get('客户意图', '')
            key_issue = row.get('关键问题', '')

            # 构建标题
            title_parts = []
            if main_sku:
                title_parts.append(f"[{main_sku}]")
            if intent and not pd.isna(intent):
                title_parts.append(str(intent)[:100])
            else:
                title_parts.append("客户咨询")
            title = ' '.join(title_parts)

            # 构建内容
            metadata = []
            buyer = row.get('买家昵称', '')
            if buyer and not pd.isna(buyer):
                metadata.append(f"买家: {buyer}")

            platform = row.get('平台', '')
            if platform and not pd.isna(platform):
                metadata.append(f"平台: {platform}")

            if intent and not pd.isna(intent):
                metadata.append(f"客户意图: {intent}")

            if key_issue and not pd.isna(key_issue):
                metadata.append(f"关键问题: {key_issue}")

            content_parts = []
            if metadata:
                content_parts.append('\n'.join(metadata))
            content_parts.append(f"## 对话记录\n{messages}")
            full_content = '\n\n'.join(content_parts)

            # 计算幂等性 key（基于文件名 + 关键字段内容的 hash）
            # 不依赖行号，Excel 加减空行不影响 key 稳定性
            key_fields = ''.join([
                str(messages),
                str(intent) if not pd.isna(intent) else '',
                str(product_sku) if not pd.isna(product_sku) else '',
                str(variation_sku) if not pd.isna(variation_sku) else ''
            ])
            content_hash = hashlib.md5(key_fields.encode('utf-8')).hexdigest()[:16]
            idempotency_key = f"{file_path.name}:{content_hash}"

            # 构建条目
            entry = {
                'sku': main_sku,
                'title': title,
                'content': full_content,
                'source_group': f'多客客服 - {file_date}',
                'source_type': 'customer_service',
                'keywords': list(all_skus)[:5],
                'status': 'approved',
                'idempotency_key': idempotency_key  # 幂等性保证
            }

            # 使用 upsert 原子地插入或跳过（数据库保证并发安全）
            # on_conflict 指定冲突键，ignore_duplicates=True 表示冲突时跳过不更新
            # 返回值：新插入返回数据，冲突跳过返回空列表
            response = client.table('knowledge_entries').upsert(
                entry,
                on_conflict='idempotency_key',
                ignore_duplicates=True
            ).execute()

            if response.data and len(response.data) > 0:
                # 新插入成功
                imported += 1
                if idx < 10:
                    logger.debug(f"第 {excel_row} 行: ✅ 新增成功")
            else:
                # 冲突跳过（幂等性保护）
                skipped += 1
                if idx < 10:
                    logger.debug(f"第 {excel_row} 行: ⏭️  跳过（idempotency_key 已存在）")

        except Exception as e:
            errors += 1
            logger.error(f"❌ 第 {excel_row} 行处理失败: {e}")
            if errors >= 10:
                logger.error(f"错误过多，终止导入")
                break
            continue

    # 最终报告
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info(f"\n{'='*70}")
    logger.info(f"导入完成")
    logger.info(f"{'='*70}")
    logger.info(f"总行数: {total_rows}")
    logger.info(f"新增: {imported}")
    logger.info(f"跳过: {skipped}")
    logger.info(f"错误: {errors}")
    logger.info(f"耗时: {duration:.1f} 秒")
    logger.info(f"速度: {imported / (duration / 60):.1f} 条/分钟")
    logger.info(f"{'='*70}")

    # 记录导入结果
    stats = {
        'total_rows': total_rows,
        'imported': imported,
        'skipped': skipped,
        'errors': errors
    }

    if errors >= 10:
        record_import_failed(client, file_path.name, f"错误过多，已中止 ({errors} 个错误)", stats)
    else:
        record_import_complete(client, file_path.name, stats)

def main():
    if len(sys.argv) != 2:
        print("用法: python3 scripts/import_one.py <excel_file>")
        print("示例: python3 scripts/import_one.py data/duoke/汇总_20260312_0600.xlsx")
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        logger.error(f"文件不存在: {file_path}")
        sys.exit(1)

    try:
        import_with_progress(file_path)
    except KeyboardInterrupt:
        logger.warning(f"\n用户中断")
        try:
            client = get_supabase_client()
            record_import_failed(client, file_path.name, "用户中断")
        except:
            pass
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n导入失败: {e}", exc_info=True)
        try:
            client = get_supabase_client()
            record_import_failed(client, file_path.name, str(e))
        except:
            pass
        sys.exit(1)

if __name__ == '__main__':
    main()
