# 多客数据自动导入系统

## 系统状态

**✅ 已配置并生效**（2026-05-17 19:49）

**测试验证：**
- ✅ 文件上传自动识别
- ✅ 自动下载（1.99 MB，耗时 4.5秒）
- ✅ 自动加入队列（第16位）
- ✅ 自动回复确认消息

**配置详情：** 见 [飞书Webhook配置指南](feishu-webhook-config-guide.md)

---

## 系统概览

飞书机器人现已支持**自动监听和导入**多客客服汇总文件。

### 工作流程

```
飞书群聊上传文件 (支持批量上传)
    ↓
机器人检测到 "汇总_YYYYMMDD_HHMM.xlsx"
    ↓
自动下载文件到 data/duoke/
    ↓
加入导入队列 (避免并发冲突)
    ↓
队列处理器逐个处理文件
    ↓
完成后自动归档 + 处理下一个
```

## 已实施功能

### 1. 文件自动监听

**监听范围:**
- 群聊: "多客智能客服消息"
- 文件格式: `汇总_YYYYMMDD_HHMM.xlsx`
- 其他文件自动忽略 (如: 胡雅倩_xxx.xlsx)

**代码实现:**
- `bot/file_handler.py` - 文件处理模块
- `bot/main.py` - 集成文件消息处理

### 2. 增强型 SKU 提取

**新增功能:**
- ✅ 从 JSON 提取 `skuValue` 字段
- ✅ 处理组合 SKU: `CBC004-1300/1306/1308` → 3个独立 SKU
- ✅ 支持多种格式: CBC004-1234, BRME0123, OSA813

**代码位置:**
```python
# scripts/import_duoke_daily.py
def extract_skus_from_text(text: str) -> list:
    # 1. 从 JSON 提取 skuValue
    # 2. 处理组合 SKU (斜杠分隔)
    # 3. 正则匹配其他格式
```

### 3. 文件导入队列系统

**核心特性:**
- ✅ 支持批量上传文件
- ✅ 自动排队逐个处理
- ✅ 避免并发冲突导致数据错乱
- ✅ 队列状态持久化
- ✅ 自动归档已处理文件

**触发条件:**
- 检测到汇总文件上传
- 文件名格式正确
- 文件成功下载

**执行过程:**
1. 下载文件到 `data/duoke/`
2. 加入导入队列
3. 队列处理器监控并逐个启动导入
4. 完成后自动归档，处理下一个

**导入统计:**
- 处理速度: ~35 条/分钟
- 3,152 条记录预计 90 分钟

**详细文档:** 参见 [队列系统文档](queue-system.md)

## 使用方式

### 日常操作

**1. 上传文件（支持批量）**
将多客汇总文件直接发送到飞书群 "多客智能客服消息"
- ✅ 支持一次上传多个文件
- ✅ 系统自动排队处理
- ✅ 避免手动等待

**2. 机器人自动响应**
```
📥 检测到多客汇总文件: 汇总_20260415_0800.xlsx
📊 文件大小: 1.60 MB
✅ 已加入队列 (第 3 个)
📋 队列状态: 待处理 15 | 处理中 1 | 已完成 2

💡 系统会自动逐个处理，每个文件约需 1.5 小时
💡 导入完成后可通过 @机器人 搜索客服对话
```

**3. 搜索使用**
导入完成后,客服可在群里 @机器人 搜索:
- SKU 搜索: `@机器人 CBC004-1300`
- 关键词搜索: `@机器人 客户投诉退货`

### 测试方法

**方式 1: 上传旧文件测试**
1. 从群聊历史下载旧的汇总文件
2. 删除数据库中对应日期的记录 (避免重复):
   ```python
   from scripts.utils import get_supabase_client
   client = get_supabase_client()
   client.table('knowledge_entries').delete().eq('source_group', '多客客服 - 0800').execute()
   ```
3. 重新上传文件到群聊
4. 观察机器人响应

**方式 2: 等待明天新文件**
等待群里发送新的汇总文件 (如 汇总_20260430_0800.xlsx)

## 系统状态

### 当前配置

**机器人服务:**
- 端口: 5001
- 状态: ✅ 运行中
- PID: 查看 `ps aux | grep "bot.main"`
- 日志: `/tmp/bot.log`

**Python 环境:**
- 版本: Python 3.13
- 位置: `/opt/homebrew/bin/python3.13`
- 依赖: Flask, lark-oapi, pandas, supabase

**当前导入进度:**
- 文件: 汇总_20260428_0800.xlsx
- 进度: 617/3152 (19.6%)
- 剩余: ~72 分钟

### 检查命令

```bash
# 检查机器人状态
curl http://localhost:5001/health

# 查看机器人日志
tail -f /tmp/bot.log

# 检查导入进程
ps aux | grep import_duoke_daily

# 查询已导入记录数
python3.13 -c "
from scripts.utils import get_supabase_client
client = get_supabase_client()
response = client.table('knowledge_entries').select('id', count='exact').eq('source_group', '多客客服 - 0800').execute()
print(f'已导入: {response.count} 条')
"
```

## 故障排查

### 机器人未响应

**检查列表:**
1. 机器人是否运行: `curl http://localhost:5001/health`
2. 端口是否被占用: `lsof -i :5001`
3. 查看日志: `tail -f /tmp/bot.log`

**重启机器人:**
```bash
# 停止旧进程
ps aux | grep "bot.main" | grep -v grep | awk '{print $2}' | xargs kill

# 启动新进程
/opt/homebrew/bin/python3.13 -m bot.main > /tmp/bot.log 2>&1 &
```

### 文件下载失败

**可能原因:**
1. 飞书权限不足 - 需要 `drive:drive:readonly` 权限
2. 文件 key 无效 - 检查日志中的 file_key
3. 网络问题 - 检查 Supabase 连接

**查看详细错误:**
```bash
tail -50 /tmp/bot.log | grep -i error
```

### 导入卡住或失败

**检查导入进程:**
```bash
ps aux | grep import_duoke_daily
```

**手动运行导入:**
```bash
cd /Users/cindy/Projects/product-knowledge-base
/opt/homebrew/bin/python3.13 scripts/import_duoke_daily.py
```

## 技术细节

### 飞书消息结构

**文件消息格式:**
```json
{
  "header": {
    "event_type": "im.message.receive_v1"
  },
  "event": {
    "message": {
      "message_type": "file",
      "content": "{\"file_key\":\"...\" ,\"file_name\":\"汇总_20260428_0800.xlsx\"}",
      "chat_type": "group",
      "chat_id": "oc_..."
    }
  }
}
```

### 文件下载 API

**Feishu Drive API:**
```python
from lark_oapi.api.drive.v1 import DownloadFileRequest

request = DownloadFileRequest.builder().file_token(file_key).build()
response = lark_client.drive.v1.file.download(request)
```

**权限要求:**
- `im.message.receive_v1` - 接收消息事件
- `drive:drive:readonly` - 下载文件

### SKU 提取算法

**JSON skuValue 提取:**
```python
# 匹配: 'skuValue': 'CBC004-1300/1306/1308'
json_sku_pattern = r"['\"]skuValue['\"]:\s*['\"]([A-Z0-9/-]+)['\"]"

# 处理组合格式
if '/' in sku_value:
    prefix = re.match(r'^([A-Z]+\d+-)', sku_value).group(1)  # CBC004-
    parts = sku_value.split('/')  # ['CBC004-1300', '1306', '1308']
    skus.add(parts[0])  # CBC004-1300
    for part in parts[1:]:
        if part.isdigit():
            skus.add(prefix + part)  # CBC004-1306, CBC004-1308
```

## 下一步改进

### Phase 2 计划

1. **葡语翻译集成**
   - 使用 Google Translate API 或 deep-translator
   - 翻译客服对话为中文
   - 增强搜索准确性

2. **说明书内容提取**
   - 使用 python-docx 提取 Word 文档
   - 索引说明书文本内容
   - 参考: `docs/phase2-manual-content-extraction.md`

3. **导入状态通知优化**
   - 导入完成后发送通知
   - 显示导入统计 (新增/跳过/错误)
   - 提供数据质量报告

4. **队列管理优化**
   - Web 管理界面可视化队列
   - 支持优先级调整
   - 失败自动重试机制

## 维护记录

**2026-04-30:**
- ✅ 实施文件导入队列系统
- ✅ 支持批量上传文件自动排队
- ✅ 修复 IM API 文件下载问题
- ✅ 集成队列处理器到机器人服务
- ✅ 批量导入 18 个历史文件 (2026-03-12 至 2026-04-28)

**2026-04-29:**
- ✅ 实施自动文件监听和导入
- ✅ 增强 SKU 提取 (JSON + 组合格式)
- ✅ 配置 Python 3.13 环境
- ✅ 部署更新后的机器人服务

**已解决问题:**
1. SKU 提取不完整 - 组合格式只提取第一个
2. 手动导入流程繁琐 - 需要下载+运行脚本
3. 文件格式识别 - 只处理汇总文件
4. 并发导入冲突 - 多进程导致数据错乱
5. 文件下载失败 - 使用错误的 API (Drive vs IM)

**2026-05-17:**
- ✅ 完成飞书Webhook事件订阅配置
- ✅ 验证自动文件下载功能（测试成功）
- ✅ 批量导入 16 个历史文件 (2026-03 至 2026-05)
- ✅ 更新配置文档和使用指南

**测试记录:**
- 测试文件: 汇总_20260428_0800.xlsx (1.99 MB)
- 下载耗时: 4.5 秒
- 队列位置: 第 16 位
- 自动回复: ✅ 成功

---

## 📖 使用指南（2026-05-17更新）

### 日常使用

**在飞书多客群直接上传文件：**
1. 准备文件：确保文件名格式为 `汇总_YYYYMMDD_HHMM.xlsx`
2. 上传文件：拖拽或选择文件上传到群聊
3. 等待确认：机器人会在几秒内回复确认消息
4. 自动导入：文件自动加入队列并开始导入

**示例确认消息：**
```
📥 检测到多客汇总文件: 汇总_20260517_0800.xlsx
📊 文件大小: 1.5 MB
✅ 已加入队列 (第 1 个)
📋 队列状态: 待处理 0 | 处理中 1 | 已完成 0

💡 系统会自动逐个处理，每个文件约需 1.5 小时
💡 导入完成后可通过 @机器人 搜索客服对话
```

### 注意事项

**✅ 会自动处理的文件：**
- `汇总_20260517_0800.xlsx` ✅
- `汇总_20260518_1200.xlsx` ✅
- `汇总_20260519_0600.xlsx` ✅

**❌ 会被忽略的文件：**
- `张亚萍_20260517_0800.xlsx` ❌ (客服姓名开头)
- `summary.xlsx` ❌ (格式不符)
- `汇总_202605170800.xlsx` ❌ (缺少下划线)

### 监控导入进度

**查看队列状态：**
```bash
cat data/duoke/import_queue.json | jq '{total: (.files | length), current: .current, processing: ([.files[] | select(.status == "processing")] | length), pending: ([.files[] | select(.status == "pending")] | length)}'
```

**查看实时日志：**
```bash
tail -f /tmp/bot.log | grep -E "Received file|Downloaded|Queue"
```

**查看已导入记录数：**
```bash
python3.13 -c "
from scripts.utils import get_supabase_client
client = get_supabase_client()
response = client.table('knowledge_entries').select('id', count='exact').execute()
print(f'总记录数: {response.count}')
"
```

---

**创建时间**: 2026-04-29  
**最后更新**: 2026-05-17  
**作者**: Claude + Cindy  
**状态**: ✅ 已部署生产并验证
