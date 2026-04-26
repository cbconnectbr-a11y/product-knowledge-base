-- Product Knowledge Base - Test Seed Data
-- Created: 2026-04-26
-- Description: Sample data for testing and development

-- ============================================================================
-- Test Users
-- ============================================================================

-- Insert test users (viewer and reviewer)
INSERT INTO users (email, name, role) VALUES
    ('test.viewer@example.com', 'Test Viewer', 'viewer'),
    ('test.reviewer@example.com', 'Test Reviewer', 'reviewer')
ON CONFLICT (email) DO NOTHING;

-- Get admin user ID for later reference
SELECT id INTO admin_user_id FROM users WHERE email = 'cbconnectbr@gmail.com';

-- ============================================================================
-- Test Products
-- ============================================================================

-- Insert test products with realistic SKUs
INSERT INTO products (sku, name, category, brand, supplier, status, metadata) VALUES
    (
        'CBC004-1234',
        'Wireless Bluetooth Headphones - Noise Cancelling',
        'Electronics',
        'AudioTech',
        'Shenzhen Electronics Co.',
        'active',
        '{"color": "black", "weight": "250g", "warranty": "12 months", "certifications": ["CE", "FCC"]}'::jsonb
    ),
    (
        'K004-5678',
        'Stainless Steel Water Bottle 500ml',
        'Home & Kitchen',
        'EcoLife',
        'Guangzhou Home Supplies Ltd.',
        'active',
        '{"capacity": "500ml", "material": "304 stainless steel", "color_options": ["silver", "blue", "pink"], "certifications": ["FDA", "LFGB"]}'::jsonb
    )
ON CONFLICT (sku) DO NOTHING;

-- ============================================================================
-- Test Knowledge Entries
-- ============================================================================

-- Get user IDs for references
DO $$
DECLARE
    admin_id UUID;
    reviewer_id UUID;
BEGIN
    -- Get user IDs
    SELECT id INTO admin_id FROM users WHERE email = 'cbconnectbr@gmail.com';
    SELECT id INTO reviewer_id FROM users WHERE email = 'test.reviewer@example.com';

    -- Insert knowledge entries with new schema
    INSERT INTO knowledge_entries (
        sku,
        title,
        content,
        source_type,
        source_id,
        source_group,
        category,
        keywords,
        status,
        reviewed_by,
        reviewed_at,
        created_by
    ) VALUES
        -- Knowledge entries for CBC004-1234 (Wireless Bluetooth Headphones)
        (
            'CBC004-1234',
            '这款耳机的电池续航时间是多久？',
            '这款无线蓝牙耳机在充满电的情况下可以连续播放音乐约 30 小时。如果开启降噪功能，续航时间约为 20 小时。充电时间约 2 小时。',
            'feishu_chat',
            'msg_20260426_001',
            'tech_group_001',
            ARRAY['specification', 'battery'],
            ARRAY['battery', 'playtime', 'charging'],
            'approved',
            reviewer_id,
            NOW() - INTERVAL '2 days',
            admin_id
        ),
        (
            'CBC004-1234',
            '耳机无法连接蓝牙怎么办？',
            '请尝试以下步骤：
1. 确保耳机已充电并开机
2. 长按电源键 5 秒进入配对模式（指示灯快速闪烁）
3. 在手机蓝牙设置中搜索设备名称 "AudioTech-BT500"
4. 如仍无法连接，请先删除已配对记录，然后重新配对
5. 确保耳机未同时连接其他设备（最多支持 2 台设备）',
            'feishu_chat',
            'msg_20260426_002',
            'tech_group_001',
            ARRAY['troubleshooting', 'connection'],
            ARRAY['bluetooth', 'pairing', 'connection'],
            'approved',
            reviewer_id,
            NOW() - INTERVAL '1 day',
            admin_id
        ),
        (
            'CBC004-1234',
            '这款耳机支持有线连接吗？',
            '是的，这款耳机支持有线连接。包装内附带一根 3.5mm 音频线，即使在没电的情况下也可以通过有线方式继续使用。需要注意的是，有线模式下降噪功能仍需耳机有电才能使用。',
            'manual',
            'manual_20260426_001',
            NULL,
            ARRAY['faq', 'connection'],
            ARRAY['aux', 'wired', 'cable'],
            'pending',
            NULL,
            NULL,
            admin_id
        ),

        -- Knowledge entries for K004-5678 (Stainless Steel Water Bottle)
        (
            'K004-5678',
            '这款水杯的保温效果如何？',
            '这款 304 不锈钢保温杯采用双层真空设计：
- 保温时间：热水可保持 6-8 小时在 60°C 以上
- 保冷时间：冷水可保持 12-24 小时低温
- 杯口密封性好，不漏水
- 容量：500ml
- 适用温度范围：-20°C 至 100°C',
            'feishu_chat',
            'msg_20260426_003',
            'tech_group_002',
            ARRAY['specification', 'insulation'],
            ARRAY['insulation', 'temperature', 'vacuum'],
            'approved',
            reviewer_id,
            NOW() - INTERVAL '3 days',
            admin_id
        ),
        (
            'K004-5678',
            '这款水杯可以放进洗碗机吗？',
            '不建议将此水杯放入洗碗机清洗。原因如下：
1. 高温和强力清洁剂可能损坏真空层
2. 可能影响保温性能
3. 杯盖的硅胶密封圈在高温下可能变形

建议手洗方式：
- 使用温水和中性洗涤剂
- 用软毛刷清洁杯内
- 杯盖和密封圈可拆卸单独清洗
- 每次使用后及时清洗，避免异味',
            'feishu_chat',
            'msg_20260426_004',
            'tech_group_002',
            ARRAY['usage', 'maintenance'],
            ARRAY['cleaning', 'dishwasher', 'maintenance', 'care'],
            'approved',
            reviewer_id,
            NOW() - INTERVAL '5 days',
            admin_id
        );

END $$;

-- ============================================================================
-- Test Search Logs
-- ============================================================================

-- Insert some test search logs
DO $$
DECLARE
    viewer_id UUID;
    bluetooth_entry_id UUID;
BEGIN
    -- Get user and entry IDs
    SELECT id INTO viewer_id FROM users WHERE email = 'test.viewer@example.com';
    SELECT id INTO bluetooth_entry_id FROM knowledge_entries WHERE title LIKE '%蓝牙%' LIMIT 1;

    -- Insert search logs
    INSERT INTO search_logs (user_id, query, result_count, clicked_entry_id, search_type, created_at) VALUES
        (viewer_id, '蓝牙连接', 3, bluetooth_entry_id, 'keyword', NOW() - INTERVAL '1 hour'),
        (viewer_id, 'CBC004', 5, NULL, 'sku', NOW() - INTERVAL '2 hours'),
        (viewer_id, '保温', 2, NULL, 'keyword', NOW() - INTERVAL '3 hours'),
        (NULL, '耳机电池', 1, NULL, 'keyword', NOW() - INTERVAL '4 hours');

END $$;

-- ============================================================================
-- Verification Query
-- ============================================================================

-- Display summary of inserted data
SELECT
    'Users' AS table_name,
    COUNT(*)::TEXT AS record_count
FROM users

UNION ALL

SELECT
    'Products' AS table_name,
    COUNT(*)::TEXT AS record_count
FROM products

UNION ALL

SELECT
    'Knowledge Entries' AS table_name,
    COUNT(*)::TEXT AS record_count
FROM knowledge_entries

UNION ALL

SELECT
    'Search Logs' AS table_name,
    COUNT(*)::TEXT AS record_count
FROM search_logs

ORDER BY table_name;
