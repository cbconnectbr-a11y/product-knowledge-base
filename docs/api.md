# API 文档

本文档详细说明产品知识库系统的数据库 Schema、搜索 API、Webhook 接口和脚本命令。

## 目录

1. [数据库 Schema](#数据库-schema)
2. [搜索 API](#搜索-api)
3. [Webhook 接口](#webhook-接口)
4. [管理脚本](#管理脚本)
5. [数据格式](#数据格式)

---

## 数据库 Schema

### 表结构

#### users - 用户表

存储系统用户及其角色。

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('viewer', 'reviewer', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
```

**字段说明**：
- `id`: 用户唯一标识（UUID）
- `email`: 邮箱（唯一）
- `name`: 用户姓名
- `role`: 角色
  - `viewer` - 只读权限（客服）
  - `reviewer` - 审核权限（审核员）
  - `admin` - 完全权限（管理员）
- `created_at`: 创建时间
- `updated_at`: 更新时间
- `last_login_at`: 最后登录时间

**索引**：
- `idx_users_email` - 邮箱查询
- `idx_users_role` - 角色筛选

---

#### products - 产品表

存储产品信息（从飞书多维表格同步）。

```sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku TEXT UNIQUE NOT NULL,
    name_cn TEXT,
    name_en TEXT,
    category TEXT,
    brand TEXT,
    
    -- 搜索增强字段
    aliases TEXT[],
    search_keywords TEXT[],
    category_path TEXT[],
    search_vector TSVECTOR,
    
    -- 飞书原始数据
    feishu_raw_data JSONB NOT NULL,
    
    -- 快速访问字段
    images TEXT[],
    package_images TEXT[],
    features TEXT,
    description TEXT,
    manual_files JSONB,
    model_3d_url TEXT,
    
    -- 元数据
    feishu_record_id TEXT,
    mabang_id TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**字段说明**：
- `sku`: 产品 SKU 编号（唯一）
- `name_cn`: 中文名称
- `name_en`: 英文名称
- `category`: 产品分类
- `aliases`: 产品别名数组（Phase 2 AI 生成）
- `search_keywords`: 搜索关键词数组
- `search_vector`: 全文搜索向量（自动生成）
- `feishu_raw_data`: 飞书原始 JSONB 数据
- `images`: 产品图片 URL 数组
- `manual_files`: 说明书文件 JSONB

**索引**：
- `products_sku_idx` - SKU 精确查询
- `products_search_vector_idx` (GIN) - 全文搜索
- `products_name_cn_trgm_idx` (GIN) - 中文名称模糊匹配
- `products_name_en_trgm_idx` (GIN) - 英文名称模糊匹配

---

#### knowledge_entries - 知识条目表

核心表，存储所有知识库条目。

```sql
CREATE TABLE knowledge_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku VARCHAR(100),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    
    -- 来源信息
    source_type VARCHAR(50) NOT NULL,  -- 'feishu_chat' | 'manual'
    source_id VARCHAR(200),
    source_group VARCHAR(200),
    
    -- 分类和标签
    category TEXT[] DEFAULT '{}',
    keywords TEXT[] DEFAULT '{}',
    
    -- 状态管理
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected' | 'draft'
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    
    -- 搜索向量（自动生成）
    search_vector TSVECTOR,
    
    -- 元数据
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- 去重约束
    CONSTRAINT unique_source UNIQUE(source_type, source_id)
);
```

**字段说明**：
- `sku`: 关联产品 SKU（可为空）
- `title`: 知识条目标题
- `content`: 详细内容
- `source_type`: 来源类型
  - `feishu_chat` - 飞书群聊采集
  - `manual` - 手动导入
- `source_id`: 来源唯一标识（用于去重）
- `source_group`: 来源群组名称
- `category`: 分类标签数组
- `keywords`: 关键词数组
- `status`: 审核状态
  - `pending` - 待审核
  - `approved` - 已批准（可搜索）
  - `rejected` - 已拒绝
  - `draft` - 草稿
- `reviewed_by`: 审核人 ID
- `reviewed_at`: 审核时间
- `reviewer_notes`: 审核意见
- `search_vector`: 全文搜索向量（由 `title + content` 自动生成）

**索引**：
- `idx_knowledge_entries_sku` - SKU 查询
- `idx_knowledge_entries_search_vector` (GIN) - 全文搜索
- `idx_knowledge_entries_status` - 状态筛选
- `unique_source` - 去重约束

**触发器**：
```sql
CREATE TRIGGER knowledge_entries_search_vector_update
    BEFORE INSERT OR UPDATE OF title, content
    ON knowledge_entries
    FOR EACH ROW
    EXECUTE FUNCTION update_knowledge_entries_search_vector();
```

自动更新 `search_vector` 字段（使用 'simple' 配置，适合中文）。

---

#### search_logs - 搜索日志表

记录所有搜索行为，用于分析和优化。

```sql
CREATE TABLE search_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    query TEXT NOT NULL,
    search_type VARCHAR(50) CHECK (search_type IN ('keyword', 'sku', 'fuzzy')),
    result_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**字段说明**：
- `user_id`: 用户 ID（Phase 1 中为 NULL）
- `query`: 搜索查询文本
- `search_type`: 搜索类型
  - `keyword` - 关键词全文搜索
  - `sku` - SKU 精确匹配
  - `fuzzy` - 模糊匹配
- `result_count`: 返回结果数量
- `created_at`: 搜索时间

**索引**：
- `idx_search_logs_user` - 按用户查询
- `idx_search_logs_created_at` - 按时间查询
- `idx_search_logs_query` - 按查询内容分析

---

## 搜索 API

搜索功能通过 `bot/search.py` 模块提供。

### search_by_sku_exact()

SKU 精确匹配搜索。

**函数签名**：
```python
def search_by_sku_exact(sku: str) -> List[Dict[str, Any]]
```

**参数**：
- `sku` (str): SKU 编号，如 "CBC004-1234"

**返回值**：
- `List[Dict]`: 匹配的知识条目列表

**示例**：
```python
from bot.search import search_by_sku_exact

results = search_by_sku_exact("CBC004-1234")

# 返回格式：
[
    {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "sku": "CBC004-1234",
        "title": "加热杯不加热问题",
        "content": "客户反馈加热杯通电后无法加热...",
        "source_group": "客服群A",
        "keywords": ["加热", "故障"],
        "created_at": "2026-04-20T10:00:00+00:00"
    }
]
```

**行为**：
- SKU 自动转大写
- 只返回 `status = 'approved'` 的条目
- 按 `created_at` 倒序排列

---

### search_by_keyword()

关键词全文搜索（使用 PostgreSQL tsvector/tsquery）。

**函数签名**：
```python
def search_by_keyword(keyword: str, limit: int = 10) -> List[Dict[str, Any]]
```

**参数**：
- `keyword` (str): 搜索关键词
- `limit` (int): 最大返回数量，默认 10

**返回值**：
- `List[Dict]`: 匹配的知识条目列表

**示例**：
```python
from bot.search import search_by_keyword

results = search_by_keyword("加热杯漏水", limit=5)

# 返回格式同上
```

**行为**：
- 使用 PostgreSQL 的 `plainto_tsquery` 进行全文搜索
- 搜索 `search_vector` 字段（由 title + content 生成）
- 中文友好（使用 'simple' 配置，不做词干提取）
- 只返回 `status = 'approved'` 的条目
- 按 `created_at` 倒序排列

---

### search_by_fuzzy_similarity()

模糊匹配搜索（使用 ILIKE）。

**函数签名**：
```python
def search_by_fuzzy_similarity(query: str, limit: int = 10) -> List[Dict[str, Any]]
```

**参数**：
- `query` (str): 搜索查询
- `limit` (int): 最大返回数量，默认 10

**返回值**：
- `List[Dict]`: 匹配的知识条目列表

**示例**：
```python
from bot.search import search_by_fuzzy_similarity

results = search_by_fuzzy_similarity("密封圈", limit=5)
```

**行为**：
- 使用 `ILIKE %query%` 进行部分匹配
- 搜索 `title` 和 `content` 字段
- 不区分大小写
- 只返回 `status = 'approved'` 的条目

---

### smart_search()

智能搜索，自动选择最佳搜索策略。

**函数签名**：
```python
def smart_search(query: str, limit: int = 10) -> Dict[str, Any]
```

**参数**：
- `query` (str): 搜索查询
- `limit` (int): 最大返回数量，默认 10

**返回值**：
- `Dict`: 包含搜索结果和元数据

**返回格式**：
```python
{
    "results": [...],           # 知识条目列表
    "search_type": "sku",       # 'sku' | 'keyword'
    "query": "CBC004-1234",     # 原始查询
    "extracted_sku": "CBC004-1234"  # 提取的 SKU（如果有）
}
```

**示例**：
```python
from bot.search import smart_search

# SKU 查询
result = smart_search("CBC004-1234 加热杯问题")
# search_type: 'sku', extracted_sku: 'CBC004-1234'

# 关键词查询
result = smart_search("加热杯漏水怎么办")
# search_type: 'keyword'
```

**行为**：
1. 先尝试从查询中提取 SKU（格式：`ABC123-4567`）
2. 如果找到 SKU，使用 `search_by_sku_exact()`
3. 否则使用 `search_by_keyword()`

---

## Webhook 接口

飞书机器人 Webhook 服务由 `bot/main.py` 提供。

### POST /webhook

接收飞书事件的主接口。

**URL**：`https://your-domain.com/webhook`

**请求方法**：`POST`

**请求头**：
```
Content-Type: application/json
```

**请求体（URL 验证）**：
```json
{
    "type": "url_verification",
    "challenge": "ajls384kdjx98XX",
    "token": "your-verification-token"
}
```

**响应（URL 验证）**：
```json
{
    "challenge": "ajls384kdjx98XX"
}
```

**请求体（接收消息 - v2 格式）**：
```json
{
    "schema": "2.0",
    "header": {
        "event_id": "5e3702a84e847582be8db7fb73283c02",
        "event_type": "im.message.receive_v1",
        "create_time": "1608725989000",
        "token": "your-verification-token",
        "app_id": "cli_xxx",
        "tenant_key": "xxx"
    },
    "event": {
        "sender": {
            "sender_id": {
                "union_id": "on_xxx",
                "user_id": "ou_xxx",
                "open_id": "ou_xxx"
            },
            "sender_type": "user",
            "tenant_key": "xxx"
        },
        "message": {
            "message_id": "om_xxx",
            "root_id": "om_xxx",
            "parent_id": "om_xxx",
            "create_time": "1609073151345",
            "chat_id": "oc_xxx",
            "chat_type": "group",
            "message_type": "text",
            "content": "{\"text\":\"加热杯不加热\"}"
        }
    }
}
```

**响应（消息事件）**：
```json
{
    "msg": "ok"
}
```

**错误响应**：
- `403 Forbidden` - Token 验证失败
- `500 Internal Server Error` - 处理异常

**行为**：
1. **URL 验证**：返回 challenge 值
2. **Token 验证**：检查 `FEISHU_VERIFICATION_TOKEN`（兼容 v1/v2 格式）
3. **消息解密**：如果配置了 `FEISHU_ENCRYPT_KEY`，解密消息
4. **消息去重**：基于 `message_id`，5 分钟内重复消息跳过
5. **异步处理**：创建后台线程处理，立即返回 200
6. **回复消息**：通过飞书 API 发送搜索结果

---

### GET /health

健康检查接口。

**URL**：`https://your-domain.com/health`

**请求方法**：`GET`

**响应**：
```json
{
    "status": "healthy",
    "service": "product-knowledge-base-bot",
    "version": "1.0.0"
}
```

**状态码**：`200 OK`

---

## 管理脚本

### sync_product_table.py

同步飞书产品表到 Supabase。

**用法**：
```bash
python3 scripts/sync_product_table.py [--limit N]
```

**参数**：
- `--limit N`: 限制同步数量（用于测试）

**功能**：
1. 从飞书多维表格读取产品记录
2. 标准化字段映射
3. 插入/更新 Supabase `products` 表
4. 记录同步时间戳

**环境变量**：
- `FEISHU_PRODUCT_TABLE_APP_TOKEN`
- `FEISHU_PRODUCT_TABLE_TABLE_ID`

---

### sync_feishu_qa.py

从飞书群聊采集技术问答。

**用法**：
```bash
python3 scripts/sync_feishu_qa.py [--days N]
```

**参数**：
- `--days N`: 采集最近 N 天的消息，默认 7

**功能**：
1. 读取配置的飞书群组 ID
2. 获取群聊消息历史
3. 提取 SKU 和技术问题
4. 插入 Supabase `knowledge_entries` 表（status = pending）

**环境变量**：
- `FEISHU_TECH_GROUPS` - 群组 ID 列表（逗号分隔）

---

### create_management_table.py

知识库审核管理脚本。

**用法**：
```bash
python3 scripts/create_management_table.py <command>
```

**命令**：

#### sync-pending
推送待审核条目到飞书表格。

```bash
python3 scripts/create_management_table.py sync-pending
```

**功能**：
- 查询 Supabase 中 `status='pending'` 的条目
- 推送到飞书多维表格（最多 100 条）
- 去重处理（基于 DB_ID）

#### sync-reviews
同步审核结果回 Supabase。

```bash
python3 scripts/create_management_table.py sync-reviews
```

**功能**：
- 从飞书表格读取已审核条目（Status != pending）
- 更新 Supabase 对应记录的 `status`、`reviewed_at`、`reviewer_notes`

#### sync-all
完整双向同步。

```bash
python3 scripts/create_management_table.py sync-all
```

**功能**：
- 先运行 `sync-pending`
- 再运行 `sync-reviews`

**环境变量**：
- `FEISHU_MANAGEMENT_APP_TOKEN`
- `FEISHU_MANAGEMENT_TABLE_ID`

详见 [管理指南](management_guide.md)。

---

### import_historical_data.py

导入历史 JSON 数据到知识库。

**用法**：
```bash
python3 scripts/import_historical_data.py [options]
```

**选项**：
- `--file <path>`: 导入指定文件
- `--dry-run`: 预览模式，不实际导入
- `--verbose`: 详细输出

**示例**：
```bash
# 导入所有文件
python3 scripts/import_historical_data.py

# 预览导入
python3 scripts/import_historical_data.py --dry-run

# 导入单个文件
python3 scripts/import_historical_data.py --file ~/客服知识库/tech_issues.json --verbose
```

**支持的文件格式**：
1. `tech_issues_filtered_final.json`
2. `技术支持问答知识库_*.json`
3. `技术问题汇总_完整版.json`

**功能**：
- 解析 JSON 文件
- 提取知识条目
- 生成唯一 `source_id`（基于内容 MD5）
- 批量插入 Supabase（自动去重）
- 统计插入/跳过/错误数量

详见 [导入指南](import_guide.md)。

---

## 数据格式

### 机器人命令

飞书机器人支持以下命令：

#### /help
显示帮助信息。

**输入**：
```
/help
```

**输出**：
```
📚 产品知识库机器人 - 使用帮助

**搜索方式：**
1. 直接发送关键词 - 自动智能搜索
   例：「加热杯漏水」

2. SKU 搜索 - 输入 SKU 自动识别
   例：「CBC004-1234」

3. 关键词搜索命令
   /search <关键词>
   例：「/search 密封圈老化」

4. SKU 精确搜索命令
   /sku <SKU编号>
   例：「/sku CBC004-1234」
```

---

#### /search <关键词>
关键词搜索。

**输入**：
```
/search 加热杯漏水
```

**输出**：
```
🔍 搜索 "加热杯漏水" - 找到 2 条结果

────────────────────────────────────────
📄 结果 1
SKU: CBC004-1234
**加热杯底部漏水问题**

客户反馈 CBC004-1234 加热杯底部漏水，经检查发现是密封圈老化导致。

解决方案：
1. 更换密封圈
2. 检查杯体是否有裂纹
3. 确认加热温度设置正确

关键词: 漏水, 密封圈, 加热杯
来源: 客服群A

────────────────────────────────────────
📄 结果 2
...
```

---

#### /sku <SKU编号>
SKU 精确搜索。

**输入**：
```
/sku CBC004-1234
```

**输出**：
格式同 `/search`，但仅返回该 SKU 的相关条目。

---

#### 智能搜索（默认）
直接发送文本，自动判断搜索类型。

**输入 1（包含 SKU）**：
```
CBC004-1234 加热问题
```
自动提取 SKU 并执行 SKU 搜索。

**输入 2（纯关键词）**：
```
加热杯不加热怎么办
```
执行关键词搜索。

---

### 知识条目 JSON 格式

从 Supabase 查询返回的标准格式：

```json
{
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "sku": "CBC004-1234",
    "title": "加热杯不加热问题",
    "content": "客户反馈加热杯通电后无法加热，检查发现是加热元件损坏...",
    "source_type": "feishu_chat",
    "source_id": "om_abc123def456",
    "source_group": "客服群A",
    "category": ["故障排查", "加热类产品"],
    "keywords": ["加热", "故障", "维修"],
    "status": "approved",
    "reviewed_by": "123e4567-e89b-12d3-a456-426614174001",
    "reviewed_at": "2026-04-21T14:30:00+00:00",
    "reviewer_notes": "信息完整，批准发布",
    "created_by": null,
    "created_at": "2026-04-20T10:00:00+00:00",
    "updated_at": "2026-04-21T14:30:00+00:00"
}
```

---

### 飞书管理表字段映射

| Supabase 字段 | 飞书字段 | 类型 | 示例值 |
|--------------|---------|------|--------|
| `id` | `DB_ID` | 文本 | `123e4567-e89b-12d3-a456-426614174000` |
| `sku` | `SKU` | 文本 | `CBC004-1234` |
| `title` | `标题` | 文本 | `加热杯不加热问题` |
| `content` | `内容` | 富文本 | `客户反馈...` |
| `source_group` | `来源` | 文本 | `客服群A` |
| `keywords` | `关键词` | 文本 | `加热, 故障, 维修` |
| `created_at` | `创建时间` | 日期时间 | `2026-04-20 10:00:00` |
| `status` | `Status` | 单选 | `pending` / `approved` / `rejected` / `draft` |
| `reviewer_notes` | `审核意见` | 富文本 | `信息完整，批准发布` |

---

## 错误代码

### 搜索 API 错误

- 空查询：返回空数组 `[]`
- 数据库连接失败：抛出 `Exception`

### Webhook 错误

| HTTP 状态码 | 原因 | 解决方案 |
|-----------|------|---------|
| 200 | 成功 | - |
| 403 | Token 验证失败 | 检查 `FEISHU_VERIFICATION_TOKEN` |
| 500 | 服务器内部错误 | 查看日志 `logs/app.log` |

### 管理脚本错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `Missing required environment variables` | .env 未配置 | 检查 `.env` 文件 |
| `Unauthorized` | 飞书凭证无效 | 验证 APP_ID 和 APP_SECRET |
| `Not Found` | APP_TOKEN 或 TABLE_ID 错误 | 检查飞书表格配置 |
| `Connection refused` | Supabase 无法连接 | 检查网络和 `SUPABASE_URL` |

---

## 性能优化

### 数据库索引

所有关键查询路径已创建索引：
- SKU 查询 - B-tree 索引
- 全文搜索 - GIN 索引（tsvector）
- 模糊匹配 - GIN 索引（pg_trgm）

### 搜索性能

**典型查询耗时**（Supabase 免费版）：
- SKU 精确匹配：< 50ms
- 关键词全文搜索：< 100ms
- 模糊匹配：< 150ms

**优化建议**：
- 限制结果数量（默认 10 条）
- 使用 SKU 搜索优于关键词搜索
- 定期清理 `status='rejected'` 的旧条目

---

## 限制和约束

### Phase 1 限制

1. **并发**：单 Worker Flask 服务，消息去重基于内存
2. **用户系统**：search_logs 中 `user_id` 暂为 NULL
3. **搜索**：无语义理解，仅基于文本匹配
4. **审核**：需手动运行同步脚本（无实时 Webhook）

### Phase 2 改进方向

1. **AI 语义搜索**：集成 Embedding 模型和 pgvector
2. **分布式缓存**：使用 Redis 支持多 Worker
3. **实时同步**：飞书 Webhook 自动触发审核流程
4. **用户关联**：飞书 user_id 映射到系统 users 表

---

## 相关文档

- [部署指南](setup.md) - 系统安装和配置
- [用户指南](user_guide.md) - 客服、审核员、管理员使用
- [管理指南](management_guide.md) - 知识库审核工作流
- [导入指南](import_guide.md) - 历史数据导入

---

**文档版本**：1.0  
**更新日期**：2026-04-27  
**维护者**：Cindy (cbconnectbr@gmail.com)
