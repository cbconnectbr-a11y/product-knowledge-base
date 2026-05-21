#!/bin/bash
# 监控导入进度

PYTHON="/opt/homebrew/bin/python3.13"
DATA_DIR="data/duoke"

echo "📊 批量导入进度监控"
echo "================================"
echo ""

# 统计总文件数
total_files=$(ls -1 "$DATA_DIR"/汇总_*.xlsx 2>/dev/null | wc -l | tr -d ' ')
echo "📁 总文件数: $total_files"
echo ""

# 查询数据库状态
$PYTHON << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from scripts.utils import get_supabase_client

client = get_supabase_client()

# 统计已完成
completed_response = client.table('import_log') \
    .select('filename', count='exact') \
    .eq('status', 'completed') \
    .execute()
completed = completed_response.count if completed_response.count else 0

# 统计失败
failed_response = client.table('import_log') \
    .select('filename', count='exact') \
    .eq('status', 'failed') \
    .execute()
failed = failed_response.count if failed_response.count else 0

# 统计正在运行
running_response = client.table('import_log') \
    .select('filename', count='exact') \
    .eq('status', 'running') \
    .execute()
running_db = running_response.count if running_response.count else 0

print(f"✅ 已完成: {completed}")
print(f"❌ 已失败: {failed}")
print(f"🔄 数据库记录运行中: {running_db}")
EOF

echo ""

# 检查实际运行进程
running_processes=$(ps aux | grep "import_one.py" | grep -v grep | wc -l | tr -d ' ')
echo "🔧 实际运行进程: $running_processes"

if [ $running_processes -gt 0 ]; then
    echo ""
    echo "运行中的进程:"
    ps aux | grep "import_one.py" | grep -v grep | while read line; do
        pid=$(echo $line | awk '{print $2}')
        etime=$(ps -o etime= -p $pid 2>/dev/null | tr -d ' ')
        cmd=$(echo $line | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}')
        filename=$(echo $cmd | grep -o '汇总_[0-9_]*\.xlsx')
        echo "  - PID $pid | 运行时长: $etime | 文件: $filename"
    done
fi

echo ""

# 统计信息和预估
$PYTHON << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from scripts.utils import get_supabase_client
from datetime import datetime

client = get_supabase_client()

# 获取已完成的导入记录（带时长）
completed_response = client.table('import_log') \
    .select('started_at', 'completed_at') \
    .eq('status', 'completed') \
    .not_.is_('completed_at', 'null') \
    .execute()

if completed_response.data and len(completed_response.data) > 0:
    # 计算平均导入时长
    durations = []
    for record in completed_response.data:
        try:
            start = datetime.fromisoformat(record['started_at'])
            end = datetime.fromisoformat(record['completed_at'])
            duration = (end - start).total_seconds() / 60  # 分钟
            if duration > 0 and duration < 300:  # 排除异常值（5小时以上）
                durations.append(duration)
        except:
            continue

    if durations:
        avg_duration = sum(durations) / len(durations)
        print(f"⏱️  平均导入时长: {avg_duration:.1f} 分钟/文件")

        # 预估剩余时间
        completed_count = len(completed_response.data)
        total_files = 18  # 可以从环境变量或参数获取
        remaining = total_files - completed_count

        if remaining > 0:
            estimated_hours = (remaining * avg_duration) / 60
            if estimated_hours < 1:
                print(f"📅 预计剩余时间: {estimated_hours * 60:.0f} 分钟")
            else:
                print(f"📅 预计剩余时间: {estimated_hours:.1f} 小时")
        else:
            print(f"🎉 所有文件已处理完成!")
    else:
        print("⚠️  暂无有效的时长数据用于预估")
else:
    print("⚠️  暂无已完成的导入记录")

EOF

echo ""
echo "================================"
echo "刷新: bash scripts/check_progress.sh"
