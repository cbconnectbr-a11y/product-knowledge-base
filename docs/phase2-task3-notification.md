# Phase 2 Task 3: 导入状态通知优化

## 目标

导入完成后自动发送飞书通知，提供详细的导入统计和数据质量报告。

## 当前状态

**Phase 1 行为:**
- ✅ 文件加入队列时发送通知
- ❌ 导入完成后无通知
- ❌ 无导入统计信息
- ❌ 无数据质量反馈

**期望行为:**
- ✅ 导入开始时通知
- ✅ 导入完成后发送详细通知
- ✅ 显示导入统计
- ✅ 提供数据质量报告

## 通知内容设计

### 1. 导入开始通知（已有）

```
📥 检测到多客汇总文件: 汇总_20260415_0800.xlsx
📊 文件大小: 1.60 MB
✅ 已加入队列 (第 3 个)
📋 队列状态: 待处理 15 | 处理中 1 | 已完成 2
```

### 2. 导入完成通知（新增）

```
✅ 导入完成：汇总_20260415_0800.xlsx

📊 导入统计
   新增: 2,847 条
   跳过: 305 条（重复）
   错误: 0 条
   总计: 3,152 条

⏱️ 耗时统计
   开始: 2026-04-30 08:00:00
   完成: 2026-04-30 09:28:15
   耗时: 1小时28分15秒
   速度: 36 条/分钟

📈 数据质量
   SKU 提取成功率: 98.5%
   有效对话: 2,847 条
   空内容跳过: 0 条

🔍 可用操作
   @机器人 CBC004-1300  (SKU搜索)
   @机器人 客户退货      (关键词搜索)

📋 队列状态: 待处理 14 | 处理中 1 | 已完成 3
```

### 3. 导入失败通知（新增）

```
❌ 导入失败：汇总_20260415_0800.xlsx

⚠️ 错误信息
   类型: DatabaseConnectionError
   详情: Connection timeout to Supabase
   
📊 部分导入
   已导入: 1,234 条
   失败位置: 第 1,235 行
   
🔧 建议操作
   1. 检查网络连接
   2. 重新上传文件触发重试
   3. 查看日志: tail -f /tmp/bot.log

📋 队列状态: 已暂停，等待人工处理
```

## 技术实现

### 1. 修改导入脚本收集统计

**文件**: `scripts/import_duoke_daily.py`

```python
class ImportStats:
    """导入统计数据"""
    def __init__(self):
        self.file_name = ''
        self.start_time = None
        self.end_time = None
        self.total_rows = 0
        self.imported = 0
        self.skipped = 0
        self.errors = 0
        self.error_details = []
        self.sku_extracted = 0
        self.sku_failed = 0
        
    def to_dict(self):
        duration = (self.end_time - self.start_time).total_seconds()
        return {
            'file_name': self.file_name,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'duration_seconds': duration,
            'duration_formatted': self._format_duration(duration),
            'speed': self.imported / (duration / 60) if duration > 0 else 0,
            'total_rows': self.total_rows,
            'imported': self.imported,
            'skipped': self.skipped,
            'errors': self.errors,
            'error_details': self.error_details,
            'sku_success_rate': (self.sku_extracted / self.total_rows * 100) if self.total_rows > 0 else 0,
        }
    
    def _format_duration(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}小时{minutes}分{secs}秒"
        else:
            return f"{minutes}分{secs}秒"

def import_duoke_file(file_path: Path) -> ImportStats:
    """
    导入文件并返回统计信息
    
    Returns:
        ImportStats: 导入统计数据
    """
    stats = ImportStats()
    stats.file_name = file_path.name
    stats.start_time = datetime.now()
    
    try:
        # ... 导入逻辑 ...
        
        for idx, row in df.iterrows():
            stats.total_rows += 1
            
            try:
                # 处理记录
                entry = process_duoke_record(row, file_date)
                
                # 统计 SKU 提取
                if entry['sku']:
                    stats.sku_extracted += 1
                else:
                    stats.sku_failed += 1
                
                # 检查重复
                if check_duplicate(client, entry):
                    stats.skipped += 1
                    continue
                
                # 插入数据库
                response = client.table('knowledge_entries').insert(entry).execute()
                
                if response.data:
                    stats.imported += 1
                    
            except Exception as e:
                stats.errors += 1
                stats.error_details.append({
                    'row': idx + 2,
                    'error': str(e)
                })
                logger.error(f"处理第 {idx+2} 行失败: {e}")
                continue
        
        stats.end_time = datetime.now()
        return stats
        
    except Exception as e:
        stats.end_time = datetime.now()
        stats.error_details.append({
            'error': str(e),
            'fatal': True
        })
        return stats
```

### 2. 保存统计到文件

**文件**: `scripts/import_duoke_daily.py`

```python
STATS_DIR = PROJECT_ROOT / 'data' / 'duoke' / 'stats'

def save_import_stats(stats: ImportStats):
    """保存导入统计到 JSON 文件"""
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    
    # 文件名: stats_汇总_20260415_0800_20260430_083015.json
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    stats_file = STATS_DIR / f"stats_{Path(stats.file_name).stem}_{timestamp}.json"
    
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats.to_dict(), f, ensure_ascii=False, indent=2)
    
    logger.info(f"Import stats saved: {stats_file}")
    return stats_file

def main():
    # ... 现有代码 ...
    
    # 导入文件
    stats = import_duoke_file(excel_file)
    
    # 保存统计
    stats_file = save_import_stats(stats)
    
    # 记录统计文件路径（供队列管理器读取）
    logger.info(f"STATS_FILE:{stats_file}")
    
    if stats.imported > 0:
        logger.info("✅ 导入成功！")
        return 0
    else:
        logger.error("❌ 导入失败")
        return 1
```

### 3. 队列管理器检测完成并发送通知

**文件**: `bot/queue_manager.py`

```python
from bot.notification import send_import_completion_notification

class QueueProcessor:
    def _process_loop(self):
        """队列处理主循环"""
        while self.running:
            try:
                # 检查是否有导入进程在运行
                if self._is_import_running():
                    time.sleep(30)
                    continue
                
                # 检查最近完成的导入
                self._check_and_notify_completed()
                
                # 获取下一个待处理文件
                next_file = self.queue.get_next_pending()
                
                if next_file:
                    # 启动导入...
                    pass
                else:
                    time.sleep(60)
                    
            except Exception as e:
                logger.error(f"Error in queue processor loop: {e}")
                time.sleep(30)
    
    def _check_and_notify_completed(self):
        """检查并通知已完成的导入"""
        queue_data = self.queue._load_queue()
        
        for file_info in queue_data['files']:
            if file_info['status'] == 'processing':
                # 检查进程是否还在运行
                if not self._is_process_running(file_info['pid']):
                    # 进程已结束，读取统计信息
                    stats = self._load_import_stats(file_info['filename'])
                    
                    if stats:
                        # 发送完成通知
                        send_import_completion_notification(stats, success=True)
                        
                        # 标记为已完成
                        self.queue.mark_completed(file_info['filename'], success=True)
                    else:
                        # 未找到统计信息，可能失败
                        send_import_completion_notification(
                            {'filename': file_info['filename']},
                            success=False
                        )
                        self.queue.mark_completed(file_info['filename'], success=False)
    
    def _is_process_running(self, pid: int) -> bool:
        """检查进程是否在运行"""
        try:
            result = subprocess.run(
                ['ps', '-p', str(pid)],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except:
            return False
    
    def _load_import_stats(self, filename: str) -> dict:
        """加载导入统计文件"""
        stats_dir = Path('data/duoke/stats')
        
        # 查找最新的统计文件
        pattern = f"stats_{Path(filename).stem}_*.json"
        stats_files = list(stats_dir.glob(pattern))
        
        if not stats_files:
            return None
        
        # 获取最新的统计文件
        latest_stats = max(stats_files, key=lambda p: p.stat().st_mtime)
        
        with open(latest_stats, 'r', encoding='utf-8') as f:
            return json.load(f)
```

### 4. 飞书通知模块

**文件**: `bot/notification.py` (新建)

```python
"""
飞书通知模块
发送导入状态通知到飞书群聊
"""
import logging
from typing import Dict, Optional
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

logger = logging.getLogger(__name__)

# 默认通知群聊 ID（多客智能客服消息群）
DEFAULT_CHAT_ID = None  # 需要配置

def get_lark_client():
    """获取飞书客户端"""
    from bot.main import get_lark_client as _get_client
    return _get_client()

def send_message_to_chat(chat_id: str, message: str) -> bool:
    """
    发送消息到飞书群聊
    
    Args:
        chat_id: 群聊 ID
        message: 消息内容
        
    Returns:
        是否发送成功
    """
    try:
        client = get_lark_client()
        
        content = json.dumps({'text': message})
        
        request = CreateMessageRequest.builder() \
            .receive_id_type('chat_id') \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type('text')
                .content(content)
                .build()
            ) \
            .build()
        
        response = client.im.v1.message.create(request)
        
        if response.code == 0:
            logger.info(f"Notification sent to chat: {chat_id}")
            return True
        else:
            logger.error(f"Failed to send notification: {response.msg}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending notification: {e}", exc_info=True)
        return False

def format_completion_notification(stats: Dict, success: bool) -> str:
    """
    格式化导入完成通知
    
    Args:
        stats: 导入统计数据
        success: 是否成功
        
    Returns:
        格式化的通知消息
    """
    if not success:
        filename = stats.get('filename', '未知文件')
        return f"""❌ 导入失败：{filename}

⚠️ 进程异常终止，未找到导入统计信息

🔧 建议操作
   1. 查看日志: tail -100 /tmp/bot.log
   2. 检查数据库连接
   3. 重新上传文件触发重试
"""
    
    filename = stats.get('file_name', '未知文件')
    imported = stats.get('imported', 0)
    skipped = stats.get('skipped', 0)
    errors = stats.get('errors', 0)
    total = stats.get('total_rows', 0)
    duration = stats.get('duration_formatted', '未知')
    speed = stats.get('speed', 0)
    sku_rate = stats.get('sku_success_rate', 0)
    start_time = stats.get('start_time', '')[:19]
    end_time = stats.get('end_time', '')[:19]
    
    message = f"""✅ 导入完成：{filename}

📊 导入统计
   新增: {imported:,} 条
   跳过: {skipped:,} 条（重复）
   错误: {errors} 条
   总计: {total:,} 条

⏱️ 耗时统计
   开始: {start_time}
   完成: {end_time}
   耗时: {duration}
   速度: {speed:.1f} 条/分钟

📈 数据质量
   SKU 提取成功率: {sku_rate:.1f}%
   有效对话: {imported:,} 条

🔍 可用操作
   @机器人 CBC004-1300  (SKU搜索)
   @机器人 客户退货      (关键词搜索)
"""
    
    if errors > 0:
        error_details = stats.get('error_details', [])
        message += f"\n⚠️ 错误详情: 查看日志获取详细信息\n"
    
    return message

def send_import_completion_notification(stats: Dict, success: bool, chat_id: Optional[str] = None):
    """
    发送导入完成通知
    
    Args:
        stats: 导入统计数据
        success: 是否成功
        chat_id: 目标群聊 ID（可选，默认使用配置的群聊）
    """
    target_chat_id = chat_id or DEFAULT_CHAT_ID
    
    if not target_chat_id:
        logger.warning("No chat_id configured for notifications")
        return
    
    message = format_completion_notification(stats, success)
    send_message_to_chat(target_chat_id, message)
```

## 实施步骤

### 步骤 1: 修改导入脚本
- [ ] 添加 `ImportStats` 类
- [ ] 修改 `import_duoke_file()` 收集统计
- [ ] 实现 `save_import_stats()` 保存统计
- [ ] 测试统计收集功能

### 步骤 2: 创建通知模块
- [ ] 创建 `bot/notification.py`
- [ ] 实现消息发送函数
- [ ] 实现通知格式化函数
- [ ] 获取群聊 ID 配置

### 步骤 3: 更新队列管理器
- [ ] 添加完成检测逻辑
- [ ] 集成通知发送
- [ ] 测试完成通知流程

### 步骤 4: 测试验证
- [ ] 测试导入成功通知
- [ ] 测试导入失败通知
- [ ] 测试通知内容格式
- [ ] 验证不影响现有流程

## 配置需求

### 环境变量
```bash
# .env
NOTIFICATION_CHAT_ID=oc_xxx  # 通知群聊 ID
```

### 获取群聊 ID
```bash
# 方法 1: 从日志中查看
tail -f /tmp/bot.log | grep "chat_id"

# 方法 2: 在群里发送消息，查看webhook事件
```

## 测试计划

### 测试用例 1: 成功导入
1. 上传一个小文件（100条记录）
2. 等待导入完成
3. 验证收到完成通知
4. 检查统计数据准确性

### 测试用例 2: 部分失败
1. 构造有错误的 Excel 文件
2. 上传并等待导入
3. 验证错误统计
4. 检查通知包含错误提示

### 测试用例 3: 导入失败
1. 断开数据库连接
2. 触发导入
3. 验证失败通知
4. 检查建议操作提示

## 预期效果

**用户体验提升:**
- ✅ 清楚知道导入是否完成
- ✅ 了解导入数据质量
- ✅ 快速发现和处理问题
- ✅ 无需手动检查导入状态

**运维效率提升:**
- ✅ 自动化状态通知
- ✅ 数据质量监控
- ✅ 问题快速定位
- ✅ 完整的导入历史记录

## 工作量估算

- 导入脚本修改: 2-3 小时
- 通知模块开发: 2-3 小时
- 队列管理器更新: 1-2 小时
- 测试和调试: 2-3 小时
- **总计**: 7-11 小时（约 1 个工作日）

---

**创建时间**: 2026-04-30
**状态**: 设计完成，待实施
**优先级**: 高
**不影响**: 当前运行的导入队列
