#!/bin/bash
# 验证批量导入系统设置

cd /Users/cindy/Projects/product-knowledge-base

echo "🔍 验证批量导入系统设置"
echo "========================================"
echo ""

# 1. 检查 Python
echo "1️⃣  检查 Python 版本..."
if /opt/homebrew/bin/python3.13 --version 2>/dev/null; then
    echo "   ✅ Python 3.13 已安装"
else
    echo "   ❌ Python 3.13 未找到"
    exit 1
fi
echo ""

# 2. 检查数据库连接
echo "2️⃣  检查数据库连接..."
if /opt/homebrew/bin/python3.13 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from scripts.utils import get_supabase_client
client = get_supabase_client()
print('   ✅ 数据库连接成功')
" 2>/dev/null; then
    :
else
    echo "   ❌ 数据库连接失败"
    exit 1
fi
echo ""

# 3. 检查 import_log 表
echo "3️⃣  检查 import_log 表..."
/opt/homebrew/bin/python3.13 << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from scripts.utils import get_supabase_client

try:
    client = get_supabase_client()
    response = client.table('import_log').select('*').limit(1).execute()
    print("   ✅ import_log 表存在")
except Exception as e:
    print(f"   ❌ import_log 表不存在或无法访问: {e}")
    sys.exit(1)
EOF
echo ""

# 4. 检查文件
echo "4️⃣  检查待导入文件..."
file_count=$(ls -1 data/duoke/汇总_*.xlsx 2>/dev/null | wc -l | tr -d ' ')
if [ $file_count -gt 0 ]; then
    echo "   ✅ 找到 $file_count 个文件"
else
    echo "   ⚠️  未找到待导入文件"
fi
echo ""

# 5. 检查脚本权限
echo "5️⃣  检查脚本可执行权限..."
for script in scripts/batch_import.sh scripts/check_progress.sh scripts/import_one.py; do
    if [ -x "$script" ] || [ "${script##*.}" = "py" ]; then
        echo "   ✅ $script"
    else
        echo "   ⚠️  $script 不可执行"
        chmod +x "$script" 2>/dev/null && echo "      已自动修复"
    fi
done
echo ""

# 6. 检查日志目录
echo "6️⃣  检查日志目录..."
if [ -d "logs" ]; then
    echo "   ✅ logs/ 目录存在"
else
    echo "   ⚠️  logs/ 目录不存在，将自动创建"
    mkdir -p logs
fi
echo ""

echo "========================================"
echo "✅ 验证完成！系统已就绪"
echo ""
echo "运行批量导入:"
echo "  caffeinate -i nohup bash scripts/batch_import.sh > import_all.log 2>&1 &"
echo ""
echo "监控进度:"
echo "  bash scripts/check_progress.sh"
