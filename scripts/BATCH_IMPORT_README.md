# 批量导入使用指南

## 快速开始

### 1. 运行批量导入（防休眠）

```bash
cd /Users/cindy/Projects/product-knowledge-base
caffeinate -i nohup bash scripts/batch_import.sh > import_all.log 2>&1 &
```

**说明:**
- `caffeinate -i`: 防止 Mac 进入休眠
- `nohup`: 忽略挂断信号，脚本继续运行
- `&`: 后台运行
- `import_all.log`: 总日志文件

### 2. 监控进度

```bash
# 查看实时进度
bash scripts/check_progress.sh

# 查看总日志
tail -f import_all.log

# 查看某个文件的详细日志
tail -f logs/汇总_20260312_0600.log
```

### 3. 检查结果

导入完成后，查看失败文件列表:

```bash
cat failed_files.txt
```

## 特性

✅ **并行处理**: 同时导入 3 个文件  
✅ **失败隔离**: 单个文件失败不影响其他  
✅ **跳过已完成**: 启动时一次性查询数据库，过滤已完成文件（无竞态条件）  
✅ **进度日志**: 实时记录每个文件的处理状态  
✅ **失败追踪**: 失败文件自动记录到 `failed_files.txt`  
✅ **总结报告**: 完成后显示成功/失败/跳过统计  
✅ **import_log 追踪**: 每个文件导入状态自动记录到数据库  

## 文件结构

```
scripts/
├── batch_import.sh          # 主批量导入脚本
├── import_one.py            # 单文件导入脚本（带进度和日志）
├── check_progress.sh        # 进度监控脚本
└── BATCH_IMPORT_README.md   # 本文档

logs/                        # 每个文件的详细日志
├── 汇总_20260312_0600.log
├── 汇总_20260313_0800.log
└── ...

failed_files.txt             # 失败文件列表
import_all.log               # 总日志
```

## 数据库追踪

导入过程自动记录到 `import_log` 表:

| 字段 | 说明 |
|------|------|
| `filename` | 文件名 |
| `status` | 状态: running / completed / failed |
| `started_at` | 开始时间 |
| `completed_at` | 完成时间 |
| `total_rows` | 总行数 |
| `imported_rows` | 新增行数 |
| `skipped_rows` | 跳过行数 |
| `error_rows` | 错误行数 |
| `error_msg` | 错误信息（如果失败） |

## 常见操作

### 停止批量导入

```bash
# 查找进程
ps aux | grep batch_import.sh

# 终止进程
kill [PID]
```

### 重新导入失败文件

```bash
# 查看失败列表
cat failed_files.txt

# 手动导入单个文件
/opt/homebrew/bin/python3.13 scripts/import_one.py data/duoke/汇总_20260312_0600.xlsx

# 或修复问题后重新运行批量导入（会自动跳过已完成的）
caffeinate -i nohup bash scripts/batch_import.sh > import_all.log 2>&1 &
```

### 清理日志

```bash
# 清理所有日志文件
rm -f logs/*.log import_all.log failed_files.txt

# 或按日期归档
mkdir -p logs/archive/$(date +%Y%m%d)
mv logs/*.log logs/archive/$(date +%Y%m%d)/
```

## 性能参考

- **并行度**: 3 个文件同时处理
- **导入速度**: ~35 条/分钟
- **单文件时长**: 
  - 小文件 (900 行): ~25 分钟
  - 中文件 (1500 行): ~45 分钟
  - 大文件 (3000 行): ~90 分钟
- **18 个文件总时长**: 预计 6-8 小时

## 故障排查

### 进程卡住

```bash
# 检查运行时长
ps -o etime,pid,command | grep import_one.py

# 如果超过 3 小时无响应，终止进程
kill -9 [PID]

# 批量导入会自动继续处理下一个文件
```

### 内存占用过高

```bash
# 检查内存
ps aux | grep import_one.py | awk '{print $4, $11}'

# 正常内存占用: ~50-100 MB
# 如果超过 500 MB，可能有问题
```

### 数据库连接失败

```bash
# 测试数据库连接
/opt/homebrew/bin/python3.13 -c "
from scripts.utils import get_supabase_client
client = get_supabase_client()
print('✅ 数据库连接成功')
"
```

## 与队列系统的区别

| 特性 | 队列系统 | 批量导入脚本 |
|------|----------|--------------|
| 并发控制 | 自动单进程 | Bash xargs -P 3 |
| 失败处理 | 自动重试 | 记录到 failed_files.txt |
| 进度追踪 | 队列 JSON | 数据库 import_log 表 |
| 日志记录 | 统一 bot.log | 每文件独立日志 |
| 使用场景 | 自动文件监听 | 手动批量导入 |

## 注意事项

⚠️ **不要同时运行多个 batch_import.sh 实例** - 会导致并发冲突  
⚠️ **确保 caffeinate 在前台** - Mac 休眠会中断导入  
⚠️ **定期检查 failed_files.txt** - 及时处理失败文件  
⚠️ **导入完成后检查数据库** - 验证记录数是否正确
