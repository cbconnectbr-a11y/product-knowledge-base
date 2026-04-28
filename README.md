# 产品知识库系统

电商客服技术支持平台，帮助客服快速查询产品技术问题和解决方案。

## 简介

产品知识库系统通过自动采集飞书群聊和产品表数据，为客服团队提供统一的知识查询平台。客服可以通过飞书机器人快速搜索 SKU 和关键词，获取准确的技术问题解决方案。

## 核心功能

### 数据采集
- 🔄 **自动同步**：从飞书多维表格同步产品信息
- 💬 **群聊采集**：自动采集飞书技术群的问答内容
- 📦 **历史导入**：支持批量导入历史 JSON 数据

### 智能搜索
- 🎯 **SKU 精确匹配**：通过产品 SKU 快速定位问题
- 🔍 **关键词全文搜索**：支持中文全文搜索（PostgreSQL tsvector）
- 🌟 **智能路由**：自动识别查询类型，选择最佳搜索策略
- 📝 **搜索日志**：记录所有搜索行为，支持数据分析

### 知识管理
- ✅ **审核工作流**：通过飞书多维表格进行知识条目审核
- 📊 **状态管理**：pending/approved/rejected/draft 四种状态
- 🏷️ **分类标签**：支持关键词和分类标签（Phase 2 AI 自动生成）

### 用户交互
- 🤖 **飞书机器人**：Webhook 服务，支持命令搜索和智能搜索
- 📱 **移动友好**：通过飞书移动端随时查询
- ⏱️ **实时响应**：异步处理，秒级返回搜索结果

## 快速开始

### 安装

```bash
# 1. 克隆项目
cd ~/Projects/product-knowledge-base

# 2. 安装依赖
pip3 install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 Supabase 和飞书凭证
```

### 初始化数据库

```bash
# 在 Supabase Dashboard → SQL Editor 中执行
# database/schema.sql
```

### 启动服务

```bash
# 开发模式（前台运行，带调试输出）
bash scripts/start.sh development

# 生产模式（后台运行，gunicorn）
bash scripts/start.sh production
# 或简写
bash scripts/start.sh

# 停止服务
bash scripts/stop.sh

# 重启服务
bash scripts/restart.sh production

# 健康检查
bash scripts/check_health.sh

# 配置定时任务（自动同步）
bash scripts/setup_launchd.sh
```

详细步骤请参考 [部署指南](docs/setup.md)。

## 使用指南

### 客服人员

通过飞书机器人搜索知识：

```
# 方式 1：直接发送 SKU
CBC004-1234

# 方式 2：发送关键词
加热杯漏水

# 方式 3：使用命令
/search 密封圈老化
/sku CBC004-1234
/help
```

### 审核员

在飞书管理表中审核知识条目：
1. 打开"知识库管理"多维表格
2. 筛选 Status = pending
3. 审核条目并修改 Status
4. 填写审核意见

### 管理员

#### 服务管理

```bash
# 启动服务
bash scripts/start.sh production       # 生产模式（后台）
bash scripts/start.sh development      # 开发模式（前台，调试）

# 停止服务
bash scripts/stop.sh

# 重启服务
bash scripts/restart.sh production

# 健康检查
bash scripts/check_health.sh

# 查看日志
tail -f logs/bot.log        # 主日志
tail -f logs/error.log      # 错误日志
tail -f logs/access.log     # 访问日志
```

#### 数据管理

```bash
# 同步产品表
python3 scripts/sync_product_table.py

# 同步群聊问答
python3 scripts/sync_feishu_qa.py

# 同步审核结果
python3 scripts/create_management_table.py sync-all

# 导入历史数据
python3 scripts/import_historical_data.py
```

详细指南请参考 [用户指南](docs/user_guide.md)。

## 文档

### 核心文档
- 📘 [部署指南](docs/setup.md) - 系统安装、配置和部署
- 📗 [API 文档](docs/api.md) - 数据库 Schema、搜索 API、Webhook 接口
- 📕 [用户指南](docs/user_guide.md) - 客服、审核员、管理员使用手册

### 专项文档
- 📙 [管理指南](docs/management_guide.md) - 知识库审核工作流详解
- 📔 [导入指南](docs/import_guide.md) - 历史数据导入步骤
- 📄 [实施文档](IMPLEMENTATION_PHASE1.md) - 完整的技术实施细节

## 项目结构

```
product-knowledge-base/
├── bot/                          # 飞书机器人服务
│   ├── main.py                  # Flask Webhook 服务
│   ├── search.py                # 搜索逻辑
│   ├── handlers.py              # 消息处理
│   ├── formatters.py            # 消息格式化
│   └── config.py                # 配置管理
│
├── database/                     # 数据库
│   ├── schema.sql               # PostgreSQL Schema
│   └── test_connection.py       # 连接测试
│
├── scripts/                      # 数据采集和管理脚本
│   ├── start.sh                 # 启动服务（生产/开发模式）
│   ├── stop.sh                  # 停止服务
│   ├── restart.sh               # 重启服务
│   ├── check_health.sh          # 健康检查
│   ├── sync_product_table.py    # 产品表同步
│   ├── sync_feishu_qa.py        # 群聊问答采集
│   ├── create_management_table.py # 审核管理
│   ├── import_historical_data.py  # 历史数据导入
│   ├── setup_launchd.sh         # 定时任务安装
│   └── utils.py                 # 工具函数
│
├── tests/                        # 测试套件
│   ├── test_search.py           # 搜索功能单元测试
│   ├── test_integration.py      # 集成测试
│   └── test_import_historical_data.py # 导入脚本测试
│
├── docs/                         # 文档
│   ├── setup.md                 # 部署指南
│   ├── api.md                   # API 文档
│   ├── user_guide.md            # 用户指南
│   ├── management_guide.md      # 管理指南
│   └── import_guide.md          # 导入指南
│
├── launchd/                      # macOS 定时任务配置
│   ├── *.plist                  # launchd 配置文件
│   └── *.sh                     # 任务执行脚本
│
├── logs/                         # 日志目录
├── .env.example                  # 环境变量模板
├── requirements.txt              # Python 依赖
├── pytest.ini                    # Pytest 配置
└── README.md                     # 本文档
```

## 技术栈

### 后端
- **语言**：Python 3.9+
- **框架**：Flask (Webhook 服务)
- **数据库**：Supabase (PostgreSQL 13+)
- **搜索**：PostgreSQL tsvector/tsquery + pg_trgm

### 集成
- **飞书**：lark-oapi SDK
- **定时任务**：macOS launchd
- **测试**：pytest

### 数据库特性
- 全文搜索索引 (GIN)
- 模糊匹配 (pg_trgm)
- 自动搜索向量生成 (Trigger)
- JSONB 存储飞书原始数据

## 测试

```bash
# 运行所有测试
bash scripts/run_tests.sh

# 分别运行
pytest tests/test_search.py -v              # 搜索功能测试
pytest tests/test_integration.py -v         # 集成测试
pytest tests/test_import_historical_data.py -v  # 导入测试
```

## Phase 1 限制与 Phase 2 改进方向

### 当前限制 (Phase 1)
- 单 Worker Flask 服务（消息去重基于内存）
- 无语义理解（基础文本匹配）
- 手动运行审核同步脚本
- search_logs 中 user_id 为 NULL

### Phase 2 计划改进
- 🚀 **AI 语义搜索**：集成 Embedding 模型和 pgvector
- 🤖 **智能分类**：LLM 自动提取关键词和分类
- 🔄 **实时同步**：飞书 Webhook 触发审核工作流
- 💾 **Redis 缓存**：支持多 Worker 和分布式部署
- 📊 **管理界面**：Web 端审核和分析仪表板
- 💬 **富文本卡片**：飞书消息卡片优化交互体验

## 贡献指南

本项目为内部使用，如需修改：
1. 在新分支上开发
2. 运行测试确保通过
3. 提交 Pull Request
4. 通知管理员 Code Review

## 技术支持

- **项目维护者**：Cindy (cbconnectbr@gmail.com)
- **实施文档**：[IMPLEMENTATION_PHASE1.md](IMPLEMENTATION_PHASE1.md)
- **问题反馈**：在客服管理群中提出

## 许可证

Private - Internal Use Only

---

**版本**：Phase 1 (v1.0)  
**更新日期**：2026-04-27  
**状态**：Production Ready
