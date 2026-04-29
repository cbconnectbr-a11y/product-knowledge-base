#!/bin/bash
# 用法: ./.claude/checkpoint.sh "这次做了什么的简短描述"

set -e

MESSAGE="${1:-checkpoint}"
DATE=$(date +"%Y-%m-%d %H:%M")
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# 1. 更新进度文档
cat > PROGRESS.md << EOF
# 项目进度

**最后更新**: $DATE
**当前分支**: $BRANCH
**最近改动**: $MESSAGE

## 当前状态
$(git status --short)

## 最近 10 次提交
$(git log --oneline -10)

## 待办事项
<!-- Claude 会在这里更新 -->

## 关键文件位置
- 数据目录: \`data/duoke/\`
- 导入队列: \`data/duoke/import_queue.json\`
- 机器人服务: \`bot/main.py\` (Port 5001)
- 队列管理: \`bot/queue_manager.py\`
- 导入脚本: \`scripts/import_duoke_daily.py\`
- 日志文件: \`/tmp/bot.log\`

## 下次继续的入口
<!-- Claude 重启后从这里读取上下文 -->
EOF

# 2. 提交并推送
git add -A
git commit -m "checkpoint: $MESSAGE" || echo "没有改动需要提交"
git push origin "$BRANCH"

echo "✅ 检查点已保存到 GitHub"
echo "📄 进度文档: PROGRESS.md"
