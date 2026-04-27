# 知识库管理指南

## 目录

1. [概述](#概述)
2. [设置步骤](#设置步骤)
3. [审核工作流](#审核工作流)
4. [字段映射](#字段映射)
5. [运行同步脚本](#运行同步脚本)
6. [常见问题](#常见问题)
7. [Phase 2 计划](#phase-2-计划)

---

## 概述

知识库管理界面通过飞书多维表格（Bitable）提供一个用户友好的审核平台。系统的工作流程为：

```
数据库 (Supabase)
    ↓
脚本同步待审核条目
    ↓
飞书多维表格（审核界面）
    ↓
用户手动审核和更新
    ↓
脚本读取审核结果
    ↓
数据库更新状态
```

### 核心特性

- **待审核条目同步** - 自动将数据库中的新条目推送到飞书表格
- **审核流程管理** - 通过表格的 Status 字段管理审核状态
- **双向同步** - 将审核结果（批准/拒绝）回写到数据库
- **易于使用** - 非技术人员可直接在飞书中进行审核

### Phase 1 MVP 范围

- 脚本推送待审核条目到飞书
- 用户在飞书中手动审核
- 脚本读取已审核结果并更新数据库
- **不包含** 实时 webhook、自动化触发等

---

## 设置步骤

### 前置条件

- 有飞书账号和创建多维表格的权限
- 已配置好 Supabase 和飞书 SDK（见 `.env.example`）
- 已运行 `database/schema.sql` 创建数据库表

### 第 1 步：在飞书创建多维表格应用

1. 打开 [飞书应用中心](https://www.feishu.cn/app)，搜索"多维表格"（Bitable）
2. 点击"创建应用"，选择一个工作区或文件夹
3. 给应用命名，例如 "知识库管理"
4. 创建一个新表格，命名为 "待审核条目"

### 第 2 步：创建表格字段

在飞书多维表格中，创建以下字段：

| 字段名 | 字段类型 | 说明 | 必填 |
|--------|--------|------|------|
| DB_ID | 文本 | 数据库条目的唯一 ID，用于后续回写 | 是 |
| SKU | 文本 | 产品 SKU 代码 | 是 |
| 标题 | 文本 | 条目标题 | 是 |
| 内容 | 富文本 | 详细内容（支持格式化） | 是 |
| 来源 | 文本 | 数据来源（如群组名称） | 否 |
| 关键词 | 文本 | 关键词列表（逗号分隔） | 否 |
| 创建时间 | 日期时间 | 条目在数据库中的创建时间 | 否 |
| Status | 单选 | 审核状态 | 是 |
| 审核意见 | 富文本 | 审核人的反馈和备注 | 否 |

#### 创建 Status 单选字段

在"Status"字段中，添加以下选项：

- **pending** (pending) - 等待审核
- **approved** (approved) - 已批准
- **rejected** (rejected) - 已拒绝
- **draft** (draft) - 草稿

### 第 3 步：获取应用和表格 Token

1. 在飞书多维表格中，点击右上角 **"..."** 菜单
2. 选择 **"设置"** → **"开发者"**
3. 复制 **应用 Token** (APP_TOKEN)
4. 找到表格 ID，通常在 URL 中可见，或者在"开发者"菜单中查看

示例 URL：
```
https://bitable.feishu.cn/app/你的APP_TOKEN?table=tbl_你的TABLE_ID
```

### 第 4 步：配置环境变量

在项目根目录的 `.env` 文件中添加：

```env
# 飞书管理表配置
FEISHU_MANAGEMENT_APP_TOKEN=你的_APP_TOKEN
FEISHU_MANAGEMENT_TABLE_ID=你的_TABLE_ID
```

### 第 5 步：验证配置

运行以下命令验证配置是否正确：

```bash
python3 scripts/create_management_table.py sync-all
```

如果出现 "表格包含 9 个字段" 的消息，说明配置成功。

---

## 审核工作流

### 工作流图解

```
Step 1: 新条目生成
    ↓
Supabase 知识库中有状态为 pending 的新条目
    ↓
Step 2: 推送到飞书
    ↓
运行脚本将条目同步到飞书表格
    ↓
Step 3: 审核
    ↓
审核人在飞书中打开表格，查看待审核条目
    ↓
Step 4: 更新状态
    ↓
审核人更改 Status 字段为 approved 或 rejected
    ↓
Step 5: 同步结果
    ↓
运行脚本读取已审核条目，回写到数据库
    ↓
完成
```

### 逐步审核流程

#### 步骤 1：审核人打开飞书表格

1. 打开飞书多维表格应用 "知识库管理"
2. 查看 "待审核条目" 表格

#### 步骤 2：查看条目详情

- **SKU** - 产品代码，用于快速识别
- **标题** - 问题或内容的简短描述
- **内容** - 完整的知识内容
- **来源** - 条目来自哪个群组或途径
- **关键词** - 与条目相关的关键词
- **创建时间** - 何时添加到系统

#### 步骤 3：进行审核

根据以下标准审核：

- **批准（approved）条件：**
  - 内容准确、完整、有帮助
  - 没有拼写或语法错误
  - SKU 和信息匹配正确
  - 格式规范、易于理解

- **拒绝（rejected）条件：**
  - 信息不准确或过时
  - 内容不完整或模糊不清
  - 重复或已存在相似条目
  - SKU 错误或不存在
  - 内容与产品无关

#### 步骤 4：更新 Status 字段

1. 点击条目的 "Status" 字段
2. 从下拉菜单中选择：
   - **approved** - 批准发布
   - **rejected** - 拒绝（需要修改）
   - **draft** - 保存为草稿（留作后用）

#### 步骤 5：添加审核意见（可选）

在 "审核意见" 字段中添加反馈：

- 批准情况下：简短说明为什么批准
- 拒绝情况下：具体指出需要改进的地方

#### 步骤 6：同步结果

管理员运行脚本同步审核结果：

```bash
python3 scripts/create_management_table.py sync-reviews
```

条目的状态将在数据库中更新，可以发布或进行修改。

---

## 字段映射

### Supabase → 飞书字段对应

| Supabase 字段 | 飞书字段 | 类型 | 说明 |
|--------------|---------|------|------|
| id | DB_ID | 文本 | 主键，用于回写 |
| sku | SKU | 文本 | 产品代码 |
| title | 标题 | 文本 | 条目标题 |
| content | 内容 | 富文本 | 详细内容 |
| source_group | 来源 | 文本 | 来源群组名 |
| keywords[] | 关键词 | 文本 | 以逗号分隔 |
| created_at | 创建时间 | 日期时间 | 创建时间戳 |
| status | Status | 单选 | pending/approved/rejected/draft |
| reviewed_by | 审核人 | 文本 | 回写时填充 |
| reviewed_at | 审核时间 | 日期时间 | 回写时填充 |
| reviewer_notes | 审核意见 | 富文本 | 来自飞书 |

### 数据类型转换规则

**文本字段 (Text)**
```
Supabase: VARCHAR, TEXT
飞书: 文本字段的富文本格式 [{"text": "value"}]
处理: 自动转换为列表格式
```

**日期时间 (DateTime)**
```
Supabase: TIMESTAMPTZ
飞书: 日期时间字段
处理: ISO 8601 格式字符串
```

**数组字段 (Array)**
```
Supabase: TEXT[]
飞书: 文本字段
处理: 逗号分隔字符串，在脚本中转换
```

---

## 运行同步脚本

### 脚本位置

```
/Users/cindy/Projects/product-knowledge-base/scripts/create_management_table.py
```

### 可用命令

#### 1. 同步待审核条目

```bash
python3 scripts/create_management_table.py sync-pending
```

功能：
- 从 Supabase 读取所有 status='pending' 的条目
- 推送到飞书表格（最多 100 条）
- 创建新记录，不覆盖现有数据

输出示例：
```
======================================================================
知识库管理脚本 - 2026-04-27 14:30:00
======================================================================
验证飞书表格访问...
表格包含 9 个字段: ['DB_ID', 'SKU', '标题', '内容', '来源', '关键词', '创建时间', 'Status', '审核意见']

--- 同步待审核条目 ---
从 Supabase 读取待审核条目 (limit=100)...
读取到 5 条待审核条目
同步 5 条待审核条目到飞书...
  ✓ 创建: CBC004 - 加热杯不加热怎么办
  ✓ 创建: CBC006 - 电池容量不足
  ...
同步完成: 新增 5, 跳过 0

======================================================================
同步统计
======================================================================
待审核条目: 新增 5, 跳过 0
审核结果: 更新 0, 跳过 0
======================================================================
```

#### 2. 同步审核结果

```bash
python3 scripts/create_management_table.py sync-reviews
```

功能：
- 从飞书表格读取所有已审核条目（status != pending）
- 将审核结果回写到 Supabase
- 更新 status、reviewed_at、reviewer_notes

输出示例：
```
--- 同步审核结果 ---
从飞书表格读取已审核条目...
读取到 3 条已审核条目
将 3 条审核结果回写到 Supabase...
  ✓ 更新: abc-123-def -> approved
  ✓ 更新: abc-124-def -> rejected
  ...
回写完成: 更新 3, 跳过 0
```

#### 3. 完整同步（推荐）

```bash
python3 scripts/create_management_table.py sync-all
```

功能：先同步待审核条目，再同步审核结果（完整工作流）

### 定时运行（可选）

可以通过 launchd 或 cron 定时运行脚本。例如，每小时运行一次：

```bash
# 编辑 launchd 配置
# /Users/cindy/Projects/product-knowledge-base/launchd/com.knowledge-base.management.plist

# 每天 10:00 和 14:00 运行
...
<key>StartCalendarInterval</key>
<array>
    <dict>
        <key>Hour</key>
        <integer>10</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <dict>
        <key>Hour</key>
        <integer>14</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</array>
...
```

### 错误处理

脚本会记录所有错误到 `logs/app.log`。常见错误：

| 错误 | 原因 | 解决方案 |
|------|------|--------|
| 缺少环境变量 | 未配置 FEISHU_APP_ID 等 | 检查 .env 文件 |
| Unauthorized | Feishu 凭证无效 | 验证 APP_ID 和 APP_SECRET |
| Not Found | APP_TOKEN 或 TABLE_ID 错误 | 检查飞书多维表格的实际 ID |
| Connection refused | Supabase 无法连接 | 检查网络和 SUPABASE_URL |

---

## 常见问题

### Q1: 如何知道哪些条目待审核？

A: 在飞书多维表格中筛选 Status = pending 的行。或者在 Supabase SQL 编辑器运行：

```sql
SELECT id, sku, title, status FROM knowledge_entries 
WHERE status = 'pending' 
ORDER BY created_at DESC;
```

### Q2: 批准的条目会自动发布吗？

A: Phase 1 中，需要手动操作。待后续 Phase 2 实现自动发布功能。

### Q3: 拒绝的条目如何修改后重新审核？

A: 
1. 在飞书表格中修改内容
2. 将 Status 改回 pending
3. 发送消息通知原作者修改
4. 原作者修改后，脚本会读取新的更新

### Q4: 如何批量导入大量条目？

A: Phase 1 不支持。可以：
- 直接在 Supabase 中插入 (SQL 编辑器)
- 或者运行脚本 `scripts/sync_feishu_qa.py` 从飞书群组导入

### Q5: 一个条目可以有多个审核人吗？

A: Phase 1 中，reviewed_by 字段只记录最后的审核人。Phase 2 可支持审核历史。

### Q6: 如何导出审核结果？

A: 在飞书中：
1. 打开表格，选择所有已批准的行
2. 点击"导出"按钮
3. 选择 Excel 或 CSV 格式

或者在 Supabase 中：
```sql
SELECT * FROM knowledge_entries 
WHERE status IN ('approved', 'rejected')
ORDER BY reviewed_at DESC;
```

### Q7: 脚本运行多久需要执行一次？

A: 建议：
- **推送待审核条目** - 每小时或每天一次（当有新条目时）
- **同步审核结果** - 每 30 分钟一次
- 或者定时任务 - 使用 launchd/cron 自动执行

### Q8: 如何重置或清空表格？

A: 不建议直接删除。更好的做法：
1. 在飞书中创建新表格（例如"备份"）
2. 将旧记录归档
3. 继续使用新表格

---

## Phase 2 计划

以下功能计划在 Phase 2 中实现：

### 自动审核触发

```python
# 当 Supabase 有新条目时，自动推送到飞书
# 不需要手动运行脚本
```

### 实时 Webhook 同步

```
飞书表格更新 → Webhook → 自动更新 Supabase
```

### 批量操作

- 批量批准/拒绝
- 批量导入
- 批量导出

### 审核历史跟踪

- 记录所有审核人的历史
- 显示修改记录
- 支持审核回溯

### 高级搜索和过滤

- 按 SKU、日期范围、来源筛选
- 搜索关键词
- 审核统计仪表板

### 自动发布

- 批准后自动发布到知识库
- 自动更新发布时间戳
- 生成发布日志

### 权限控制

- 细粒度的用户角色（查看者、审核人、管理员）
- 只能审核分配给自己的条目
- 审计日志

---

## 故障排除

### 脚本无法连接到 Supabase

**错误信息：** `Connection refused` 或 `timeout`

**解决方案：**
1. 检查网络连接
2. 验证 SUPABASE_URL 和 SUPABASE_KEY
3. 确保 Supabase 项目已启动
4. 检查防火墙设置

### 飞书 API 返回 401 Unauthorized

**原因：** APP_ID 或 APP_SECRET 错误

**解决方案：**
1. 登录飞书，打开飞书开放平台
2. 验证应用的 APP_ID 和 APP_SECRET
3. 检查 .env 文件中的值是否正确
4. 重新生成凭证（如需要）

### 找不到表格（Not Found）

**原因：** APP_TOKEN 或 TABLE_ID 错误

**解决方案：**
1. 打开飞书多维表格应用
2. 在设置 → 开发者中复制准确的 APP_TOKEN
3. 在多维表格的 URL 中找到 TABLE_ID
4. 更新 .env 文件
5. 重新运行脚本

### 字段数据显示不完整

**原因：** 飞书字段类型不匹配

**解决方案：**
1. 检查飞书表格的字段类型（应该按照上面的建议）
2. 如果有自定义字段，需要在脚本中添加映射逻辑
3. 查看 logs/app.log 了解详细错误

---

## 获取帮助

- 查看脚本日志：`cat logs/app.log`
- 检查 Supabase 数据：访问 https://supabase.com/dashboard
- 飞书开放平台文档：https://open.feishu.cn/document
- 项目 README：`docs/README.md`

---

**文档版本：** 1.0  
**更新日期：** 2026-04-27  
**维护者：** Cindy (cbconnectbr@gmail.com)
