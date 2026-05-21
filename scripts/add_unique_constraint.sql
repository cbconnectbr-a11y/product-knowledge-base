-- Bug C 修复：添加数据库唯一约束
-- 防止重复记录写入（即使脚本有bug，数据库也会拒绝）

-- 步骤1: 先清理现有重复数据（可选，取决于回滚策略）
-- 这一步在确定回滚策略后再执行

-- 步骤2: 添加唯一约束
-- 选项 A: 只约束 (source_group, title) 组合
ALTER TABLE knowledge_entries
ADD CONSTRAINT unique_source_title UNIQUE (source_group, title);

-- 选项 B: 约束 (source_group, title, sku) 组合（更严格）
-- ALTER TABLE knowledge_entries
-- ADD CONSTRAINT unique_source_title_sku UNIQUE (source_group, title, sku);

-- 说明:
-- - 选项A: 同一来源（source_group）+ 同一标题（title）→ 唯一
--   适合场景: 标题已经能唯一标识一条记录
--
-- - 选项B: 同一来源 + 同一标题 + 同一SKU → 唯一
--   适合场景: 标题可能重复（如"客户咨询"），需要SKU辅助区分
--   但问题: SKU可能为NULL，NULL不参与唯一性判断
--
-- 推荐: 选项A（标题已经包含了SKU和意图信息）

-- 验证约束是否生效:
-- SELECT constraint_name, constraint_type
-- FROM information_schema.table_constraints
-- WHERE table_name = 'knowledge_entries';

-- 如果需要删除约束:
-- ALTER TABLE knowledge_entries DROP CONSTRAINT unique_source_title;
