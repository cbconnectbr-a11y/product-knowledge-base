# 下一步操作指引

## 当前状态

✅ Step 1: DRY-RUN 验证通过 (7,964 条记录待删除)  
✅ Step 2: 备份已完成 (48 MB, 可恢复)  
⏸️  Step 3: DELETE 因 Python 客户端超时需手动执行

---

## 立即执行

### Step 3: 手动执行 DELETE

**打开 Supabase SQL Editor:**
```
https://supabase.com/dashboard/project/vhfvbqaflibozihlejin/sql/new
```

**复制并执行以下 SQL:**
```sql
DELETE FROM knowledge_entries
WHERE source_group IN (
    '多客客服 - 0800',
    '多客客服 - 0600',
    '多客客服 - 0928',
    '多客客服 - 0901',
    '多客客服 - 0903'
);
```

**记录结果:**
- Supabase 会显示 "DELETE 7964" (或其他数字)
- 记下这个数字

---

### Step 4: 运行验证脚本

**删除完成后，立即运行:**
```bash
cd /Users/cindy/Projects/product-knowledge-base
python3.13 scripts/verify_deletion.py
```

**脚本会自动检查:**
- ① 总记录数是否为 103 条
- ② 是否只剩 3 个历史数据 source_group
- ③ 是否没有任何多客客服残留

---

## 验证通过后的步骤

### Step 5: 添加唯一约束

**在 Supabase SQL Editor 执行:**
```sql
ALTER TABLE knowledge_entries
ADD CONSTRAINT unique_source_title UNIQUE (source_group, title);
```

**验证约束已生效:**
```sql
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'knowledge_entries'
  AND constraint_type = 'UNIQUE';
```

---

### Step 6: 测试修复后的导入脚本

**选择最小文件测试:**
```bash
python3.13 scripts/import_one.py data/duoke/汇总_20260313_0903.xlsx
```

**验证 4 项指标:**
1. source_group 格式: `多客客服 - 20260313` (8位日期)
2. 重复插入被拒绝: 唯一约束报错而不是静默成功
3. 数据正确性: SKU/title/content 完整
4. import_log 记录: status = 'completed'

---

### Step 7: 批量导入所有文件

**只有 Step 6 所有验证通过后才执行:**
```bash
./scripts/batch_import.sh
```

**监控进度:**
```bash
./scripts/check_progress.sh
```

---

## 如果出问题

### 恢复备份
```bash
python3.13 scripts/restore_backup.py backups/knowledge_entries_backup_2026-05-05_before_cleanup.json
```

### 删除唯一约束 (如果需要)
```sql
ALTER TABLE knowledge_entries DROP CONSTRAINT unique_source_title;
```

---

## 文件位置

- DELETE SQL: `scripts/delete_wrong_format.sql`
- 验证脚本: `scripts/verify_deletion.py`
- 唯一约束 SQL: `scripts/add_unique_constraint.sql`
- 备份文件: `backups/knowledge_entries_backup_2026-05-05_before_cleanup.json`
- 恢复脚本: `scripts/restore_backup.py`

---

**最后更新**: 2026-05-01  
**当前步骤**: Step 3 (等待手动 DELETE)
