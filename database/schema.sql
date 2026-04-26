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
-- Description: Product catalog with SKU and metadata
-- ============================================================================
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(500) NOT NULL,
    category VARCHAR(200),
    brand VARCHAR(200),
    supplier VARCHAR(200),
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'discontinued', 'draft')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for product lookups
CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_brand ON products(brand);
CREATE INDEX idx_products_status ON products(status);
CREATE INDEX idx_products_name_trgm ON products USING gin (name gin_trgm_ops);

COMMENT ON TABLE products IS 'Product catalog with SKU and metadata';
COMMENT ON COLUMN products.metadata IS 'Flexible JSON field for additional product attributes';

-- ============================================================================
-- Table: knowledge_entries
-- Description: Knowledge base entries linked to products
-- ============================================================================
CREATE TABLE knowledge_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL CHECK (category IN (
        'specification',
        'usage',
        'troubleshooting',
        'faq',
        'comparison',
        'certification',
        'other'
    )),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    source VARCHAR(200),
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_by UUID REFERENCES users(id),
    verified_at TIMESTAMPTZ,
    search_vector tsvector,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for knowledge entry lookups
CREATE INDEX idx_knowledge_entries_product_id ON knowledge_entries(product_id);
CREATE INDEX idx_knowledge_entries_category ON knowledge_entries(category);
CREATE INDEX idx_knowledge_entries_verified ON knowledge_entries(verified);
CREATE INDEX idx_knowledge_entries_created_by ON knowledge_entries(created_by);
CREATE INDEX idx_knowledge_entries_tags ON knowledge_entries USING gin(tags);
CREATE INDEX idx_knowledge_entries_search_vector ON knowledge_entries USING gin(search_vector);

COMMENT ON TABLE knowledge_entries IS 'Knowledge base entries linked to products';
COMMENT ON COLUMN knowledge_entries.search_vector IS 'Auto-generated full-text search vector';
COMMENT ON COLUMN knowledge_entries.verified IS 'Whether this entry has been reviewed and verified';

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

-- Function: Update search_vector automatically for full-text search
CREATE OR REPLACE FUNCTION update_knowledge_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.question, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.answer, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(array_to_string(NEW.tags, ' '), '')), 'C');
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger: Auto-update search_vector for knowledge_entries
CREATE TRIGGER update_knowledge_entries_search_vector
BEFORE INSERT OR UPDATE ON knowledge_entries
    FOR EACH ROW EXECUTE FUNCTION update_knowledge_search_vector();

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
