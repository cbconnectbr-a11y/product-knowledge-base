#!/bin/bash
# 查看导入队列状态的快速脚本

cd /Users/cindy/Projects/product-knowledge-base

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 知识库导入队列状态"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 统计信息
TOTAL=$(cat data/duoke/import_queue.json | jq '.files | length')
PROCESSING=$(cat data/duoke/import_queue.json | jq '[.files[] | select(.status == "processing")] | length')
PENDING=$(cat data/duoke/import_queue.json | jq '[.files[] | select(.status == "pending")] | length')
COMPLETED=$(cat data/duoke/import_queue.json | jq '[.files[] | select(.status == "completed")] | length')
CURRENT=$(cat data/duoke/import_queue.json | jq -r '.current // "无"')

echo "总文件数: $TOTAL"
echo "🔄 处理中: $PROCESSING"
echo "⏸️  等待中: $PENDING"
echo "✅ 已完成: $COMPLETED"
echo ""
echo "当前处理: $CURRENT"
echo ""

# 检查导入进程
PROCESS_COUNT=$(ps aux | grep import_duoke_daily | grep -v grep | wc -l | tr -d ' ')
if [ "$PROCESS_COUNT" -gt 0 ]; then
    echo "导入进程: ✅ 运行中"
    ps aux | grep import_duoke_daily | grep -v grep | awk '{print "  PID: " $2 "  运行时间: " $10}'
else
    echo "导入进程: ⚠️  未运行"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 文件列表："
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat data/duoke/import_queue.json | jq -r '.files[] | "\(.status | if . == "processing" then "🔄" elif . == "pending" then "⏸️" elif . == "completed" then "✅" else "❓" end) \(.filename)"'

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏱️  预计完成时间: $(date -v+24H '+%Y-%m-%d %H:%M') (约24-48小时)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
