#!/usr/bin/env python3
"""
飞书群技术问答同步脚本

从配置的飞书技术支持群中提取技术问题并同步到 Supabase knowledge_entries 表

Usage:
    python3 scripts/sync_feishu_qa.py [hours]

Args:
    hours: 获取最近N小时的消息（默认24）
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import ListMessageRequest
from dotenv import load_dotenv

# 导入共用工具函数
sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    get_supabase_client,
    extract_sku,
    is_tech_question,
    extract_keywords
)

# 加载环境变量
load_dotenv()

# 配置日志
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "sync_feishu_qa.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 飞书配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
FEISHU_TECH_GROUPS = [
    g.strip() for g in os.environ.get("FEISHU_TECH_GROUP_IDS", "").split(",") if g.strip()
]

# 群组名称映射（chat_id → 群组名）
GROUP_NAMES = {
    'oc_8db7befe45b123b77b958680ed81dcea': 'CBC004技术支持群',
    'oc_0166622dbb023561e492924a38920c15': 'CBC006技术支持群',
    'oc_5cc2ded63967c47fd93ea22c1e3e5aeb': 'CBC008技术支持群',
    'oc_37ab045e7c51bd4d78f3f26dccca10d8': '多客智能客服群'
}


def get_lark_client():
    """创建飞书客户端"""
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise ValueError("Missing FEISHU_APP_ID or FEISHU_APP_SECRET environment variables")
    return lark.Client.builder().app_id(FEISHU_APP_ID).app_secret(FEISHU_APP_SECRET).build()


def extract_text_from_message(msg) -> str:
    """从消息体提取文本内容（支持 text 和 post 类型）"""
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
    except Exception as e:
        logger.debug(f"Failed to extract text from message: {e}")
        pass

    return content


def fetch_recent_messages(client, chat_id: str, hours: int = 24) -> List:
    """获取最近N小时的消息"""
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


def get_or_create_product(supabase, sku: str) -> Optional[str]:
    """
    获取或创建产品记录，返回 product_id

    NOTE: 由于当前 schema 中 knowledge_entries 需要 product_id (NOT NULL),
    如果产品不存在，我们创建一个占位产品记录
    """
    try:
        # 尝试查找产品
        result = supabase.table("products").select("id").eq("sku", sku).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]['id']

        # 产品不存在，创建占位记录
        logger.info(f"  产品 {sku} 不存在，创建占位记录")
        insert_result = supabase.table("products").insert({
            "sku": sku,
            "name": f"[待补充] {sku}",
            "category": "未分类",
            "status": "draft"
        }).execute()

        if insert_result.data:
            return insert_result.data[0]['id']

    except Exception as e:
        logger.error(f"  处理产品 {sku} 时出错: {e}")

    return None


def get_system_user_id(supabase) -> Optional[str]:
    """获取系统用户ID（用于created_by字段）"""
    try:
        # 尝试查找admin用户
        result = supabase.table("users").select("id").eq("role", "admin").limit(1).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['id']

        # 如果没有admin，查找任意用户
        result = supabase.table("users").select("id").limit(1).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['id']

        logger.warning("  未找到系统用户，需要先创建用户")
        return None

    except Exception as e:
        logger.error(f"  获取系统用户ID失败: {e}")
        return None


def sync_group_messages(chat_id: str, group_name: str, hours: int = 24) -> Dict:
    """同步单个群组的消息到 knowledge_entries 表"""
    logger.info(f"开始同步群组: {group_name} ({chat_id})")

    client = get_lark_client()
    supabase = get_supabase_client()

    # 获取系统用户ID
    system_user_id = get_system_user_id(supabase)
    if not system_user_id:
        logger.error("  无法获取系统用户ID，跳过该群组")
        return {
            "group": group_name,
            "total_messages": 0,
            "tech_questions": 0,
            "inserted": 0,
            "skipped": 0,
            "error": "No system user found"
        }

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

        # 获取或创建产品
        product_id = get_or_create_product(supabase, sku)
        if not product_id:
            logger.warning(f"  跳过（无法获取产品ID）: {sku}")
            skipped_count += 1
            continue

        # 提取关键词作为tags
        keywords = extract_keywords(content)

        # 生成简单的question（取前100字符）
        question = content[:100] + "..." if len(content) > 100 else content

        # 插入数据库
        # NOTE: 适配当前schema: product_id (required), category, question, answer, tags, source, created_by
        try:
            result = supabase.table("knowledge_entries").insert({
                "product_id": product_id,
                "category": "troubleshooting",  # 默认分类为故障排除
                "question": question,
                "answer": content,  # 完整内容作为answer
                "tags": keywords,
                "source": f"feishu_chat:{group_name}:{msg.message_id}",  # 记录来源
                "created_by": system_user_id,
                "verified": False  # 待审核
            }).execute()

            inserted_count += 1
            logger.info(f"  ✅ 插入: {sku} - {question[:30]}...")

        except Exception as e:
            error_msg = str(e)
            # 检查是否是重复记录（通过source字段判断）
            if "duplicate" in error_msg.lower() or "unique" in error_msg.lower():
                skipped_count += 1
                logger.debug(f"  跳过（已存在）: {msg.message_id}")
            else:
                logger.error(f"  ❌ 插入失败: {e}")
                skipped_count += 1

    logger.info(f"  完成: 技术问题 {tech_count} 个, 新增 {inserted_count} 个, 跳过 {skipped_count} 个")

    return {
        "group": group_name,
        "total_messages": len(messages),
        "tech_questions": tech_count,
        "inserted": inserted_count,
        "skipped": skipped_count
    }


def sync_all_groups(hours: int = 24) -> List[Dict]:
    """同步所有配置的群组"""
    logger.info("=" * 60)
    logger.info(f"开始同步飞书群问答 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    results = []

    # 如果没有配置群组，使用默认群组
    groups_to_sync = FEISHU_TECH_GROUPS if FEISHU_TECH_GROUPS else list(GROUP_NAMES.keys())

    if not groups_to_sync:
        logger.error("未配置飞书技术群组 ID (FEISHU_TECH_GROUP_IDS)")
        return results

    for chat_id in groups_to_sync:
        group_name = GROUP_NAMES.get(chat_id, chat_id)
        try:
            result = sync_group_messages(chat_id, group_name, hours)
            results.append(result)
        except Exception as e:
            logger.error(f"同步群组 {group_name} 失败: {e}")
            results.append({
                "group": group_name,
                "total_messages": 0,
                "tech_questions": 0,
                "inserted": 0,
                "skipped": 0,
                "error": str(e)
            })

    # 统计汇总
    total_messages = sum(r.get('total_messages', 0) for r in results)
    total_tech = sum(r.get('tech_questions', 0) for r in results)
    total_inserted = sum(r.get('inserted', 0) for r in results)
    total_skipped = sum(r.get('skipped', 0) for r in results)

    logger.info("=" * 60)
    logger.info("同步完成汇总:")
    logger.info(f"  总消息数: {total_messages}")
    logger.info(f"  技术问题: {total_tech}")
    logger.info(f"  新增记录: {total_inserted}")
    logger.info(f"  跳过记录: {total_skipped}")
    logger.info("=" * 60)

    return results


def main():
    """主程序"""
    # 解析命令行参数
    hours = 24
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except ValueError:
            logger.error(f"无效的小时数: {sys.argv[1]}")
            sys.exit(1)

    logger.info(f"开始同步最近 {hours} 小时的消息")

    try:
        results = sync_all_groups(hours)

        # 如果所有群组都失败，退出码为1
        if all(r.get('error') for r in results):
            sys.exit(1)

    except Exception as e:
        logger.error(f"同步失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
