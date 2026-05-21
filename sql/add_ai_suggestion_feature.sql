-- =============================================================================
-- AI 建议答案功能数据库迁移
-- 执行位置：Supabase Dashboard → SQL Editor
-- 功能：当知识库无答案时，AI生成建议答案，客服可采纳/拒绝/忽略
-- =============================================================================

-- ========================================
-- 1. 扩展 knowledge_entries 表
-- ========================================

-- 添加 source 字段（记录数据来源）
ALTER TABLE knowledge_entries
ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual';

COMMENT ON COLUMN knowledge_entries.source IS '数据来源：manual(手动), ai_approved(AI生成已采纳), ai_edited(AI生成已编辑), import(批量导入)';

-- 添加 reviewed_by 字段（记录谁批准的）
ALTER TABLE knowledge_entries
ADD COLUMN IF NOT EXISTS reviewed_by TEXT;

COMMENT ON COLUMN knowledge_entries.reviewed_by IS '审核人（飞书用户ID）';

-- 添加 reviewed_at 字段（记录审核时间）
ALTER TABLE knowledge_entries
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;

COMMENT ON COLUMN knowledge_entries.reviewed_at IS '审核时间';

-- 添加索引加速查询
CREATE INDEX IF NOT EXISTS idx_knowledge_entries_source
ON knowledge_entries(source);

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_reviewed_at
ON knowledge_entries(reviewed_at DESC);


-- ========================================
-- 2. 创建 ai_rejected_answers 表
-- ========================================

CREATE TABLE IF NOT EXISTS ai_rejected_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    ai_answer TEXT NOT NULL,
    rejected_by TEXT,
    rejected_at TIMESTAMP DEFAULT NOW(),
    question_hash TEXT NOT NULL,  -- MD5 hash 用于快速去重
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE ai_rejected_answers IS 'AI生成的被拒绝答案记录（避免重复调用AI）';

-- 添加索引
CREATE INDEX IF NOT EXISTS idx_rejected_question_hash
ON ai_rejected_answers(question_hash);

CREATE INDEX IF NOT EXISTS idx_rejected_created_at
ON ai_rejected_answers(created_at DESC);

-- ========================================
-- 3. 创建 ai_suggestion_log 表
-- ========================================

CREATE TABLE IF NOT EXISTS ai_suggestion_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    ai_answer TEXT NOT NULL,
    action TEXT,  -- approved, edited, rejected, ignored, null(未操作)
    final_answer TEXT,  -- 如果是 edited，记录最终版本
    user_id TEXT,  -- 飞书用户ID
    chat_id TEXT,  -- 飞书群聊ID
    latency_ms INT,  -- AI 生成耗时（毫秒）
    model TEXT,  -- 使用的模型（deepseek-chat, gpt-4o）
    created_at TIMESTAMP DEFAULT NOW(),
    responded_at TIMESTAMP,  -- 用户响应时间

    -- 额外元数据
    search_result_count INT DEFAULT 0,  -- 搜索结果数量（触发AI建议的原因）
    question_hash TEXT  -- 问题hash，用于关联
);

COMMENT ON TABLE ai_suggestion_log IS 'AI建议答案的完整日志（用于分析采纳率和优化prompt）';

-- 添加索引
CREATE INDEX IF NOT EXISTS idx_suggestion_log_created_at
ON ai_suggestion_log(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_suggestion_log_action
ON ai_suggestion_log(action);

CREATE INDEX IF NOT EXISTS idx_suggestion_log_user_id
ON ai_suggestion_log(user_id);

CREATE INDEX IF NOT EXISTS idx_suggestion_log_question_hash
ON ai_suggestion_log(question_hash);


-- ========================================
-- 4. 创建统计视图（方便分析采纳率）
-- ========================================

CREATE OR REPLACE VIEW ai_suggestion_stats AS
SELECT
    DATE_TRUNC('day', created_at) AS date,
    COUNT(*) AS total_suggestions,
    COUNT(CASE WHEN action = 'approved' THEN 1 END) AS approved_count,
    COUNT(CASE WHEN action = 'edited' THEN 1 END) AS edited_count,
    COUNT(CASE WHEN action = 'rejected' THEN 1 END) AS rejected_count,
    COUNT(CASE WHEN action = 'ignored' THEN 1 END) AS ignored_count,
    COUNT(CASE WHEN action IS NULL THEN 1 END) AS no_action_count,
    ROUND(
        100.0 * COUNT(CASE WHEN action IN ('approved', 'edited') THEN 1 END) / NULLIF(COUNT(*), 0),
        2
    ) AS adoption_rate,  -- 采纳率（%）
    AVG(latency_ms) AS avg_latency_ms,
    model
FROM ai_suggestion_log
GROUP BY DATE_TRUNC('day', created_at), model
ORDER BY date DESC;

COMMENT ON VIEW ai_suggestion_stats IS 'AI建议答案采纳率统计（按天）';


-- ========================================
-- 5. 查询示例（验证创建成功）
-- ========================================

-- 查看新增的字段
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'knowledge_entries'
  AND column_name IN ('source', 'reviewed_by', 'reviewed_at')
ORDER BY column_name;

-- 查看新创建的表
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('ai_rejected_answers', 'ai_suggestion_log')
ORDER BY table_name;

-- 预期输出示例
-- column_name   | data_type | column_default | is_nullable
-- reviewed_at   | timestamp | NULL           | YES
-- reviewed_by   | text      | NULL           | YES
-- source        | text      | 'manual'       | YES
--
-- table_name            | table_type
-- ai_rejected_answers   | BASE TABLE
-- ai_suggestion_log     | BASE TABLE
