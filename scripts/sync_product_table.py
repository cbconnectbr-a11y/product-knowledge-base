#!/usr/bin/env python3
"""
飞书产品信息表同步脚本
"""
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    ListAppTableRecordRequest,
    ListAppTableFieldRequest
)
from dotenv import load_dotenv

from scripts.utils import get_supabase_client

load_dotenv()

# 配置日志
Path('logs').mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/sync_products.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 飞书配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
APP_TOKEN = os.environ.get("FEISHU_PRODUCT_TABLE_APP_TOKEN")
TABLE_ID = os.environ.get("FEISHU_PRODUCT_TABLE_TABLE_ID")

# 环境变量验证
if not FEISHU_APP_ID or not FEISHU_APP_SECRET or not APP_TOKEN or not TABLE_ID:
    raise ValueError(
        "Missing required environment variables: "
        "FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_PRODUCT_TABLE_APP_TOKEN, FEISHU_PRODUCT_TABLE_TABLE_ID"
    )

def get_lark_client():
    """创建飞书客户端"""
    return lark.Client.builder() \
        .app_id(FEISHU_APP_ID) \
        .app_secret(FEISHU_APP_SECRET) \
        .build()

def get_table_fields(client):
    """获取表格字段定义"""
    request = ListAppTableFieldRequest.builder() \
        .app_token(APP_TOKEN) \
        .table_id(TABLE_ID) \
        .build()

    response = client.bitable.v1.app_table_field.list(request)

    if not response.success():
        raise Exception(f"获取字段失败: {response.code} - {response.msg}")

    fields = {}
    for field in response.data.items:
        fields[field.field_name] = field.type

    logger.info(f"表格包含 {len(fields)} 个字段")
    return fields

def fetch_all_records(client):
    """获取表格所有记录"""
    records = []
    page_token = None

    while True:
        request = ListAppTableRecordRequest.builder() \
            .app_token(APP_TOKEN) \
            .table_id(TABLE_ID) \
            .page_size(500) \
            .page_token(page_token) \
            .build()

        response = client.bitable.v1.app_table_record.list(request)

        if not response.success():
            raise Exception(f"获取记录失败: {response.code} - {response.msg}")

        records.extend(response.data.items)

        if not response.data.has_more:
            break

        page_token = response.data.page_token

    logger.info(f"共读取 {len(records)} 条产品记录")
    return records

def extract_field_value(field_data, field_type):
    """提取字段值（处理不同类型）"""
    if not field_data:
        return None

    # 文本/数字类型
    if field_type in ['Text', 'Number']:
        if isinstance(field_data, list) and field_data and isinstance(field_data[0], dict):
            return field_data[0].get('text')
        elif isinstance(field_data, str):
            return field_data
        return None

    # URL 类型
    if field_type == 'Url':
        if isinstance(field_data, list):
            # 验证列表中的元素，过滤掉无效的
            return [item.get('link') for item in field_data if isinstance(item, dict) and item.get('link')]
        elif isinstance(field_data, dict):
            return field_data.get('link')
        elif isinstance(field_data, str):
            return field_data
        return None

    # 附件类型
    if field_type == 'Attachment':
        if isinstance(field_data, list):
            attachments = []
            for att in field_data:
                if isinstance(att, dict):
                    attachments.append({
                        "name": att.get('name'),
                        "url": att.get('url'),
                        "file_token": att.get('file_token')
                    })
            return attachments
        return None

    # 其他类型，直接返回
    return field_data

def process_record(record, fields_info):
    """处理单条产品记录"""
    raw_data = record.fields

    # 提取 SKU（必需字段）- 处理多种数据格式
    sku_raw = raw_data.get("SKU")

    # 处理不同的 SKU 数据类型
    if isinstance(sku_raw, list) and sku_raw:
        # 飞书可能返回列表格式的文本字段
        first_item = sku_raw[0]
        if isinstance(first_item, dict):
            sku = first_item.get('text')
        elif isinstance(first_item, str):
            sku = first_item
        else:
            sku = str(first_item) if first_item else None
    elif isinstance(sku_raw, str):
        sku = sku_raw
    elif isinstance(sku_raw, dict):
        # 处理字典格式（某些特殊情况）
        sku = sku_raw.get('text')
    else:
        sku = None

    if not sku:
        logger.warning(f"跳过：缺少或无效的 SKU - {record.record_id}")
        return None

    # 提取字段
    name_en = raw_data.get("库存SKU英文名称", "")
    description = raw_data.get("商品备注", "")
    features = raw_data.get("卖点+产品特性", "")

    # 提取URL和附件
    images_raw = raw_data.get("库存图片链接")
    images = [images_raw] if isinstance(images_raw, str) else \
             extract_field_value(images_raw, fields_info.get("库存图片链接", "Url")) or []

    package_images = extract_field_value(
        raw_data.get("产品包装图"),
        fields_info.get("产品包装图", "Attachment")
    ) or []

    manual_files = extract_field_value(
        raw_data.get("说明书"),
        fields_info.get("说明书", "Attachment")
    ) or []

    model_3d_url = extract_field_value(
        raw_data.get("3D模型"),
        fields_info.get("3D模型", "Url")
    )

    # Phase 1: 简单的中文名称提取（从英文名称或特性中提取）
    # Phase 2+ 将使用 AI 生成
    name_cn = raw_data.get("产品名称") or name_en  # 如果有中文名称字段就用

    # 构建产品数据
    product_data = {
        "sku": sku,
        "name_en": name_en,
        "name_cn": name_cn,
        "description": description,
        "features": features,
        "images": images,
        "package_images": [img.get('url') for img in package_images] if package_images else [],
        "manual_files": manual_files,
        "model_3d_url": model_3d_url if isinstance(model_3d_url, str) else None,
        "feishu_raw_data": raw_data,  # 保存完整原始数据
        "feishu_record_id": record.record_id,
        "synced_at": datetime.now().isoformat(),
    }

    return product_data

def sync_products():
    """同步所有产品"""
    logger.info("=" * 60)
    logger.info(f"开始同步飞书产品表 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    client = get_lark_client()
    supabase = get_supabase_client()

    # 获取字段信息
    fields_info = get_table_fields(client)

    # 获取所有记录
    records = fetch_all_records(client)

    # 处理每条记录
    inserted_count = 0
    updated_count = 0
    skipped_count = 0

    for record in records:
        product_data = process_record(record, fields_info)

        if not product_data:
            skipped_count += 1
            continue

        sku = product_data["sku"]

        try:
            # 检查是否已存在
            existing = supabase.table("products") \
                .select("id") \
                .eq("sku", sku) \
                .execute()

            if existing.data:
                # 更新
                supabase.table("products") \
                    .update(product_data) \
                    .eq("sku", sku) \
                    .execute()
                updated_count += 1
                logger.info(f"  更新: {sku} - {product_data['name_cn']}")
            else:
                # 插入
                supabase.table("products") \
                    .insert(product_data) \
                    .execute()
                inserted_count += 1
                logger.info(f"  新增: {sku} - {product_data['name_cn']}")

        except Exception as e:
            logger.error(f"  处理失败 {sku}: {e}")
            skipped_count += 1

    logger.info("=" * 60)
    logger.info(f"同步完成！")
    logger.info(f"  新增: {inserted_count}")
    logger.info(f"  更新: {updated_count}")
    logger.info(f"  跳过: {skipped_count}")
    logger.info("=" * 60)

    return {
        "inserted": inserted_count,
        "updated": updated_count,
        "skipped": skipped_count
    }

if __name__ == "__main__":
    try:
        result = sync_products()
        sys.exit(0)
    except Exception as e:
        logger.error(f"同步失败: {e}", exc_info=True)
        sys.exit(1)
