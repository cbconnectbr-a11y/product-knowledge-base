# 用户指南

本指南面向产品知识库系统的三类用户：客服人员、审核员、管理员。

## 目录

1. [系统概述](#系统概述)
2. [客服人员使用指南](#客服人员使用指南)
3. [审核员使用指南](#审核员使用指南)
4. [管理员使用指南](#管理员使用指南)
5. [常见工作流](#常见工作流)
6. [最佳实践](#最佳实践)
7. [常见问题](#常见问题)

---

## 系统概述

### 什么是产品知识库系统？

产品知识库系统是为电商客服团队设计的技术支持平台，帮助快速查找产品技术问题和解决方案。

**核心功能**：
- 📚 统一管理产品技术问答
- 🔍 快速搜索 SKU 和关键词
- 🤖 飞书机器人实时查询
- ✅ 知识条目审核发布
- 📊 搜索行为分析

### 系统架构

```
数据来源                     系统核心                     用户界面
────────────               ──────────               ────────────

飞书产品表 ──┐
             │
飞书群聊 ────┼──> 知识库 ──> 搜索引擎 ──┬──> 飞书机器人
             │   (Supabase)              │
历史数据 ────┘                           └──> 飞书管理表
```

### 用户角色

| 角色 | 权限 | 主要任务 |
|------|------|---------|
| **客服人员 (Viewer)** | 只读 | 通过飞书机器人搜索知识 |
| **审核员 (Reviewer)** | 审核 | 审核和发布知识条目 |
| **管理员 (Admin)** | 完全 | 系统配置、数据导入、运维 |

---

## 客服人员使用指南

### 前置准备

1. **加入飞书群**：确认已被邀请加入客服支持群
2. **添加机器人**：在群中找到"产品知识库机器人"
3. **测试连接**：发送 `/help` 确认机器人响应

### 使用飞书机器人搜索

#### 方式 1：直接发送关键词（推荐）

最简单的方式，直接发送问题描述。

**示例 1：搜索技术问题**
```
输入：加热杯不加热
```

机器人会自动执行关键词搜索，返回相关知识条目。

**示例 2：搜索特定 SKU**
```
输入：CBC004-1234
```

机器人自动识别 SKU 格式，执行精确搜索。

**示例 3：混合搜索**
```
输入：CBC004-1234 漏水问题
```

机器人提取 SKU 并搜索该产品的相关问题。

---

#### 方式 2：使用命令搜索

使用明确的命令格式。

**SKU 精确搜索**
```
/sku CBC004-1234
```

**关键词搜索**
```
/search 密封圈老化
```

**查看帮助**
```
/help
```

---

### 理解搜索结果

机器人返回的搜索结果格式：

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

**结果字段说明**：
- **SKU**：产品 SKU 编号
- **标题**：问题简要描述
- **内容**：详细的问题分析和解决方案
- **关键词**：相关标签，帮助理解问题类型
- **来源**：知识来源（如客服群A、历史数据）

---

### 搜索技巧

#### 技巧 1：使用准确的 SKU

**优先使用 SKU 搜索**，结果最精确。

✅ 推荐：
```
CBC004-1234
```

❌ 不推荐：
```
CBC004 加热杯
```
（可能返回其他 SKU 的结果）

---

#### 技巧 2：使用核心关键词

**使用具体的技术词汇**，而非完整句子。

✅ 推荐：
```
漏水 密封圈
```

❌ 不推荐：
```
我们的客户说他的杯子好像有点漏水的样子
```
（过长的句子可能降低搜索准确性）

---

#### 技巧 3：尝试不同关键词

如果第一次搜索无结果，尝试同义词或相关词。

**示例**：
```
第一次：加热杯不加热
无结果？

第二次：加热 故障
第三次：CBC004 加热元件
```

---

#### 技巧 4：利用搜索历史

**记录常见问题的 SKU 或关键词**，建立个人知识库。

推荐工具：
- 飞书"收藏"功能（收藏机器人回复）
- 个人笔记（记录常用 SKU）

---

### 无结果怎么办？

如果机器人返回"未找到相关知识条目"：

**步骤 1：检查 SKU 格式**
- 确认 SKU 正确（3字母+3数字-4数字，如 CBC004-1234）
- 注意大小写（系统会自动转大写，但建议统一）

**步骤 2：简化关键词**
- 去掉"的"、"是"、"怎么办"等无意义词
- 使用核心技术词汇

**步骤 3：联系审核员**
- 如果确认问题存在但搜索不到，可能是：
  - 知识条目尚未审核（status = pending）
  - 该问题尚未收录
- 通知审核员或管理员添加知识条目

**步骤 4：反馈给管理员**
- 高频搜索无果的查询应记录下来
- 定期反馈给管理员，帮助完善知识库

---

### 客服日常工作流

**早上上班**：
1. 打开飞书客服群
2. @机器人 `/help` 确认服务正常
3. 准备常用 SKU 列表

**处理客户咨询**：
1. 客户描述问题
2. 识别产品 SKU
3. @机器人 搜索 SKU 或关键词
4. 阅读搜索结果
5. 结合实际情况回复客户
6. 如有新问题，记录下来

**下班前**：
1. 整理今天遇到的新问题
2. 在客服群分享（机器人会采集）
3. 或提交给审核员

---

## 审核员使用指南

审核员负责审核和发布知识条目，确保知识库内容准确可靠。

### 前置准备

1. **访问飞书管理表**：管理员会分享"知识库管理"多维表格
2. **了解审核标准**：见下文"审核标准"
3. **配置通知**：设置飞书表格的更新提醒

### 打开管理表

1. 在飞书中搜索"知识库管理"（或点击管理员分享的链接）
2. 打开"待审核条目"表格
3. 筛选 `Status = pending`（待审核）

### 审核知识条目

#### 步骤 1：查看条目详情

审核表格包含以下字段：
- **DB_ID**：数据库 ID（系统自动生成，无需修改）
- **SKU**：产品 SKU 编号
- **标题**：知识条目标题
- **内容**：详细内容
- **来源**：数据来源（如"客服群A"、"历史数据导入"）
- **关键词**：关键词列表
- **创建时间**：条目创建时间
- **Status**：审核状态（pending/approved/rejected/draft）
- **审核意见**：审核员填写的备注

---

#### 步骤 2：审核标准

**批准条件（approved）**：
- ✅ 内容准确、完整、有帮助
- ✅ SKU 和产品信息匹配
- ✅ 没有明显的拼写或语法错误
- ✅ 格式规范，易于阅读
- ✅ 解决方案可行且安全

**拒绝条件（rejected）**：
- ❌ 信息不准确或过时
- ❌ 内容不完整或模糊不清
- ❌ 重复已有条目
- ❌ SKU 错误或不存在
- ❌ 内容与产品无关
- ❌ 存在安全隐患的建议

**草稿（draft）**：
- 📝 内容有价值但需要补充
- 📝 等待进一步验证
- 📝 暂时不发布

---

#### 步骤 3：更新 Status 字段

根据审核结果，点击 `Status` 列：
1. 选择 `approved`（批准）
2. 或选择 `rejected`（拒绝）
3. 或选择 `draft`（草稿）

---

#### 步骤 4：填写审核意见（可选但推荐）

在 `审核意见` 字段中：

**批准示例**：
```
信息准确，解决方案可行。已验证 SKU 正确。
```

**拒绝示例**：
```
SKU 错误，应为 CBC004-1235 而非 CBC004-1234。
建议重新核对后再提交。
```

**草稿示例**：
```
内容有价值，但缺少具体的操作步骤。
建议补充：1. 检查方法 2. 更换步骤 3. 注意事项
```

---

#### 步骤 5：保存修改

飞书多维表格会自动保存修改。

---

### 同步审核结果

审核完成后，需要管理员运行同步脚本：

```bash
python3 scripts/create_management_table.py sync-reviews
```

**或者联系管理员**：
- 在管理群中 @管理员
- 说明已完成审核，请求同步

**同步后**：
- `approved` 的条目会在机器人搜索中出现
- `rejected` 的条目不会出现在搜索中
- `draft` 的条目保持待审核状态

---

### 审核工作流

**每天定时审核**：
1. 打开飞书管理表
2. 筛选 `Status = pending`
3. 逐条审核
4. 批量处理相似问题
5. 通知管理员同步

**优先级排序**：
1. **高优先级**：常见 SKU、高频问题
2. **中优先级**：新产品、季节性问题
3. **低优先级**：冷门产品、历史问题

---

### 审核技巧

#### 技巧 1：快速验证 SKU

在飞书产品表中搜索 SKU，确认：
- SKU 存在
- 产品名称匹配
- 产品状态（在售/停产）

---

#### 技巧 2：检查重复条目

在管理表中搜索相同的 SKU 和关键词：
```
Ctrl+F 搜索 "CBC004-1234 漏水"
```

如果发现重复：
- 保留信息更完整的条目
- 拒绝重复条目，备注"重复，见条目 #123"

---

#### 技巧 3：改进内容

如果条目有价值但需要改进：
1. 先标记为 `draft`
2. 在审核意见中说明需要改进的地方
3. （可选）自己在飞书表格中直接编辑改进
4. 改进后再批准

---

#### 技巧 4：批量审核

对于同一来源的批量条目（如历史数据导入）：
1. 先审核 5-10 条样本
2. 如果质量稳定，可以批量批准
3. 如果质量不稳定，逐条审核

---

### 审核统计

定期查看审核统计，优化审核效率：

在 Supabase Dashboard → SQL Editor 运行：
```sql
-- 审核统计
SELECT 
    status, 
    COUNT(*) as count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
FROM knowledge_entries
GROUP BY status;

-- 审核员工作量
SELECT 
    reviewed_by, 
    COUNT(*) as reviewed_count
FROM knowledge_entries
WHERE reviewed_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY reviewed_by
ORDER BY reviewed_count DESC;
```

或联系管理员生成报表。

---

## 管理员使用指南

管理员负责系统配置、数据导入、运维监控。

### 日常运维任务

#### 1. 监控服务状态

**检查 Webhook 服务**：
```bash
curl http://localhost:5000/health

# 预期输出：
# {"status": "healthy", "service": "product-knowledge-base-bot", "version": "1.0.0"}
```

**检查定时任务**：
```bash
launchctl list | grep com.product-kb

# 输出示例：
# -	0	com.product-kb.sync-products
# -	0	com.product-kb.sync-feishu-qa
# 第二列为 0 表示正常
```

**查看日志**：
```bash
# 同步日志
tail -f logs/sync-products.log
tail -f logs/sync-feishu-qa.log

# 服务日志
tail -f logs/app.log

# 错误日志
tail -f logs/sync-products.error.log
```

---

#### 2. 同步审核结果

审核员完成审核后，运行同步脚本：

```bash
# 方法 1：仅同步审核结果
python3 scripts/create_management_table.py sync-reviews

# 方法 2：完整同步（推送待审核 + 同步审核结果）
python3 scripts/create_management_table.py sync-all
```

**建议频率**：
- 每天 2-3 次
- 或配置为定时任务（每 2 小时）

---

#### 3. 数据备份

**备份 Supabase 数据**：

方法 1：通过 Supabase Dashboard
1. 登录 Supabase Dashboard
2. Database → Backups
3. 点击"Download backup"

方法 2：通过命令行
```bash
# 使用 pg_dump
pg_dump "postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres" \
  -t public.knowledge_entries \
  -t public.products \
  -t public.users \
  -t public.search_logs \
  > backup-$(date +%Y%m%d).sql
```

**建议频率**：每周一次

---

### 数据管理

#### 导入历史数据

详见 [历史数据导入指南](import_guide.md)。

**快速导入**：
```bash
# 预览
python3 scripts/import_historical_data.py --dry-run

# 导入
python3 scripts/import_historical_data.py
```

---

#### 批量更新条目状态

如果需要批量批准条目（如历史数据质量稳定）：

```sql
-- 批准所有来自特定来源的条目
UPDATE knowledge_entries
SET 
    status = 'approved',
    reviewed_at = NOW(),
    reviewer_notes = '历史数据批量导入，已验证'
WHERE source_group LIKE '历史数据导入%'
  AND status = 'pending';
```

⚠️ **注意**：批量操作前务必备份数据。

---

#### 清理无效数据

定期清理被拒绝的旧条目：

```sql
-- 查看拒绝条目统计
SELECT source_group, COUNT(*) 
FROM knowledge_entries 
WHERE status = 'rejected'
GROUP BY source_group;

-- 删除 30 天前被拒绝的条目（谨慎操作）
DELETE FROM knowledge_entries
WHERE status = 'rejected'
  AND reviewed_at < CURRENT_DATE - INTERVAL '30 days';
```

---

### 用户管理

#### 添加新用户

```sql
INSERT INTO users (email, name, role)
VALUES ('newuser@example.com', 'New User', 'viewer')
ON CONFLICT (email) DO NOTHING;
```

#### 修改用户角色

```sql
UPDATE users
SET role = 'reviewer'
WHERE email = 'user@example.com';
```

#### 查看用户列表

```sql
SELECT email, name, role, created_at
FROM users
ORDER BY created_at DESC;
```

---

### 搜索分析

#### 查看搜索热词

```sql
SELECT 
    query, 
    COUNT(*) as search_count,
    AVG(result_count) as avg_results
FROM search_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY query
ORDER BY search_count DESC
LIMIT 20;
```

#### 查看无结果搜索

```sql
SELECT query, COUNT(*) as count
FROM search_logs
WHERE result_count = 0
  AND created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY query
ORDER BY count DESC
LIMIT 20;
```

这些查询可以帮助识别知识库的缺口。

---

### 系统优化

#### 重建搜索索引

如果搜索性能下降：

```sql
-- 重建全文搜索索引
REINDEX INDEX idx_knowledge_entries_search_vector;

-- 更新搜索向量（如果触发器失效）
UPDATE knowledge_entries
SET updated_at = NOW()
WHERE search_vector IS NULL;
```

#### 清理搜索日志

搜索日志会不断增长，定期清理：

```sql
-- 删除 90 天前的日志
DELETE FROM search_logs
WHERE created_at < CURRENT_DATE - INTERVAL '90 days';
```

---

### 故障处理

#### 问题 1：定时任务未运行

**诊断**：
```bash
# 查看任务状态
launchctl list | grep com.product-kb

# 查看详细信息
launchctl print gui/$(id -u)/com.product-kb.sync-products

# 查看错误日志
tail -f logs/sync-products.error.log
```

**常见原因**：
- .env 文件未加载
- Python 路径错误
- 权限问题

**解决方案**：
```bash
# 重新安装定时任务
bash scripts/setup_launchd.sh
```

---

#### 问题 2：Webhook 服务挂掉

**诊断**：
```bash
curl http://localhost:5000/health
# 如果无响应，说明服务未运行
```

**解决方案**：
```bash
# 查看进程
ps aux | grep "bot.main"

# 重启服务
pkill -f "bot.main"
python3 bot/main.py &

# 或使用启动脚本
bash scripts/start_bot.sh
```

---

#### 问题 3：飞书机器人无响应

**诊断步骤**：
1. 检查服务状态：`curl http://localhost:5000/health`
2. 查看日志：`tail -f logs/app.log`
3. 测试 Webhook：在飞书后台点击"重新验证"
4. 检查飞书应用权限

**常见原因**：
- Webhook URL 失效（如 ngrok 重启）
- Token 验证失败
- 应用权限不足

---

## 常见工作流

### 工作流 1：添加新产品知识

**场景**：上架新产品，需要添加产品信息和常见问题。

**步骤**：
1. **管理员**：在飞书产品表中添加产品信息
2. **管理员**：运行产品同步脚本
   ```bash
   python3 scripts/sync_product_table.py
   ```
3. **客服**：在客服群中分享新产品的常见问题
4. **管理员**：运行问答同步脚本（或等待定时任务）
   ```bash
   python3 scripts/sync_feishu_qa.py
   ```
5. **审核员**：在飞书管理表中审核新条目
6. **管理员**：运行审核同步脚本
   ```bash
   python3 scripts/create_management_table.py sync-reviews
   ```
7. **客服**：测试机器人搜索新产品 SKU

---

### 工作流 2：处理客户咨询

**场景**：客服收到客户关于产品故障的咨询。

**步骤**：
1. **客服**：确认客户的产品 SKU
2. **客服**：@机器人 搜索 SKU
   ```
   CBC004-1234
   ```
3. **机器人**：返回该 SKU 的相关知识条目
4. **客服**：阅读解决方案，结合实际情况回复客户
5. **客服**：如果问题未收录，在群中分享：
   ```
   【新问题】CBC004-1234 - 客户反馈加热元件不工作
   解决方法：检查电源线连接，确认插座有电
   ```
6. **系统**：定时任务自动采集群消息
7. **审核员**：审核新条目
8. **管理员**：同步审核结果

---

### 工作流 3：批量导入历史数据

**场景**：有大量历史技术问题需要导入系统。

**步骤**：
1. **管理员**：准备 JSON 文件，放入 `~/客服知识库/` 目录
2. **管理员**：预览导入
   ```bash
   python3 scripts/import_historical_data.py --dry-run --verbose
   ```
3. **管理员**：确认无误后导入
   ```bash
   python3 scripts/import_historical_data.py
   ```
4. **管理员**：推送待审核条目到飞书
   ```bash
   python3 scripts/create_management_table.py sync-pending
   ```
5. **审核员**：在飞书管理表中批量审核
6. **管理员**：同步审核结果
   ```bash
   python3 scripts/create_management_table.py sync-reviews
   ```
7. **客服**：测试搜索历史数据

详见 [历史数据导入指南](import_guide.md)。

---

## 最佳实践

### 客服最佳实践

1. **优先使用 SKU 搜索**
   - SKU 精确匹配，结果最可靠
   - 建立常用 SKU 清单

2. **使用核心关键词**
   - 避免完整句子
   - 使用技术词汇而非口语

3. **分享新问题**
   - 在客服群中及时分享新遇到的问题
   - 使用统一格式：【新问题】SKU - 问题描述 + 解决方法

4. **反馈搜索问题**
   - 高频搜索无果的查询记录下来
   - 定期反馈给审核员或管理员

---

### 审核员最佳实践

1. **定时审核**
   - 每天固定时间审核（如上午、下午各一次）
   - 避免积压大量待审核条目

2. **优先处理常见 SKU**
   - 高频产品优先审核
   - 新产品优先审核

3. **详细的审核意见**
   - 拒绝时说明具体原因
   - 帮助提高知识条目质量

4. **定期去重**
   - 检查并合并重复条目
   - 保留信息更完整的版本

---

### 管理员最佳实践

1. **自动化运维**
   - 使用 launchd 自动运行定时任务
   - 配置日志轮转

2. **定期备份**
   - 每周备份 Supabase 数据
   - 保留至少 4 周的备份

3. **监控和告警**
   - 定期检查服务健康
   - 配置关键错误告警

4. **数据分析**
   - 定期查看搜索热词
   - 识别知识库缺口
   - 优化搜索体验

---

## 常见问题

### Q1：机器人无响应怎么办？

**A1**：按以下顺序排查：
1. 确认机器人已加入群聊
2. 检查是否 @ 了机器人（私聊不需要 @）
3. 查看消息是否重复（5 分钟内重复消息会被忽略）
4. 联系管理员检查服务状态

---

### Q2：搜索不到明明存在的条目？

**A2**：可能原因：
1. **条目未审核**：只有 `approved` 状态的条目才能搜索到
2. **SKU 格式错误**：确认 SKU 格式正确
3. **关键词不匹配**：尝试使用不同的关键词
4. **索引未更新**：联系管理员重建索引

---

### Q3：如何知道哪些知识需要补充？

**A3**：
- **客服**：记录高频无结果搜索
- **审核员**：查看飞书管理表中的 draft 条目
- **管理员**：分析 search_logs 中 `result_count = 0` 的查询

---

### Q4：审核意见客服能看到吗？

**A4**：
- 审核意见存储在 Supabase，机器人搜索结果中不显示
- 仅审核员和管理员可见
- 如需向客服反馈，可在客服群中单独说明

---

### Q5：一个 SKU 可以有多个知识条目吗？

**A5**：
- 可以。一个 SKU 可能有多个不同的技术问题
- 搜索 SKU 时，会返回所有相关条目
- 建议：每个条目聚焦一个具体问题

---

### Q6：如何批量导入数据？

**A6**：
- 使用历史数据导入脚本（管理员操作）
- 详见 [历史数据导入指南](import_guide.md)
- 或手动在 Supabase 中插入数据

---

### Q7：搜索结果太多怎么办？

**A7**：
- 使用更具体的关键词
- 优先使用 SKU 精确搜索
- Phase 2 将支持结果排序和筛选

---

### Q8：如何删除错误的知识条目？

**A8**：
- **审核员**：标记为 `rejected`
- **管理员**：在 Supabase 中直接删除
  ```sql
  DELETE FROM knowledge_entries WHERE id = 'xxx';
  ```

---

## 相关文档

- [部署指南](setup.md) - 系统安装和配置
- [API 文档](api.md) - 详细的 API 接口说明
- [管理指南](management_guide.md) - 知识库审核工作流
- [导入指南](import_guide.md) - 历史数据导入步骤

---

## 技术支持

- **系统问题**：联系管理员
- **审核问题**：联系审核组长
- **产品问题**：在客服群中讨论

**管理员联系方式**：Cindy (cbconnectbr@gmail.com)

**文档版本**：1.0  
**更新日期**：2026-04-27
