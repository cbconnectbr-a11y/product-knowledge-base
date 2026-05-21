#!/bin/bash
# 批量导入多客汇总文件 - 健壮版
# 特性: 并行3个文件 | 失败隔离 | 跳过已完成 | 进度日志 | 失败列表 | 总结报告

set -e

# 配置
PARALLEL_JOBS=3
DATA_DIR="data/duoke"
PYTHON="/opt/homebrew/bin/python3.13"
IMPORT_SCRIPT="scripts/import_one.py"
FAILED_LIST="failed_files.txt"
LOG_DIR="logs"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 初始化失败列表
> "$FAILED_LIST"

# 统计变量文件
STATS_FILE="/tmp/import_stats_$$"
echo "0" > "${STATS_FILE}.success"
echo "0" > "${STATS_FILE}.failed"
echo "0" > "${STATS_FILE}.skipped"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 获取已完成文件列表（在主进程执行一次，避免并发竞态）
get_completed_files() {
    $PYTHON << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from scripts.utils import get_supabase_client

try:
    client = get_supabase_client()
    response = client.table('import_log') \
        .select('filename') \
        .eq('status', 'completed') \
        .execute()

    if response.data:
        for record in response.data:
            print(record['filename'])
except:
    # 如果表不存在或查询失败，返回空（所有文件都需要导入）
    pass
EOF
}

# 导入单个文件的包装函数
import_file() {
    local filepath="$1"
    local filename=$(basename "$filepath")
    local logfile="$LOG_DIR/${filename%.xlsx}.log"

    log "开始处理: $filename"

    # 执行导入
    if $PYTHON "$IMPORT_SCRIPT" "$filepath" > "$logfile" 2>&1; then
        log "✅ 成功: $filename"
        local success=$(cat "${STATS_FILE}.success")
        echo $((success + 1)) > "${STATS_FILE}.success"
        return 0
    else
        log "❌ 失败: $filename (查看日志: $logfile)"
        echo "$filepath" >> "$FAILED_LIST"
        local failed=$(cat "${STATS_FILE}.failed")
        echo $((failed + 1)) > "${STATS_FILE}.failed"
        return 1
    fi
}

# 导出函数供 xargs 使用
export -f import_file
export -f log
export PYTHON
export IMPORT_SCRIPT
export LOG_DIR
export FAILED_LIST
export STATS_FILE

# 主流程
main() {
    log "=========================================="
    log "批量导入开始"
    log "=========================================="
    log "数据目录: $DATA_DIR"
    log "并行度: $PARALLEL_JOBS"
    log "失败列表: $FAILED_LIST"
    log ""

    # 获取所有 Excel 文件
    local all_files=($DATA_DIR/汇总_*.xlsx)
    local total_found=${#all_files[@]}
    log "找到 $total_found 个文件"

    # 获取已完成文件列表
    log "检查已完成文件..."
    local completed_files=$(get_completed_files)

    # 过滤出需要导入的文件
    local files_to_import=()
    local skipped_count=0

    for filepath in "${all_files[@]}"; do
        local filename=$(basename "$filepath")
        if echo "$completed_files" | grep -q "^${filename}$"; then
            log "⏭️  跳过 (已完成): $filename"
            skipped_count=$((skipped_count + 1))
        else
            files_to_import+=("$filepath")
        fi
    done

    # 更新跳过计数
    echo "$skipped_count" > "${STATS_FILE}.skipped"

    local to_import=${#files_to_import[@]}
    log ""
    log "需要导入: $to_import 个文件"
    log "已跳过: $skipped_count 个文件"
    log ""

    if [ $to_import -eq 0 ]; then
        log "🎉 所有文件都已完成，无需导入"
        return 0
    fi

    # 开始时间
    local start_time=$(date +%s)

    # 使用 xargs 并行处理（只处理需要导入的文件）
    printf '%s\n' "${files_to_import[@]}" | \
        xargs -P $PARALLEL_JOBS -I {} bash -c 'import_file "$@"' _ {}

    # 结束时间
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))

    # 读取统计
    local success=$(cat "${STATS_FILE}.success")
    local failed=$(cat "${STATS_FILE}.failed")
    local skipped=$(cat "${STATS_FILE}.skipped")

    # 清理临时文件
    rm -f "${STATS_FILE}".{success,failed,skipped}

    # 打印总结报告
    log ""
    log "=========================================="
    log "批量导入完成"
    log "=========================================="
    log "总文件数: $total_found"
    log "✅ 成功: $success"
    log "❌ 失败: $failed"
    log "⏭️  跳过: $skipped"
    log "⏱️  总耗时: ${hours}小时${minutes}分${seconds}秒"
    log ""

    if [ $failed -gt 0 ]; then
        log "失败的文件列表:"
        cat "$FAILED_LIST" | while read file; do
            log "  - $(basename $file)"
        done
        log ""
        log "查看失败详情: ls -lh $LOG_DIR/"
    else
        log "🎉 所有文件导入成功!"
    fi

    log "=========================================="
}

# 运行主流程
main
