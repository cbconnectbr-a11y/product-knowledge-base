"""
飞书群文件扫描脚本
处理webhook记录的待下载文件列表
"""
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import lark_oapi as lark

from bot.config import FEISHU_APP_ID, FEISHU_APP_SECRET
from bot.file_handler import is_duoke_summary_file, download_feishu_file
from bot.queue_manager import add_file_to_queue

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 待处理文件列表
PENDING_FILES_JSON = PROJECT_ROOT / 'data' / 'duoke' / 'pending_downloads.json'

# 数据目录
DATA_DIR = PROJECT_ROOT / 'data' / 'duoke'


def get_lark_client():
    """创建飞书客户端"""
    return lark.Client.builder() \
        .app_id(FEISHU_APP_ID) \
        .app_secret(FEISHU_APP_SECRET) \
        .build()


def load_pending_files() -> list:
    """加载待处理文件列表"""
    if not PENDING_FILES_JSON.exists():
        return []

    try:
        with open(PENDING_FILES_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load pending files: {e}")
        return []


def save_pending_files(files: list):
    """保存待处理文件列表"""
    try:
        PENDING_FILES_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(PENDING_FILES_JSON, 'w', encoding='utf-8') as f:
            json.dump(files, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save pending files: {e}")


def get_local_files() -> set:
    """获取本地已下载的文件名集合"""
    files = set()

    # 检查data目录
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("汇总_*.xlsx"):
            files.add(f.name)

    # 检查archive目录
    archive_dir = DATA_DIR / 'archive'
    if archive_dir.exists():
        for f in archive_dir.glob("汇总_*.xlsx"):
            files.add(f.name)

    return files


def add_pending_file(message_id: str, file_key: str, filename: str, chat_id: str):
    """
    添加文件到待处理列表（从webhook调用）

    Args:
        message_id: 消息ID
        file_key: 文件key
        filename: 文件名
        chat_id: 群聊ID
    """
    pending_files = load_pending_files()

    # 检查是否已存在
    for f in pending_files:
        if f['file_key'] == file_key:
            logger.info(f"File already in pending list: {filename}")
            return

    # 添加到列表
    pending_files.append({
        'message_id': message_id,
        'file_key': file_key,
        'filename': filename,
        'chat_id': chat_id,
        'added_at': datetime.now().isoformat()
    })

    save_pending_files(pending_files)
    logger.info(f"Added to pending list: {filename}")


def scan_and_download():
    """扫描并下载待处理文件"""
    logger.info("=" * 60)
    logger.info("Starting file download scan")
    logger.info("=" * 60)

    try:
        # 加载待处理列表
        pending_files = load_pending_files()

        if not pending_files:
            logger.info("No pending files to download")
            return

        logger.info(f"Found {len(pending_files)} pending files")

        # 获取本地已有文件
        local_files = get_local_files()

        # 创建客户端
        client = get_lark_client()

        # 处理每个文件
        success_count = 0
        fail_count = 0
        processed_indices = []

        for i, file_info in enumerate(pending_files):
            filename = file_info['filename']

            # 检查是否已下载
            if filename in local_files:
                logger.info(f"⏭️  Skip (already exists): {filename}")
                processed_indices.append(i)
                continue

            logger.info(f"Processing: {filename}")

            # 下载文件
            save_path = DATA_DIR / filename
            if download_feishu_file(client, file_info['message_id'], file_info['file_key'], save_path):
                # 加入队列
                position, status = add_file_to_queue(filename, save_path)
                logger.info(f"✅ {filename} added to queue (position: {position})")
                success_count += 1
                processed_indices.append(i)
            else:
                logger.error(f"❌ Failed to download: {filename}")
                fail_count += 1

        # 清理已处理的文件
        if processed_indices:
            pending_files = [f for i, f in enumerate(pending_files) if i not in processed_indices]
            save_pending_files(pending_files)
            logger.info(f"Removed {len(processed_indices)} processed files from pending list")

        # 总结
        logger.info("=" * 60)
        logger.info("Scan completed")
        logger.info(f"✅ Success: {success_count}")
        logger.info(f"❌ Failed: {fail_count}")
        logger.info(f"📋 Remaining in pending list: {len(pending_files)}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in scan_and_download: {e}", exc_info=True)


if __name__ == "__main__":
    scan_and_download()
