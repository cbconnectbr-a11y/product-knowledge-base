# Phase 2: 说明书内容提取与索引

## 需求背景

**当前状态（Phase 1）**:
- ✅ 存储说明书文件链接（飞书 URL）
- ✅ 在搜索结果中显示链接
- ❌ 说明书内容未被提取，无法通过内容搜索

**目标（Phase 2）**:
- 自动下载并提取说明书文档内容
- 将说明书文本内容索引到数据库
- 使客服可以通过说明书内容关键词搜索产品

## 技术信息

### 文件格式
- **格式**: Word 文档（.docx）
- **语言**: 中文 + 葡萄牙语
- **存储**: 飞书文件系统

### 技术选型
```python
# 主要依赖
python-docx      # Word 文档解析
requests         # 下载飞书文件
```

## 实现方案

### 1. 数据库变更

```sql
-- 在 products 表添加字段
ALTER TABLE products 
ADD COLUMN manual_content TEXT;  -- 存储提取的说明书文本内容

-- 更新 search_vector 触发器，包含 manual_content
CREATE OR REPLACE FUNCTION update_products_search_vector()
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_vector := to_tsvector('simple', 
    COALESCE(NEW.sku, '') || ' ' ||
    COALESCE(NEW.name_cn, '') || ' ' ||
    COALESCE(NEW.name_en, '') || ' ' ||
    COALESCE(NEW.features, '') || ' ' ||
    COALESCE(NEW.description, '') || ' ' ||
    COALESCE(NEW.searchable_content, '') || ' ' ||
    COALESCE(NEW.manual_content, '')  -- 新增
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### 2. 飞书文件下载

```python
def download_feishu_file(file_url: str, app_token: str) -> bytes:
    """
    从飞书下载文件
    
    Args:
        file_url: 飞书文件链接（从 manual_files.link 获取）
        app_token: 飞书应用 token
    
    Returns:
        文件二进制内容
    
    Note:
        需要验证飞书 API 权限：
        - 需要 drive:drive:readonly 权限
        - 或 bitable:app:readonly 权限（如果文件在多维表格中）
    """
    # 解析文件 URL，提取 file_token
    # 调用飞书 API: /open-apis/drive/v1/medias/{file_token}/download
    # 需要 tenant_access_token 认证
    pass
```

### 3. Word 内容提取

```python
from docx import Document
from io import BytesIO

def extract_word_content(docx_bytes: bytes) -> str:
    """
    从 Word 文档提取文本内容
    
    Args:
        docx_bytes: Word 文档二进制内容
    
    Returns:
        提取的文本内容（保留段落结构）
    
    Example:
        >>> content = extract_word_content(file_bytes)
        >>> print(content[:100])
        产品安装说明
        
        1. 准备工具
        - 螺丝刀
        - 扳手
        ...
    """
    doc = Document(BytesIO(docx_bytes))
    
    # 提取所有段落
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)
    
    # 提取表格内容（如果需要）
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    paragraphs.append(text)
    
    return '\n'.join(paragraphs)
```

### 4. 同步脚本更新

在 `scripts/sync_product_table.py` 中添加：

```python
def process_manual_files(manual_files: dict, lark_client) -> str:
    """
    处理说明书文件，提取内容
    
    Args:
        manual_files: 说明书字段（包含 link 和 text）
        lark_client: 飞书客户端
    
    Returns:
        提取的文本内容
    """
    if not manual_files or not isinstance(manual_files, dict):
        return ''
    
    file_url = manual_files.get('link', manual_files.get('url'))
    if not file_url:
        return ''
    
    try:
        # 下载文件
        file_bytes = download_feishu_file(file_url, lark_client)
        
        # 提取内容
        content = extract_word_content(file_bytes)
        
        logger.info(f"Extracted {len(content)} chars from manual")
        return content
        
    except Exception as e:
        logger.error(f"Failed to extract manual content: {e}")
        return ''

def process_record(record, fields_info, lark_client):
    # ... 现有代码 ...
    
    # 新增：提取说明书内容
    manual_content = ''
    manual_files = raw_data.get("说明书")
    if manual_files:
        manual_content = process_manual_files(manual_files, lark_client)
    
    # 更新 searchable_content，包含说明书内容
    searchable_content_parts.append(f"说明书内容: {manual_content}")
    
    product_data = {
        # ... 现有字段 ...
        'manual_content': manual_content,  # 新增
        'searchable_content': searchable_content,
    }
```

### 5. 机器人响应格式更新

在 `bot/formatters.py` 中，可选择是否显示说明书摘要：

```python
# 说明书内容摘要（如果有）
manual_content = entry.get('manual_content')
if manual_content and len(manual_content) > 100:
    formatted += f"\n📄 说明书摘要:\n"
    formatted += f"  {manual_content[:200]}...\n"
```

## 实现步骤

### 阶段 1：准备工作
- [ ] 安装依赖：`pip install python-docx`
- [ ] 测试飞书文件下载权限
  - 验证应用是否有 `drive:drive:readonly` 权限
  - 测试下载单个说明书文件
- [ ] 验证 Word 内容提取
  - 测试中文内容提取
  - 测试葡萄牙语内容提取

### 阶段 2：数据库变更
- [ ] 执行 SQL 添加 `manual_content` 字段
- [ ] 更新 `search_vector` 触发器

### 阶段 3：同步脚本开发
- [ ] 实现 `download_feishu_file()` 函数
- [ ] 实现 `extract_word_content()` 函数
- [ ] 更新 `process_record()` 逻辑
- [ ] 测试单个产品同步

### 阶段 4：批量同步
- [ ] 统计有说明书的产品数量
- [ ] 执行批量提取（预计耗时：根据文件数量）
- [ ] 验证提取结果质量

### 阶段 5：搜索验证
- [ ] 测试说明书内容关键词搜索
- [ ] 验证中文搜索
- [ ] 验证葡语搜索

## 注意事项

### 权限问题
- 确认飞书应用有文件下载权限
- 说明书文件可能需要特定的访问权限

### 性能考虑
- 3,735 个产品中，有说明书的产品数量未知
- 首次同步需要下载和处理所有说明书
- 建议：增量处理，只处理新增/更新的说明书
- 可以添加 `manual_extracted_at` 字段记录提取时间

### 错误处理
- 文件下载失败：重试机制
- Word 解析失败：记录错误，继续处理其他产品
- 权限不足：提示管理员授权

### 存储优化
- 说明书内容可能很长（几千到几万字）
- 考虑是否需要压缩存储
- 考虑是否需要限制最大长度

## 预期效果

### 搜索增强示例

**场景 1：安装步骤搜索**
```
客服搜索："如何安装"
返回：所有说明书中包含"安装"、"安装步骤"的产品
```

**场景 2：故障排查**
```
客服搜索："não funciona"（葡语：不工作）
返回：说明书中包含故障排查内容的产品
```

**场景 3：规格参数**
```
客服搜索："220V"
返回：产品信息或说明书中提到 220V 的产品
```

## 估算工作量

- **开发时间**: 2-3 天
  - 飞书 API 集成: 0.5 天
  - Word 提取实现: 0.5 天
  - 同步脚本更新: 1 天
  - 测试和调优: 0.5-1 天

- **首次数据处理**: 根据文件数量，预计 1-4 小时

- **后续维护**: 定期同步（每周/每月）

## 相关文件

- 同步脚本: `scripts/sync_product_table.py`
- 搜索模块: `bot/search.py`
- 格式化模块: `bot/formatters.py`
- 数据库 schema: Supabase `products` 表

## 参考资料

- [python-docx 文档](https://python-docx.readthedocs.io/)
- [飞书开放平台 - 文件下载 API](https://open.feishu.cn/document/server-docs/docs/drive-v1/media/download)
- PostgreSQL 全文搜索: 已配置 `simple` config（支持中文）

---

**创建时间**: 2026-04-29  
**状态**: 待实现（Phase 2）  
**优先级**: 中  
**依赖**: Phase 1 基础功能完成
