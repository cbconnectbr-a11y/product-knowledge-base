"""
飞书文件自动处理模块
监听群聊文件上传，自动下载并触发多客数据导入
"""
import os
import re
import logging
import subprocess
from pathlib import Path
from datetime import datetime
import lark_oapi as lark
from lark_oapi.api.im.v1 import GetMessageResourceRequest
from bot.queue_manager import add_file_to_queue

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'duoke'
IMPORT_SCRIPT = PROJECT_ROOT / 'scripts' / 'import_duoke_daily.py'


def is_duoke_summary_file(filename: str) -> bool:
    """
    检查是否为多客汇总文件

    格式: 汇总_YYYYMMDD_HHMM.xlsx

    Args:
        filename: 文件名

    Returns:
        是否为多客汇总文件
    """
    pattern = r'^汇总_\d{8}_\d{4}\.xlsx$'
    return bool(re.match(pattern, filename))


def download_feishu_file(lark_client: lark.Client, message_id: str, file_key: str, save_path: Path) -> bool:
    """
    从飞书下载文件到本地

    Args:
        lark_client: 飞书客户端
        message_id: 消息 ID
        file_key: 文件 key (从消息中获取)
        save_path: 保存路径

    Returns:
        是否下载成功
    """
    try:
        # 构建消息附件下载请求 (IM API)
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(file_key) \
            .type("file") \
            .build()

        # 调用飞书 IM API 下载消息附件
        response = lark_client.im.v1.message_resource.get(request)

        if not response.success():
            error_details = {
                'msg': response.msg,
                'code': getattr(response, 'code', None),
                'error': getattr(response, 'error', None),
            }
            logger.error(f"Failed to download file. Details: {error_details}")
            return False

        # 保存文件
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(response.file.read())

        logger.info(f"File downloaded successfully: {save_path}")
        return True

    except Exception as e:
        logger.error(f"Error downloading file: {e}", exc_info=True)
        return False


def trigger_duoke_import() -> tuple[bool, str]:
    """
    触发多客数据导入脚本

    Returns:
        (是否成功, 消息)
    """
    try:
        # 使用 Python 3.13 运行导入脚本
        python_path = '/opt/homebrew/bin/python3.13'

        logger.info(f"Starting import script: {IMPORT_SCRIPT}")

        # 使用 subprocess.Popen 在后台运行
        process = subprocess.Popen(
            [python_path, str(IMPORT_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # 不等待完成,立即返回
        logger.info(f"Import process started with PID: {process.pid}")

        return True, f"✅ 导入任务已启动 (PID: {process.pid})\n预计需要 1.5 小时完成 3,152 条记录"

    except Exception as e:
        logger.error(f"Error triggering import: {e}", exc_info=True)
        return False, f"❌ 启动导入失败: {str(e)}"


def handle_file_message(lark_client: lark.Client, message_id: str, file_key: str, filename: str) -> str:
    """
    处理文件消息

    Args:
        lark_client: 飞书客户端
        message_id: 消息 ID
        file_key: 文件 key
        filename: 文件名

    Returns:
        处理结果消息
    """
    try:
        # 检查是否为多客汇总文件
        if not is_duoke_summary_file(filename):
            logger.info(f"Ignored non-summary file: {filename}")
            return ""  # 返回空字符串表示不需要回复

        logger.info(f"Detected Duoke summary file: {filename}")

        # 下载文件
        save_path = DATA_DIR / filename
        if not download_feishu_file(lark_client, message_id, file_key, save_path):
            return f"❌ 下载文件失败: {filename}"

        file_size_mb = save_path.stat().st_size / 1024 / 1024
        logger.info(f"File saved: {save_path} ({file_size_mb:.2f} MB)")

        # 添加到队列
        position, queue_status = add_file_to_queue(filename, save_path)

        # 构建队列状态消息
        if position == 1 and queue_status['processing'] == 0:
            status_msg = "✅ 已加入队列，立即开始处理"
        else:
            status_msg = f"✅ 已加入队列 (第 {position} 个)"

        queue_info = f"📋 队列状态: 待处理 {queue_status['pending']} | 处理中 {queue_status['processing']} | 已完成 {queue_status['completed']}"

        return f"📥 检测到多客汇总文件: {filename}\n" \
               f"📊 文件大小: {file_size_mb:.2f} MB\n" \
               f"{status_msg}\n" \
               f"{queue_info}\n\n" \
               f"💡 系统会自动逐个处理，每个文件约需 1.5 小时\n" \
               f"💡 导入完成后可通过 @机器人 搜索客服对话"

    except Exception as e:
        logger.error(f"Error handling file message: {e}", exc_info=True)
        return f"❌ 处理文件时出错: {str(e)}"


if __name__ == "__main__":
    # 测试文件名匹配
    test_cases = [
        ("汇总_20260428_0800.xlsx", True),
        ("汇总_20260429_1200.xlsx", True),
        ("胡雅倩_20260428_0800.xlsx", False),
        ("summary.xlsx", False),
        ("汇总_202604280800.xlsx", False),  # 格式错误
    ]

    print("测试文件名匹配:")
    for filename, expected in test_cases:
        result = is_duoke_summary_file(filename)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {filename}: {result}")
