# Database Migrations

This directory contains database migration scripts for the Product Knowledge Base system.

## How to Apply Migrations

Migrations should be applied in order, before running the corresponding sync scripts.

### Option 1: Supabase Dashboard (Recommended)

1. Go to Supabase Dashboard > SQL Editor
2. Copy the content of the migration file
3. Paste and execute
4. Verify the changes were applied successfully

### Option 2: psql Command Line

```bash
# Get connection string from: Supabase Dashboard > Settings > Database
psql "postgresql://postgres:[PASSWORD]@[PROJECT-REF].supabase.co:5432/postgres" \
  -f database/migrations/001_add_product_fields.sql
```

## Migration List

- **001_add_product_fields.sql** - Add extended product fields for Feishu sync
  - Required before running: `scripts/sync_product_table.py`
  - Adds: name_en, name_cn, images, package_images, features, description, manual_files, model_3d_url, feishu_raw_data, etc.
  - Renames: `name` → `name_legacy` for backward compatibility
