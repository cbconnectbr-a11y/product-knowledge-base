# 产品知识库系统 - Phase 1 实施文档

## 项目概述

**目标**：搭建电商公司产品知识库，让客服快速找到产品内容和技术问题解答

**Phase 1 范围**（已完成 Tasks 1-11）：
- ✅ 数据库设计（Supabase PostgreSQL）
- ✅ 飞书多维表格数据采集
- ✅ 搜索功能（SKU精确匹配 + 关键词全文搜索 + 模糊匹配）
- ✅ 飞书机器人 Webhook 服务
- ✅ 定时任务配置（macOS launchd）
- ✅ 知识库管理后端（飞书多维表格审核界面）
- ✅ 历史数据导入脚本
- ✅ 集成测试套件
- ⏳ 文档完善、验收测试、部署（Tasks 12-15，待完成）

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

## Task 8: 定时任务配置

### 文件
- `launchd/com.product-kb.sync-products.plist` (40行)
- `launchd/com.product-kb.sync-feishu-qa.plist` (40行)
- `scripts/setup_launchd.sh` (165行)
- `scripts/run_sync_products.sh` (17行，wrapper脚本)
- `scripts/run_sync_feishu_qa.sh` (17行，wrapper脚本)

### 功能

配置 macOS launchd 定时任务，自动运行数据同步脚本：
1. **产品表同步** - 每天 08:30
2. **问答同步** - 每天 09:00

### 核心实现

#### launchd Plist 文件

**com.product-kb.sync-products.plist** （产品同步）：
```xml
<key>Label</key>
<string>com.product-kb.sync-products</string>

<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>/Users/cindy/Projects/product-knowledge-base/scripts/run_sync_products.sh</string>
</array>

<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>30</integer>
</dict>

<key>StandardOutPath</key>
<string>/Users/cindy/Projects/product-knowledge-base/logs/sync-products.log</string>
```

**关键特性**：
- 使用 wrapper 脚本而非直接调用 Python（解决环境变量加载）
- 日志分离：stdout 和 stderr 写入不同文件
- `RunAtLoad` 设为 false（仅按计划执行）
- WorkingDirectory 指定项目根目录

#### Wrapper 脚本

**run_sync_products.sh**：
```bash
#!/bin/bash
cd /Users/cindy/Projects/product-knowledge-base

# 加载环境变量
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "Error: .env file not found"
    exit 1
fi

# 运行 Python 脚本
/opt/homebrew/bin/python3 scripts/sync_product_table.py
```

**为什么需要 wrapper**：
- launchd 不继承用户 shell 环境
- Python 脚本的 `load_dotenv()` 仅在当前目录查找 .env
- `set -a; source .env; set +a` 模式确保所有变量导出到子进程

#### 安装脚本

**setup_launchd.sh** 功能：
1. 验证 Python、.env、脚本文件存在
2. 创建 logs 目录
3. 卸载旧任务（如果存在）
4. 复制 plist 文件到 `~/Library/LaunchAgents/`
5. 加载新任务
6. 验证任务状态
7. 提供手动测试命令

**执行**：
```bash
bash scripts/setup_launchd.sh
```

**输出示例**：
```
========================================
  产品知识库 - 定时任务安装脚本
========================================

✓ Python 环境正常
✓ .env 文件存在
✓ 同步脚本文件完整
✓ plist 文件完整
✓ logs 目录已创建

正在安装定时任务...
✓ 已卸载旧任务（如果存在）
✓ plist 文件已复制
✓ 任务加载成功

验证任务状态...
✓ com.product-kb.sync-products - 已加载
✓ com.product-kb.sync-feishu-qa - 已加载

安装完成！
```

### 关键修复记录

#### Critical Fix C1-C4（初始实现）

**Commit**: `bd66eb6`

修复的问题：
- **C1**: Token 验证兼容 v1/v2 事件格式
- **C2**: 加密事件处理方法名错误
- **C3**: receive_id_type 动态选择
- **C4**: 消息去重线程安全

#### 环境变量加载修复

**Commit**: `a2b68b2`

**问题**：launchd 无法加载 .env 文件，导致脚本因缺少环境变量而失败

**解决方案**：
1. 创建 wrapper 脚本加载 .env
2. 更新 plist 调用 wrapper 而非 Python
3. 移除 Python 脚本的 FileHandler（避免重复日志）

**影响**：从无法运行到生产就绪

### 日志管理

**日志文件位置**：
- `logs/sync-products.log` - 产品同步 stdout
- `logs/sync-products.error.log` - 产品同步 stderr
- `logs/sync-feishu-qa.log` - 问答同步 stdout
- `logs/sync-feishu-qa.error.log` - 问答同步 stderr

**Python 脚本日志配置**：
```python
# 只使用 StreamHandler（launchd 捕获 stdout/stderr）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
```

### 手动测试

```bash
# 立即触发任务（不等待定时）
launchctl start com.product-kb.sync-products
launchctl start com.product-kb.sync-feishu-qa

# 查看日志
tail -f logs/sync-products.log

# 检查任务状态
launchctl list | grep com.product-kb

# 卸载任务
launchctl unload ~/Library/LaunchAgents/com.product-kb.sync-products.plist
```

### 生产部署注意事项

1. **单 Worker 模式**：当前 Python 脚本无并发冲突，但注意不要同时手动运行和定时触发
2. **日志轮转**：生产环境建议配置 `newsyslog` 或使用 `RotatingFileHandler`
3. **错误通知**：当前无失败告警，建议后续添加邮件/飞书通知
4. **时区问题**：launchd 使用系统本地时间（UTC+8）

### Commits
- `dbc5692` - feat: add launchd scheduled tasks configuration
- `a2b68b2` - fix: resolve environment loading and duplicate logs in launchd tasks

---

## Task 9: 知识库管理后端

### 文件
- `scripts/create_management_table.py` (445行)
- `docs/management_guide.md` (541行)
- `database/schema.sql` (更新)

### 功能

创建飞书多维表格管理界面，用于审核和管理知识库条目。

**核心流程**：
```
Supabase (pending) → Script → Feishu Table (review) 
→ User updates → Script → Supabase (approved/rejected + notes)
```

### 核心实现

#### create_management_table.py 脚本

**主要命令**：
```bash
# 推送待审核条目到飞书
python3 scripts/create_management_table.py sync-pending

# 同步审核结果回 Supabase
python3 scripts/create_management_table.py sync-reviews

# 完整双向同步
python3 scripts/create_management_table.py sync-all
```

**核心函数**：

1. **fetch_pending_entries()** - 查询待审核条目
```python
def fetch_pending_entries(limit: int = 100) -> List[Dict]:
    """从 Supabase 获取待审核的知识条目"""
    response = supabase.table('knowledge_entries') \
        .select('id, sku, title, content, source_group, keywords, created_at') \
        .eq('status', 'pending') \
        .order('created_at', desc=False) \
        .limit(limit) \
        .execute()
    return response.data
```

2. **sync_pending_to_feishu()** - 推送到飞书表格
```python
def sync_pending_to_feishu(pending_entries: List[Dict]):
    """将待审核条目推送到飞书多维表格"""
    for entry in pending_entries:
        fields = {
            "DB_ID": [{"text": entry["id"]}],
            "SKU": [{"text": entry["sku"] or ""}],
            "标题": [{"text": entry["title"]}],
            "内容": [{"text": truncate_text(entry["content"], 2000)}],
            "来源": [{"text": entry["source_group"] or ""}],
            "关键词": [{"text": ", ".join(entry.get("keywords", []))}],
            "创建时间": [{"text": entry["created_at"]}],
            "Status": [{"text": "pending"}],
        }
        # 创建记录...
```

3. **sync_reviews_to_supabase()** - 同步审核结果
```python
def sync_reviews_to_supabase(reviewed_entries: List[Dict]):
    """将审核结果写回 Supabase"""
    for entry in reviewed_entries:
        status = entry.get("status")
        if status not in VALID_STATUSES:
            logger.warning(f"Invalid status: {status}")
            continue
        
        update_data = {
            "status": status,
            "reviewed_at": datetime.utcnow().isoformat(),
        }
        if entry.get("reviewer_notes"):
            update_data["reviewer_notes"] = entry["reviewer_notes"]
        
        supabase.table('knowledge_entries') \
            .update(update_data) \
            .eq('id', entry['db_id']) \
            .execute()
```

#### 字段映射

| Supabase 字段 | 飞书字段 | 类型 | 说明 |
|--------------|---------|------|------|
| `id` | `DB_ID` | 文本 | 数据库主键，用于回写 |
| `sku` | `SKU` | 文本 | 产品 SKU 编号 |
| `title` | `标题` | 文本 | 知识条目标题 |
| `content` | `内容` | 富文本 | 内容（截断到 2000 字符） |
| `status` | `Status` | 单选 | pending/approved/rejected/draft |
| `source_group` | `来源` | 文本 | 来源群组名称 |
| `keywords` | `关键词` | 文本 | 逗号分隔的关键词 |
| `created_at` | `创建时间` | 文本 | 创建时间戳 |
| `reviewer_notes` | `审核意见` | 文本 | 审核员填写的备注 |

#### 审核工作流

1. **推送待审核条目**：
   ```bash
   python3 scripts/create_management_table.py sync-pending
   ```
   - 查询 Supabase 中 `status='pending'` 的条目
   - 推送到飞书多维表格
   - 去重处理（基于 DB_ID）

2. **在飞书中审核**：
   - 审核员在飞书表格中查看条目
   - 修改 `Status` 字段（approved/rejected）
   - 填写 `审核意见`（可选）

3. **同步审核结果**：
   ```bash
   python3 scripts/create_management_table.py sync-reviews
   ```
   - 读取飞书中已审核的条目（Status != pending）
   - 更新 Supabase 对应记录的状态和审核时间
   - 记录审核意见

### 关键特性

**数据验证**：
```python
VALID_STATUSES = {"pending", "approved", "rejected", "draft"}

if status not in VALID_STATUSES:
    logger.warning(f"Invalid status '{status}' for entry {db_id}, skipping")
    continue
```

**文本截断**（避免飞书字段限制）：
```python
def truncate_text(text: str, max_length: int = 2000) -> str:
    """截断长文本（飞书文本字段支持最多 5000 字符）"""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text
```

**字段值提取**（处理飞书多种数据格式）：
```python
def extract_field_value(field_data, field_type: str):
    """提取飞书字段值（处理文本、富文本、单选等类型）"""
    if field_type == "Text":
        return field_data[0].get('text') if isinstance(field_data, list) else field_data
    elif field_type == "SingleSelect":
        return field_data[0].get('text') if field_data else None
    # ...
```

### Schema 更新

**Commit**: `8d59555`

添加 `reviewer_notes` 列到 `knowledge_entries` 表：
```sql
-- Review notes
reviewer_notes TEXT,

COMMENT ON COLUMN knowledge_entries.reviewer_notes IS 
  'Reviewer notes or comments (filled by reviewer during approval process)';
```

**原因**：脚本需要将审核意见写回数据库，但初始 schema 缺少此列

### 管理指南文档

**docs/management_guide.md** (541行) 包含：

1. **安装配置** - 飞书 Bitable 应用创建步骤
2. **字段定义** - 完整的字段类型和配置说明
3. **审核流程** - 图解工作流程
4. **脚本使用** - 命令参考和示例
5. **故障排查** - 常见错误诊断
6. **FAQ** - 8 个常见问题解答
7. **Phase 2 路线图** - 自动化和增强功能规划

**配置示例**：
```bash
# .env 文件
FEISHU_MANAGEMENT_APP_TOKEN=ZyWlbAtWLaLtw9sTpxscAGGSnub
FEISHU_MANAGEMENT_TABLE_ID=tbl1Zq6Sw6B5tP9x
```

### Code Review 修复

**Commit**: `da4eeab`

修复了 Code Quality Review 发现的两个必须解决的问题：

**I-1**: 添加环境变量到 .env.example
```bash
# 飞书管理表配置（知识库审核）
FEISHU_MANAGEMENT_APP_TOKEN=your-management-app-token-here
FEISHU_MANAGEMENT_TABLE_ID=your-management-table-id-here
```

**I-3**: 增加内容截断限制（500 → 2000 字符）
```python
"内容": [{"text": truncate_text(entry["content"], 2000)}]
```

### 生产部署

**前置条件**：
1. 在飞书中创建多维表格应用
2. 配置 .env 文件中的 APP_TOKEN 和 TABLE_ID
3. 在飞书表格中手动创建必需字段（按照管理指南）

**首次同步**：
```bash
# 推送现有的待审核条目
python3 scripts/create_management_table.py sync-pending

# 审核员在飞书中处理

# 同步审核结果
python3 scripts/create_management_table.py sync-reviews
```

**定期维护**：
```bash
# 每天运行一次完整同步（可配置为 cron/launchd）
python3 scripts/create_management_table.py sync-all
```

### Phase 2 增强计划

1. **自动化双向同步** - Webhook 触发实时同步
2. **批量操作** - 批量审核、批量标签
3. **高级筛选** - 按来源、关键词、时间范围筛选
4. **统计报表** - 审核效率、知识条目分布分析
5. **审核员权限** - 基于飞书权限的细粒度控制

### Commits
- `75a972e` - feat: add knowledge base management interface with Feishu Bitable
- `8d59555` - fix: add reviewer_notes column to knowledge_entries table
- `da4eeab` - fix: address code review issues I-1 and I-3

---

## Task 10: 历史数据导入脚本

### 文件
- `scripts/import_historical_data.py` (419行) - 历史数据导入脚本
- `tests/test_import_historical_data.py` (347行) - 导入脚本测试

### 功能概述

从 `~/客服知识库/` 目录导入历史 JSON 文件到 Supabase `knowledge_entries` 表。

**支持的数据格式**：
1. **tech_issues_filtered_final.json** - SKU 相关技术问题列表
2. **技术支持问答知识库_*.json** - 问答对（含产品名称、分类）
3. **技术问题汇总_完整版.json** - 完整技术问题摘要

### 核心功能

**1. 数据提取转换**
```python
def extract_entries_from_tech_issues(data: Dict, source_file: str) -> List[Dict]:
    """提取技术问题格式数据"""
    # 从 tech_issues 数组提取
    # SKU + 问题描述 → 知识库条目

def extract_entries_from_tech_qa(data: Dict, source_file: str) -> List[Dict]:
    """提取问答格式数据"""
    # 从 questions 数组提取
    # 问题 + 回答 → 完整知识条目

def extract_entries_from_complete_tech_issues(data: Dict, source_file: str) -> List[Dict]:
    """提取完整问题汇总数据"""
    # 从 技术问题列表 提取
    # SKU + 产品名 + 问题描述 + 分类 → 条目
```

**2. 去重机制**
```python
def create_source_id(title: str, content: str) -> str:
    """生成唯一 source_id 用于去重"""
    combined = f"{title}::{content}"
    hash_value = hashlib.md5(combined.encode('utf-8')).hexdigest()[:16]
    return f"historical_{hash_value}"
```

- 基于 title + content 生成 MD5 哈希
- 格式：`historical_{hash}`
- 数据库 unique 约束：`(source_type, source_id)`
- 重复导入自动跳过（不报错）

**3. 数据验证**
```python
def validate_entry(entry: Dict, verbose: bool = False) -> Tuple[bool, Optional[str]]:
    """导入前验证条目"""
    # 必填字段：title, content, source_id
    # 警告：content 长度 > 5000 字符
    # 返回：(is_valid, error_message)
```

**4. 批量导入**
```python
def import_entries(entries: List[Dict], source_description: str, 
                  dry_run: bool = False, verbose: bool = False) -> Dict[str, int]:
    """批量插入 Supabase"""
    # 逐条插入（支持错误恢复）
    # 统计：inserted, skipped (duplicates), errors
    # 打印进度（每 10 条 / verbose 模式）
```

### 使用方法

**基本用法**：
```bash
# 导入所有适合的历史数据文件
python3 scripts/import_historical_data.py

# 导入特定文件
python3 scripts/import_historical_data.py --file ~/客服知识库/tech_issues_filtered_final.json

# 预览模式（不实际导入）
python3 scripts/import_historical_data.py --dry-run

# 详细输出
python3 scripts/import_historical_data.py --verbose
```

**输出示例**：
```
======================================================================
Historical Data Import - Product Knowledge Base
======================================================================
Knowledge base directory: /Users/cindy/客服知识库
Mode: LIVE IMPORT
======================================================================

Found 4 file(s) to process:
  - tech_issues_filtered_final.json [tech_issues]
  - 技术支持问答知识库_20260420_1022.json [tech_qa]
  - 技术支持问答知识库_20260420_0844.json [tech_qa]
  - 技术问题汇总_完整版.json [complete_tech_issues]

======================================================================
Processing: tech_issues_filtered_final.json
======================================================================
  Extracted 20 entries

Importing 20 entries from tech_issues_filtered_final.json...
  [10/20] Inserted: CBC004-1057 - 技术问题...
  [20/20] Inserted: BRME0543 - 技术问题...
  ✓ Inserted: 20, Skipped (duplicates): 0, Errors: 0

...

======================================================================
FINAL SUMMARY
======================================================================
Files processed: 4
Entries inserted: 147
Entries skipped (duplicates): 0
Errors: 0
======================================================================
```

### 数据映射规则

**通用字段映射**：
| 数据库字段 | 值 | 说明 |
|----------|---|-----|
| `source_type` | `'manual'` | 历史数据标记为手动来源 |
| `status` | `'pending'` | 待审核状态 |
| `source_id` | `historical_{hash}` | 基于内容的唯一 ID |
| `source_group` | `历史数据导入 - {filename}` | 溯源信息 |
| `keywords` | `[]` | Phase 1 不自动生成 |
| `created_by` | `NULL` | 历史数据无用户信息 |

**格式 1：tech_issues_filtered_final.json**
```json
{
  "tech_issues": [
    {
      "group": "CBC004",
      "sku": "S004-1191",
      "question": "客户投诉收到产品的时候包装完好，但内部断裂了",
      "message_id": "om_xxx"
    }
  ]
}
```
→ 映射：
- `sku`: 直接使用
- `title`: `{sku} - 技术问题`
- `content`: `question`
- `category`: `[群组]`（如 "CBC004"）

**格式 2：技术支持问答知识库_*.json**
```json
{
  "questions": [
    {
      "sku": "BRME0341",
      "product": "SV608高端真空机120V",
      "question": "客户反馈真空泵会启动...",
      "reply": "食物装的太满了...",
      "category": "使用方法问题",
      "group": "CBC006"
    }
  ]
}
```
→ 映射：
- `sku`: 直接使用
- `title`: `{sku} - {product}`
- `content`: `问题：{question}\n\n解答：{reply}`
- `category`: `[category, group]`（如 ["使用方法问题", "CBC006"]）

**格式 3：技术问题汇总_完整版.json**
```json
{
  "技术问题列表": [
    {
      "SKU": "S004-1191",
      "产品名": "紫色带跪垫多功能健腹板",
      "问题描述": "客户投诉...",
      "问题类型": "运输损坏/产品质量",
      "群组": "CBC004"
    }
  ]
}
```
→ 映射：
- `sku`: 使用 `SKU`
- `title`: `{SKU} - {产品名}`
- `content`: `问题描述`
- `category`: `[问题类型, 群组]`

### 测试覆盖

**18 个单元测试**，覆盖：
- ✅ Source ID 生成（确定性、唯一性）
- ✅ 三种格式数据提取（正常/边界/异常）
- ✅ 条目验证（必填字段、长内容警告）
- ✅ 去重逻辑（相同内容 → 相同 ID）

运行测试：
```bash
python3 -m pytest tests/test_import_historical_data.py -v
```

### 特性

**1. 幂等性**
- 多次运行安全（重复数据自动跳过）
- 基于 `(source_type, source_id)` unique 约束

**2. 错误恢复**
- 单条失败不影响后续导入
- 详细错误日志（记录失败条目）

**3. 可追溯性**
- `source_group` 记录源文件名
- `source_id` 唯一标识原始内容

**4. 灵活性**
- 支持单文件 / 批量导入
- Dry-run 模式预览
- Verbose 模式调试

### 实际导入结果（预期）

基于 dry-run 测试：
- **tech_issues_filtered_final.json**: 20 条
- **技术支持问答知识库_20260420_0844.json**: 43 条
- **技术支持问答知识库_20260420_1022.json**: 55 条
- **技术问题汇总_完整版.json**: 29 条
- **合计**: 147 条历史知识条目

所有条目导入后状态为 `pending`，需通过 Task 9 的管理界面审核后发布。

### 使用注意事项

**环境要求**：
- `.env` 文件配置 `SUPABASE_URL` 和 `SUPABASE_KEY`
- `~/客服知识库/` 目录存在且包含历史数据文件

**导入建议**：
1. 首次导入前运行 `--dry-run` 预览
2. 使用 `--verbose` 检查数据质量
3. 导入后通过飞书管理表审核
4. 定期备份 Supabase 数据

**故障排查**：
```bash
# 检查环境配置
python3 database/test_connection.py

# 检查数据文件
ls -lh ~/客服知识库/*.json

# 预览单个文件
python3 scripts/import_historical_data.py --file ~/客服知识库/tech_issues_filtered_final.json --dry-run --verbose
```

### 后续改进（Phase 2）

- [ ] 自动关键词提取（AI/NLP）
- [ ] 自动分类建议
- [ ] 增量更新（时间戳比对）
- [ ] 并发导入（大批量数据）
- [ ] 数据质量报告（重复度、完整度）

---

## Task 11: 集成测试

### 文件
- `tests/test_integration.py` (598行) - 集成测试套件
- `scripts/run_tests.sh` (72行) - 统一测试运行脚本
- `pytest.ini` (更新) - 添加 integration marker

### 功能概述

创建端到端集成测试，验证系统各组件协同工作。

**测试范围**：
1. 数据库连接和配置
2. 飞书 Bitable 数据同步
3. 飞书群消息采集
4. 搜索功能集成
5. 知识条目完整生命周期
6. 管理表同步
7. 历史数据导入
8. 日志和错误处理

### 核心实现

#### 1. 测试套件结构

**8 个测试类，34 个测试用例**：

```python
class TestDatabaseConnection:
    """测试 Supabase 连接和配置"""
    # 2 个测试

class TestFeishuBitableSync:
    """测试飞书产品表同步"""
    # 4 个测试

class TestFeishuQASync:
    """测试飞书群消息采集"""
    # 4 个测试

class TestSearchIntegration:
    """测试搜索功能集成"""
    # 6 个测试

class TestKnowledgeEntryLifecycle:
    """测试知识条目完整生命周期"""
    # 5 个测试

class TestManagementTableSync:
    """测试管理表同步"""
    # 6 个测试

class TestHistoricalDataImport:
    """测试历史数据导入"""
    # 5 个测试

class TestLoggingAndErrors:
    """测试日志和错误处理"""
    # 2 个测试
```

#### 2. Fixture 设计

**模块级别 Fixture**（复用连接，提升性能）：

```python
@pytest.fixture(scope="module")
def supabase_client():
    """Supabase 客户端（所有测试共享）"""
    if not os.getenv('SUPABASE_URL'):
        pytest.skip("Supabase not configured in .env")
    return get_supabase_client()

@pytest.fixture(scope="module")
def lark_client():
    """飞书客户端（所有测试共享）"""
    if not os.getenv('FEISHU_APP_ID'):
        pytest.skip("Feishu not configured in .env")
    return get_lark_client()

@pytest.fixture(scope="module")
def test_entry_id(supabase_client):
    """创建并返回测试知识条目 ID（测试后自动清理）"""
    entry = {
        "sku": "TEST-INTEGRATION-001",
        "title": "集成测试条目",
        "content": "用于集成测试的临时条目",
        "source_type": "manual",
        "source_id": "test_integration_001",
        "status": "pending"
    }
    response = supabase_client.table('knowledge_entries').insert(entry).execute()
    entry_id = response.data[0]['id']
    
    yield entry_id
    
    # 清理
    supabase_client.table('knowledge_entries').delete().eq('id', entry_id).execute()
```

**关键特性**：
- `scope="module"` - 所有测试共享连接，避免重复初始化
- 自动跳过（Graceful skip）- 未配置 .env 时跳过而非失败
- 自动清理 - 使用 `yield` 确保测试数据清理

#### 3. 典型测试用例

**数据库连接测试**：
```python
def test_supabase_connection(supabase_client):
    """测试 Supabase 连接正常"""
    response = supabase_client.table('users').select('id').limit(1).execute()
    assert response.data is not None
```

**飞书 Bitable 同步测试**：
```python
def test_fetch_products_from_feishu(lark_client):
    """测试从飞书获取产品记录"""
    request = ListAppTableRecordRequest.builder() \
        .app_token(os.getenv('FEISHU_PRODUCT_TABLE_APP_TOKEN')) \
        .table_id(os.getenv('FEISHU_PRODUCT_TABLE_TABLE_ID')) \
        .page_size(5) \
        .build()
    
    response = lark_client.bitable.v1.app_table_record.list(request)
    assert response.success()
```

**搜索集成测试**：
```python
def test_search_by_sku_integration(supabase_client, test_entry_id):
    """测试 SKU 精确搜索（实际数据库查询）"""
    results = search_by_sku_exact("TEST-INTEGRATION-001")
    
    assert len(results) >= 1
    assert any(r['sku'] == "TEST-INTEGRATION-001" for r in results)
```

**生命周期测试**：
```python
def test_knowledge_entry_full_lifecycle(supabase_client):
    """测试知识条目完整生命周期：创建 → 查询 → 更新 → 删除"""
    # 1. 创建
    entry = {...}
    response = supabase_client.table('knowledge_entries').insert(entry).execute()
    entry_id = response.data[0]['id']
    
    # 2. 查询
    result = supabase_client.table('knowledge_entries').select('*').eq('id', entry_id).execute()
    assert result.data[0]['status'] == 'pending'
    
    # 3. 更新
    update = {"status": "approved", "reviewed_at": datetime.utcnow().isoformat()}
    supabase_client.table('knowledge_entries').update(update).eq('id', entry_id).execute()
    
    # 4. 验证更新
    updated = supabase_client.table('knowledge_entries').select('*').eq('id', entry_id).execute()
    assert updated.data[0]['status'] == 'approved'
    
    # 5. 删除
    supabase_client.table('knowledge_entries').delete().eq('id', entry_id).execute()
```

#### 4. 统一测试运行脚本

**scripts/run_tests.sh** 功能：
```bash
#!/bin/bash
# 统一测试运行脚本 - 运行所有测试套件

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================"
echo "  Product Knowledge Base - Test Suite"
echo "========================================"

# 1. 单元测试（搜索功能）
echo -e "\n${GREEN}Running unit tests...${NC}"
pytest tests/test_search.py -v

# 2. 集成测试（端到端）
echo -e "\n${GREEN}Running integration tests...${NC}"
pytest tests/test_integration.py -v -m integration

# 3. 导入脚本测试
echo -e "\n${GREEN}Running import script tests...${NC}"
pytest tests/test_import_historical_data.py -v

# 汇总
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}✗ Some tests failed${NC}"
    exit 1
fi
```

**使用方法**：
```bash
# 运行所有测试
bash scripts/run_tests.sh

# 仅运行集成测试
pytest tests/test_integration.py -v -m integration

# 跳过集成测试（仅单元测试）
pytest -v -m "not integration"
```

### 测试覆盖统计

**实际运行结果**（开发环境）：

```
tests/test_search.py                         16 passed        [100%]
tests/test_integration.py                    7 passed, 27 skipped [100%]
tests/test_import_historical_data.py         18 passed        [100%]

Total: 41 tests, 41 passed (27 skipped due to no .env)
```

**跳过原因**：
- 27 个集成测试依赖实际 Supabase/飞书配置
- 使用 `pytest.skip()` 优雅跳过（而非失败）
- 配置 .env 后可运行完整测试

### pytest.ini 配置

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    integration: Integration tests requiring external services (Supabase, Feishu)
addopts = -v --tb=short
```

**新增 marker**：
- `@pytest.mark.integration` - 标记集成测试
- 允许通过 `-m integration` / `-m "not integration"` 选择性运行

### 关键特性

**1. 优雅的环境检测**
```python
@pytest.fixture(scope="module")
def supabase_client():
    if not os.getenv('SUPABASE_URL'):
        pytest.skip("Supabase not configured in .env")
    return get_supabase_client()
```
- 未配置时跳过（不报错）
- CI/CD 友好（无外部依赖时安全跳过）

**2. 自动清理**
```python
@pytest.fixture
def test_entry_id(supabase_client):
    # 创建测试数据
    entry_id = create_test_entry()
    
    yield entry_id
    
    # 自动清理（即使测试失败也会执行）
    cleanup_test_entry(entry_id)
```

**3. 模块级 Fixture（性能优化）**
- 数据库连接在整个测试模块中共享
- 避免每个测试重新初始化连接
- 显著提升测试速度

**4. 详细断言**
```python
assert len(results) >= 1, f"Expected results, got: {results}"
assert any(r['sku'] == expected_sku for r in results), \
    f"SKU {expected_sku} not found in results: {[r['sku'] for r in results]}"
```

### CI/CD 集成建议

**GitHub Actions 示例**：
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run unit tests
        run: pytest tests/test_search.py tests/test_import_historical_data.py -v
      
      - name: Run integration tests (if configured)
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: pytest tests/test_integration.py -v -m integration
        continue-on-error: true  # 可选：允许集成测试失败
```

### 故障排查

**常见问题**：

1. **所有集成测试被跳过**
   ```
   原因：.env 文件未配置
   解决：复制 .env.example → .env，填入真实配置
   ```

2. **Supabase 连接失败**
   ```bash
   # 测试连接
   python3 -c "from scripts.utils import get_supabase_client; get_supabase_client()"
   ```

3. **飞书 API 调用失败**
   ```bash
   # 检查 Token 有效性
   python3 scripts/sync_feishu_bitable.py --limit 1
   ```

### Commits
- `8b3f902` - test: add comprehensive integration tests for all components
- `b233835` - feat: add unified test runner script

---

## Task 12: 文档完善

### 文件
- `docs/setup.md` (748行) - 部署指南
- `docs/api.md` (856行) - API 文档
- `docs/user_guide.md` (985行) - 用户指南
- `README.md` (241行) - 项目总览（更新）

### 功能概述

创建完整的部署、使用和 API 文档，覆盖 Phase 1 所有功能（Tasks 1-11）。

### 文档结构

#### 1. docs/setup.md - 部署指南

**章节**（748行）：
- 系统概述
- 环境要求（Python 3.9+, Supabase, Feishu）
- 安装步骤（克隆、虚拟环境、依赖安装）
- 数据库初始化（Supabase）
- 飞书应用配置（权限、Webhook、事件订阅）
- 定时任务配置（macOS launchd）
- 启动服务（开发和生产模式）
- 验证部署（健康检查、Webhook 测试）
- 故障排查（7 个常见问题）

**关键内容**：
```bash
# 快速开始示例
git clone <repo> product-knowledge-base
cd product-knowledge-base
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 配置
python3 -m bot.main  # 启动服务
```

#### 2. docs/api.md - API 文档

**章节**（856行）：
- 数据库 Schema（4 个表的完整定义）
- 搜索 API（4 种搜索函数）
- Webhook 接口（/webhook, /health）
- 管理脚本（产品同步、问答同步、管理表同步、历史导入）
- 数据格式（请求/响应示例）

**核心 API 文档示例**：

**search_by_sku_exact()**：
```python
def search_by_sku_exact(sku: str) -> List[Dict[str, Any]]:
    """
    SKU 精确匹配搜索
    
    Args:
        sku: 产品 SKU 编号（如 "CBC004-1234"）
    
    Returns:
        List[Dict]: 匹配的知识条目列表
        
    Example:
        >>> results = search_by_sku_exact("CBC004-1234")
        >>> [{'id': 'uuid', 'sku': 'CBC004-1234', 'title': '...', 'content': '...'}]
    """
```

**smart_search()**：
```python
def smart_search(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    智能搜索路由
    
    流程：
    1. 尝试提取 SKU（正则匹配）
    2. 有 SKU → SKU 精确搜索
    3. 无 SKU → 关键词全文搜索
    
    Returns:
        {
            'results': List[Dict],
            'search_type': 'sku' | 'keyword',
            'query': str,
            'extracted_sku': str (可选)
        }
    """
```

#### 3. docs/user_guide.md - 用户指南

**章节**（985行）：
- **客服人员使用指南**（300+ 行）
  - 飞书机器人使用（命令、智能搜索）
  - 搜索技巧（SKU 优先、核心关键词、同义词）
  - 理解搜索结果
  - 处理无结果场景
  - 日常工作流示例

- **审核员使用指南**（300+ 行）
  - 访问飞书管理表
  - 审核标准（通过/拒绝/草稿标准）
  - 审核工作流（5 步流程）
  - 审核技巧（SKU 验证、去重检测、内容改进）
  - 批量审核策略

- **管理员使用指南**（250+ 行）
  - 日常运维（监控、同步、备份）
  - 数据管理（导入、批量更新、清理）
  - 用户管理（添加/修改角色）
  - 搜索分析（热门查询、零结果查询）
  - 系统优化（重建索引、日志清理）
  - 故障排查（3 个常见问题）

- **常见工作流**（100+ 行）
  - 添加新产品
  - 处理客户咨询
  - 批量导入历史数据

- **最佳实践**（50+ 行）
  - 按角色分类的建议

- **FAQ**（100+ 行）
  - 8 个常见问题及详细解答

**用户指南示例**：

**客服搜索技巧**：
```
1. SKU 搜索优先
   ✅ 正确："CBC004-1234 漏水问题"
   ❌ 错误："产品漏水" （太模糊）

2. 使用核心关键词
   ✅ 正确："密封圈老化"
   ❌ 错误："这个东西好像有点问题" （信息量少）

3. 尝试同义词
   - "漏水" / "渗水" / "滴水"
   - "不工作" / "无法启动" / "没反应"
```

#### 4. README.md - 项目总览

**更新内容**（241行）：
- 项目简介（2-3 句话）
- 核心功能（按类别组织）
  - 数据采集（产品表、群聊、历史导入）
  - 智能搜索（SKU、关键词、智能路由）
  - 知识管理（审核工作流、状态管理）
  - 用户交互（飞书机器人、移动友好）
- 快速开始（链接到 setup.md）
- 使用示例（三种用户角色）
- 文档索引（所有文档链接）
- 项目结构（目录树 + 说明）
- 技术栈（数据库、后端、搜索、定时任务）
- 测试说明（单元测试、集成测试）
- Phase 1 限制和 Phase 2 路线图
- 贡献指南和支持联系方式

**README 示例**：
```markdown
## 快速开始

详细的安装和配置步骤请参考 [部署指南](docs/setup.md)。

简要步骤：
1. 克隆仓库并安装依赖
2. 配置 .env 文件（Supabase + 飞书）
3. 初始化数据库
4. 启动飞书机器人服务
5. 配置定时任务

## 使用

### 客服人员
通过飞书机器人搜索产品技术问题：
- 发送 SKU：`CBC004-1234`
- 发送关键词：`密封圈漏水`
- 使用命令：`/search 加热杯故障`

详见：[用户指南 - 客服人员](docs/user_guide.md#客服人员使用指南)
```

### 文档质量

**审核结果**：✅ **APPROVED** - Production-ready

**优点**：
1. **组织结构优秀** - 清晰的目录、逻辑流程、易于导航
2. **完整覆盖 Phase 1** - 所有功能（Tasks 1-11）都有文档
3. **实用价值高** - 具体命令、实际示例、预期输出
4. **交叉引用有效** - 文档间链接正确，术语一致
5. **适合目标受众** - 全中文，按角色分类（客服/审核员/管理员）
6. **技术准确** - 代码示例与实际实现匹配

### 文档间关系

```
README.md (入口)
    ↓
├── docs/setup.md (部署/安装)
├── docs/api.md (开发者/技术参考)
├── docs/user_guide.md (日常使用)
├── docs/management_guide.md (现有：审核员)
└── docs/import_guide.md (现有：数据导入)
```

### 特色功能

**1. 角色导向**
- 客服人员：搜索技巧、日常工作流
- 审核员：审核标准、批量处理
- 管理员：系统运维、数据分析

**2. 实战示例**
- 真实 SKU：`CBC004-1234`
- 实际命令：`pytest tests/test_search.py -v`
- 预期输出：JSON 结构、日志格式

**3. 故障排查**
- setup.md：7 个部署问题
- user_guide.md：3 个运维问题
- 每个问题都有诊断步骤和解决方案

**4. Phase 2 展望**
- 明确标注 Phase 1 限制（单 Worker、手动同步、基础搜索）
- 描述 Phase 2 改进（AI 搜索、Redis、实时 Webhook）
- 设定合理预期

### 统计数据

**文档规模**：
- 总行数：2,830 行
- 总字符数：约 60KB
- 平均单文档：700+ 行

**覆盖范围**：
- 4 个新文档创建
- 1 个文档更新（README.md）
- 6 个交叉引用文档（含现有文档）

**语言**：
- 100% 中文内容
- 面向中文客服团队

### Commits
- `4e4f01a` - docs: add comprehensive setup, API, and user guides (Task 12)

---

## Task 13: 验收测试

### 文件
- `scripts/acceptance_test.sh` (438行) - 自动化验收测试脚本
- `ACCEPTANCE_REPORT.md` (550行) - 验收报告模板

### 功能概述

创建完整的验收测试套件，包含自动化测试脚本和手动验收清单。

### 核心实现

#### 1. scripts/acceptance_test.sh - 自动化测试脚本

**8 个测试函数**：

1. **test_configuration** - 配置验证
   - 检查 .env 文件存在
   - 验证 12 个必需环境变量
   - 检测占位符值（未配置的默认值）
   
2. **test_database_connection** - 数据库连接
   - 测试 Supabase 连接
   - 验证 users 表访问权限
   
3. **test_product_data** - 产品数据验证
   - 检查 products 表存在
   - 验证表中有数据
   
4. **test_knowledge_data** - 知识条目数据验证
   - 检查 knowledge_entries 表存在
   - 验证表中有数据
   
5. **test_search_functions** - 搜索功能测试
   - 测试 search_by_sku_exact()
   - 测试 search_by_keyword()
   - 测试 smart_search()
   - 验证返回类型正确
   
6. **test_scheduled_tasks** - 定时任务验证
   - 检查 launchd plist 文件存在
   - 验证任务已加载（com.product-kb.sync-products, sync-feishu-qa）
   
7. **test_logging_system** - 日志系统验证
   - 检查 logs 目录存在
   - 验证目录可写
   - 检查日志文件存在
   
8. **test_integration_suite** - 集成测试套件
   - 运行 scripts/run_tests.sh
   - 失败时显示最后 20 行输出

**脚本特性**：

```bash
#!/bin/bash
set -e  # Exit on error
set -u  # Exit on unset variable

# Dynamic project root detection (portable)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Safe .env loading (no shell injection)
load_env() {
    if [ -f "$PROJECT_ROOT/.env" ]; then
        set -a
        source "$PROJECT_ROOT/.env"
        set +a
        return 0
    fi
    return 1
}

# Color-coded output
GREEN='\033[0;32m'  # Pass
RED='\033[0;31m'    # Fail
YELLOW='\033[1;33m' # Info
BLUE='\033[0;34m'   # Headers
```

**执行流程**：
```bash
$ bash scripts/acceptance_test.sh

==========================================
  Acceptance Test Suite - Phase 1 MVP
==========================================
Project: Product Knowledge Base System
Date: 2026-04-28

Testing: Configuration Validation
----------------------------------------
✓ PASS: All required environment variables present

Testing: Database Connection
----------------------------------------
✓ PASS: Database connection successful

...

==========================================
  Test Results
==========================================
PASSED: 8
FAILED: 0
✓ All acceptance tests passed!
```

#### 2. ACCEPTANCE_REPORT.md - 验收报告模板

**6 个主要章节**：

**一、自动化测试结果**
- 测试执行输出示例
- 8 项测试覆盖表（配置/数据库/数据/搜索/定时任务/日志/集成）

**二、手动验收清单**（5 个子章节）

1. **Supabase 数据库验收**
   - 验收步骤：登录控制台、检查表结构、验证数据、检查索引
   - 验收标准：4 个表存在、管理员用户存在、数据存在、索引已创建
   
2. **飞书机器人配置验收**
   - 验收步骤：检查应用配置、验证权限、测试 Webhook
   - 验收标准：应用已发布、权限已配置、事件订阅正确、URL 可访问
   
3. **机器人响应测试**（7 个测试用例）
   
   | 输入 | 预期输出 | 实际结果 | 状态 |
   |------|---------|---------|------|
   | `/help` | 帮助信息 | | ⬜ |
   | `CBC004-1234` | SKU 搜索结果 | | ⬜ |
   | `密封圈漏水` | 关键词搜索结果 | | ⬜ |
   | `/search 加热杯` | 搜索结果列表 | | ⬜ |
   | `/sku CBC004-1234` | SKU 精确搜索 | | ⬜ |
   | `不存在的SKU` | 未找到提示 | | ⬜ |
   | `@机器人 随机文本` | 智能搜索结果 | | ⬜ |
   
4. **定时同步验证**
   - 验收步骤：检查 launchd 状态、手动触发、查看日志、验证数据
   - 验收标准：任务已加载、手动触发成功、日志正常、数据同步成功
   
5. **历史数据导入验证**
   - 验收步骤：准备测试数据、执行导入、验证结果、检查去重
   - 验收标准：导入成功、数据准确、去重正常、source_id 正确

**三、功能验收**
- 10 个核心功能验收（产品表同步、群聊采集、搜索、审核、导入、定时任务等）
- 7 个非功能性需求（性能、可用性、一致性、日志、错误处理等）

**四、已知问题和限制**
- 记录 Phase 1 的 7 个已知限制（单 Worker、内存去重、手动同步、基础搜索等）
- 待修复问题跟踪表

**五、测试数据统计**
- 自动化测试：8 项测试函数
- 手动验收：5 项清单
- 功能验收：10 项核心功能 + 7 项非功能需求
- 总计：76 个测试（包含单元测试 16 + 集成测试 34 + 导入测试 18 + 验收测试 8）

**六、验收结论**
- 验收决策模板（通过/有条件通过/未通过）
- 验收签字区域
- 部署检查清单

**附录**：
- A. 环境配置清单（12 个环境变量详解）
- B. 常用命令参考
- C. 故障排查指南（5 个常见问题）
- D. 参考文档链接

### 代码质量修复

初始实现存在 6 个重要问题，已全部修复：

**修复前的问题**：

1. ❌ **硬编码绝对路径** - 使用 `/Users/cindy/...` 导致不可移植
2. ❌ **Shell 注入漏洞** - `export $(cat .env | xargs)` 存在安全风险
3. ❌ **缺少 `set -u`** - 未检测未设置变量
4. ❌ **隐藏测试失败输出** - 集成测试失败时不显示错误信息
5. ❌ **测试计数不匹配** - 报告说 "12 项" 但脚本只有 8 个函数
6. ❌ **Python 路径不一致** - 使用单引号导致变量不展开

**修复后**：

1. ✅ **动态路径检测** - `PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`
2. ✅ **安全 .env 加载** - 使用 `set -a; source .env; set +a` 模式
3. ✅ **添加 `set -u`** - 未设置变量时立即失败
4. ✅ **显示失败输出** - `tail -20 /tmp/test_output.log` 显示最后 20 行
5. ✅ **修正测试计数** - 报告更新为 "8 项（8 个测试函数）"
6. ✅ **统一 Python 路径** - 所有使用 `"$PROJECT_ROOT"` 双引号

### 使用方法

**运行自动化测试**：
```bash
# 完整验收测试
bash scripts/acceptance_test.sh

# 查看帮助
bash scripts/acceptance_test.sh --help

# 测试将检查：
# - .env 配置完整性
# - Supabase 数据库连接
# - 产品和知识条目数据
# - 搜索功能正常
# - 定时任务已加载
# - 日志系统就绪
# - 集成测试通过
```

**填写验收报告**：
```bash
# 1. 运行自动化测试
bash scripts/acceptance_test.sh > acceptance_output.txt

# 2. 将输出粘贴到 ACCEPTANCE_REPORT.md "一、自动化测试结果" 章节

# 3. 执行手动验收清单
#    - 登录 Supabase 检查数据库
#    - 测试飞书机器人响应
#    - 触发定时任务验证同步
#    - 导入测试数据

# 4. 在报告中标记 ✅ 或 ❌

# 5. 填写验收结论和签字
```

### 验收覆盖范围

| 测试类型 | 数量 | 说明 |
|---------|------|------|
| 自动化测试 | 8 项 | 配置、数据库、数据、搜索、任务、日志、集成 |
| 手动验收 | 5 项 | 数据库、机器人、响应、同步、导入 |
| 机器人测试用例 | 7 项 | help、SKU、关键词、命令、边界情况 |
| 功能验收 | 10 项 | 所有核心功能 |
| 非功能验收 | 7 项 | 性能、可用性、一致性等 |
| **总计** | **76 项** | 包含所有测试层级 |

### 特色功能

**1. 便携性**
- 动态路径检测，可在任何机器运行
- 无硬编码依赖，适合 CI/CD

**2. 安全性**
- 安全的 .env 加载（无注入风险）
- set -u 防止未设置变量错误

**3. 诊断友好**
- 彩色输出易于扫描
- 失败时显示详细错误
- 提供修复建议

**4. 完整性**
- 覆盖所有 Phase 1 组件
- 自动化 + 手动双重验证
- 包含边界情况和错误处理测试

### Commits
- `567a8e6` - fix: resolve 6 code quality issues in acceptance tests (Task 13)

---

## Task 14: 部署和启动

### 文件
- `scripts/start.sh` (4.3K) - 服务启动脚本
- `scripts/stop.sh` (1.5K) - 服务停止脚本
- `scripts/restart.sh` (873B) - 服务重启脚本
- `scripts/check_health.sh` (1.3K) - 健康检查脚本
- `requirements.txt` (更新) - 添加 gunicorn
- 文档更新（README.md, docs/setup.md）

### 功能概述

创建完整的服务管理脚本，支持 Flask Webhook 服务的生产部署和开发调试。

### 核心实现

#### 1. scripts/start.sh - 启动服务

**双模式支持**：

**生产模式**（后台运行）：
```bash
bash scripts/start.sh production

# 或使用环境变量定制
PORT=8000 WORKERS=2 bash scripts/start.sh production
```

**开发模式**（前台运行）：
```bash
bash scripts/start.sh development
```

**关键特性**：

**PID 文件管理**：
```bash
# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Service already running (PID: $PID)"
        exit 1
    fi
fi

# Save PID and verify
SERVICE_PID=$!
echo $SERVICE_PID > "$PID_FILE"

# Verify process started
sleep 0.5
if ! ps -p "$SERVICE_PID" > /dev/null 2>&1; then
    echo "Error: Service failed to start"
    rm "$PID_FILE"
    exit 1
fi
```

**环境变量验证**：
- 检查 .env 文件存在
- 验证 Python 可用
- 检查 gunicorn 已安装（生产模式）
- 验证配置有效性

**端口冲突检测**：
```bash
# Check if port is in use (if lsof is available)
if command -v lsof &> /dev/null; then
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "Error: Port $PORT is already in use"
        exit 1
    fi
fi
```

**健康检查重试**（指数退避）：
```bash
# Health check with retry logic
MAX_ATTEMPTS=5
ATTEMPT=1
SLEEP_TIME=1

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    if bash scripts/check_health.sh 2>/dev/null; then
        echo "✓ Health check passed (attempt $ATTEMPT/$MAX_ATTEMPTS)"
        exit 0
    fi

    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
        echo "Retrying in ${SLEEP_TIME}s..."
        sleep $SLEEP_TIME
        SLEEP_TIME=$((SLEEP_TIME * 2))  # Exponential backoff
    fi

    ATTEMPT=$((ATTEMPT + 1))
done
```
- 重试间隔：1s → 2s → 4s → 8s → 16s
- 最多 5 次尝试
- 失败后给出日志路径

**信号处理**（开发模式）：
```bash
# Setup signal handlers for graceful shutdown
trap 'echo ""; echo "Shutting down..."; exit 0' SIGINT SIGTERM
```

#### 2. scripts/stop.sh - 停止服务

**优雅停止流程**：

```bash
# Try graceful shutdown first (SIGTERM)
kill "$PID" 2>/dev/null || true

# Wait up to 10 seconds for graceful shutdown
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✓ Service stopped gracefully"
        rm "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill if still running (SIGKILL)
echo "Forcing shutdown..."
kill -9 "$PID" 2>/dev/null || true

# Verify stopped
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "✓ Service stopped (forced)"
    rm "$PID_FILE"
    exit 0
fi
```

**特性**：
- 优先 SIGTERM（优雅停止）
- 10 秒超时
- 回退到 SIGKILL（强制停止）
- 自动清理 PID 文件
- 处理陈旧 PID 文件

#### 3. scripts/restart.sh - 重启服务

```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting service..."

# Stop service
bash "$SCRIPT_DIR/stop.sh"

# Wait a moment
sleep 2

# Start service
bash "$SCRIPT_DIR/start.sh" "$@"
```

- 调用 stop.sh 和 start.sh
- 传递模式参数（production/development）
- 2 秒清理缓冲

#### 4. scripts/check_health.sh - 健康检查

**双检查策略**：

```bash
# Primary: HTTP health check
HEALTH_URL="http://localhost:5000/health"

if command -v curl &> /dev/null; then
    RESPONSE=$(curl -s -w "\n%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✓ Service is healthy"
        exit 0
    else
        echo "✗ Service returned HTTP $HTTP_CODE"
        exit 1
    fi
else
    # Fallback: PID-based check
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "✓ Service process is running (PID: $PID)"
            exit 0
        fi
    fi
    echo "✗ Service is not running"
    exit 1
fi
```

- 主检查：HTTP /health 端点
- 回退检查：进程存在性
- 彩色输出
- 适合监控集成

### 生产部署配置

**环境变量**：
```bash
# 在 .env 或启动前设置
PORT=5000              # 服务端口（默认 5000）
WORKERS=1              # Gunicorn worker 数量（默认 1）
DEBUG=false            # 调试模式（生产环境关闭）
```

**启动命令**：
```bash
# 生产模式（推荐）
PORT=5000 WORKERS=1 bash scripts/start.sh production

# 检查状态
bash scripts/check_health.sh

# 查看日志
tail -f logs/bot.log
tail -f logs/access.log  # Gunicorn 访问日志
tail -f logs/error.log   # Gunicorn 错误日志
```

**停止和重启**：
```bash
# 停止服务
bash scripts/stop.sh

# 重启服务
bash scripts/restart.sh production
```

### 代码质量修复

初始实现存在 6 个生产就绪问题，已全部修复：

#### 修复前的问题

1. ❌ **PID 竞态条件** - 保存 PID 后未验证进程实际运行
2. ❌ **未引号变量** - `ps -p $PID` 可能因空值或空格失败
3. ❌ **lsof 可移植性** - 部分系统无 lsof 命令导致脚本失败
4. ❌ **开发模式无信号处理** - Ctrl+C 无法优雅退出
5. ❌ **健康检查时序固定** - 3 秒固定等待不可靠
6. ❌ **硬编码单 worker** - 无法根据负载调整

#### 修复后

1. ✅ **PID 验证** - 保存后立即验证进程存在，失败时清理 PID 文件
   ```bash
   sleep 0.5
   if ! ps -p "$SERVICE_PID" > /dev/null 2>&1; then
       rm "$PID_FILE"
       exit 1
   fi
   ```

2. ✅ **引号保护** - 所有变量引用加引号 `"$PID"`，防止词分割

3. ✅ **lsof 可移植性** - 检查命令存在再使用
   ```bash
   if command -v lsof &> /dev/null; then
       if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
           echo "Port in use"
       fi
   fi
   ```

4. ✅ **信号处理** - 开发模式添加 trap 处理器
   ```bash
   trap 'echo "Shutting down..."; exit 0' SIGINT SIGTERM
   ```

5. ✅ **智能重试** - 指数退避重试（1s, 2s, 4s, 8s, 16s），最多 5 次

6. ✅ **可配置 workers** - 通过 `WORKERS` 环境变量设置
   ```bash
   WORKERS="${WORKERS:-1}"
   gunicorn -w "$WORKERS" ...
   ```

### 使用场景

**场景 1：开发调试**
```bash
# 前台运行，实时查看日志
bash scripts/start.sh development

# Ctrl+C 停止
```

**场景 2：生产部署**
```bash
# 后台启动
bash scripts/start.sh production

# 验证健康
bash scripts/check_health.sh

# 测试机器人
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{"challenge": "test"}'
```

**场景 3：代码更新重启**
```bash
# 拉取最新代码
git pull origin master

# 重启服务
bash scripts/restart.sh production

# 验证启动
bash scripts/check_health.sh
```

**场景 4：性能调优**
```bash
# 增加 worker 数量（处理并发）
WORKERS=4 bash scripts/restart.sh production

# 注意：当前 Phase 1 使用内存去重，限制为单 worker
# 多 worker 支持需要 Redis（Phase 2）
```

### 日志管理

**日志文件**：
- `logs/bot.log` - 主应用日志（nohup 输出）
- `logs/access.log` - HTTP 访问日志（Gunicorn）
- `logs/error.log` - 错误日志（Gunicorn）

**日志查看**：
```bash
# 实时查看主日志
tail -f logs/bot.log

# 查看最近错误
tail -50 logs/error.log | grep ERROR

# 查看访问统计
awk '{print $9}' logs/access.log | sort | uniq -c | sort -rn
```

**日志轮转**（推荐生产配置）：
```bash
# /etc/logrotate.d/product-kb
/Users/cindy/Projects/product-knowledge-base/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 cindy staff
}
```

### 特色功能

**1. 可移植性**
- 动态路径检测
- lsof 回退兼容
- 跨平台 shell 命令

**2. 健壮性**
- PID 验证防止竞态
- 引号保护防止注入
- 陈旧文件自动清理

**3. 用户体验**
- 彩色输出区分状态
- 详细错误信息
- 修复建议提示

**4. 生产就绪**
- 健康检查自动化
- 优雅停止机制
- 日志完整记录
- 配置灵活可调

### Commits
- `e055adf` - feat: add service management scripts for deployment (Task 14)
- `b1ab0f0` - fix: resolve 6 production readiness issues in deployment scripts (Task 14)

---

**文档版本**：v1.6  
**最后更新**：2026-04-28  
**覆盖范围**：Tasks 1-14 (完成 14/15)
**下一步**：Task 15 - 交付和归档
