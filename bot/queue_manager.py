"""
文件导入队列管理模块
支持多文件批量上传，自动排队逐个处理，避免并发冲突
"""
import json
import time
import logging
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'duoke'
QUEUE_FILE = DATA_DIR / 'import_queue.json'
IMPORT_SCRIPT = PROJECT_ROOT / 'scripts' / 'import_duoke_daily.py'

# 全局队列处理器实例
_queue_processor = None
_processor_lock = threading.Lock()


class FileQueue:
    """文件导入队列管理"""

    def __init__(self):
        self.queue_file = QUEUE_FILE
        self.lock = threading.Lock()
        self._ensure_queue_file()

    def _ensure_queue_file(self):
        """确保队列文件存在"""
        if not self.queue_file.exists():
            self._save_queue({'files': [], 'current': None})

    def _load_queue(self) -> Dict:
        """加载队列数据"""
        with self.lock:
            try:
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load queue: {e}")
                return {'files': [], 'current': None}

    def _save_queue(self, data: Dict):
        """保存队列数据"""
        with self.lock:
            try:
                self.queue_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.queue_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to save queue: {e}")

    def add_file(self, filename: str, filepath: Path) -> int:
        """
        添加文件到队列

        Args:
            filename: 文件名
            filepath: 文件路径

        Returns:
            队列中的位置（从1开始）
        """
        queue_data = self._load_queue()

        # 检查是否已在队列中
        for file_info in queue_data['files']:
            if file_info['filename'] == filename:
                logger.info(f"File already in queue: {filename}")
                return queue_data['files'].index(file_info) + 1

        # 添加到队列
        file_info = {
            'filename': filename,
            'filepath': str(filepath),
            'status': 'pending',
            'added_at': datetime.now().isoformat(),
            'started_at': None,
            'completed_at': None,
            'pid': None
        }

        queue_data['files'].append(file_info)
        self._save_queue(queue_data)

        position = len(queue_data['files'])
        logger.info(f"File added to queue: {filename} (position: {position})")

        return position

    def get_next_pending(self) -> Optional[Dict]:
        """获取下一个待处理的文件"""
        queue_data = self._load_queue()

        for file_info in queue_data['files']:
            if file_info['status'] == 'pending':
                return file_info

        return None

    def mark_processing(self, filename: str, pid: int):
        """标记文件为处理中"""
        queue_data = self._load_queue()

        for file_info in queue_data['files']:
            if file_info['filename'] == filename:
                file_info['status'] = 'processing'
                file_info['started_at'] = datetime.now().isoformat()
                file_info['pid'] = pid
                queue_data['current'] = filename
                break

        self._save_queue(queue_data)
        logger.info(f"File marked as processing: {filename} (PID: {pid})")

    def mark_completed(self, filename: str, success: bool = True):
        """标记文件为已完成"""
        queue_data = self._load_queue()

        for file_info in queue_data['files']:
            if file_info['filename'] == filename:
                file_info['status'] = 'completed' if success else 'failed'
                file_info['completed_at'] = datetime.now().isoformat()
                break

        if queue_data['current'] == filename:
            queue_data['current'] = None

        self._save_queue(queue_data)
        logger.info(f"File marked as completed: {filename} (success: {success})")

    def get_status(self) -> Dict:
        """
        获取队列状态

        Returns:
            {
                'total': 总文件数,
                'pending': 待处理数,
                'processing': 处理中数,
                'completed': 已完成数,
                'current': 当前处理的文件,
                'queue': 队列详情
            }
        """
        queue_data = self._load_queue()

        pending = sum(1 for f in queue_data['files'] if f['status'] == 'pending')
        processing = sum(1 for f in queue_data['files'] if f['status'] == 'processing')
        completed = sum(1 for f in queue_data['files'] if f['status'] in ['completed', 'failed'])

        return {
            'total': len(queue_data['files']),
            'pending': pending,
            'processing': processing,
            'completed': completed,
            'current': queue_data['current'],
            'queue': queue_data['files']
        }

    def clear_completed(self):
        """清理已完成的文件记录"""
        queue_data = self._load_queue()
        queue_data['files'] = [f for f in queue_data['files'] if f['status'] not in ['completed', 'failed']]
        self._save_queue(queue_data)
        logger.info("Cleared completed files from queue")


class QueueProcessor:
    """队列处理器 - 后台线程逐个处理文件"""

    def __init__(self):
        self.queue = FileQueue()
        self.running = False
        self.thread = None
        self.python_path = '/opt/homebrew/bin/python3.13'

    def start(self):
        """启动队列处理器"""
        if self.running:
            logger.info("Queue processor already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
        logger.info("Queue processor started")

    def stop(self):
        """停止队列处理器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Queue processor stopped")

    def _is_import_running(self) -> bool:
        """检查是否有导入进程正在运行"""
        import subprocess
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'import_duoke_daily.py'],
                capture_output=True,
                text=True
            )
            return bool(result.stdout.strip())
        except Exception as e:
            logger.error(f"Failed to check import process: {e}")
            return False

    def _start_import(self, filepath: str) -> Optional[int]:
        """
        启动导入脚本

        Returns:
            进程 PID，如果失败返回 None
        """
        try:
            logger.info(f"Starting import for: {filepath}")

            process = subprocess.Popen(
                [self.python_path, str(IMPORT_SCRIPT)],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            logger.info(f"Import process started with PID: {process.pid}")
            return process.pid

        except Exception as e:
            logger.error(f"Failed to start import: {e}", exc_info=True)
            return None

    def _process_loop(self):
        """队列处理主循环"""
        logger.info("Queue processor loop started")

        while self.running:
            try:
                # 检查是否有导入进程在运行
                if self._is_import_running():
                    # 有进程在运行，等待
                    time.sleep(30)  # 每30秒检查一次
                    continue

                # 没有进程在运行，检查队列
                next_file = self.queue.get_next_pending()

                if next_file:
                    # 有待处理文件，启动导入
                    filename = next_file['filename']
                    filepath = next_file['filepath']

                    logger.info(f"Processing next file from queue: {filename}")

                    pid = self._start_import(filepath)

                    if pid:
                        self.queue.mark_processing(filename, pid)
                        # 等待进程完成
                        time.sleep(10)  # 给进程一点启动时间
                    else:
                        # 启动失败
                        self.queue.mark_completed(filename, success=False)
                        logger.error(f"Failed to start import for: {filename}")
                else:
                    # 队列为空，等待
                    time.sleep(60)  # 队列空时，每分钟检查一次

            except Exception as e:
                logger.error(f"Error in queue processor loop: {e}", exc_info=True)
                time.sleep(30)

        logger.info("Queue processor loop stopped")


def get_queue_processor() -> QueueProcessor:
    """获取全局队列处理器实例（单例）"""
    global _queue_processor

    with _processor_lock:
        if _queue_processor is None:
            _queue_processor = QueueProcessor()
            _queue_processor.start()

        return _queue_processor


def add_file_to_queue(filename: str, filepath: Path) -> tuple[int, Dict]:
    """
    添加文件到队列并返回状态

    Returns:
        (队列位置, 队列状态)
    """
    processor = get_queue_processor()
    position = processor.queue.add_file(filename, filepath)
    status = processor.queue.get_status()

    return position, status
