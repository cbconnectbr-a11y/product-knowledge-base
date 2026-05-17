# 产品知识库系统 - Claude 工作指引

## 项目概述

电商公司产品知识库系统，通过飞书机器人为客服提供快速查询产品信息和技术问题解答。

**核心功能:**
- 📥 自动监听飞书文件上传，导入多客客服对话数据
- 🔍 支持 SKU 和关键词搜索
- 🤖 基于 DeepSeek/GPT-4o 的 RAG 智能问答
- 💬 智能追问与对话上下文管理（记忆最近3轮对话）
- 🌐 多语言自动切换（中文/葡萄牙语）
- 📋 批量文件导入队列系统
- 🎯 AI建议答案审核机制

## 系统架构

```
飞书机器人 (Flask)
    ├─ 消息监听 (bot/main.py)
    ├─ 文件处理 (bot/file_handler.py)
    ├─ 队列管理 (bot/queue_manager.py)
    └─ 知识搜索 + RAG (bot/handlers.py)
          ↓
Supabase 数据库 (knowledge_entries)
    ├─ 客服对话记录
    ├─ SKU 索引
    └─ 向量嵌入
```

## 关键文件

### 核心模块
- `bot/main.py` - 飞书 Webhook 服务 (Port 5001)
- `bot/handlers.py` - 消息处理、RAG 搜索、追问识别
- `bot/rag.py` - RAG 智能问答（DeepSeek/GPT-4o）
- `bot/session_manager.py` - 对话上下文管理 ⭐
- `bot/ai_suggestion.py` - AI建议答案生成
- `bot/card_messages.py` - 飞书交互卡片
- `bot/card_handler.py` - 卡片回调处理
- `bot/file_handler.py` - 文件监听和下载
- `bot/queue_manager.py` - 导入队列管理
- `scripts/import_duoke_daily.py` - 数据导入脚本
- `scripts/utils.py` - 工具函数（SKU提取、语言检测）

### 配置文件
- `.env` - 环境变量 (飞书/Supabase/OpenAI 密钥)
- `bot/config.py` - 配置管理
- `.claude/settings.json` - Claude Code 权限配置

### 文档
- `docs/auto-import-setup.md` - 自动导入系统文档
- `docs/queue-system.md` - 队列系统详解
- `docs/system-status-2026-04-30.md` - 系统状态总览

## 工作流程规范

### 1. 开发前检查

运行检查点脚本验证系统状态:
```bash
./.claude/checkpoint.sh
```

检查项:
- ✅ 机器人服务是否运行
- ✅ 队列处理器是否正常
- ✅ 导入进程状态
- ✅ 数据库连接

### 2. 代码修改规则

**允许操作:**
- ✅ 读取任何项目文件
- ✅ 编辑代码和文档
- ✅ 运行 Python 脚本
- ✅ Git 常规操作 (status/diff/log/add/commit/push)
- ✅ 运行检查点脚本

**禁止操作:**
- ❌ 破坏性 Git 操作 (force push, reset --hard)
- ❌ 删除命令 (rm -rf)
- ❌ Sudo 权限命令

**重要提醒:**
- 修改 bot/ 目录代码后必须重启机器人服务
- 修改队列系统后检查是否有导入进程在运行
- 不要手动编辑 `data/duoke/import_queue.json`

### 3. 重启服务流程

```bash
# 1. 停止旧服务
ps aux | grep "bot.main" | grep -v grep | awk '{print $2}' | xargs kill

# 2. 启动新服务
/opt/homebrew/bin/python3.13 -m bot.main > /tmp/bot.log 2>&1 &

# 3. 验证启动
sleep 2 && curl http://localhost:5001/health

# 4. 查看日志
tail -f /tmp/bot.log
```

### 4. Git 提交规范

**Commit 格式:**
```
<type>: <简短描述>

<详细说明>
- 列表项1
- 列表项2

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

**Type 类型:**
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `refactor`: 重构
- `chore`: 配置/构建变更

**提交前检查:**
- [ ] 代码已测试
- [ ] 文档已更新
- [ ] 不包含敏感信息 (.env, keys)
- [ ] 不包含数据文件 (*.xlsx, *.json)

### 5. 故障排查流程

**机器人无响应:**
1. 检查服务: `curl http://localhost:5001/health`
2. 查看日志: `tail -100 /tmp/bot.log`
3. 检查进程: `ps aux | grep bot.main`
4. 重启服务 (参考上面流程)

**队列卡住:**
1. 检查队列: `cat data/duoke/import_queue.json | jq`
2. 检查进程: `ps aux | grep import_duoke_daily`
3. 查看日志: `tail -f /tmp/bot.log | grep Queue`

**导入失败:**
1. 查看进程运行时间: `ps -o etime,pid,command | grep import_duoke_daily`
2. 如果超过 3 小时: `kill -9 [PID]` (队列会自动继续)
3. 检查数据库连接: `python3.13 -c "from scripts.utils import get_supabase_client; get_supabase_client()"`

## 技术栈

### 后端
- **Python 3.13** - 主要开发语言
- **Flask 3.1.0** - Web 框架
- **lark-oapi 1.3.17** - 飞书 SDK
- **pandas 2.2.3** - Excel 处理
- **supabase 2.11.0** - 数据库客户端
- **openai 1.57.4** - GPT-4o API

### 数据库
- **Supabase (PostgreSQL)** - 主数据库
- **pgvector** - 向量搜索

### 第三方服务
- **飞书开放平台** - 机器人和文件 API
- **OpenAI GPT-4o** - RAG 问答

## 环境变量

必需配置 (`.env` 文件):
```bash
# Feishu App
FEISHU_APP_ID=cli_***
FEISHU_APP_SECRET=***
FEISHU_VERIFICATION_TOKEN=***
FEISHU_ENCRYPT_KEY=***

# Supabase
SUPABASE_URL=https://[project].supabase.co
SUPABASE_KEY=***

# OpenAI
OPENAI_API_KEY=sk-***
```

## 数据流

### 文件导入流程
```
1. 用户上传 Excel → 飞书群聊
2. Webhook 触发 → bot/main.py 接收事件
3. 文件处理 → bot/file_handler.py 下载文件
4. 加入队列 → bot/queue_manager.py 排队
5. 逐个处理 → scripts/import_duoke_daily.py 导入
6. 写入数据库 → Supabase knowledge_entries 表
7. 自动归档 → data/duoke/archive/
```

### 搜索查询流程
```
1. 用户 @机器人 + 查询词
2. 消息处理 → bot/handlers.py
3. Embedding → OpenAI API 生成向量
4. 向量搜索 → Supabase pgvector
5. 上下文构建 → 检索相关记录
6. GPT-4o 生成 → 返回答案
7. 格式化回复 → 发送到飞书
```

## 常用命令

### 系统监控
```bash
# 检查所有状态
./.claude/checkpoint.sh

# 查看机器人日志
tail -f /tmp/bot.log

# 查看队列状态
cat data/duoke/import_queue.json | jq

# 查看导入进程
ps aux | grep import_duoke_daily

# 查询数据库记录数
python3.13 -c "
from scripts.utils import get_supabase_client
client = get_supabase_client()
response = client.table('knowledge_entries').select('id', count='exact').execute()
print(f'总记录数: {response.count}')
"
```

### 手动操作
```bash
# 手动运行导入
cd /Users/cindy/Projects/product-knowledge-base
/opt/homebrew/bin/python3.13 scripts/import_duoke_daily.py

# 清理已完成队列
python3.13 -c "
from bot.queue_manager import FileQueue
queue = FileQueue()
queue.clear_completed()
"
```

## 开发注意事项

### 1. 并发控制
- ❗ 导入脚本同时只能运行 1 个进程
- ❗ 多进程并发会导致数据冲突
- ✅ 使用队列系统自动控制并发

### 2. 文件处理
- 文件名格式必须匹配: `汇总_YYYYMMDD_HHMM.xlsx`
- 其他格式文件自动忽略
- Excel 列名映射在 `import_duoke_daily.py` 中定义

### 3. SKU 提取
支持多种格式:
- JSON: `'skuValue': 'CBC004-1300'`
- 组合: `CBC004-1300/1306/1308` → 3 个独立 SKU
- 标准: `CBC004-1234`, `BRME0123`, `OSA813`

### 4. 去重机制
- 基于 `title` + `source_group` 检查重复
- 导入前自动跳过已存在记录
- 支持增量更新

### 5. 性能考虑
- 导入速度: ~35 条/分钟
- 单文件 (3000 条): ~90 分钟
- 内存占用: ~50 MB per process

## 部署信息

### 运行环境
- **服务器**: 本地 Mac (macOS 14.3)
- **Python**: 3.13.12 (`/opt/homebrew/bin/python3.13`)
- **工作目录**: `/Users/cindy/Projects/product-knowledge-base/`
- **日志位置**: `/tmp/bot.log`

### 服务状态
- **机器人**: Port 5001 (自动启动)
- **队列处理器**: 后台线程 (随机器人启动)
- **ngrok 隧道**: `https://gripier-jonas-wannest.ngrok-free.dev` (Webhook URL)

## 文档资源

- 📖 [对话上下文与追问功能](docs/conversation-context-feature.md) ⭐ NEW
- 📖 [自动导入系统](docs/auto-import-setup.md)
- 📖 [队列系统详解](docs/queue-system.md)
- 📖 [系统状态总览](docs/system-status-2026-04-30.md)
- 📖 [Phase 2 规划](docs/phase2-manual-content-extraction.md)

## 联系与支持

- **项目路径**: `/Users/cindy/Projects/product-knowledge-base/`
- **Git 仓库**: (本地)
- **维护**: Cindy + Claude

---

**最后更新**: 2026-04-30  
**文档版本**: 1.0  
**Claude Code 版本**: 支持
