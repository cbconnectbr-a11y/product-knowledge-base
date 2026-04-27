#!/usr/bin/env python3
"""
飞书群技术问答同步脚本
复用 tech-qa-extraction 项目的逻辑
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import lark_oapi as lark
from lark_oapi.api.im.v1 import ListMessageRequest
from dotenv import load_dotenv

from scripts.utils import (
    get_supabase_client,
    extract_sku,
    is_tech_question,
    extract_keywords
)

load_dotenv()

# 配置日志（launchd 会捕获 stdout/stderr 到日志文件）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 飞书配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
FEISHU_TECH_GROUPS = os.environ.get("FEISHU_TECH_GROUPS", "").split(",")

# 验证必需的环境变量
if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
    raise ValueError("Missing required environment variables: FEISHU_APP_ID and FEISHU_APP_SECRET")

# 群组名称映射
GROUP_NAMES = {
    "oc_8db7befe45b123b77b958680ed81dcea": "CBC004",
    "oc_0166622dbb023561e492924a38920c15": "CBC006",
    "oc_5cc2ded63967c47fd93ea22c1e3e5aeb": "CBC008",
}

def get_lark_client():
    """创建飞书客户端"""
    return lark.Client.builder() \
        .app_id(FEISHU_APP_ID) \
        .app_secret(FEISHU_APP_SECRET) \
        .build()

def extract_text_from_message(msg):
    """从消息体提取文本"""
    body = msg.body
    msg_type = msg.msg_type
    content = ''

    try:
        if msg_type == 'text':
            content_json = json.loads(body.content)
            content = content_json.get('text', '')
        elif msg_type == 'post':
            content_json = json.loads(body.content)
            text_parts = []
            for section in content_json.get('content', []):
                for element in section:
                    if element.get('tag') == 'text':
                        text_parts.append(element.get('text', ''))
            content = ' '.join(text_parts)
    except (json.JSONDecodeError, KeyError, AttributeError) as e:
        logger.debug(f"Failed to parse message: {e}")

    return content

def fetch_recent_messages(client, chat_id, hours=24):
    """获取最近 N 小时的消息"""
    cutoff_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

    request = ListMessageRequest.builder() \
        .container_id_type("chat") \
        .container_id(chat_id) \
        .page_size(50) \
        .sort_type("ByCreateTimeDesc") \
        .build()

    messages = []
    while True:
        response = client.im.v1.message.list(request)

        if not response.success():
            logger.warning(f"获取消息失败: {response.code} - {response.msg}")
            break

        for msg in response.data.items or []:
            create_time = int(msg.create_time)
            if create_time < cutoff_time:
                return messages  # 超出时间范围
            messages.append(msg)

        if not response.data.has_more:
            break

        request = ListMessageRequest.builder() \
            .container_id_type("chat") \
            .container_id(chat_id) \
            .page_size(50) \
            .sort_type("ByCreateTimeDesc") \
            .page_token(response.data.page_token) \
            .build()

    return messages

def sync_group_messages(chat_id, group_name, hours=24):
    """同步单个群组的消息"""
    logger.info(f"开始同步群组: {group_name} ({chat_id})")

    client = get_lark_client()
    supabase = get_supabase_client()

    # 获取最近消息
    messages = fetch_recent_messages(client, chat_id, hours)
    logger.info(f"  获取到 {len(messages)} 条消息")

    # 筛选技术问题
    tech_count = 0
    inserted_count = 0
    skipped_count = 0

    for msg in messages:
        content = extract_text_from_message(msg)
        if not content or len(content) < 10:
            continue

        if not is_tech_question(content):
            continue

        tech_count += 1
        sku = extract_sku(content)

        if not sku:
            logger.debug(f"  跳过（无SKU）: {content[:50]}...")
            continue

        # 提取关键词
        keywords = extract_keywords(content)

        # 生成简单的标题（取前50字符）
        title = content[:50] + "..." if len(content) > 50 else content

        # 插入数据库
        try:
            result = supabase.table("knowledge_entries").insert({
                "sku": sku,
                "title": title,
                "content": content,
                "source_type": "feishu_chat",
                "source_id": msg.message_id,
                "source_group": group_name,
                "keywords": keywords,
                "status": "pending",  # 待审核
            }).execute()

            inserted_count += 1
            logger.info(f"  ✅ 插入: {sku} - {title}")

        except Exception as e:
            if "unique_source" in str(e):
                skipped_count += 1
                logger.debug(f"  跳过（已存在）: {msg.message_id}")
            else:
                logger.error(f"  ❌ 插入失败: {e}")

    logger.info(f"  完成: 技术问题 {tech_count} 个, 新增 {inserted_count} 个, 跳过 {skipped_count} 个")

    return {
        "group": group_name,
        "total_messages": len(messages),
        "tech_questions": tech_count,
        "inserted": inserted_count,
        "skipped": skipped_count
    }

def sync_all_groups(hours=24):
    """同步所有配置的群组"""
    logger.info("=" * 60)
    logger.info(f"开始同步飞书群问答 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    results = []

    for chat_id in FEISHU_TECH_GROUPS:
        chat_id = chat_id.strip()
        if not chat_id:
            continue

        group_name = GROUP_NAMES.get(chat_id, chat_id)

        try:
            result = sync_group_messages(chat_id, group_name, hours)
            results.append(result)
        except Exception as e:
            logger.error(f"同步群组 {group_name} 失败: {e}")
            results.append({
                "group": group_name,
                "error": str(e)
            })

    # 汇总统计
    total_tech = sum(r.get("tech_questions", 0) for r in results)
    total_inserted = sum(r.get("inserted", 0) for r in results)

    logger.info("=" * 60)
    logger.info(f"同步完成！")
    logger.info(f"  技术问题总数: {total_tech}")
    logger.info(f"  新增知识条目: {total_inserted}")
    logger.info("=" * 60)

    return results

if __name__ == "__main__":
    # 默认同步最近 24 小时
    try:
        hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
        if hours <= 0:
            raise ValueError("Hours must be positive")
    except ValueError as e:
        logger.error(f"Invalid hours argument: {e}. Usage: python3 sync_feishu_qa.py [hours]")
        sys.exit(1)

    try:
        results = sync_all_groups(hours)
        sys.exit(0)
    except Exception as e:
        logger.error(f"同步失败: {e}", exc_info=True)
        sys.exit(1)
