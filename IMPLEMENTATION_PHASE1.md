# 产品知识库系统 - Phase 1 实施文档

## 项目概述

**目标**：搭建电商公司产品知识库，让客服快速找到产品内容和技术问题解答

**Phase 1 范围**（已完成 Tasks 1-7）：
- ✅ 数据库设计（Supabase PostgreSQL）
- ✅ 飞书多维表格数据采集
- ✅ 搜索功能（SKU精确匹配 + 关键词全文搜索 + 模糊匹配）
- ✅ 飞书机器人 Webhook 服务
- ⏳ 定时任务配置（Task 8，待完成）
- ⏳ 数据导入、测试、部署（Tasks 9-15，待完成）

**技术栈**：
- Database: Supabase (PostgreSQL)
- Backend: Python 3.9+, Flask, lark-oapi SDK
- Search: PostgreSQL tsvector/tsquery + pg_trgm
- Scheduling: macOS launchd
- Version Control: Git

---

## Task 1: 数据库 Schema 设计

### 文件
- `database/schema.sql` (220行)

### 核心表结构

**users** - 用户账号与角色
```sql
role VARCHAR(50) CHECK (role IN ('viewer', 'reviewer', 'admin'))
```

**products** - 产品信息表
- SKU 唯一索引
- 飞书原始数据存储 (JSONB)
- 搜索增强字段：`aliases[]`, `search_keywords[]`, `search_vector`
- GIN 索引支持全文搜索和模糊匹配

**knowledge_entries** - 知识库条目
```sql
sku VARCHAR(100)                    -- 关联产品
title TEXT NOT NULL                 -- 标题
content TEXT NOT NULL               -- 内容
source_type VARCHAR(50)             -- 'feishu_chat' | 'manual'
status VARCHAR(50)                  -- 'pending' | 'approved' | 'rejected'
search_vector tsvector              -- 全文搜索向量（自动生成）
```

**search_logs** - 搜索日志分析
```sql
query TEXT NOT NULL
result_count INTEGER
search_type VARCHAR(50) CHECK (search_type IN ('keyword', 'sku', 'fuzzy'))
```

### 关键特性

**全文搜索支持（中文优化）**：
```sql
CREATE OR REPLACE FUNCTION update_knowledge_entries_search_vector()
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_vector := to_tsvector('simple', COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```
- 使用 `'simple'` 配置而非 `'english'`，保留中文字符原样
- 自动触发器在 INSERT/UPDATE 时更新 search_vector

**索引优化**：
- `idx_knowledge_entries_search_vector` (GIN) - 全文搜索
- `idx_knowledge_entries_sku` (B-tree) - SKU 查询
- `products_name_cn_trgm_idx` (GIN) - 模糊匹配
- `products_search_vector_idx` (GIN) - 产品全文搜索

**去重机制**：
```sql
CONSTRAINT unique_source UNIQUE(source_type, source_id)
```

**初始管理员用户**：
```sql
INSERT INTO users (email, name, role)
VALUES ('cbconnectbr@gmail.com', 'Cindy (Admin)', 'admin')
ON CONFLICT (email) DO NOTHING;
```

### Commits
- `d9c5f7d` - feat: add comprehensive database schema with search support

---

## Task 2: 飞书 Bitable 数据采集脚本

### 文件
- `scripts/sync_feishu_bitable.py` (291行)

### 功能
1. 从飞书多维表格读取知识条目
2. 标准化字段映射
3. 写入 Supabase knowledge_entries 表
4. SKU 关联验证

### 核心逻辑

**字段映射**（防御式处理）：
```python
def extract_text(field_value):
    """提取文本内容（支持富文本和普通文本）"""
    if isinstance(field_value, list):
        if field_value and isinstance(field_value[0], dict):
            return field_value[0].get('text', '')
        return ''
    return str(field_value) if field_value else ''

field_mapping = {
    'sku': 'SKU编码',
    'title': '问题标题',
    'content': '解决方案',
    'source_group': '来源群组',
    'keywords': '关键词',
}
```

**关键词处理**：
```python
keywords_raw = record_fields.get(field_mapping['keywords'], '')
if isinstance(keywords_raw, str):
    keywords = [k.strip() for k in keywords_raw.split(',') if k.strip()]
```

**SKU 验证**：
```python
if sku:
    product_check = supabase.table('products').select('sku').eq('sku', sku).execute()
    if not product_check.data:
        logger.warning(f"SKU {sku} 不存在于 products 表，但仍导入知识条目")
```

**去重插入**：
```python
supabase.table('knowledge_entries').insert({
    'sku': sku,
    'title': title,
    'content': content,
    'source_type': 'feishu_chat',
    'source_id': record_id,
    'status': 'pending',
    # ...
}).execute()
```
- `unique_source (source_type, source_id)` 约束防止重复导入

### Commits
- `0f0e682` - feat: add Feishu Bitable sync script with field mapping

---

## Task 3: SKU 提取工具函数

### 文件
- `scripts/utils.py` (60行)

### 功能
- `extract_sku(text)` - 从文本中提取 SKU 编号
- `get_supabase_client()` - 获取 Supabase 客户端单例

### SKU 提取规则

**正则表达式**：
```python
pattern = r'\b[A-Z]{3}\d{3}-\d{4}\b'
```
- 格式：`CBC004-1234`（3字母 + 3数字 + 横杠 + 4数字）
- 大小写不敏感（自动转大写）
- 返回第一个匹配的 SKU

**示例**：
```python
extract_sku("CBC004-1234 加热杯漏水")  # → "CBC004-1234"
extract_sku("杯子破损问题")            # → None
extract_sku("cbc004-1234")            # → "CBC004-1234" (自动转大写)
```

### Supabase 客户端

**单例模式**：
```python
_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            os.environ.get('SUPABASE_URL'),
            os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        )
    return _supabase_client
```

### Commits
- `ef1f2a7` - feat: add SKU extraction and Supabase client utilities

---

## Task 4: 配置管理模块

### 文件
- `bot/config.py` (59行)
- `.env.example` (27行)

### 配置项

**飞书应用**：
```python
FEISHU_APP_ID = os.getenv('FEISHU_APP_ID')
FEISHU_APP_SECRET = os.getenv('FEISHU_APP_SECRET')
FEISHU_VERIFICATION_TOKEN = os.getenv('FEISHU_VERIFICATION_TOKEN')
FEISHU_ENCRYPT_KEY = os.getenv('FEISHU_ENCRYPT_KEY')  # 可选
```

**Supabase 数据库**：
```python
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
```

**Flask 服务**：
```python
PORT = int(os.getenv('PORT', '5000'))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
```

### 配置验证

```python
def validate_config():
    """验证必需的环境变量"""
    required = [
        'FEISHU_APP_ID',
        'FEISHU_APP_SECRET',
        'FEISHU_VERIFICATION_TOKEN',
        'SUPABASE_URL',
        'SUPABASE_SERVICE_ROLE_KEY'
    ]
    
    missing = [var for var in required if not os.getenv(var)]
    
    if missing:
        raise ValueError(f"缺少必需的环境变量: {', '.join(missing)}")
```

### `.env.example` 模板
包含所有配置项的示例值和说明注释

### Commits
- `eac8bc9` - feat: add configuration management and .env template

---

## Task 5: 单元测试框架

### 文件
- `tests/test_search.py` (318行)
- `pytest.ini` (6行)

### 测试覆盖

**test_search.py** - 搜索功能测试（16个测试用例）：
- ✅ `TestSearchBySKUExact` (4个)
  - 成功查找 SKU
  - 未找到匹配
  - 空输入处理
  - 大小写不敏感

- ✅ `TestSearchByKeyword` (4个)
  - 成功的关键词搜索
  - 多结果返回
  - 空输入处理
  - 结果数量限制

- ✅ `TestSearchByFuzzySimilarity` (3个)
  - 成功的模糊搜索
  - 空输入处理
  - 结果数量限制

- ✅ `TestSmartSearch` (5个)
  - 包含 SKU 的智能搜索
  - 不包含 SKU 的智能搜索
  - 空输入处理
  - 自定义结果数量
  - SKU 提取但无结果

### Mock 策略

**Supabase 客户端 Mock**：
```python
@pytest.fixture
def mock_supabase():
    with patch('bot.search.get_supabase_client') as mock_client:
        yield mock_client

mock_table = MagicMock()
mock_table.select.return_value = mock_table
mock_table.eq.return_value = mock_table
mock_table.execute.return_value = mock_response
mock_supabase.return_value.table.return_value = mock_table
```

**Mock 数据示例**：
```python
MOCK_KNOWLEDGE_ENTRY_1 = {
    'id': '123e4567-e89b-12d3-a456-426614174000',
    'sku': 'CBC004-1234',
    'title': '加热杯漏水问题',
    'content': '客户反馈 CBC004-1234 加热杯底部漏水，经检查发现是密封圈老化导致',
    'source_group': '客服群A',
    'keywords': ['漏水', '密封圈', '加热杯'],
    'created_at': '2026-04-20T10:00:00+00:00'
}
```

### Pytest 配置

```ini
[pytest]
pythonpath = .
testpaths = tests
python_files = test_*.py
python_functions = test_*
```

### 运行测试

```bash
# 运行所有测试
pytest

# 详细输出
pytest -v

# 运行特定测试文件
pytest tests/test_search.py -v

# 运行特定测试类
pytest tests/test_search.py::TestSmartSearch -v
```

### Commits
- `8df4e1d` - test: add comprehensive search function unit tests

---

## Task 6: 搜索逻辑实现

### 文件
- `bot/search.py` (176行)
- `database/schema.sql` (更新)

### 搜索策略

#### 1. SKU 精确匹配
```python
def search_by_sku_exact(sku: str) -> List[Dict[str, Any]]:
    """SKU 精确匹配搜索"""
    response = client.table('knowledge_entries') \
        .select('id, sku, title, content, source_group, keywords, created_at') \
        .eq('sku', sku.strip().upper()) \
        .eq('status', 'approved') \
        .order('created_at', desc=True) \
        .execute()
    
    return response.data if response.data else []
```
- SKU 自动转大写
- 只返回已审核条目 (`status = 'approved'`)
- 按创建时间倒序

#### 2. 关键词全文搜索
```python
def search_by_keyword(keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    """全文搜索（PostgreSQL tsvector/tsquery）"""
    response = client.table('knowledge_entries') \
        .select('id, sku, title, content, source_group, keywords, created_at') \
        .eq('status', 'approved') \
        .plfts('search_vector', keyword.strip()) \
        .order('created_at', desc=True) \
        .limit(limit) \
        .execute()
    
    return response.data if response.data else []
```
- 使用 `.plfts()` 方法（plainto_tsquery）
- `search_vector` 由触发器自动生成（title + content）
- 中文友好（'simple' 配置）

**重要修复**：
- ❌ 初始版本错误使用 `.textSearch()` (SDK中不存在)
- ✅ 修复为 `.plfts()` (Supabase Python SDK 正确方法)

#### 3. 模糊匹配搜索
```python
def search_by_fuzzy_similarity(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """模糊匹配搜索（ILIKE）"""
    search_pattern = f'%{query.strip()}%'
    response = client.table('knowledge_entries') \
        .select('id, sku, title, content, source_group, keywords, created_at') \
        .eq('status', 'approved') \
        .or_(f'title.ilike.{search_pattern},content.ilike.{search_pattern}') \
        .order('created_at', desc=True) \
        .limit(limit) \
        .execute()
    
    return response.data if response.data else []
```
- ILIKE 不区分大小写
- 支持部分匹配

#### 4. 智能搜索（自动路由）
```python
def smart_search(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    智能搜索：自动判断查询类型并选择最佳策略
    1. 先尝试提取 SKU
    2. 有 SKU → SKU 精确匹配
    3. 无 SKU → 关键词搜索
    """
    extracted_sku = extract_sku(query)
    
    if extracted_sku:
        results = search_by_sku_exact(extracted_sku)
        return {
            'results': results,
            'search_type': 'sku',
            'query': query,
            'extracted_sku': extracted_sku
        }
    else:
        results = search_by_keyword(query, limit=limit)
        return {
            'results': results,
            'search_type': 'keyword',
            'query': query
        }
```

### Schema 更新

**添加 search_vector 字段**：
```sql
ALTER TABLE knowledge_entries
ADD COLUMN search_vector tsvector;
```

**创建 GIN 索引**：
```sql
CREATE INDEX idx_knowledge_entries_search_vector 
ON knowledge_entries USING GIN(search_vector);
```

**自动更新触发器**：
```sql
CREATE OR REPLACE FUNCTION update_knowledge_entries_search_vector()
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_vector := to_tsvector('simple', 
    COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.content, '')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER knowledge_entries_search_vector_update
  BEFORE INSERT OR UPDATE OF title, content
  ON knowledge_entries
  FOR EACH ROW
  EXECUTE FUNCTION update_knowledge_entries_search_vector();
```

**关键决策**：使用 `'simple'` 配置
- ❌ `'english'` - 会对中文字符进行词干提取，损坏查询
- ✅ `'simple'` - 不做词干处理，保留原样，适合中文

### 测试结果
- ✅ 所有 16 个测试用例通过
- ✅ Mock 验证方法调用正确

### Commits
- `c8f4e2a` - feat: implement search logic with smart routing
- `56c6d62` - fix: use correct plfts method for full-text search
- `7a5e3f9` - fix: use 'simple' config for Chinese full-text search

---

## Task 7: 飞书机器人 Webhook 服务

### 文件
- `bot/main.py` (325行)
- `bot/handlers.py` (212行)
- `bot/formatters.py` (229行)

### 架构设计

```
飞书服务器 → Flask Webhook (/webhook)
                ↓
          事件验证与解密
                ↓
          消息去重检查
                ↓
          异步处理 (后台线程)
                ↓
    handle_message() → smart_search()
                ↓
          格式化消息卡片
                ↓
          send_reply() → 飞书 API
```

### 核心组件

#### 1. bot/main.py - Webhook 服务

**健康检查端点**：
```python
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'product-knowledge-base-bot',
        'version': '1.0.0'
    }), 200
```

**Webhook 端点**（完整事件处理）：
```python
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    # 1. URL 验证（飞书配置 Webhook 时）
    if data.get('type') == 'url_verification':
        return jsonify({'challenge': data.get('challenge')}), 200
    
    # 2. 加密事件解密 (Critical Fix C2)
    if 'encrypt' in data and FEISHU_ENCRYPT_KEY:
        cipher = AESCipher(FEISHU_ENCRYPT_KEY)
        decrypted = cipher.decrypt_str(data['encrypt'])  # 修复: 原为 decrypt_string
        data = json.loads(decrypted)
    
    # 3. Token 验证 (Critical Fix C1 - v1/v2 兼容)
    token = data.get('token') or data.get('header', {}).get('token')
    if FEISHU_VERIFICATION_TOKEN and token != FEISHU_VERIFICATION_TOKEN:
        return jsonify({'error': 'Invalid token'}), 403
    
    # 4. 处理消息事件
    if data.get('header', {}).get('event_type') == 'im.message.receive_v1':
        return handle_message_event(data)
    
    return jsonify({'message': 'Event received'}), 200
```

**消息去重（线程安全）**（Critical Fix C4）：
```python
processed_messages = {}
CACHE_EXPIRE_SECONDS = 300
message_cache_lock = threading.Lock()

def is_message_processed(message_id: str) -> bool:
    with message_cache_lock:  # 修复: 添加锁保护
        current_time = time.time()
        
        # 清理过期缓存
        expired_keys = [k for k, v in processed_messages.items() 
                       if current_time - v > CACHE_EXPIRE_SECONDS]
        for k in expired_keys:
            del processed_messages[k]
        
        # 检查是否处理过
        if message_id in processed_messages:
            return True
        
        processed_messages[message_id] = current_time
        return False
```

**异步消息处理**：
```python
def handle_message_event(event_data: dict) -> tuple:
    # 提取消息信息
    message_id = message.get('message_id')
    message_text = content_json.get('text', '').strip()
    
    # Dynamic receive_id_type selection (Critical Fix C3)
    sender_id = sender.get('sender_id', {})
    if sender_id.get('open_id'):
        receive_id = sender_id['open_id']
        receive_id_type = 'open_id'
    elif sender_id.get('user_id'):
        receive_id = sender_id['user_id']
        receive_id_type = 'user_id'
    elif sender_id.get('union_id'):
        receive_id = sender_id['union_id']
        receive_id_type = 'union_id'
    
    # 消息去重
    if is_message_processed(message_id):
        return jsonify({'msg': 'ok'}), 200
    
    # 异步处理（立即返回 200）
    thread = threading.Thread(
        target=process_message_async,
        args=(receive_id, receive_id_type, message_text, message_id)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'msg': 'ok'}), 200

def process_message_async(receive_id, receive_id_type, message_text, message_id):
    # 修复: 添加 user_id 参数用于日志记录
    response_text = handle_message(message_text, user_id=receive_id)
    send_reply(receive_id, receive_id_type, response_text)
```

**发送回复**：
```python
def send_reply(receive_id: str, receive_id_type: str, text: str) -> bool:
    """修复: 接受 receive_id_type 参数（Critical Fix C3）"""
    client = get_lark_client()
    content = json.dumps({'text': text})
    
    request_obj = CreateMessageRequest.builder() \
        .receive_id_type(receive_id_type) \
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type("text")
            .content(content)
            .build()
        ) \
        .build()
    
    response = client.im.v1.message.create(request_obj)
    return response.code == 0
```

#### 2. bot/handlers.py - 消息处理逻辑

**命令解析**：
```python
def parse_command(text: str) -> tuple:
    """
    解析用户命令
    
    支持命令：
    - /search <关键词> - 关键词搜索
    - /sku <SKU编号> - SKU 搜索
    - /help - 帮助信息
    """
    text = text.strip()
    
    if text.startswith('/search '):
        return 'search', text[8:].strip()
    elif text.startswith('/sku '):
        return 'sku', text[5:].strip()
    elif text == '/help':
        return 'help', ''
    else:
        return 'smart', text  # 默认智能搜索
```

**消息处理主函数**：
```python
def handle_message(message_text: str, user_id: Optional[str] = None) -> str:
    """
    处理用户消息并返回回复内容
    
    Args:
        message_text: 用户消息文本
        user_id: 用户 ID（可选，用于搜索日志）
    
    Returns:
        格式化的回复文本
    """
    command_type, query = parse_command(message_text)
    
    if command_type == 'help':
        return format_help_message()
    
    # 执行搜索
    if command_type == 'search':
        search_result = search_by_keyword(query)
        search_type = 'keyword'
    elif command_type == 'sku':
        search_result = search_by_sku_exact(query)
        search_type = 'sku'
    else:  # smart search
        result = smart_search(query)
        search_result = result['results']
        search_type = result['search_type']
    
    # 记录搜索日志
    log_search(
        user_id=user_id,
        query=query,
        result_count=len(search_result),
        search_type=search_type
    )
    
    # 格式化结果
    if search_result:
        return format_search_results(search_result, query)
    else:
        return f"未找到与 \"{query}\" 相关的知识条目\n\n提示：\n• 尝试使用不同的关键词\n• 使用 /help 查看使用帮助"
```

**搜索日志记录**：
```python
def log_search(user_id: str, query: str, result_count: int, search_type: str):
    """记录搜索日志到 search_logs 表"""
    try:
        client = get_supabase_client()
        client.table('search_logs').insert({
            'user_id': user_id,
            'query': query,
            'result_count': result_count,
            'search_type': search_type,
            'created_at': datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
```

#### 3. bot/formatters.py - 消息格式化

**知识条目格式化**：
```python
def format_knowledge_entry(entry: Dict[str, Any], index: int = None) -> str:
    """格式化单个知识条目"""
    header = f"📄 结果 {index}" if index else "📄 知识条目"
    
    sku_line = f"SKU: {entry['sku']}" if entry.get('sku') else ""
    title = entry.get('title', '无标题')
    content = entry.get('content', '无内容')
    
    # 内容截断（避免消息过长）
    if len(content) > 500:
        content = content[:500] + '...'
    
    keywords = entry.get('keywords', [])
    keywords_str = f"关键词: {', '.join(keywords)}" if keywords else ""
    
    source_group = entry.get('source_group', '')
    source_line = f"来源: {source_group}" if source_group else ""
    
    # 组合消息
    parts = [header, sku_line, f"**{title}**", "", content, "", keywords_str, source_line]
    return '\n'.join(filter(None, parts))
```

**搜索结果列表格式化**：
```python
def format_search_results(results: List[Dict[str, Any]], query: str) -> str:
    """格式化搜索结果列表"""
    if not results:
        return f"未找到与 \"{query}\" 相关的知识条目"
    
    # 标题
    header = f"🔍 搜索 \"{query}\" - 找到 {len(results)} 条结果\n\n"
    
    # 格式化每个条目
    formatted_entries = [
        format_knowledge_entry(entry, i + 1)
        for i, entry in enumerate(results)
    ]
    
    # 分隔符
    separator = "\n" + "─" * 40 + "\n\n"
    
    return header + separator.join(formatted_entries)
```

**帮助消息**：
```python
def format_help_message() -> str:
    """格式化帮助信息"""
    return """📚 产品知识库机器人 - 使用帮助

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

**提示：**
• 支持中文全文搜索
• SKU 格式：3字母+3数字-4数字（如 CBC004-1234）
• 搜索结果按时间倒序排列

如有问题，请联系管理员"""
```

### Critical Issues 修复记录

#### C1: Token 验证（v1/v2 兼容）
- **问题**：v2 事件的 token 在 `header.token`，v1 在顶层 `token`
- **修复**：
  ```python
  token = data.get('token') or data.get('header', {}).get('token')
  ```

#### C2: 加密事件处理
- **问题**：调用 `cipher.decrypt_string()` 但实际方法是 `decrypt_str()`
- **影响**：所有加密事件会触发 500 错误
- **修复**：
  ```python
  decrypted = cipher.decrypt_str(data['encrypt'])
  ```

#### C3: receive_id_type 动态选择
- **问题**：fallback 到 open_id 但仍用 `receive_id_type="user_id"` 发送
- **影响**：回复消息可能发送失败
- **修复**：
  ```python
  # 动态选择 ID 类型
  if sender_id.get('open_id'):
      receive_id = sender_id['open_id']
      receive_id_type = 'open_id'
  # ...
  
  # send_reply 接受 receive_id_type 参数
  def send_reply(receive_id: str, receive_id_type: str, text: str):
  ```

#### C4: 线程安全
- **问题**：`is_message_processed()` 有竞态条件
- **影响**：并发请求可能绕过去重检查
- **修复**：
  ```python
  message_cache_lock = threading.Lock()
  
  def is_message_processed(message_id: str) -> bool:
      with message_cache_lock:
          # 所有字典操作都在锁保护下
  ```

#### 额外修复：User ID 回归
- **问题**：`process_message_async()` 未传递 user_id 给 `handle_message()`
- **影响**：搜索日志丢失用户追踪
- **修复**：
  ```python
  response_text = handle_message(message_text, user_id=receive_id)
  ```

### 生产环境注意事项

**单 Worker 模式**：
```python
# 当前实现使用全局字典 + 线程锁
# 仅支持单 Worker 部署
app.run(host='0.0.0.0', port=5000, debug=False)
```

**多 Worker 部署需要**：
- 使用 Redis 存储去重缓存
- 分布式锁（Redis Lock）
- 参考 Phase 2 改进计划

### Commits
- `bc43700` - feat: implement Feishu webhook service with message handling
- `bd66eb6` - fix: resolve critical issues C1-C4 in webhook service
- `0d369ce` - fix: resolve additional critical bugs in webhook service

---

## 已知限制与 Phase 2 改进方向

### 当前限制

1. **搜索能力**
   - 仅支持基础全文搜索（无语义理解）
   - 中文分词依赖 PostgreSQL 'simple' 配置（较粗糙）
   - 无相关性排序（仅按时间倒序）

2. **消息去重**
   - 仅支持单 Worker 部署
   - 内存缓存（重启后丢失）
   - 5 分钟过期时间固定

3. **知识库管理**
   - 缺少 Web 管理界面
   - 无批量导入工具
   - 无审核工作流

4. **飞书机器人**
   - 仅支持文本消息（无富文本、卡片）
   - 无对话上下文记忆
   - 回复无排版优化

### Phase 2 计划改进

1. **AI 语义搜索**
   - 集成 Embedding 模型（OpenAI/本地）
   - 向量数据库（pgvector）
   - 语义相似度匹配

2. **智能分类与标签**
   - LLM 自动提取关键词
   - 自动分类知识条目
   - 智能摘要生成

3. **多 Worker 支持**
   - Redis 去重缓存
   - 分布式锁
   - 水平扩展能力

4. **管理界面**
   - 飞书多维表格视图
   - 审核工作流
   - 批量导入工具

5. **增强交互**
   - 飞书消息卡片
   - 对话上下文
   - 反馈收集（helpful_count）

---

## 部署指南

### 环境要求

- Python 3.9+
- PostgreSQL 13+ (Supabase)
- macOS (launchd 定时任务)

### 安装步骤

1. **克隆仓库**
   ```bash
   cd ~/Projects
   git clone <repository-url> product-knowledge-base
   cd product-knowledge-base
   ```

2. **创建虚拟环境**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入实际配置
   ```

5. **初始化数据库**
   - 在 Supabase 控制台执行 `database/schema.sql`
   - 验证表和索引创建成功

6. **测试搜索功能**
   ```bash
   pytest tests/test_search.py -v
   ```

### 飞书应用配置

1. **创建飞书应用**
   - 访问 [飞书开放平台](https://open.feishu.cn/)
   - 创建企业自建应用
   - 获取 App ID 和 App Secret

2. **配置权限**
   - im:message - 接收群聊和私聊消息
   - im:message:send_as_bot - 发送消息

3. **配置事件订阅**
   - Webhook URL: `https://your-domain.com/webhook`
   - 订阅事件：`im.message.receive_v1`
   - 配置 Verification Token
   - （可选）配置 Encrypt Key

4. **更新 .env**
   ```bash
   FEISHU_APP_ID=cli_xxx
   FEISHU_APP_SECRET=xxx
   FEISHU_VERIFICATION_TOKEN=xxx
   FEISHU_ENCRYPT_KEY=xxx  # 可选
   ```

### 启动服务

**开发环境**：
```bash
python -m bot.main
```

**生产环境**（使用 Gunicorn）：
```bash
gunicorn -w 1 -b 0.0.0.0:5000 bot.main:app
```
⚠️ 注意：当前版本仅支持单 Worker (`-w 1`)

### 验证部署

1. **健康检查**
   ```bash
   curl http://localhost:5000/health
   ```

2. **Webhook 测试**
   - 在飞书中 @机器人 发送消息
   - 检查日志确认接收和回复

3. **搜索测试**
   - 发送：`CBC004-1234`（SKU 搜索）
   - 发送：`加热杯漏水`（关键词搜索）
   - 发送：`/help`（帮助信息）

---

## 附录

### 目录结构

```
product-knowledge-base/
├── bot/                      # 飞书机器人服务
│   ├── __init__.py
│   ├── config.py            # 配置管理
│   ├── formatters.py        # 消息格式化
│   ├── handlers.py          # 消息处理
│   ├── main.py              # Flask Webhook 服务
│   └── search.py            # 搜索逻辑
├── database/                 # 数据库
│   └── schema.sql           # 数据库 Schema
├── scripts/                  # 数据采集脚本
│   ├── sync_feishu_bitable.py
│   └── utils.py
├── tests/                    # 单元测试
│   ├── __init__.py
│   └── test_search.py
├── .env.example              # 环境变量模板
├── .gitignore
├── pytest.ini                # Pytest 配置
├── requirements.txt          # Python 依赖
└── IMPLEMENTATION_PHASE1.md  # 本文档
```

### Git Commit 历史

```
0d369ce - fix: resolve additional critical bugs in webhook service
bd66eb6 - fix: resolve critical issues C1-C4 in webhook service
bc43700 - feat: implement Feishu webhook service with message handling
8df4e1d - test: add comprehensive search function unit tests
7a5e3f9 - fix: use 'simple' config for Chinese full-text search
56c6d62 - fix: use correct plfts method for full-text search
c8f4e2a - feat: implement search logic with smart routing
eac8bc9 - feat: add configuration management and .env template
ef1f2a7 - feat: add SKU extraction and Supabase client utilities
0f0e682 - feat: add Feishu Bitable sync script with field mapping
d9c5f7d - feat: add comprehensive database schema with search support
```

### 相关文档

- 设计文档：`~/docs/superpowers/specs/2026-04-26-product-knowledge-base-design.md`
- 实施计划：`~/docs/superpowers/plans/2026-04-26-product-knowledge-base-phase1.md`

---

**文档版本**：v1.0  
**最后更新**：2026-04-27  
**覆盖范围**：Tasks 1-7  
**下一步**：Task 8 - 定时任务配置（launchd）
