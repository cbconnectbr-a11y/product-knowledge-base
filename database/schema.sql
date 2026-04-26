-- Product Knowledge Base - Phase 1 Database Schema
-- Created: 2026-04-26
-- Description: Core tables for product knowledge management system

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- Table: users
-- Description: User accounts with role-based access control
-- ============================================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('viewer', 'reviewer', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- Index for user lookups by email
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

COMMENT ON TABLE users IS 'User accounts with role-based access control';
COMMENT ON COLUMN users.role IS 'viewer: read-only, reviewer: can edit knowledge, admin: full access';

-- ============================================================================
-- Table: products
-- Description: Product information table
-- ============================================================================
CREATE TABLE IF NOT EXISTS products (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  sku text UNIQUE NOT NULL,
  name_cn text,
  name_en text,
  category text,
  brand text,

  -- Search enhancement fields (Phase 1: manual, Phase 2+: AI-generated)
  aliases text[],
  search_keywords text[],
  category_path text[],
  search_vector tsvector,  -- Full-text search vector

  -- Feishu raw data
  feishu_raw_data jsonb NOT NULL,

  -- Common fields for quick access
  images text[],
  package_images text[],
  features text,
  description text,
  manual_files jsonb,
  model_3d_url text,

  -- Metadata
  feishu_record_id text,
  mabang_id text,
  synced_at timestamp with time zone DEFAULT now(),
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);

-- Indexes for product lookups
CREATE INDEX products_sku_idx ON products(sku);
CREATE INDEX products_search_vector_idx ON products USING GIN(search_vector);
CREATE INDEX products_name_cn_trgm_idx ON products USING GIN(name_cn gin_trgm_ops);
CREATE INDEX products_name_en_trgm_idx ON products USING GIN(name_en gin_trgm_ops);
CREATE INDEX products_feishu_data_idx ON products USING GIN(feishu_raw_data);
CREATE INDEX products_aliases_idx ON products USING GIN(aliases);

COMMENT ON TABLE products IS 'Product information table';
COMMENT ON COLUMN products.search_vector IS 'Full-text search vector (auto-generated)';
COMMENT ON COLUMN products.feishu_raw_data IS 'Complete Feishu raw data (JSONB)';

-- ============================================================================
-- Table: knowledge_entries
-- Description: Knowledge base entries
-- ============================================================================
CREATE TABLE knowledge_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku VARCHAR(100),
    title TEXT NOT NULL,
    content TEXT NOT NULL,

    -- Source information
    source_type VARCHAR(50) NOT NULL,  -- 'feishu_chat', 'manual'
    source_id VARCHAR(200),
    source_group VARCHAR(200),

    -- Classification and tags (Phase 1 manual, Phase 2+ AI)
    category TEXT[] DEFAULT '{}',
    keywords TEXT[] DEFAULT '{}',

    -- Status management
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'draft', 'approved', 'rejected'

    -- Full-text search
    search_vector tsvector,  -- Full-text search vector (auto-generated)

    -- Usage statistics
    view_count INTEGER DEFAULT 0,
    helpful_count INTEGER DEFAULT 0,

    -- Review information
    created_by UUID REFERENCES users(id),
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,

    -- Constraint: Prevent duplicate imports
    CONSTRAINT unique_source UNIQUE(source_type, source_id)
);

-- Indexes for knowledge entry lookups
CREATE INDEX idx_knowledge_entries_sku ON knowledge_entries(sku);
CREATE INDEX idx_knowledge_entries_status ON knowledge_entries(status);
CREATE INDEX idx_knowledge_entries_category ON knowledge_entries USING GIN(category);
CREATE INDEX idx_knowledge_entries_created_at ON knowledge_entries(created_at DESC);
CREATE INDEX idx_knowledge_entries_search_vector ON knowledge_entries USING GIN(search_vector);

COMMENT ON TABLE knowledge_entries IS 'Knowledge base entries';
COMMENT ON COLUMN knowledge_entries.source_type IS 'Source type: feishu_chat (Feishu groups) / manual (Manual entry)';
COMMENT ON COLUMN knowledge_entries.status IS 'Status: pending (awaiting review) / draft (draft) / approved (published) / rejected (rejected)';

-- ============================================================================
-- Table: search_logs
-- Description: Search query logs for analytics
-- ============================================================================
CREATE TABLE search_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    query TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    clicked_entry_id UUID REFERENCES knowledge_entries(id),
    search_type VARCHAR(50) NOT NULL DEFAULT 'keyword' CHECK (search_type IN ('keyword', 'sku', 'fuzzy')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for search log analytics
CREATE INDEX idx_search_logs_user_id ON search_logs(user_id);
CREATE INDEX idx_search_logs_created_at ON search_logs(created_at);
CREATE INDEX idx_search_logs_query_trgm ON search_logs USING gin (query gin_trgm_ops);

COMMENT ON TABLE search_logs IS 'Search query logs for analytics and improvement';
COMMENT ON COLUMN search_logs.clicked_entry_id IS 'Which knowledge entry the user clicked (if any)';

-- ============================================================================
-- Functions and Triggers
-- ============================================================================

-- Function: Update updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger: Auto-update updated_at for users
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger: Auto-update updated_at for products
CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger: Auto-update updated_at for knowledge_entries
CREATE TRIGGER update_knowledge_entries_updated_at BEFORE UPDATE ON knowledge_entries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function: Auto-update search_vector for knowledge_entries
CREATE OR REPLACE FUNCTION update_knowledge_entries_search_vector()
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_vector := to_tsvector('english', COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Auto-update search_vector for knowledge_entries
CREATE TRIGGER knowledge_entries_search_vector_update
  BEFORE INSERT OR UPDATE OF title, content
  ON knowledge_entries
  FOR EACH ROW
  EXECUTE FUNCTION update_knowledge_entries_search_vector();


-- ============================================================================
-- Initial Admin User
-- ============================================================================

-- Insert initial admin user (using the user's email from context)
INSERT INTO users (email, name, role)
VALUES ('cbconnectbr@gmail.com', 'Cindy (Admin)', 'admin')
ON CONFLICT (email) DO NOTHING;

-- ============================================================================
-- Row Level Security (RLS) - Optional for Phase 1
-- ============================================================================

-- Enable RLS on tables (commented out for Phase 1 MVP, can enable later)
-- ALTER TABLE users ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE products ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE knowledge_entries ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE search_logs ENABLE ROW LEVEL SECURITY;

-- Example RLS policies (commented out for Phase 1)
-- CREATE POLICY "Users can view all products" ON products FOR SELECT USING (true);
-- CREATE POLICY "Reviewers can edit knowledge" ON knowledge_entries FOR UPDATE
--     USING (auth.uid() IN (SELECT id FROM users WHERE role IN ('reviewer', 'admin')));
