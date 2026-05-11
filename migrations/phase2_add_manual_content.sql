-- Phase 2: 添加说明书内容字段和更新搜索触发器
-- 执行位置: Supabase Dashboard > SQL Editor
-- 执行时间: 约 1 分钟

-- 1. 添加 manual_content 字段
ALTER TABLE products
ADD COLUMN IF NOT EXISTS manual_content TEXT;

-- 2. 为 manual_content 字段添加注释
COMMENT ON COLUMN products.manual_content IS '说明书提取的文本内容 (Phase 2)';

-- 3. 更新 search_vector 触发器（可选 - 如果需要全文搜索向量）
-- 如果 search_vector 触发器存在，更新它以包含 manual_content
DO $$
BEGIN
    -- 检查触发器是否存在
    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'update_products_search_vector_trigger'
    ) THEN
        -- 重新创建触发器函数
        CREATE OR REPLACE FUNCTION update_products_search_vector()
        RETURNS TRIGGER AS $func$
        BEGIN
          NEW.search_vector := to_tsvector('simple',
            COALESCE(NEW.sku, '') || ' ' ||
            COALESCE(NEW.name_cn, '') || ' ' ||
            COALESCE(NEW.name_en, '') || ' ' ||
            COALESCE(NEW.features, '') || ' ' ||
            COALESCE(NEW.description, '') || ' ' ||
            COALESCE(NEW.searchable_content, '') || ' ' ||
            COALESCE(NEW.manual_content, '')  -- Phase 2: 添加说明书内容
          );
          RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql;

        RAISE NOTICE '✅ search_vector 触发器已更新';
    ELSE
        RAISE NOTICE 'ℹ️  search_vector 触发器不存在，跳过更新';
    END IF;
END $$;

-- 4. 验证字段已添加
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'products'
  AND column_name = 'manual_content';

-- 预期输出:
-- column_name    | data_type | is_nullable
-- ---------------+-----------+-------------
-- manual_content | text      | YES
