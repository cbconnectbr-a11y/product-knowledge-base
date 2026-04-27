# 部署指南

本文档详细介绍如何在 macOS 环境下部署和配置产品知识库系统。

## 目录

1. [系统概述](#系统概述)
2. [环境要求](#环境要求)
3. [安装步骤](#安装步骤)
4. [数据库初始化](#数据库初始化)
5. [飞书应用配置](#飞书应用配置)
6. [定时任务配置](#定时任务配置)
7. [启动服务](#启动服务)
8. [验证部署](#验证部署)
9. [故障排查](#故障排查)

---

## 系统概述

产品知识库系统是为电商客服团队设计的技术支持平台，主要功能包括：

- **数据采集**：自动从飞书多维表格和群聊采集产品信息与技术问答
- **智能搜索**：支持 SKU 精确匹配、关键词全文搜索、模糊匹配
- **飞书机器人**：通过飞书 Webhook 提供实时查询服务
- **管理界面**：使用飞书多维表格进行知识条目审核
- **定时同步**：通过 launchd 自动同步数据

**技术架构**：
```
飞书产品表 ──┐
             │
飞书群聊 ────┼──> Python 同步脚本 ──> Supabase PostgreSQL
             │                            │
历史数据 ────┘                            │
                                          ↓
                                    搜索引擎 (tsvector)
                                          │
                                          ↓
                           飞书机器人 Webhook 服务 (Flask)
                                          │
                                          ↓
                                      客服用户
```

---

## 环境要求

### 必需软件

- **Python**: 3.9 或更高版本
- **pip**: Python 包管理器
- **Git**: 版本控制
- **macOS**: 10.15 或更高版本（用于 launchd）

验证 Python 版本：
```bash
python3 --version
# 应输出: Python 3.9.x 或更高
```

### 外部服务

1. **Supabase 账号**
   - 免费账号即可（Phase 1 数据量较小）
   - 访问 https://supabase.com 注册

2. **飞书企业账号**
   - 需要企业管理员权限创建应用
   - 访问 https://open.feishu.cn

### 网络要求

- 能够访问 Supabase API (https://*.supabase.co)
- 能够访问飞书 API (https://open.feishu.cn)
- 如果使用 Webhook，需要公网可访问的地址（或使用 ngrok）

---

## 安装步骤

### 1. 克隆仓库

```bash
# 进入项目目录
cd ~/Projects

# 克隆代码（如果是 Git 仓库）
git clone <repository-url> product-knowledge-base

# 或者直接使用现有目录
cd ~/Projects/product-knowledge-base
```

### 2. 创建 Python 虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 验证虚拟环境
which python3
# 应输出: /Users/cindy/Projects/product-knowledge-base/venv/bin/python3
```

### 3. 安装 Python 依赖

```bash
# 安装所有依赖
pip install -r requirements.txt

# 验证关键包
python3 -c "import supabase; import lark_oapi; import flask; print('All packages installed successfully')"
```

**依赖说明**（来自 requirements.txt）：
- `supabase>=2.0.0` - Supabase 数据库客户端
- `lark-oapi>=1.2.0` - 飞书 API SDK
- `flask>=2.3.0` - Webhook 服务框架
- `python-dotenv>=1.0.0` - 环境变量管理
- `pytest>=7.4.0` - 测试框架

---

## 环境配置

### 1. 创建 .env 文件

```bash
# 复制示例文件
cp .env.example .env

# 编辑配置
vim .env  # 或使用其他编辑器
```

### 2. 配置 Supabase

登录 [Supabase Dashboard](https://app.supabase.com)：

1. 创建新项目（或使用现有项目）
2. 进入 **Settings → API**
3. 复制以下凭证：
   - **Project URL** → `SUPABASE_URL`
   - **anon/public key** → `SUPABASE_KEY`
   - **service_role key** → `SUPABASE_SERVICE_KEY`

在 `.env` 中填入：
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # anon key
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # service_role key
```

### 3. 配置飞书应用

访问 [飞书开放平台](https://open.feishu.cn)：

#### 创建企业自建应用

1. 点击"企业自建应用" → "创建应用"
2. 填写应用名称（如"产品知识库机器人"）
3. 上传应用图标
4. 提交审核（通常几分钟内通过）

#### 获取凭证

在应用详情页：
1. 进入 **凭证与基础信息**
2. 复制 **App ID** → `FEISHU_APP_ID`
3. 复制 **App Secret** → `FEISHU_APP_SECRET`
4. 复制 **Verification Token** → `FEISHU_VERIFICATION_TOKEN`
5. （可选）如需加密，启用并复制 **Encrypt Key** → `FEISHU_ENCRYPT_KEY`

在 `.env` 中填入：
```bash
FEISHU_APP_ID=cli_a1b2c3d4e5f6g7h8
FEISHU_APP_SECRET=abc123def456ghi789jkl012mno345pq
FEISHU_VERIFICATION_TOKEN=xyz789abc123def456ghi789jkl012mn
FEISHU_ENCRYPT_KEY=encrypt_key_here  # 可选
```

### 4. 配置飞书产品表

如果需要同步产品信息表：

1. 在飞书中打开产品信息多维表格
2. 点击右上角 **...** → **设置** → **高级设置**
3. 复制 **App Token** 和 **Table ID**

在 `.env` 中填入：
```bash
FEISHU_PRODUCT_TABLE_APP_TOKEN=ZyWlbAtWLaLtw9sTpxscAGGSnub
FEISHU_PRODUCT_TABLE_TABLE_ID=tbl1Zq6Sw6B5tP9x
```

### 5. 配置飞书管理表

用于知识库审核的飞书表格（详见 [管理指南](management_guide.md)）：

```bash
FEISHU_MANAGEMENT_APP_TOKEN=your-management-app-token-here
FEISHU_MANAGEMENT_TABLE_ID=your-management-table-id-here
```

### 6. 配置技术群组（可选）

如需从飞书群组采集技术问答：

```bash
FEISHU_TECH_GROUPS=oc_abc123def456,oc_xyz789ghi012
```

### 7. 验证配置

```bash
# 测试数据库连接
python3 database/test_connection.py

# 预期输出：
# ✓ Supabase credentials found
# ✓ Successfully connected to Supabase
# ✓ Database connection test passed
```

---

## 数据库初始化

### 1. 在 Supabase 中创建表

方法一：通过 Supabase Dashboard（推荐）

1. 登录 Supabase Dashboard
2. 选择项目 → **SQL Editor**
3. 打开本地文件 `database/schema.sql`
4. 复制全部内容粘贴到 SQL 编辑器
5. 点击 **Run** 执行

方法二：通过 psql 命令行

```bash
# 获取 Supabase 数据库连接字符串
# Dashboard → Settings → Database → Connection string (URI)

psql "postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres" \
  -f database/schema.sql
```

### 2. 验证表结构

在 Supabase Dashboard → **Table Editor** 中检查：
- ✓ `users` - 用户表
- ✓ `products` - 产品表
- ✓ `knowledge_entries` - 知识条目表
- ✓ `search_logs` - 搜索日志表

### 3. 验证索引

在 SQL Editor 中运行：
```sql
SELECT tablename, indexname 
FROM pg_indexes 
WHERE schemaname = 'public' 
ORDER BY tablename, indexname;
```

应看到以下关键索引：
- `idx_knowledge_entries_search_vector` (GIN)
- `idx_knowledge_entries_sku` (B-tree)
- `products_search_vector_idx` (GIN)
- `products_name_cn_trgm_idx` (GIN)

### 4. 创建初始管理员用户

在 SQL Editor 中运行：
```sql
INSERT INTO users (email, name, role)
VALUES ('your-email@example.com', 'Your Name', 'admin')
ON CONFLICT (email) DO NOTHING;
```

---

## 飞书应用配置

### 1. 配置应用权限

在飞书开放平台 → 应用详情 → **权限管理**：

**必需权限**：
- ✅ `im:message` - 接收消息
- ✅ `im:message:send_as_bot` - 发送消息
- ✅ `bitable:app` - 读取多维表格

**可选权限**（如需采集群聊）：
- ✅ `im:chat` - 获取群信息
- ✅ `im:chat:member` - 获取群成员

权限修改后需要重新发布应用。

### 2. 配置事件订阅

在飞书开放平台 → 应用详情 → **事件订阅**：

#### 开发环境（本地测试）

使用 ngrok 暴露本地服务：
```bash
# 安装 ngrok (如果未安装)
brew install ngrok

# 启动 ngrok
ngrok http 5000

# 复制 Forwarding URL，如：
# https://abc123.ngrok.io
```

#### 配置 Webhook URL

1. 请求地址：`https://your-domain.com/webhook`（或 ngrok URL）
2. 订阅事件：
   - ✅ `im.message.receive_v1` - 接收消息
3. 确认启用

#### 验证 Webhook

飞书会发送验证请求，确保服务已启动：
```bash
# 先启动服务（见下文"启动服务"章节）
python3 bot/main.py

# 然后在飞书后台点击"验证"
```

### 3. 发布应用

1. 在飞书开放平台 → 应用详情 → **版本管理与发布**
2. 创建应用版本
3. 提交审核
4. 审核通过后，点击"全员发布"（或仅发布给特定部门）

### 4. 邀请机器人入群

在飞书群聊中：
1. 点击群设置 → **群机器人**
2. 添加自建机器人
3. 选择刚创建的应用
4. @机器人 发送 `/help` 测试

---

## 定时任务配置

使用 macOS launchd 配置自动同步任务。

### 自动安装（推荐）

```bash
# 运行安装脚本
bash scripts/setup_launchd.sh
```

脚本会自动：
1. 验证环境（Python、.env、脚本文件）
2. 创建 logs 目录
3. 安装定时任务到 `~/Library/LaunchAgents/`
4. 加载并启动任务
5. 验证任务状态

### 手动安装

如果自动脚本失败，可以手动安装：

```bash
# 复制 plist 文件
cp launchd/com.product-kb.sync-products.plist ~/Library/LaunchAgents/
cp launchd/com.product-kb.sync-feishu-qa.plist ~/Library/LaunchAgents/

# 创建日志目录
mkdir -p logs

# 加载任务
launchctl load ~/Library/LaunchAgents/com.product-kb.sync-products.plist
launchctl load ~/Library/LaunchAgents/com.product-kb.sync-feishu-qa.plist

# 验证任务状态
launchctl list | grep com.product-kb
```

### 定时任务说明

| 任务 | 脚本 | 运行时间 | 功能 |
|------|------|---------|------|
| sync-products | `sync_product_table.py` | 每天 08:30 | 同步飞书产品表 |
| sync-feishu-qa | `sync_feishu_qa.py` | 每天 09:00 | 采集飞书群技术问答 |

### 手动测试定时任务

```bash
# 立即运行产品同步
launchctl start com.product-kb.sync-products

# 立即运行问答同步
launchctl start com.product-kb.sync-feishu-qa

# 查看日志
tail -f logs/sync-products.log
tail -f logs/sync-feishu-qa.log
```

### 卸载定时任务

```bash
launchctl unload ~/Library/LaunchAgents/com.product-kb.sync-products.plist
launchctl unload ~/Library/LaunchAgents/com.product-kb.sync-feishu-qa.plist
```

---

## 启动服务

### 开发环境

```bash
# 激活虚拟环境
source venv/bin/activate

# 启动 Flask 服务
python3 bot/main.py

# 预期输出：
# * Running on http://0.0.0.0:5000
# * Serving Flask app 'main'
```

服务启动后可访问：
- 健康检查：http://localhost:5000/health
- Webhook：http://localhost:5000/webhook

### 生产环境

使用 Gunicorn 部署（更稳定）：

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动服务（单 Worker）
gunicorn -w 1 -b 0.0.0.0:5000 bot.main:app

# 或使用启动脚本
bash scripts/start_bot.sh
```

**重要**：当前版本仅支持单 Worker (`-w 1`)，因为消息去重使用内存缓存。多 Worker 需要使用 Redis（Phase 2 改进）。

### 后台运行

使用 screen 或 tmux：
```bash
# 使用 screen
screen -S kb-bot
gunicorn -w 1 -b 0.0.0.0:5000 bot.main:app
# 按 Ctrl+A 然后 D 退出

# 重新连接
screen -r kb-bot
```

或配置为 launchd 服务（推荐生产环境）：
```bash
# 创建 plist 文件
cp launchd/com.product-kb.bot-service.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.product-kb.bot-service.plist
```

---

## 验证部署

### 1. 健康检查

```bash
curl http://localhost:5000/health

# 预期输出：
# {
#   "status": "healthy",
#   "service": "product-knowledge-base-bot",
#   "version": "1.0.0"
# }
```

### 2. 测试数据库连接

```bash
python3 -c "from scripts.utils import get_supabase_client; client = get_supabase_client(); print('Connected to Supabase:', client.table('users').select('id').limit(1).execute())"
```

### 3. 测试飞书机器人

在飞书中 @机器人 发送测试消息：

**测试 1：帮助命令**
```
/help
```
应收到使用帮助信息。

**测试 2：关键词搜索**
```
加热杯
```
应返回相关知识条目（如果有数据）。

**测试 3：SKU 搜索**
```
CBC004-1234
```
应返回该 SKU 的技术问题（如果有数据）。

### 4. 导入测试数据

如果系统没有数据，先导入历史数据：
```bash
python3 scripts/import_historical_data.py --dry-run
python3 scripts/import_historical_data.py
```

详见 [历史数据导入指南](import_guide.md)。

### 5. 验证定时任务

```bash
# 查看任务状态
launchctl list | grep com.product-kb

# 应输出：
# -	0	com.product-kb.sync-products
# -	0	com.product-kb.sync-feishu-qa

# 第二列为 0 表示正常，非 0 表示失败
```

### 6. 运行测试套件

```bash
# 运行所有测试
bash scripts/run_tests.sh

# 或分别运行
pytest tests/test_search.py -v
pytest tests/test_integration.py -v -m integration
pytest tests/test_import_historical_data.py -v
```

---

## 故障排查

### 问题 1：Python 依赖安装失败

**错误**：
```
ERROR: Could not find a version that satisfies the requirement...
```

**解决方案**：
```bash
# 升级 pip
pip install --upgrade pip

# 清除缓存重新安装
pip cache purge
pip install -r requirements.txt
```

### 问题 2：Supabase 连接失败

**错误**：
```
supabase.errors.HTTPException: 401 Unauthorized
```

**原因**：
- `SUPABASE_URL` 或 `SUPABASE_KEY` 配置错误
- Supabase 项目已暂停（免费版超过限制）

**解决方案**：
1. 检查 `.env` 配置
2. 登录 Supabase Dashboard 确认项目状态
3. 确认使用正确的 API Key（anon key 或 service_role key）

### 问题 3：飞书 Webhook 验证失败

**错误**：
```
飞书后台显示"Webhook 验证失败"
```

**解决方案**：
1. 确认服务已启动：`curl http://localhost:5000/health`
2. 如果使用 ngrok，确认 URL 正确
3. 检查 `FEISHU_VERIFICATION_TOKEN` 配置
4. 查看服务日志：`tail -f logs/app.log`

### 问题 4：定时任务未运行

**症状**：
```bash
launchctl list | grep com.product-kb
# 第二列显示非 0 值
```

**解决方案**：
```bash
# 查看详细错误
launchctl print gui/$(id -u)/com.product-kb.sync-products

# 检查日志
tail -f logs/sync-products.error.log

# 常见原因：
# 1. .env 文件未加载 → 使用 wrapper 脚本 (run_sync_products.sh)
# 2. Python 路径错误 → 检查 plist 中的 ProgramArguments
# 3. 权限问题 → 确保脚本有执行权限 (chmod +x scripts/*.sh)
```

### 问题 5：搜索无结果

**症状**：
机器人返回"未找到相关知识条目"

**解决方案**：
1. 检查数据库是否有数据：
   ```bash
   python3 -c "from scripts.utils import get_supabase_client; client = get_supabase_client(); print('Total entries:', len(client.table('knowledge_entries').select('id').execute().data))"
   ```

2. 检查条目状态（只有 `approved` 状态才能被搜索）：
   ```sql
   SELECT status, COUNT(*) 
   FROM knowledge_entries 
   GROUP BY status;
   ```

3. 如果都是 `pending` 状态，需要审核：
   - 方法 1：通过飞书管理表审核（见 [管理指南](management_guide.md)）
   - 方法 2：直接在 Supabase 中批量更新：
     ```sql
     UPDATE knowledge_entries 
     SET status = 'approved' 
     WHERE status = 'pending';
     ```

### 问题 6：消息重复回复

**原因**：
- 飞书重试机制（Webhook 未在 3 秒内返回 200）
- 消息去重缓存失效

**解决方案**：
1. 确保 Webhook 立即返回 200（已实现异步处理）
2. 检查消息缓存是否正常：
   ```python
   # 在 bot/main.py 中添加调试日志
   logger.info(f"Processed messages cache size: {len(processed_messages)}")
   ```

### 问题 7：飞书机器人无权限

**错误**：
```
{"code": 99991663, "msg": "app has no permission"}
```

**解决方案**：
1. 在飞书开放平台检查应用权限
2. 确认已添加必需权限（im:message, im:message:send_as_bot）
3. 重新发布应用
4. 重新邀请机器人入群

---

## 生产部署建议

### 1. 安全性

- 使用 HTTPS（通过 Nginx 反向代理）
- 启用飞书消息加密（`FEISHU_ENCRYPT_KEY`）
- 定期轮换 API 密钥
- 限制 Supabase service_role key 使用（仅后台脚本使用）

### 2. 监控

- 配置日志轮转（logrotate 或 newsyslog）
- 监控服务健康：
  ```bash
  */5 * * * * curl -f http://localhost:5000/health || echo "Service down" | mail -s "Alert" admin@example.com
  ```
- 监控数据库性能（Supabase Dashboard → Database → Performance）

### 3. 备份

- 定期备份 Supabase 数据：
  ```bash
  # 使用 Supabase CLI
  supabase db dump -f backup-$(date +%Y%m%d).sql
  ```
- 备份 `.env` 文件（加密存储）

### 4. 扩展性

Phase 1 限制：
- 单 Worker Flask 服务
- 内存消息去重缓存
- 同步 I/O 操作

Phase 2 改进方向：
- 使用 Redis 做分布式缓存
- 支持多 Worker Gunicorn
- 异步数据库操作（aiohttp + asyncpg）

---

## 相关文档

- [API 文档](api.md) - 详细的 API 接口说明
- [用户指南](user_guide.md) - 客服、审核员、管理员使用指南
- [管理指南](management_guide.md) - 知识库审核工作流
- [导入指南](import_guide.md) - 历史数据导入步骤

---

## 技术支持

- **项目文档**：`IMPLEMENTATION_PHASE1.md`
- **代码仓库**：GitHub (如有)
- **联系人**：Cindy (cbconnectbr@gmail.com)

**文档版本**：1.0  
**更新日期**：2026-04-27
