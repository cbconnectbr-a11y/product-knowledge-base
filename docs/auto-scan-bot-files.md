# 机器人文件自动扫描功能

## 概述

解决机器人发送的汇总文件无法自动导入的问题。系统通过 **Webhook记录 + 定时扫描** 的方式，实现完全自动化的文件处理。

## 问题背景

### 原有问题

- Webhook配置为忽略所有机器人消息（防止消息循环）
- "多客每日客诉消息推送"机器人发送的文件被忽略
- 需要手动下载并重新上传才能触发导入

### 解决方案

**两阶段处理：**
1. **Webhook阶段** - 检测机器人文件并记录到待处理列表
2. **定时扫描阶段** - 每天11:00自动下载并加入队列

## 系统架构

```
机器人发送文件
    ↓
Webhook检测 (bot/main.py)
    ↓
记录到 pending_downloads.json
    ↓
定时任务触发 (每天11:00)
    ↓
扫描脚本 (scripts/scan_feishu_files.py)
    ↓
下载文件 + 加入队列
    ↓
自动导入处理
```

## 核心文件

### 1. Webhook处理 - bot/main.py

**修改内容：**
```python
# 特殊处理：机器人发送的汇总文件记录到pending list
if (sender_type == 'app' or sender_type == 'bot') and message_type == 'file':
    try:
        from bot.file_handler import is_duoke_summary_file
        from scripts.scan_feishu_files import add_pending_file

        content_json = json.loads(content_str)
        file_name = content_json.get('file_name', '')
        file_key = content_json.get('file_key')

        if is_duoke_summary_file(file_name):
            add_pending_file(message_id, file_key, file_name, chat_id)
            logger.info(f"Bot file added to pending list: {file_name}")
        else:
            logger.info(f"Ignored non-summary file from bot: {file_name}")

    except Exception as e:
        logger.error(f"Error handling bot file: {e}", exc_info=True)

    return jsonify({'msg': 'ok'}), 200
```

**功能：**
- 检测机器人发送的文件消息
- 判断是否为汇总文件（格式：`汇总_YYYYMMDD_HHMM.xlsx`）
- 记录文件信息到 `pending_downloads.json`

### 2. 扫描脚本 - scripts/scan_feishu_files.py

**主要功能：**

#### `add_pending_file(message_id, file_key, filename, chat_id)`
从webhook调用，添加文件到待处理列表

**参数：**
- `message_id` - 飞书消息ID
- `file_key` - 文件key（用于下载）
- `filename` - 文件名
- `chat_id` - 群聊ID

**记录格式：**
```json
{
  "message_id": "om_xxx",
  "file_key": "file_v3_xxx",
  "filename": "汇总_20260518_0800.xlsx",
  "chat_id": "oc_xxx",
  "added_at": "2026-05-19T04:25:58.426993"
}
```

#### `scan_and_download()`
定时任务主函数，处理待下载文件

**流程：**
1. 加载 `pending_downloads.json`
2. 检查本地已有文件（去重）
3. 下载新文件
4. 加入导入队列
5. 清理已处理的记录

### 3. 待处理列表 - data/duoke/pending_downloads.json

**存储位置：**
```
/Users/cindy/Projects/product-knowledge-base/data/duoke/pending_downloads.json
```

**数据结构：**
```json
[
  {
    "message_id": "om_x100b6f8313e468a4b301ed42ed7eaec",
    "file_key": "file_v3_0011r_fdbf1dae-f6f6-4580-b056-0d6527be371g",
    "filename": "汇总_20260519_0800.xlsx",
    "chat_id": "oc_f84dfdd1b3d52a84f2cafb54044435d8",
    "added_at": "2026-05-19T08:08:15.123456"
  }
]
```

## 定时任务配置

### Cron设置

**任务内容：**
```bash
0 11 * * * /opt/homebrew/bin/python3.13 /Users/cindy/Projects/product-knowledge-base/scripts/scan_feishu_files.py >> /Users/cindy/Projects/product-knowledge-base/logs/scan_feishu_files.log 2>&1
```

**执行时间：** 每天 11:00

**日志位置：** `logs/scan_feishu_files.log`

### 查看/修改Cron任务

```bash
# 查看当前任务
crontab -l

# 编辑任务
crontab -e

# 查看任务日志
tail -f /Users/cindy/Projects/product-knowledge-base/logs/scan_feishu_files.log
```

## 使用说明

### 自动模式（推荐）

**无需任何操作！**

1. 机器人发送文件到群
2. Webhook自动记录
3. 每天11:00自动下载处理

### 手动触发

如果需要立即处理pending list：

```bash
cd /Users/cindy/Projects/product-knowledge-base
/opt/homebrew/bin/python3.13 scripts/scan_feishu_files.py
```

### 查看待处理列表

```bash
cat data/duoke/pending_downloads.json | jq
```

## 日志说明

### Webhook日志 - /tmp/bot.log

**机器人文件记录：**
```
2026-05-19 08:08:15,123 - __main__ - INFO - Received file: 汇总_20260519_0800.xlsx (key: file_v3_xxx)
2026-05-19 08:08:15,124 - __main__ - INFO - Bot file added to pending list: 汇总_20260519_0800.xlsx
```

### 扫描日志 - logs/scan_feishu_files.log

**扫描执行：**
```
2026-05-19 11:00:01,123 - __main__ - INFO - ============================================================
2026-05-19 11:00:01,123 - __main__ - INFO - Starting file download scan
2026-05-19 11:00:01,123 - __main__ - INFO - ============================================================
2026-05-19 11:00:01,124 - __main__ - INFO - Found 1 pending files
2026-05-19 11:00:01,125 - __main__ - INFO - Processing: 汇总_20260519_0800.xlsx
2026-05-19 11:00:03,456 - bot.file_handler - INFO - File downloaded successfully: ...
2026-05-19 11:00:03,457 - bot.queue_manager - INFO - File added to queue: ... (position: 5)
2026-05-19 11:00:03,458 - __main__ - INFO - ✅ 汇总_20260519_0800.xlsx added to queue (position: 5)
2026-05-19 11:00:03,459 - __main__ - INFO - Removed 1 processed files from pending list
2026-05-19 11:00:03,460 - __main__ - INFO - ============================================================
2026-05-19 11:00:03,460 - __main__ - INFO - Scan completed
2026-05-19 11:00:03,460 - __main__ - INFO - ✅ Success: 1
2026-05-19 11:00:03,460 - __main__ - INFO - ❌ Failed: 0
2026-05-19 11:00:03,460 - __main__ - INFO - 📋 Remaining in pending list: 0
2026-05-19 11:00:03,460 - __main__ - INFO - ============================================================
```

## 故障排查

### 1. 机器人文件未记录

**检查：**
```bash
# 查看webhook日志
tail -100 /tmp/bot.log | grep "Bot file"

# 检查pending list
cat data/duoke/pending_downloads.json
```

**可能原因：**
- 文件名格式不匹配（必须是 `汇总_YYYYMMDD_HHMM.xlsx`）
- Webhook服务未运行
- 文件不在监控的群里

### 2. 定时任务未执行

**检查：**
```bash
# 查看cron任务
crontab -l | grep scan_feishu_files

# 查看执行日志
tail -50 logs/scan_feishu_files.log

# 查看系统日志
grep CRON /var/log/system.log | grep scan_feishu_files
```

**可能原因：**
- Cron服务未启动
- Python路径错误
- 权限问题

### 3. 文件下载失败

**检查：**
```bash
# 查看扫描日志
tail -100 logs/scan_feishu_files.log | grep "Failed"

# 手动测试下载
/opt/homebrew/bin/python3.13 scripts/scan_feishu_files.py
```

**可能原因：**
- 飞书API权限不足
- message_id或file_key过期
- 网络连接问题

## 优势对比

### 旧方案：手动上传

❌ 每次需要手动操作  
❌ 容易遗漏  
❌ 效率低  

### 新方案：自动扫描

✅ 完全自动化  
✅ 无需人工干预  
✅ 可靠稳定  
✅ 日志可追溯  

## 技术细节

### 文件去重机制

**检查范围：**
- `data/duoke/` - 待处理文件
- `data/duoke/archive/` - 已归档文件

**去重逻辑：**
```python
local_files = set()
if DATA_DIR.exists():
    for f in DATA_DIR.glob("汇总_*.xlsx"):
        local_files.add(f.name)

archive_dir = DATA_DIR / 'archive'
if archive_dir.exists():
    for f in archive_dir.glob("汇总_*.xlsx"):
        local_files.add(f.name)

# 过滤已存在的文件
new_files = [f for f in pending_files if f['filename'] not in local_files]
```

### 错误处理

**失败重试：**
- 下载失败的文件保留在pending list
- 下次扫描时自动重试
- 最大保留时间：无限制（直到成功）

**日志记录：**
- 成功/失败统计
- 详细错误信息
- 处理文件列表

## 维护建议

### 定期检查

**每周：**
- 查看pending list大小
- 检查扫描日志是否有错误
- 清理过期的pending记录（如果有）

**每月：**
- 检查日志文件大小
- 归档历史日志

### 日志清理

```bash
# 清理30天前的日志（可选）
find logs/ -name "scan_feishu_files.log.*" -mtime +30 -delete
```

## 配置变量

**目标群聊ID：**
```python
TARGET_CHAT_ID = "oc_f84dfdd1b3d52a84f2cafb54044435d8"
```

如果需要监控其他群，修改此变量。

**定时时间：**
```bash
# 修改cron表达式
0 11 * * *  # 每天11:00
0 */6 * * * # 每6小时
0 8,20 * * * # 每天8:00和20:00
```

## 扩展功能建议

### 未来可添加

1. **多群监控** - 支持监控多个群聊
2. **实时下载** - 收到文件后立即下载（不等定时任务）
3. **下载失败通知** - 失败时发送飞书通知
4. **文件分类** - 根据日期自动分类存储
5. **统计报表** - 每日导入文件统计

## 相关文档

- [自动导入系统](auto-import-setup.md)
- [队列系统详解](queue-system.md)
- [飞书Webhook配置](feishu-webhook-config-guide.md)

---

**创建日期：** 2026-05-19  
**维护者：** Cindy + Claude  
**版本：** 1.0
