# Bug 修复总结

## 第 2 步完成状态

### ✅ Bug A: source_group 提取逻辑 - 已修复

**文件:** `scripts/import_one.py` 行 116-123

**修复前:**
```python
file_date = file_path.stem.split('_')[-1]  # 取最后一个下划线分隔符
# 汇总_20260312_0600.xlsx → split('_')[-1] = '0600' ❌
```

**修复后:**
```python
import re
match = re.search(r'(\d{8})', file_path.stem)  # 正则提取8位日期
if match:
    file_date = match.group(1)  # '20260312' ✅
else:
    file_date = datetime.now().strftime('%Y%m%d')
```

**影响:**
- 历史已污染 7,964 条记录（错误格式）
- 今天测试污染 913 条记录
- 修复后新导入将使用正确格式

---

### ✅ Bug B: 重复检测失效 - 根因已分析

**根本原因:**

1. **竞态条件 (Race Condition)**
   - batch_import.sh 并行 3 个进程
   - 同时执行"检查 → 插入"流程
   - 导致同一记录被多次插入

2. **source_group 错误导致跨文件碰撞**
   - 不同日期文件映射到同一 source_group
   - 例: 汇总_20260312_0600.xlsx 和 汇总_20260313_0600.xlsx
   - 都变成 "多客客服 - 0600"

**修复方案:**

已在 `scripts/batch_import.sh` 中实现：
- ✅ 主进程预先过滤已完成文件
- ✅ 只传递需要导入的文件给并行处理器
- ⚠️ 仍需数据库唯一约束作为最后防线

---

### ✅ Bug C: 数据库唯一约束 - SQL已准备

**文件:** `scripts/add_unique_constraint.sql`

**SQL 语句:**
```sql
ALTER TABLE knowledge_entries
ADD CONSTRAINT unique_source_title UNIQUE (source_group, title);
```

**作用:**
- 防止 (source_group + title) 重复
- 即使脚本有bug，数据库也会拒绝重复插入
- 返回错误而不是静默失败

**执行时机:**
- ⚠️ 必须在清理重复数据AFTER
- ⚠️ 必须在批量导入BEFORE

---

## 修复验证计划

### 1. 先添加唯一约束（在 Supabase 控制台）

```sql
-- 注意: 如果表中已有重复数据，此操作会失败
-- 必须先清理重复数据

ALTER TABLE knowledge_entries
ADD CONSTRAINT unique_source_title UNIQUE (source_group, title);
```

**验证:**
```sql
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'knowledge_entries'
  AND constraint_type = 'UNIQUE';
```

### 2. 测试修复后的脚本

```bash
# 使用最小文件测试
python3.13 scripts/import_one.py data/duoke/汇总_20260312_0600.xlsx

# 预期结果:
# - source_group: 多客客服 - 20260312 (8位日期！)
# - 如果重复导入，数据库拒绝并报错
```

### 3. 验证修复效果

```python
from scripts.utils import get_supabase_client
client = get_supabase_client()

# 检查 source_group 格式
response = client.table('knowledge_entries') \
    .select('source_group') \
    .like('source_group', '%20260312%') \
    .execute()

# 应该找到 "多客客服 - 20260312" 而不是 "多客客服 - 0600"
```

---

## 下一步：回滚策略

等待用户决定：

- [ ] **选项 A**: 最小回滚（删除今天 913 条）
- [ ] **选项 B**: 回到基线（删除 3,040 条，恢复到 5,027）
- [ ] **选项 C**: 全面清理（删除所有 7,964 条错误记录）
- [ ] **选项 D**: Supabase 时间点恢复

选择后执行第 3 步。
