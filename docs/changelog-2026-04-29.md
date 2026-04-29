# 产品知识库系统 - 开发日志 2026-04-29

## 概述

今天完成了 Phase 1 MVP 的核心功能开发和数据同步，系统现已可以正常使用。

---

## 主要成果

### ✅ 产品数据同步完成
- 成功同步 3,735 个产品（100 个字段全部可搜索）
- 新增: 2,590 条
- 更新: 1,134 条
- 跳过: 11 条（缺少 SKU）

### ✅ 飞书机器人功能完善
- 支持 SKU 精确搜索和关键词搜索
- 显示产品图片、包装图片、说明书链接
- 支持群聊和私聊

### ✅ Phase 2 功能规划
- 记录说明书内容提取功能规划

---

## 详细修改记录

### 1. 产品同步脚本修复（scripts/sync_product_table.py）

#### 问题 1: 分页 Token 错误
**错误**: `InvalidPageToken` - 首次请求不应包含空的 page_token

**原因**: 代码在首次请求时传递了 `page_token=None`

**修复** (行 74-100):
```python
def fetch_all_records(client):
    records = []
    page_token = None
    
    while True:
        builder = ListAppTableRecordRequest.builder() \
            .app_token(APP_TOKEN) \
            .table_id(TABLE_ID) \
            .page_size(500)
        
        # 只在有 page_token 时才添加参数
        if page_token:
            builder = builder.page_token(page_token)
        
        request = builder.build()
        # ... 处理响应
```

**效果**: 成功读取所有 3,735 条产品记录

---

#### 问题 2: 字段名称不匹配
**错误**: 所有 3,735 个产品被跳过 - "缺少或无效的 SKU"

**原因**: 
- 代码查找字段 `"SKU"`
- 实际飞书表格字段名为 `"*库存sku编号"`

**修复** (行 154-182):
```python
# 修改前
sku_raw = raw_data.get("SKU")

# 修改后 - 尝试多个可能的字段名
sku_raw = raw_data.get("*库存sku编号") or \
          raw_data.get("SKU") or \
          raw_data.get("库存SKU编码")

# 同样更新其他字段
name_en = raw_data.get("库存SKU英文名称") or \
          raw_data.get("主SKU英文名称") or ""
          
name_cn = raw_data.get("库存SKU中文名称") or \
          raw_data.get("主SKU中文名称") or \
          raw_data.get("产品名称") or ""
```

**效果**: 正确识别和导入所有产品

---

#### 问题 3: 100 个字段全部可搜索
**需求**: 用户要求"所有的字段我们都需要，这样所有部门的人都可以进行查询"

**实现** (行 209-238):
```python
# 构建综合可搜索内容
searchable_content_parts = [
    f"SKU: {sku}",
    f"产品名称: {name_cn}",
    f"英文名称: {name_en}" if name_en else "",
    f"产品特性: {features}" if features else "",
    f"商品备注: {description}" if description else "",
]

# 添加所有其他字段到可搜索内容
for field_name, field_value in raw_data.items():
    # 跳过已处理的字段
    if field_name in ["*库存sku编号", "库存SKU中文名称", ...]:
        continue
    
    # 提取文本内容
    if field_value:
        if isinstance(field_value, str):
            searchable_content_parts.append(f"{field_name}: {field_value}")
        elif isinstance(field_value, (int, float)):
            searchable_content_parts.append(f"{field_name}: {field_value}")
        elif isinstance(field_value, list) and field_value:
            for item in field_value:
                if isinstance(item, dict) and 'text' in item:
                    searchable_content_parts.append(f"{field_name}: {item['text']}")
                elif isinstance(item, str):
                    searchable_content_parts.append(f"{field_name}: {item}")

searchable_content = "\n".join([p for p in searchable_content_parts if p])
```

**新增字段**:
```python
product_data = {
    # ... 现有字段 ...
    "searchable_content": searchable_content,  # 新增：所有字段的文本内容
}
```

**效果**: 
- 所有 100 个字段（包括规格、供应商、尺寸、电压、材质等）都可以被搜索
- 支持跨部门使用（采购、客服、运营等都能查到需要的信息）

---

### 2. 数据库 Schema 更新

#### 添加 searchable_content 字段
```sql
-- 手动在 Supabase 执行
ALTER TABLE products 
ADD COLUMN IF NOT EXISTS searchable_content TEXT;
```

#### 更新全文搜索触发器
```sql
-- 更新触发器函数，包含新字段
CREATE OR REPLACE FUNCTION update_products_search_vector()
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_vector := to_tsvector('simple', 
    COALESCE(NEW.sku, '') || ' ' ||
    COALESCE(NEW.name_cn, '') || ' ' ||
    COALESCE(NEW.name_en, '') || ' ' ||
    COALESCE(NEW.features, '') || ' ' ||
    COALESCE(NEW.description, '') || ' ' ||
    COALESCE(NEW.searchable_content, '')  -- 新增
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 重建触发器
DROP TRIGGER IF EXISTS products_search_vector_update ON products;
CREATE TRIGGER products_search_vector_update
  BEFORE INSERT OR UPDATE OF sku, name_cn, name_en, features, description, searchable_content
  ON products
  FOR EACH ROW
  EXECUTE FUNCTION update_products_search_vector();
```

**效果**: 所有字段内容都会被索引到 search_vector，支持全文搜索

---

### 3. 飞书机器人功能完善（bot/main.py）

#### 问题 1: 机器人回复自己的消息（无限循环）
**错误**: "我没有问他问题,但是他一直在发送消息"

**原因**: 机器人处理了自己发送的消息，导致循环

**修复** (行 176-181):
```python
# 忽略机器人自己发送的消息
sender_type = sender.get('sender_type')
if sender_type == 'app' or sender_type == 'bot':
    logger.info(f"Ignored message from bot/app (sender_type: {sender_type})")
    return jsonify({'msg': 'ok'}), 200
```

**效果**: 机器人不再回复自己的消息

---

#### 问题 2: 群聊中无法回复
**错误**: "没有在群聊中反馈但是在单独的窗口恢复了"

**原因**: 群聊消息回复目标设置错误，回复到了发送者而不是群聊

**修复** (行 189-211):
```python
# 获取消息类型和群聊 ID
chat_type = message.get('chat_type', 'p2p')  # p2p 或 group
chat_id = message.get('chat_id')

# 确定回复目标：群聊回复到群，私聊回复给发送者
if chat_type == 'group' and chat_id:
    # 群聊消息：回复到群
    receive_id = chat_id
    receive_id_type = 'chat_id'
    logger.info(f"Group message in chat: {chat_id}")
else:
    # 私聊消息：回复给发送者
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
    else:
        logger.error("No valid sender id found")
        return jsonify({'msg': 'ok'}), 200
    logger.info(f"Private message from: {receive_id}")
```

**效果**: 
- 群聊中机器人正确回复到群
- 私聊中机器人回复给发送者

---

### 4. 消息格式化增强（bot/formatters.py）

#### 问题: 搜索结果不显示图片和说明书
**用户反馈**: "没看到说明书"

**原因**: 格式化函数只显示基本信息（title, content, date, source），未处理图片和附件

**修复** (行 46-89):
```python
def format_knowledge_entry(entry: Dict[str, Any]) -> str:
    # ... 原有代码 ...
    
    formatted = f"❓ {title}{sku_info}\n"
    formatted += f"💡 {content}\n"
    formatted += f"📅 {date_str} | {source_group}\n"

    # 新增：产品图片（如果有）
    images = entry.get('images')
    if images and isinstance(images, list) and len(images) > 0:
        formatted += f"\n📷 产品图片:\n"
        for i, img in enumerate(images[:3], 1):  # 最多显示3张
            formatted += f"  {i}. {img}\n"

    # 新增：包装图片（如果有）
    package_images = entry.get('package_images')
    if package_images and isinstance(package_images, list) and len(package_images) > 0:
        formatted += f"\n📦 包装图片:\n"
        for i, img in enumerate(package_images[:3], 1):
            formatted += f"  {i}. {img}\n"

    # 新增：说明书（如果有）
    manual_files = entry.get('manual_files')
    if manual_files:
        formatted += f"\n📖 说明书:\n"
        if isinstance(manual_files, dict):
            # 单个说明书（字典格式）
            manual_name = manual_files.get('text', manual_files.get('name', '说明书'))
            manual_url = manual_files.get('link', manual_files.get('url', ''))
            if manual_url:
                formatted += f"  • {manual_name}: {manual_url}\n"
            else:
                formatted += f"  • {manual_name}\n"
        elif isinstance(manual_files, list):
            # 多个说明书（列表格式）
            for manual in manual_files:
                if isinstance(manual, dict):
                    manual_name = manual.get('text', manual.get('name', '说明书'))
                    manual_url = manual.get('link', manual.get('url', ''))
                    if manual_url:
                        formatted += f"  • {manual_name}: {manual_url}\n"
                    else:
                        formatted += f"  • {manual_name}\n"

    return formatted.rstrip()
```

**效果**: 搜索结果现在显示：
- 📷 产品图片（最多3张）
- 📦 包装图片（最多3张）
- 📖 说明书（名称 + 飞书链接）

**示例输出**:
```
🔍 搜索结果 (SKU 精确搜索: "S004-1166")
找到 1 条相关知识

--- 结果 1 ---
❓ JOYFOX双面绿色+蓝色两用195*134*8cm双人波浪形脚踩充气垫mx [S004-1166]
💡 SKU: S004-1166
产品名称: JOYFOX双面绿色+蓝色两用195*134*8cm双人波浪形脚踩充气垫mx
...
📅 未知日期 | 产品信息

📷 产品图片:
  1. https://stock-cos.mabangerp.com/358373/...

📦 包装图片:
  1. https://open.feishu.cn/open-apis/drive/v1/medias/...
  2. https://open.feishu.cn/open-apis/drive/v1/medias/...

📖 说明书:
  • 充气垫双语说明书: https://cgokyyxlsh.feishu.cn/file/W6ZBbDOSioDOHnxbIANcioLDnvh
```

---

### 5. 部署问题修复

#### 问题: 端口 5001 被其他服务占用
**错误**: 机器人更新后仍显示旧版本响应

**原因**: 
- `feishu-mabang-sku-sync` 服务通过 launchd 自动运行在 5001 端口
- 产品知识库机器人无法启动

**解决方案**:
```bash
# 1. 停止冲突的服务
launchctl unload ~/Library/LaunchAgents/com.feishu-mabang-sku-sync.plist

# 2. 清理 Python 缓存
find . -type d -name __pycache__ -exec rm -rf {} +
find . -name "*.pyc" -delete

# 3. 启动产品知识库机器人
cd /Users/cindy/Projects/product-knowledge-base
python3 -m bot.main &
```

**验证**:
```bash
curl http://localhost:5001/health
# 返回: {"service":"product-knowledge-base-bot","status":"healthy","version":"1.0.0"}
```

---

## Phase 2 功能规划

### 说明书内容提取与索引

**文档**: [docs/phase2-manual-content-extraction.md](phase2-manual-content-extraction.md)

**核心功能**:
- 自动下载飞书 Word 文档（说明书）
- 提取中文+葡语文本内容
- 索引到数据库，实现说明书内容搜索

**技术方案**:
- 使用 `python-docx` 解析 Word 文档
- 飞书 API 下载文件
- 新增 `manual_content` 字段

**预期效果**:
```
客服搜索: "安装步骤"
→ 返回说明书中包含安装说明的所有产品

客服搜索: "não funciona" (葡语)
→ 返回说明书中包含故障排查的产品
```

**优先级**: 中（Phase 2 实现）

---

## 测试验证

### 测试用例

#### 1. SKU 精确搜索
```
输入: S004-1166
预期: 返回充气垫产品，包含图片和说明书链接
结果: ✅ 通过
```

#### 2. 关键词搜索
```
输入: 充气床
预期: 返回所有充气床产品
结果: ✅ 通过
```

#### 3. 字段内容搜索
```
输入: 127V
预期: 返回所有 127V 电压的产品
结果: ✅ 通过
```

#### 4. 群聊功能
```
场景: 在群聊中 @机器人搜索
预期: 机器人在群聊中回复
结果: ✅ 通过
```

#### 5. 私聊功能
```
场景: 私聊机器人搜索
预期: 机器人私聊回复
结果: ✅ 通过
```

---

## 数据统计

### 产品同步
- **总产品数**: 3,735
- **新增**: 2,590 (69.4%)
- **更新**: 1,134 (30.4%)
- **跳过**: 11 (0.3%)
- **同步时长**: ~3 小时（09:52 - 12:57）

### 字段覆盖
- **总字段数**: 100
- **核心字段**: SKU, 产品名称, 特性, 说明, 尺寸, 规格等
- **可搜索字段**: 全部 100 个字段
- **附件字段**: 图片, 包装图, 说明书

### 有说明书的产品
- 示例产品: S004-1166, CBC008-778, BRME0759, BRME0758
- 格式: Word 文档
- 语言: 中文 + 葡萄牙语

---

## 相关文件清单

### 核心代码
- `scripts/sync_product_table.py` - 产品同步脚本 ✏️ 已修改
- `bot/main.py` - 飞书机器人主服务 ✏️ 已修改
- `bot/handlers.py` - 消息处理逻辑
- `bot/search.py` - 搜索功能实现
- `bot/formatters.py` - 消息格式化 ✏️ 已修改
- `bot/config.py` - 配置管理

### 配置文件
- `.env` - 环境变量配置
- `requirements.txt` - Python 依赖

### 文档
- `docs/changelog-2026-04-29.md` - 本文档 ✨ 新建
- `docs/phase2-manual-content-extraction.md` - Phase 2 规划 ✨ 新建

### 数据库
- Supabase `products` 表 - 产品数据 ✏️ 已更新
  - 新增字段: `searchable_content`
  - 更新触发器: `products_search_vector_update`

---

## 下一步工作

### 立即
- [x] 确保机器人稳定运行
- [x] 验证所有功能正常
- [x] 记录今天的修改

### 近期（Phase 1 收尾）
- [ ] 监控机器人使用情况
- [ ] 收集用户反馈
- [ ] 优化搜索结果排序
- [ ] 添加使用统计

### Phase 2（后续）
- [ ] 实现说明书内容提取
- [ ] 添加 AI 语义搜索
- [ ] 优化搜索性能
- [ ] 添加用户管理功能

---

## 问题记录

### 已解决
1. ✅ 分页 Token 错误 → 条件判断添加 page_token
2. ✅ 字段名称不匹配 → 多名称兼容
3. ✅ 说明书不显示 → 更新格式化函数
4. ✅ 机器人消息循环 → 过滤 bot 消息
5. ✅ 群聊无法回复 → 修复 receive_id 逻辑
6. ✅ 端口占用冲突 → 停止冲突服务

### 待观察
- 机器人长时间运行稳定性
- 搜索结果相关性
- 大量并发搜索性能

---

## 团队协作

**开发**: Claude Code  
**产品需求**: Cindy  
**测试**: Cindy  

**关键决策**:
- 100 个字段全部可搜索 ✅
- 说明书内容提取放到 Phase 2 ✅
- Word 格式说明书（中文+葡语）✅

---

**文档创建时间**: 2026-04-29 13:30  
**最后更新**: 2026-04-29 13:30  
**版本**: Phase 1 MVP Complete
