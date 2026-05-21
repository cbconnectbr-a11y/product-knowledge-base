-- =============================================================================
-- 为 knowledge_entries 表添加 pg_trgm 索引，加速中文 LIKE 搜索
-- 执行位置：Supabase Dashboard → SQL Editor
-- 预计耗时：2-5 分钟
-- =============================================================================

-- 步骤 1: 启用 pg_trgm 扩展（Supabase 默认支持）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 步骤 2: 为 title 字段创建 GIN 索引（加速 LIKE '%xxx%'）
CREATE INDEX IF NOT EXISTS idx_knowledge_title_trgm
ON knowledge_entries USING GIN (title gin_trgm_ops);

-- 步骤 3: 为 content 字段创建 GIN 索引
CREATE INDEX IF NOT EXISTS idx_knowledge_content_trgm
ON knowledge_entries USING GIN (content gin_trgm_ops);

-- 步骤 4: 查看索引创建结果（验证）
SELECT
    i.schemaname,
    i.tablename,
    i.indexname,
    pg_size_pretty(pg_relation_size(i.indexrelid)) as index_size,
    idx.indisvalid as is_valid
FROM pg_stat_user_indexes i
JOIN pg_index idx ON i.indexrelid = idx.indexrelid
WHERE i.tablename = 'knowledge_entries'
  AND i.indexname LIKE '%trgm%'
ORDER BY i.indexname;

-- 预期输出：
-- indexname                         | index_size | is_valid
-- idx_knowledge_title_trgm         | xxx MB     | t
-- idx_knowledge_content_trgm       | xxx MB     | t
