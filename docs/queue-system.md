# 文件导入队列系统

## 系统概述

为解决多文件并发导入导致的数据冲突问题，实现了文件导入队列系统，支持批量上传文件，自动逐个处理。

## 核心功能

### 1. 队列管理

**特性:**
- ✅ 支持批量添加文件到队列
- ✅ 自动逐个处理，避免并发冲突
- ✅ 队列状态持久化 (JSON 文件)
- ✅ 进程监控和自动调度
- ✅ 文件处理完成后自动归档

**实现位置:**
- `bot/queue_manager.py` - 队列管理核心模块
- `bot/main.py` - 集成队列处理器启动
- `bot/file_handler.py` - 文件上传时加入队列

### 2. 队列处理流程

```
文件上传 → 下载到本地 → 加入队列
                              ↓
                        队列处理器检查
                              ↓
                    是否有进程在运行?
                    ↙           ↘
                 是 (等待)      否 (启动下一个)
                    ↓              ↓
               等待30秒         获取队列首个文件
                    ↓              ↓
                 重新检查        启动导入进程
                                  ↓
                            标记为"处理中"
                                  ↓
                            等待进程完成
                                  ↓
                            标记为"已完成"
                                  ↓
                            处理下一个文件
```

## 代码架构

### FileQueue 类

负责队列数据的增删改查：

```python
class FileQueue:
    def add_file(filename, filepath) -> int:
        """添加文件到队列，返回队列位置"""
        
    def get_next_pending() -> Dict:
        """获取下一个待处理的文件"""
        
    def mark_processing(filename, pid):
        """标记文件为处理中"""
        
    def mark_completed(filename, success=True):
        """标记文件为已完成/失败"""
        
    def get_status() -> Dict:
        """获取队列状态统计"""
        
    def clear_completed():
        """清理已完成的文件记录"""
```

### QueueProcessor 类

后台线程，负责监控队列并启动导入：

```python
class QueueProcessor:
    def start():
        """启动队列处理器（后台线程）"""
        
    def stop():
        """停止队列处理器"""
        
    def _is_import_running() -> bool:
        """检查是否有导入进程在运行"""
        
    def _start_import(filepath) -> int:
        """启动导入脚本，返回进程 PID"""
        
    def _process_loop():
        """队列处理主循环（后台线程）"""
```

### 关键函数

```python
def get_queue_processor() -> QueueProcessor:
    """获取全局队列处理器实例（单例模式）"""

def add_file_to_queue(filename, filepath) -> tuple[int, Dict]:
    """添加文件到队列并返回状态"""
```

## 队列状态文件

**位置:** `data/duoke/import_queue.json`

**格式:**
```json
{
  "files": [
    {
      "filename": "汇总_20260312_0600.xlsx",
      "filepath": "data/duoke/汇总_20260312_0600.xlsx",
      "status": "pending",      // pending | processing | completed | failed
      "added_at": "2026-04-30T07:00:00",
      "started_at": null,
      "completed_at": null,
      "pid": null
    }
  ],
  "current": "汇总_20260312_0600.xlsx"  // 当前处理的文件名
}
```

## 使用方式

### 方式 1: 通过飞书上传（推荐）

直接在飞书群或私聊中上传多个文件，系统自动：
1. 下载文件
2. 加入队列
3. 发送状态通知

**示例响应:**
```
📥 检测到多客汇总文件: 汇总_20260415_0800.xlsx
📊 文件大小: 1.60 MB
✅ 已加入队列 (第 3 个)
📋 队列状态: 待处理 15 | 处理中 1 | 已完成 2

💡 系统会自动逐个处理，每个文件约需 1.5 小时
💡 导入完成后可通过 @机器人 搜索客服对话
```

### 方式 2: 手动批量添加

将文件放入 `data/duoke/` 目录，然后运行：

```python
from bot.queue_manager import add_file_to_queue
from pathlib import Path

data_dir = Path('data/duoke')
files = sorted(data_dir.glob('*.xlsx'))

for filepath in files:
    position, status = add_file_to_queue(filepath.name, filepath)
    print(f'{filepath.name} - 队列位置 {position}')
```

## 监控和管理

### 检查队列状态

```python
from bot.queue_manager import FileQueue

queue = FileQueue()
status = queue.get_status()

print(f"总数: {status['total']}")
print(f"待处理: {status['pending']}")
print(f"处理中: {status['processing']}")
print(f"已完成: {status['completed']}")
print(f"当前: {status['current']}")
```

### 检查导入进程

```bash
# 查看导入进程
ps aux | grep import_duoke_daily

# 查看机器人日志
tail -f /tmp/bot.log

# 查看队列文件
cat data/duoke/import_queue.json | jq
```

### 清理已完成记录

```python
from bot.queue_manager import FileQueue

queue = FileQueue()
queue.clear_completed()
```

## 当前部署状态

### 2026-04-30 配置

**队列中的文件:** 18 个文件 (2026-03-12 至 2026-04-28)

```
批次 1: 2026-03-12 至 2026-03-16 (4个文件)
批次 2: 2026-04-07 至 2026-04-28 (14个文件)
```

**处理进度:**
- 开始时间: 2026-04-30 07:05
- 当前处理: 汇总_20260312_0600.xlsx
- 预计完成: 2026-05-01 10:00 (约27小时)

**系统配置:**
- 机器人端口: 5001
- Python 环境: Python 3.13
- 队列处理器: 后台线程，随机器人启动

## 技术细节

### 进程检测

使用 `pgrep` 命令检测导入进程：

```python
result = subprocess.run(
    ['pgrep', '-f', 'import_duoke_daily.py'],
    capture_output=True,
    text=True
)
is_running = bool(result.stdout.strip())
```

### 后台线程

队列处理器运行在 daemon 线程中：

```python
self.thread = threading.Thread(target=self._process_loop, daemon=True)
self.thread.start()
```

**特性:**
- daemon=True: 主进程退出时自动终止
- 30秒检查间隔（有进程运行时）
- 60秒检查间隔（队列为空时）

### 单例模式

全局唯一的队列处理器实例：

```python
_queue_processor = None
_processor_lock = threading.Lock()

def get_queue_processor():
    global _queue_processor
    with _processor_lock:
        if _queue_processor is None:
            _queue_processor = QueueProcessor()
            _queue_processor.start()
        return _queue_processor
```

## 故障排查

### 队列处理器未启动

**症状:** 文件加入队列后没有开始处理

**解决方法:**
```bash
# 重启机器人
ps aux | grep "bot.main" | grep -v grep | awk '{print $2}' | xargs kill
/opt/homebrew/bin/python3.13 -m bot.main > /tmp/bot.log 2>&1 &

# 检查日志
tail -f /tmp/bot.log | grep "Queue processor"
```

### 多个导入进程并发

**症状:** `ps aux | grep import_duoke_daily` 显示多个进程

**原因:** 队列系统实施前上传的文件

**解决方法:**
```bash
# 停止所有导入进程
ps aux | grep import_duoke_daily | grep -v grep | awk '{print $2}' | xargs kill -9

# 重新加入队列（参考上面"手动批量添加"部分）
```

### 队列状态文件损坏

**症状:** 队列处理器报错或状态异常

**解决方法:**
```bash
# 备份现有队列文件
cp data/duoke/import_queue.json data/duoke/import_queue.json.bak

# 重置队列
rm data/duoke/import_queue.json

# 重新添加文件到队列
```

## 未来改进

### Phase 2 计划

1. **队列状态通知**
   - 每个文件完成后发送飞书通知
   - 包含导入统计（新增/跳过/错误）
   - 队列进度更新

2. **Web 管理界面**
   - 可视化队列状态
   - 手动调整队列顺序
   - 暂停/恢复/重试功能

3. **优先级队列**
   - 支持紧急文件优先处理
   - 根据文件大小调整顺序

4. **失败重试**
   - 自动重试失败的文件
   - 配置重试次数和间隔

5. **并发处理优化**
   - 支持多个导入进程（数据库锁机制）
   - 根据服务器资源动态调整并发数

## 相关文档

- [自动导入系统设置](auto-import-setup.md) - 完整系统配置
- [SKU 提取增强](../scripts/import_duoke_daily.py) - 导入脚本实现

---

**创建时间**: 2026-04-30  
**作者**: Claude + Cindy  
**状态**: ✅ 已部署生产
