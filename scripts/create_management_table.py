#!/usr/bin/env python3
"""
知识库管理界面 - 飞书多维表格管理脚本

此脚本管理知识库条目的审核流程：
1. 从 Supabase 读取待审核条目（status='pending'）
2. 创建/检查飞书管理表
3. 将待审核条目同步到飞书表格
4. 从飞书表格读取审核结果并回写 Supabase

Phase 1 MVP：
- 脚本将待审核条目推送到飞书
- 用户在飞书表格中手动审核和更新状态
- 脚本读取审核结果并更新数据库
"""
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    CreateAppTableRecordRequest,
    ListAppTableRecordRequest,
    UpdateAppTableRecordRequest,
    ListAppTableFieldRequest,
)
from dotenv import load_dotenv

from scripts.utils import get_supabase_client

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 飞书配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")

# 管理表配置 - 从环境变量或使用默认
FEISHU_MANAGEMENT_APP_TOKEN = os.environ.get("FEISHU_MANAGEMENT_APP_TOKEN")
FEISHU_MANAGEMENT_TABLE_ID = os.environ.get("FEISHU_MANAGEMENT_TABLE_ID")

# 环境变量验证
if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
    raise ValueError(
        "Missing required environment variables: FEISHU_APP_ID, FEISHU_APP_SECRET"
    )


def get_lark_client():
    """创建飞书客户端"""
    return lark.Client.builder() \
        .app_id(FEISHU_APP_ID) \
        .app_secret(FEISHU_APP_SECRET) \
        .build()


def truncate_text(text: str, max_length: int = 2000) -> str:
    """截断长文本（飞书文本字段支持最多 5000 字符）"""
    if not text:
        return ""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def get_table_fields(client, app_token: str, table_id: str) -> Dict[str, str]:
    """获取表格字段定义"""
    request = ListAppTableFieldRequest.builder() \
        .app_token(app_token) \
        .table_id(table_id) \
        .build()

    response = client.bitable.v1.app_table_field.list(request)

    if not response.success():
        raise Exception(f"获取字段失败: {response.code} - {response.msg}")

    fields = {}
    for field in response.data.items:
        fields[field.field_name] = field.type

    logger.info(f"表格包含 {len(fields)} 个字段: {list(fields.keys())}")
    return fields


def fetch_pending_entries(supabase, limit: int = 100) -> List[Dict]:
    """从 Supabase 读取待审核条目"""
    logger.info(f"从 Supabase 读取待审核条目 (limit={limit})...")

    try:
        response = supabase.table("knowledge_entries") \
            .select(
                "id, sku, title, content, source_group, keywords, created_at, created_by"
            ) \
            .eq("status", "pending") \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()

        entries = response.data or []
        logger.info(f"读取到 {len(entries)} 条待审核条目")
        return entries

    except Exception as e:
        logger.error(f"读取失败: {e}")
        raise


def fetch_reviewed_entries(client, app_token: str, table_id: str) -> List[Dict]:
    """从飞书表格读取已审核条目（status != pending）"""
    logger.info("从飞书表格读取已审核条目...")

    reviewed_entries = []
    page_token = None

    try:
        while True:
            request = ListAppTableRecordRequest.builder() \
                .app_token(app_token) \
                .table_id(table_id) \
                .page_size(500) \
                .page_token(page_token) \
                .build()

            response = client.bitable.v1.app_table_record.list(request)

            if not response.success():
                logger.warning(f"获取记录失败: {response.code} - {response.msg}")
                break

            for record in response.data.items:
                fields = record.fields or {}
                status = extract_field_value(fields.get("Status"))
                db_id = extract_field_value(fields.get("DB_ID"))

                # 只关心已审核的条目（非 pending）
                if status and status != "pending" and db_id:
                    reviewed_entries.append({
                        "record_id": record.record_id,
                        "db_id": db_id,
                        "status": status,
                        "reviewer_notes": extract_field_value(fields.get("审核意见")),
                    })

            if not response.data.has_more:
                break

            page_token = response.data.page_token

        logger.info(f"读取到 {len(reviewed_entries)} 条已审核条目")
        return reviewed_entries

    except Exception as e:
        logger.error(f"读取失败: {e}")
        return []


def extract_field_value(field_data) -> Optional[str]:
    """提取字段值（处理不同数据格式）"""
    if not field_data:
        return None

    # 列表格式（富文本）
    if isinstance(field_data, list):
        if field_data and isinstance(field_data[0], dict):
            return field_data[0].get('text')
        return None

    # 字符串格式
    if isinstance(field_data, str):
        return field_data

    # 字典格式
    if isinstance(field_data, dict):
        return field_data.get('text')

    return None


def sync_pending_to_feishu(
    client,
    app_token: str,
    table_id: str,
    pending_entries: List[Dict]
) -> Dict[str, int]:
    """将待审核条目同步到飞书表格"""
    logger.info(f"同步 {len(pending_entries)} 条待审核条目到飞书...")

    inserted_count = 0
    skipped_count = 0

    for entry in pending_entries:
        try:
            # 准备字段数据
            fields = {
                "DB_ID": [{"text": entry["id"]}],  # 数据库 ID，用于回写
                "SKU": [{"text": entry["sku"] or ""}],
                "标题": [{"text": entry["title"]}],
                "内容": [{"text": truncate_text(entry["content"], 2000)}],
                "来源": [{"text": entry["source_group"] or ""}],
                "关键词": [{"text": ", ".join(entry.get("keywords", []))}],
                "创建时间": [{"text": entry["created_at"]}],
                "Status": [{"text": "pending"}],  # 初始状态
            }

            # 创建记录
            request = CreateAppTableRecordRequest.builder() \
                .app_token(app_token) \
                .table_id(table_id) \
                .fields(fields) \
                .build()

            response = client.bitable.v1.app_table_record.create(request)

            if response.success():
                inserted_count += 1
                logger.info(f"  ✓ 创建: {entry['sku']} - {entry['title'][:40]}")
            else:
                logger.warning(f"  ✗ 创建失败 {entry['id']}: {response.code} - {response.msg}")
                skipped_count += 1

        except Exception as e:
            logger.error(f"  ✗ 处理失败 {entry['id']}: {e}")
            skipped_count += 1

    logger.info(f"同步完成: 新增 {inserted_count}, 跳过 {skipped_count}")
    return {
        "inserted": inserted_count,
        "skipped": skipped_count
    }


def sync_reviews_to_supabase(
    supabase,
    reviewed_entries: List[Dict],
    user_id: Optional[str] = None
) -> Dict[str, int]:
    """将飞书审核结果回写到 Supabase"""
    logger.info(f"将 {len(reviewed_entries)} 条审核结果回写到 Supabase...")

    updated_count = 0
    skipped_count = 0

    for entry in reviewed_entries:
        try:
            db_id = entry["db_id"]
            status = entry["status"]

            # 验证 status 值
            valid_statuses = ["pending", "approved", "rejected", "draft"]
            if status not in valid_statuses:
                logger.warning(f"  ✗ 无效的状态 {status}，跳过 {db_id}")
                skipped_count += 1
                continue

            # 准备更新数据
            update_data = {
                "status": status,
                "reviewed_at": datetime.now().isoformat(),
            }

            # 如果有用户 ID，记录审核人
            if user_id:
                update_data["reviewed_by"] = user_id

            # 如果有审核意见，记录到 content 的末尾或单独字段
            if entry.get("reviewer_notes"):
                update_data["reviewer_notes"] = entry["reviewer_notes"]

            # 更新数据库
            response = supabase.table("knowledge_entries") \
                .update(update_data) \
                .eq("id", db_id) \
                .execute()

            if response.data:
                updated_count += 1
                logger.info(f"  ✓ 更新: {db_id} -> {status}")
            else:
                logger.warning(f"  ✗ 更新失败 {db_id}: 无数据返回")
                skipped_count += 1

        except Exception as e:
            logger.error(f"  ✗ 处理失败 {entry.get('db_id')}: {e}")
            skipped_count += 1

    logger.info(f"回写完成: 更新 {updated_count}, 跳过 {skipped_count}")
    return {
        "updated": updated_count,
        "skipped": skipped_count
    }


def validate_management_config() -> bool:
    """验证管理表配置"""
    if not FEISHU_MANAGEMENT_APP_TOKEN or not FEISHU_MANAGEMENT_TABLE_ID:
        logger.warning("\n" + "=" * 70)
        logger.warning("⚠️  飞书管理表未配置！")
        logger.warning("=" * 70)
        logger.warning("\n请按照以下步骤设置：\n")
        logger.warning("1. 在飞书创建新的多维表格应用")
        logger.warning("2. 获取应用 Token（APP_TOKEN）和表格 ID（TABLE_ID）")
        logger.warning("3. 在 .env 文件中配置以下环境变量：")
        logger.warning("   FEISHU_MANAGEMENT_APP_TOKEN=<your-app-token>")
        logger.warning("   FEISHU_MANAGEMENT_TABLE_ID=<your-table-id>")
        logger.warning("\n或者在运行脚本时通过环境变量传入：")
        logger.warning("   FEISHU_MANAGEMENT_APP_TOKEN=... FEISHU_MANAGEMENT_TABLE_ID=... python3 scripts/create_management_table.py")
        logger.warning("\n表格需要以下字段（自动创建或手动创建）：")
        logger.warning("  - DB_ID (文本) - 数据库条目 ID")
        logger.warning("  - SKU (文本) - 产品 SKU")
        logger.warning("  - 标题 (文本) - 条目标题")
        logger.warning("  - 内容 (富文本) - 条目内容")
        logger.warning("  - 来源 (文本) - 数据来源")
        logger.warning("  - 关键词 (文本) - 关键词列表")
        logger.warning("  - 创建时间 (日期时间) - 创建时间")
        logger.warning("  - Status (单选) - 审核状态（pending/approved/rejected/draft）")
        logger.warning("  - 审核意见 (富文本) - 审核人的反馈")
        logger.warning("=" * 70 + "\n")
        return False
    return True


def show_usage_guide():
    """显示使用指南"""
    logger.info("\n" + "=" * 70)
    logger.info("知识库管理界面 - 使用指南")
    logger.info("=" * 70 + "\n")

    logger.info("1. 自动同步待审核条目")
    logger.info("   $ python3 scripts/create_management_table.py sync-pending\n")

    logger.info("2. 同步审核结果回 Supabase")
    logger.info("   $ python3 scripts/create_management_table.py sync-reviews\n")

    logger.info("3. 完整同步（待审核 + 审核结果）")
    logger.info("   $ python3 scripts/create_management_table.py sync-all\n")

    logger.info("审核流程：")
    logger.info("  1. 脚本将待审核条目推送到飞书表格")
    logger.info("  2. 用户在飞书中打开表格进行审核")
    logger.info("  3. 更新 Status 字段（pending → approved/rejected）")
    logger.info("  4. 可选：在审核意见字段中填写反馈")
    logger.info("  5. 脚本定期读取已审核条目，回写 Supabase")
    logger.info("\n" + "=" * 70 + "\n")


def main(action: str = "sync-all"):
    """主执行函数"""
    logger.info("=" * 70)
    logger.info(f"知识库管理脚本 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    # 验证配置
    if not validate_management_config():
        show_usage_guide()
        return False

    try:
        client = get_lark_client()
        supabase = get_supabase_client()

        # 验证表格访问
        logger.info(f"验证飞书表格访问...")
        get_table_fields(client, FEISHU_MANAGEMENT_APP_TOKEN, FEISHU_MANAGEMENT_TABLE_ID)

        results = {
            "pending_sync": {"inserted": 0, "skipped": 0},
            "reviews_sync": {"updated": 0, "skipped": 0}
        }

        # 执行同步操作
        if action in ["sync-pending", "sync-all"]:
            logger.info("\n--- 同步待审核条目 ---")
            pending_entries = fetch_pending_entries(supabase)

            if pending_entries:
                results["pending_sync"] = sync_pending_to_feishu(
                    client,
                    FEISHU_MANAGEMENT_APP_TOKEN,
                    FEISHU_MANAGEMENT_TABLE_ID,
                    pending_entries
                )
            else:
                logger.info("没有待审核条目")

        if action in ["sync-reviews", "sync-all"]:
            logger.info("\n--- 同步审核结果 ---")
            reviewed_entries = fetch_reviewed_entries(
                client,
                FEISHU_MANAGEMENT_APP_TOKEN,
                FEISHU_MANAGEMENT_TABLE_ID
            )

            if reviewed_entries:
                results["reviews_sync"] = sync_reviews_to_supabase(supabase, reviewed_entries)
            else:
                logger.info("没有待同步的审核结果")

        # 汇总统计
        logger.info("\n" + "=" * 70)
        logger.info("同步统计")
        logger.info("=" * 70)
        logger.info(f"待审核条目: 新增 {results['pending_sync']['inserted']}, 跳过 {results['pending_sync']['skipped']}")
        logger.info(f"审核结果: 更新 {results['reviews_sync']['updated']}, 跳过 {results['reviews_sync']['skipped']}")
        logger.info("=" * 70)

        return True

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    show_usage_guide()

    # 解析命令行参数
    action = sys.argv[1] if len(sys.argv) > 1 else "sync-all"
    valid_actions = ["sync-pending", "sync-reviews", "sync-all"]

    if action not in valid_actions:
        logger.error(f"无效的操作: {action}")
        logger.error(f"有效的操作: {', '.join(valid_actions)}")
        sys.exit(1)

    try:
        success = main(action)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"脚本失败: {e}", exc_info=True)
        sys.exit(1)
