# 产品知识库系统 - Phase 1 MVP

## 项目简介

电商产品知识库系统，帮助客服快速查询产品技术问题和解决方案。

## 功能特性（Phase 1）

- ✅ 飞书群技术问答自动采集
- ✅ 飞书产品信息表同步
- ✅ SKU 精确查询
- ✅ 关键词全文搜索
- ✅ 产品名称模糊匹配
- ✅ 飞书机器人交互
- ✅ 搜索日志记录

## 技术栈

- **数据库**: Supabase (PostgreSQL)
- **后端**: Python 3.x
- **飞书集成**: lark-oapi
- **定时任务**: macOS launchd

## 快速开始

### 1. 环境配置

```bash
# 安装依赖
pip3 install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入飞书和 Supabase 凭证
```

### 2. 数据库初始化

```bash
# 执行 schema 创建表
psql -h <supabase-host> -U postgres -d postgres -f database/schema.sql
```

### 3. 启动飞书机器人

```bash
python3 bot/main.py
```

### 4. 配置定时任务

```bash
# 复制 plist 到 LaunchAgents
cp config/launchd/*.plist ~/Library/LaunchAgents/

# 加载定时任务
launchctl load ~/Library/LaunchAgents/com.kb.sync.feishu.plist
launchctl load ~/Library/LaunchAgents/com.kb.sync.products.plist
```

## 项目结构

详见 `docs/setup.md`

## 文档

- [部署文档](docs/setup.md)
- [API 文档](docs/api.md)
- [用户指南](docs/user_guide.md)

## License

Private - Internal Use Only
