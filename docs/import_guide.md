# 历史数据导入指南

## 概述

本指南介绍如何使用 `import_historical_data.py` 脚本将历史知识库数据导入到 Supabase 数据库。

## 前置要求

### 1. 环境配置

确保 `.env` 文件已配置：

```bash
# 检查 .env 文件
cat .env

# 应包含以下配置
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here
```

如果没有 `.env` 文件：

```bash
# 复制示例文件
cp .env.example .env

# 编辑并填入实际凭证
vim .env
```

### 2. 测试数据库连接

```bash
python3 database/test_connection.py
```

预期输出：
```
✓ Supabase credentials found
✓ Successfully connected to Supabase
✓ Database connection test passed
```

### 3. 检查历史数据文件

```bash
ls -lh ~/客服知识库/*.json
```

确认以下文件存在：
- `tech_issues_filtered_final.json`
- `技术支持问答知识库_*.json`
- `技术问题汇总_完整版.json`

## 使用步骤

### Step 1: 预览导入（强烈推荐）

首次导入前，使用 `--dry-run` 模式预览：

```bash
python3 scripts/import_historical_data.py --dry-run
```

这将：
- 扫描所有支持的文件
- 解析并验证数据
- 显示将要导入的条目数
- **不会**实际写入数据库

输出示例：
```
Found 4 file(s) to process:
  - tech_issues_filtered_final.json [tech_issues]
  - 技术支持问答知识库_20260420_1022.json [tech_qa]
  ...

======================================================================
FINAL SUMMARY
======================================================================
Files processed: 4
Entries inserted: 147
Entries skipped (duplicates): 0
Errors: 0
======================================================================

NOTE: This was a dry run. No data was actually imported.
```

### Step 2: 详细检查（可选）

如果需要查看具体每条数据：

```bash
python3 scripts/import_historical_data.py --dry-run --verbose
```

这将打印每条验证通过的条目标题。

### Step 3: 单文件测试（可选）

先测试一个小文件：

```bash
python3 scripts/import_historical_data.py \
  --file ~/客服知识库/tech_issues_filtered_final.json \
  --verbose
```

检查导入结果：
1. 登录 Supabase Dashboard
2. 打开 `knowledge_entries` 表
3. 筛选 `source_group LIKE '历史数据导入%'`
4. 确认数据正确

### Step 4: 批量导入

确认无误后，执行完整导入：

```bash
python3 scripts/import_historical_data.py
```

导入过程中会显示：
- 每 10 条的进度提示
- 每个文件的统计（inserted/skipped/errors）
- 最终汇总报告

### Step 5: 验证导入结果

**方法 1：通过 Supabase Dashboard**

1. 登录 https://app.supabase.com
2. 选择项目 → Table Editor → `knowledge_entries`
3. 运行查询：
   ```sql
   SELECT source_group, status, COUNT(*) 
   FROM knowledge_entries 
   WHERE source_type = 'manual'
   GROUP BY source_group, status;
   ```

**方法 2：通过飞书管理表**

1. 打开飞书多维表格（知识库管理表）
2. 筛选 `来源类型 = manual`
3. 查看 `来源分组` 列确认导入的文件
4. 所有条目应为 `待审核` 状态

## 常见场景

### 场景 1：重新导入（去重）

如果需要重新运行脚本，重复数据会自动跳过：

```bash
python3 scripts/import_historical_data.py
```

输出将显示：
```
✓ Inserted: 0, Skipped (duplicates): 147, Errors: 0
```

### 场景 2：增量导入新文件

将新的历史数据文件放入 `~/客服知识库/` 目录：

```bash
# 预览新文件
python3 scripts/import_historical_data.py --dry-run

# 导入
python3 scripts/import_historical_data.py
```

只有新文件会被导入，已存在的条目会被跳过。

### 场景 3：单独导入特定文件

```bash
python3 scripts/import_historical_data.py \
  --file ~/客服知识库/新增问题汇总.json
```

### 场景 4：修正数据后重新导入

如果修改了源 JSON 文件内容：

1. **删除旧数据**（通过 Supabase Dashboard）：
   ```sql
   DELETE FROM knowledge_entries 
   WHERE source_group = '历史数据导入 - tech_issues_filtered_final.json';
   ```

2. **重新导入**：
   ```bash
   python3 scripts/import_historical_data.py \
     --file ~/客服知识库/tech_issues_filtered_final.json
   ```

## 故障排查

### 问题 1：找不到数据文件

**错误信息**：
```
ERROR: Knowledge base directory not found: /Users/cindy/客服知识库
```

**解决方法**：
- 检查目录是否存在：`ls -la ~/客服知识库/`
- 确认路径拼写正确（注意中文字符）

### 问题 2：数据库连接失败

**错误信息**：
```
ERROR: Failed to connect to Supabase: Missing required environment variables
```

**解决方法**：
1. 检查 `.env` 文件：`cat .env`
2. 确认 `SUPABASE_URL` 和 `SUPABASE_KEY` 已设置
3. 测试连接：`python3 database/test_connection.py`

### 问题 3：JSON 解析失败

**错误信息**：
```
ERROR: Failed to load /path/to/file.json: Expecting value: line 1 column 1
```

**解决方法**：
- 检查 JSON 文件格式：`python3 -m json.tool < file.json`
- 确认文件编码为 UTF-8
- 查看文件前几行：`head -20 file.json`

### 问题 4：部分条目导入失败

**错误信息**：
```
ERROR: Failed to insert entry: ...
```

**解决方法**：
- 使用 `--verbose` 查看详细错误
- 检查失败条目的 title 和 content
- 确认数据符合验证规则（必填字段、长度限制）

### 问题 5：没有找到适合的文件

**输出信息**：
```
WARNING: No suitable files found for import.
```

**解决方法**：
- 检查文件名是否匹配支持的格式：
  - `tech_issues_filtered_final.json`
  - `技术支持问答知识库_*.json`
  - `技术问题汇总_完整版.json`
- 使用 `--file` 参数手动指定文件

## 支持的数据格式

脚本自动识别以下三种格式：

### 格式 1：技术问题列表

文件名模式：`tech_issues_filtered_final.json`

```json
{
  "tech_issues": [
    {
      "sku": "CBC004-1177",
      "question": "客户说每个档位的阻力都是一样的",
      "group": "CBC004"
    }
  ]
}
```

### 格式 2：技术支持问答

文件名模式：`技术支持问答知识库_*.json`

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

### 格式 3：完整问题汇总

文件名模式：`技术问题汇总_完整版.json`

```json
{
  "技术问题列表": [
    {
      "SKU": "S004-1191",
      "产品名": "紫色带跪垫多功能健腹板",
      "问题描述": "客户投诉收到产品时包装完好但内部断裂",
      "问题类型": "运输损坏/产品质量",
      "群组": "CBC004"
    }
  ]
}
```

## 导入后操作

### 1. 审核知识条目

所有导入的条目状态为 `pending`，需要审核：

1. 打开飞书多维表格（知识库管理表）
2. 筛选 `审核状态 = 待审核`
3. 逐条审核：
   - 检查内容准确性
   - 补充关键词（Phase 1 手动，Phase 2 AI 自动）
   - 选择分类标签
   - 批准或拒绝

### 2. 发布知识

审核通过后，条目状态变为 `approved`，即可被搜索。

### 3. 测试搜索

通过飞书机器人测试：

```
/search CBC004-1177
/search 逆变器警报
```

确认历史数据可以被正常搜索到。

## 最佳实践

1. **首次导入前备份数据库**
   - 使用 Supabase Dashboard 导出表数据

2. **分批导入**
   - 先导入小文件测试
   - 确认无误后批量导入

3. **保留源文件**
   - 不要删除 `~/客服知识库/` 中的原始 JSON
   - 便于后续核对和重新导入

4. **定期审核**
   - 导入后尽快审核，避免积压
   - 优先审核高频 SKU 的问题

5. **监控导入质量**
   - 检查 errors 统计
   - 使用 `--verbose` 排查问题数据

## 自动化建议

如果需要定期导入新的历史数据，可以创建 launchd 任务：

```bash
# 创建 plist 文件
cat > ~/Library/LaunchAgents/com.company.knowledge-import.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.company.knowledge-import</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/cindy/Projects/product-knowledge-base/scripts/import_historical_data.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/cindy/Projects/product-knowledge-base/logs/import.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/cindy/Projects/product-knowledge-base/logs/import.error.log</string>
</dict>
</plist>
EOF

# 加载任务
launchctl load ~/Library/LaunchAgents/com.company.knowledge-import.plist
```

这将在每天凌晨 2 点自动检查并导入新文件。

## 相关文档

- [数据库 Schema 说明](../database/schema.sql)
- [知识库管理指南](management_guide.md)
- [飞书机器人使用](bot_usage.md)

## 技术支持

如遇问题，请检查：
1. 日志文件：`logs/app.log`
2. 测试连接：`python3 database/test_connection.py`
3. 运行测试：`python3 -m pytest tests/test_import_historical_data.py -v`
