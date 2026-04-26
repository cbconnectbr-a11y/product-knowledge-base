-- Migration: Add extended product fields for Feishu sync
-- Created: 2026-04-26
-- Description: Add fields needed for product table sync from Feishu Bitable

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS name_en TEXT,
  ADD COLUMN IF NOT EXISTS name_cn TEXT,
  ADD COLUMN IF NOT EXISTS aliases TEXT[],
  ADD COLUMN IF NOT EXISTS search_keywords TEXT[],
  ADD COLUMN IF NOT EXISTS category_path TEXT[],
  ADD COLUMN IF NOT EXISTS images TEXT[],
  ADD COLUMN IF NOT EXISTS package_images TEXT[],
  ADD COLUMN IF NOT EXISTS features TEXT,
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS manual_files JSONB,
  ADD COLUMN IF NOT EXISTS model_3d_url TEXT,
  ADD COLUMN IF NOT EXISTS feishu_raw_data JSONB,
  ADD COLUMN IF NOT EXISTS feishu_record_id TEXT,
  ADD COLUMN IF NOT EXISTS mabang_id TEXT,
  ADD COLUMN IF NOT EXISTS synced_at TIMESTAMPTZ;

-- Rename existing name column to avoid confusion
ALTER TABLE products
  RENAME COLUMN name TO name_legacy;

-- Create composite name view for backward compatibility
COMMENT ON COLUMN products.name_cn IS 'Chinese product name';
COMMENT ON COLUMN products.name_en IS 'English product name';
COMMENT ON COLUMN products.name_legacy IS 'Legacy name field (deprecated, use name_cn/name_en)';
COMMENT ON COLUMN products.feishu_raw_data IS 'Complete raw data from Feishu Bitable';
COMMENT ON COLUMN products.feishu_record_id IS 'Feishu record ID for tracking updates';

-- Add index for Feishu record lookups
CREATE INDEX IF NOT EXISTS idx_products_feishu_record_id ON products(feishu_record_id);
CREATE INDEX IF NOT EXISTS idx_products_synced_at ON products(synced_at);
