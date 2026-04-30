# Phase 2 Task 3: 导入状态通知优化（修订版）

**基于审查反馈的最终设计方案**

## 审查反馈总结

### 1. 通知内容调整
- ❌ 删除"可用操作"部分
- ✅ 加入"对比上次"耗时差值
- ✅ 错误为 0 时不显示该行

### 2. 发送目标分级
- 正常完成 → 群聊
- 部分失败 → 群聊 + @个人
- 完全失败 → 私聊个人（优先）

### 3. 统计数据优化
- ✅ 增加: 跳过原因 Top 3
- ✅ 增加: 文件行数
- ✅ 修改: "SKU成功率" → "SKU缺失: X条"

### 4. 自动重试机制
- 网络/数据库错误 → 重试 3 次，指数退避（30s/2min/5min）
- 数据格式错误 → 不重试，直接通知
- 部分导入数据保留，标记 `import_status: 'partial'`

### 5. 配置需求
- 获取群聊 ID（机器人临时打印）
- 支持多目标（主群/个人/备用群）
- 环境变量配置

### 6. 历史统计
- JSON 文件: `stats_YYYY-MM-DD_xxx.json`
- 添加到 `.gitignore`
- 命令行汇总工具
- Web 界面留给任务 4

## 修订后的通知格式

### 正常完成（发送到群聊）

```
✅ 导入完成：汇总_20260415_0800.xlsx

📊 导入统计
   文件行数: 3,152 行
   新增: 2,847 条
   跳过: 305 条（重复）
   
📋 跳过原因 Top 3
   1. 重复记录: 285 条
   2. 空内容: 15 条
   3. SKU 缺失: 5 条

⏱️ 耗时统计
   开始: 2026-04-30 08:00:00
   完成: 2026-04-30 09:28:15
   耗时: 1小时28分15秒
   速度: 36 条/分钟
   📈 比上次快 12%

📈 数据质量
   SKU 缺失: 47 条
   有效对话: 2,847 条
```

### 部分失败（群聊 + @个人）

```
⚠️ 导入部分失败：汇总_20260415_0800.xlsx

@ou_xxx (Cindy)

📊 导入统计
   文件行数: 3,152 行
   已导入: 1,234 条
   失败位置: 第 1,235 行
   错误数: 15 条

⚠️ 错误原因
   类型: DatabaseConnectionError
   详情: Connection timeout after 30s
   
🔄 自动重试
   已重试: 3 次
   状态: 已放弃，需人工处理

📋 跳过原因 Top 3
   1. 重复记录: 125 条
   2. 空内容: 8 条
   3. 格式错误: 7 条

⏱️ 耗时统计
   开始: 2026-04-30 08:00:00
   失败: 2026-04-30 08:45:20
   已耗时: 45分20秒

💾 数据状态
   已导入数据已保留 (标记: partial)
   断点位置: 第 1,235 行
   
🔧 建议操作
   1. 检查数据库连接: scripts/utils.py
   2. 修复后重新上传文件（会跳过已导入）
   3. 查看详细日志: tail -100 /tmp/bot.log
```

### 完全失败（私聊个人）

```
❌ 导入失败：汇总_20260415_0800.xlsx

⚠️ 错误信息
   类型: FileFormatError
   详情: Excel 文件格式不正确，缺少必需列"与买家沟通消息"
   
📊 导入统计
   文件行数: 未能读取
   已导入: 0 条
   
🔧 建议操作
   1. 检查文件格式是否正确
   2. 确认列名是否匹配
   3. 参考正确格式: data/duoke/archive/汇总_20260428_0800.xlsx
   4. 修复后重新上传

⏱️ 耗时统计
   开始: 2026-04-30 08:00:00
   失败: 2026-04-30 08:00:15
   已耗时: 15秒

💡 提示
   数据格式错误不会自动重试，请修复文件后重新上传
```

## 技术实现细节

### 1. 统计数据结构（修订）

```python
class ImportStats:
    """导入统计数据"""
    def __init__(self):
        self.file_name = ''
        self.start_time = None
        self.end_time = None
        self.file_rows = 0          # 新增: 文件总行数
        self.total_rows = 0         # 处理的行数
        self.imported = 0
        self.skipped = 0
        self.errors = 0
        self.error_type = None      # 新增: 错误类型
        self.error_message = ''     # 新增: 错误消息
        self.retry_count = 0        # 新增: 重试次数
        self.import_status = 'completed'  # completed | partial | failed
        self.break_point = None     # 新增: 断点行号
        
        # 跳过原因统计
        self.skip_reasons = {}      # 新增: {'重复记录': 285, '空内容': 15, ...}
        
        # SKU 统计
        self.sku_missing = 0        # 新增: SKU 缺失数量
        
        # 性能对比
        self.previous_duration = None  # 新增: 上次耗时（用于对比）
        
    def add_skip_reason(self, reason: str):
        """记录跳过原因"""
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1
    
    def get_skip_reasons_top3(self) -> list:
        """获取跳过原因 Top 3"""
        sorted_reasons = sorted(
            self.skip_reasons.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_reasons[:3]
    
    def calculate_improvement(self) -> Optional[float]:
        """计算相比上次的性能提升"""
        if not self.previous_duration:
            return None
        
        current = (self.end_time - self.start_time).total_seconds()
        improvement = (self.previous_duration - current) / self.previous_duration * 100
        return improvement
```

### 2. 导入脚本修改（修订）

```python
def import_duoke_file(file_path: Path) -> ImportStats:
    """导入文件并返回统计信息"""
    stats = ImportStats()
    stats.file_name = file_path.name
    stats.start_time = datetime.now()
    
    # 加载上次统计（用于性能对比）
    stats.previous_duration = load_previous_duration(file_path.stem)
    
    try:
        # 读取 Excel
        df = pd.read_excel(file_path, header=2)
        stats.file_rows = len(df)  # 记录文件行数
        
        logger.info(f"文件包含 {stats.file_rows} 条记录")
        
        for idx, row in df.iterrows():
            stats.total_rows += 1
            
            try:
                # 跳过空行
                if pd.isna(row.get('与买家沟通消息')):
                    stats.skipped += 1
                    stats.add_skip_reason('空内容')
                    continue
                
                # 处理记录
                entry = process_duoke_record(row, file_date)
                
                # 统计 SKU 缺失
                if not entry['sku']:
                    stats.sku_missing += 1
                
                # 检查重复
                if check_duplicate(client, entry):
                    stats.skipped += 1
                    stats.add_skip_reason('重复记录')
                    continue
                
                # 插入数据库
                response = client.table('knowledge_entries').insert(entry).execute()
                
                if response.data:
                    stats.imported += 1
                    
            except Exception as e:
                stats.errors += 1
                stats.break_point = idx + 3  # Excel 行号（header=2）
                logger.error(f"处理第 {idx+3} 行失败: {e}")
                
                # 判断错误类型
                if 'connection' in str(e).lower() or 'timeout' in str(e).lower():
                    stats.error_type = 'DatabaseConnectionError'
                    stats.error_message = str(e)
                    raise  # 抛出以触发重试
                else:
                    stats.add_skip_reason('格式错误')
                    continue
        
        # 正常完成
        stats.end_time = datetime.now()
        stats.import_status = 'completed'
        return stats
        
    except Exception as e:
        stats.end_time = datetime.now()
        
        # 判断是部分失败还是完全失败
        if stats.imported > 0:
            stats.import_status = 'partial'
        else:
            stats.import_status = 'failed'
        
        stats.error_type = type(e).__name__
        stats.error_message = str(e)
        
        return stats

def load_previous_duration(file_stem: str) -> Optional[float]:
    """加载上次导入的耗时（用于对比）"""
    stats_dir = Path('data/duoke/stats')
    pattern = f"stats_*_{file_stem.split('_')[1]}_*.json"  # 匹配相同日期
    
    stats_files = sorted(stats_dir.glob(pattern))
    if len(stats_files) < 2:
        return None
    
    # 获取倒数第二个文件（上次的统计）
    prev_stats_file = stats_files[-2]
    
    try:
        with open(prev_stats_file, 'r', encoding='utf-8') as f:
            prev_stats = json.load(f)
            return prev_stats.get('duration_seconds')
    except:
        return None
```

### 3. 自动重试机制

```python
def import_with_retry(file_path: Path, max_retries: int = 3) -> ImportStats:
    """
    带重试的导入
    
    Args:
        file_path: 文件路径
        max_retries: 最大重试次数
        
    Returns:
        ImportStats: 导入统计
    """
    retry_delays = [30, 120, 300]  # 30s, 2min, 5min
    
    for attempt in range(max_retries + 1):
        stats = import_duoke_file(file_path)
        
        # 成功或数据格式错误（不重试）
        if stats.import_status == 'completed':
            return stats
        
        if stats.error_type and 'Format' in stats.error_type:
            logger.info(f"数据格式错误，不重试")
            return stats
        
        # 网络或数据库错误，重试
        if attempt < max_retries:
            stats.retry_count = attempt + 1
            delay = retry_delays[attempt]
            logger.warning(f"导入失败，{delay}秒后重试 ({attempt + 1}/{max_retries})...")
            time.sleep(delay)
        else:
            logger.error(f"已达最大重试次数，放弃")
            stats.retry_count = max_retries
            return stats
    
    return stats
```

### 4. 通知发送逻辑（修订）

```python
def send_import_notification(stats: Dict, user_id: Optional[str] = None):
    """
    根据导入状态发送分级通知
    
    Args:
        stats: 导入统计数据
        user_id: 用户 ID（用于 @ 或私聊）
    """
    import_status = stats.get('import_status', 'completed')
    
    if import_status == 'completed':
        # 正常完成 → 发送到群聊
        message = format_success_notification(stats)
        send_to_group(message)
        
    elif import_status == 'partial':
        # 部分失败 → 群聊 + @个人
        message = format_partial_failure_notification(stats, user_id)
        send_to_group(message)
        
    elif import_status == 'failed':
        # 完全失败 → 私聊个人（优先）
        message = format_failure_notification(stats)
        if user_id:
            send_to_user(user_id, message)
        else:
            send_to_group(message)  # 兜底

def format_success_notification(stats: Dict) -> str:
    """格式化成功通知"""
    filename = stats['file_name']
    file_rows = stats['file_rows']
    imported = stats['imported']
    skipped = stats['skipped']
    
    # 跳过原因 Top 3
    skip_reasons = stats.get('skip_reasons_top3', [])
    skip_text = '\n'.join([
        f"   {i+1}. {reason}: {count} 条"
        for i, (reason, count) in enumerate(skip_reasons)
    ])
    
    # 耗时对比
    duration = stats['duration_formatted']
    speed = stats['speed']
    improvement = stats.get('improvement_percent')
    improvement_text = ''
    if improvement is not None:
        if improvement > 0:
            improvement_text = f"\n   📈 比上次快 {improvement:.1f}%"
        else:
            improvement_text = f"\n   📉 比上次慢 {abs(improvement):.1f}%"
    
    # SKU 缺失
    sku_missing = stats.get('sku_missing', 0)
    
    # 错误行（仅当有错误时显示）
    error_text = ''
    errors = stats.get('errors', 0)
    if errors > 0:
        error_text = f"   错误: {errors} 条\n"
    
    message = f"""✅ 导入完成：{filename}

📊 导入统计
   文件行数: {file_rows:,} 行
   新增: {imported:,} 条
   跳过: {skipped:,} 条
{error_text}
📋 跳过原因 Top 3
{skip_text}

⏱️ 耗时统计
   耗时: {duration}
   速度: {speed:.1f} 条/分钟{improvement_text}

📈 数据质量
   SKU 缺失: {sku_missing} 条
   有效对话: {imported:,} 条
"""
    return message
```

### 5. 配置管理

**环境变量:**
```bash
# .env

# 通知目标
NOTIFICATION_GROUP_ID=oc_xxx          # 主群聊 ID
NOTIFICATION_USER_ID=ou_xxx           # 个人用户 ID (Cindy)
NOTIFICATION_BACKUP_GROUP_ID=oc_yyy  # 备用群聊 ID（可选）
```

**获取 ID 的工具:**
```python
# bot/config.py

def enable_id_logging():
    """临时启用 ID 打印（用于配置）"""
    logger.info("=" * 60)
    logger.info("ID 日志模式已启用")
    logger.info("=" * 60)

# bot/main.py

def handle_message_event(event_data: dict):
    # ... 现有代码 ...
    
    # 临时: 打印 ID 信息
    if os.environ.get('ENABLE_ID_LOGGING') == 'true':
        logger.info(f"[ID] chat_id: {chat_id}")
        logger.info(f"[ID] sender_id: {sender_id}")
        logger.info(f"[ID] receive_id: {receive_id}")
```

### 6. 历史统计管理

**文件命名规则:**
```
data/duoke/stats/
  ├─ stats_2026-04-30_汇总_20260312_0600.json
  ├─ stats_2026-04-30_汇总_20260313_0600.json
  └─ ...
```

**命令行汇总工具:**
```python
# scripts/stats_summary.py

def generate_summary(date_range: Optional[str] = None):
    """
    生成统计汇总报告
    
    Args:
        date_range: 日期范围，如 "2026-04-01:2026-04-30" 或 None（全部）
    """
    stats_dir = Path('data/duoke/stats')
    
    # 读取所有统计文件
    all_stats = []
    for stats_file in stats_dir.glob('stats_*.json'):
        with open(stats_file, 'r') as f:
            all_stats.append(json.load(f))
    
    # 过滤日期范围
    if date_range:
        start, end = date_range.split(':')
        all_stats = [s for s in all_stats if start <= s['start_time'][:10] <= end]
    
    # 汇总统计
    total_files = len(all_stats)
    total_imported = sum(s['imported'] for s in all_stats)
    total_skipped = sum(s['skipped'] for s in all_stats)
    total_errors = sum(s['errors'] for s in all_stats)
    avg_speed = sum(s['speed'] for s in all_stats) / total_files if total_files > 0 else 0
    
    # 成功率
    success_count = sum(1 for s in all_stats if s['import_status'] == 'completed')
    success_rate = success_count / total_files * 100 if total_files > 0 else 0
    
    # 打印报告
    print(f"""
📊 导入统计汇总报告
{'=' * 60}

📅 统计周期: {date_range or '全部'}
📁 文件数量: {total_files} 个

📊 导入统计
   总导入: {total_imported:,} 条
   总跳过: {total_skipped:,} 条
   总错误: {total_errors} 条

📈 性能统计
   平均速度: {avg_speed:.1f} 条/分钟
   成功率: {success_rate:.1f}%
   
🏆 最快导入: {max(all_stats, key=lambda s: s['speed'])['file_name']}
   速度: {max(all_stats, key=lambda s: s['speed'])['speed']:.1f} 条/分钟
""")

# 使用方法:
# python3.13 scripts/stats_summary.py
# python3.13 scripts/stats_summary.py --range 2026-04-01:2026-04-30
```

**.gitignore 更新:**
```bash
# Data files
data/duoke/*.xlsx
data/duoke/archive/*.xlsx
data/duoke/import_queue.json
data/duoke/stats/*.json    # 新增
.env.backup
```

## 实施计划

### 明天（2026-05-01）10:00 - 队列完成后

**Step 1: 环境准备（10:00 - 10:15）**
- [ ] 运行 checkpoint 保存当前状态
- [ ] 创建新分支: `git checkout -b feature/import-notification`
- [ ] 启用 ID 日志获取配置
- [ ] 更新 `.gitignore`

**Step 2: 导入脚本修改（10:15 - 12:00）**
- [ ] 添加 `ImportStats` 类（修订版）
- [ ] 修改 `import_duoke_file()` 收集统计
- [ ] 实现跳过原因统计
- [ ] 实现性能对比逻辑
- [ ] 实现自动重试机制
- [ ] 测试统计收集功能

**Step 3: 通知模块开发（13:00 - 15:00）**
- [ ] 创建 `bot/notification.py`
- [ ] 实现分级通知逻辑
- [ ] 实现通知格式化函数（3种）
- [ ] 配置环境变量
- [ ] 测试消息发送

**Step 4: 队列管理器集成（15:00 - 16:30）**
- [ ] 更新 `bot/queue_manager.py`
- [ ] 添加完成检测逻辑
- [ ] 集成通知发送
- [ ] 处理重试逻辑

**Step 5: 命令行工具开发（16:30 - 17:00）**
- [ ] 创建 `scripts/stats_summary.py`
- [ ] 实现汇总报告功能
- [ ] 测试报告生成

**Step 6: 测试验证（17:00 - 18:00）**
- [ ] 测试成功通知
- [ ] 测试部分失败通知
- [ ] 测试完全失败通知
- [ ] 测试重试机制
- [ ] 测试性能对比
- [ ] 验证不影响现有流程

**Step 7: 文档和 Checkpoint（18:00 - 18:30）**
- [ ] 更新使用文档
- [ ] 合并到 master
- [ ] 运行 checkpoint: "完成任务3 - 导入状态通知系统"

## 预期成果

**功能完成度:**
- ✅ 导入完成自动通知
- ✅ 详细统计信息
- ✅ 分级通知发送
- ✅ 自动重试机制
- ✅ 历史统计管理
- ✅ 命令行汇总工具

**用户体验:**
- ✅ 清楚了解每次导入结果
- ✅ 快速发现和处理问题
- ✅ 性能趋势可视化
- ✅ 无需手动检查状态

---

**文档版本**: 2.0 (修订版)
**创建时间**: 2026-04-30
**审查状态**: ✅ 已通过
**实施时间**: 2026-05-01 10:00
**预计完成**: 2026-05-01 18:00
