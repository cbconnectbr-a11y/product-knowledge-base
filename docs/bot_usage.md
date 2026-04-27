# 飞书机器人使用指南

## 快速启动

### 1. 配置环境变量

确保 `.env` 文件包含以下配置：

```bash
# Supabase 配置
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# 飞书配置
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_VERIFICATION_TOKEN=your_verification_token
FEISHU_ENCRYPT_KEY=your_encrypt_key  # 可选

# 服务配置（可选）
PORT=5000
DEBUG=False
```

### 2. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 3. 启动服务

```bash
# 开发环境
python3 -m bot.main

# 或使用环境变量
PORT=8080 python3 -m bot.main

# 生产环境（推荐使用 Gunicorn）
gunicorn -w 4 -b 0.0.0.0:5000 bot.main:app
```

### 4. 配置飞书 Webhook

在飞书开放平台配置：

1. 进入应用管理 → 事件订阅
2. 配置 Webhook URL: `https://your-domain.com/webhook`
3. 订阅事件类型: `im.message.receive_v1`
4. 保存并验证 URL

## 支持的命令

### 1. /search - 关键词搜索

搜索产品相关问题和解决方案

```
/search 加热杯不加热
/search 漏水
```

### 2. /sku - SKU 精确搜索

查询指定 SKU 的相关知识

```
/sku CBC004-1234
/sku BRME0341
```

### 3. /help - 帮助信息

显示机器人使用帮助

```
/help
```

### 4. 智能搜索（无需命令）

直接发送消息即可搜索，机器人会自动识别：

```
CBC004-1234 不加热  → 自动识别为 SKU 搜索
加热杯漏水怎么办   → 关键词搜索
```

## API 端点

### GET /health

健康检查端点

**响应:**
```json
{
  "status": "healthy",
  "service": "product-knowledge-base-bot",
  "version": "1.0.0"
}
```

**使用场景:**
- 监控服务状态
- 负载均衡健康检查

### POST /webhook

飞书事件 Webhook 端点

**事件类型:**
1. `url_verification` - URL 验证
2. `im.message.receive_v1` - 接收消息

## 架构说明

### 消息处理流程

```
飞书用户发送消息
    ↓
飞书服务器 → POST /webhook
    ↓
bot.main.webhook()
    ↓
handle_message_event()
    ↓
handlers.handle_message()
    ↓
parse_command() → smart_search()
    ↓
formatters.format_search_results()
    ↓
send_reply() → 飞书用户收到回复
    ↓
log_search() → Supabase (异步)
```

### 模块说明

**bot/formatters.py**
- 格式化消息内容
- 生成搜索结果卡片
- 错误消息格式化

**bot/handlers.py**
- 解析用户命令
- 调用搜索逻辑
- 记录搜索日志

**bot/main.py**
- Flask Web 服务
- Webhook 事件处理
- 飞书 SDK 集成

**bot/search.py** (已有)
- SKU 精确搜索
- 关键词全文搜索
- 智能搜索策略

## 测试

### 运行集成测试

```bash
# 测试命令解析和消息格式化
python tests/test_bot_integration.py

# 测试 Flask 端点
python tests/test_flask_app.py
```

### 手动测试

1. 启动服务
2. 使用 curl 测试健康检查:
   ```bash
   curl http://localhost:5000/health
   ```
3. 测试 URL 验证:
   ```bash
   curl -X POST http://localhost:5000/webhook \
     -H "Content-Type: application/json" \
     -d '{"type":"url_verification","challenge":"test123","token":"your_token"}'
   ```

## 日志

日志级别: INFO (默认)

**日志内容:**
- 接收到的事件类型
- 解析的命令和参数
- 搜索查询和结果数量
- 消息发送状态
- 错误和异常信息

**示例:**
```
2026-04-27 10:30:00,123 - __main__ - INFO - Received webhook event: im.message.receive_v1
2026-04-27 10:30:00,234 - __main__ - INFO - Parsed command: search, argument: 加热杯, user: ou_xxx
2026-04-27 10:30:00,345 - __main__ - INFO - Search logged: query='加热杯', type=keyword, results=3
2026-04-27 10:30:00,456 - __main__ - INFO - Reply sent successfully to user ou_xxx
```

## 故障排查

### 1. 机器人无响应

**检查:**
- Flask 服务是否运行
- Webhook URL 是否配置正确
- 飞书事件订阅是否启用
- 网络是否可达

**查看日志:**
```bash
tail -f logs/app.log
```

### 2. Token 验证失败

**错误:** `Invalid verification token`

**解决:**
- 检查 `.env` 中的 `FEISHU_VERIFICATION_TOKEN`
- 确保与飞书开放平台配置一致

### 3. 数据库连接失败

**错误:** `Missing required environment variables: SUPABASE_URL and SUPABASE_KEY`

**解决:**
- 检查 `.env` 文件是否存在
- 验证 Supabase 凭证是否正确

### 4. 消息发送失败

**错误:** `Feishu API error: xxx`

**解决:**
- 检查 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`
- 确认应用有发送消息权限
- 查看飞书开放平台日志

## 生产环境部署

### 1. 使用 Gunicorn

```bash
# 安装 Gunicorn
pip3 install gunicorn

# 启动服务 (4个 worker)
gunicorn -w 4 -b 0.0.0.0:5000 bot.main:app

# 或使用配置文件
gunicorn -c gunicorn.conf.py bot.main:app
```

**gunicorn.conf.py 示例:**
```python
bind = "0.0.0.0:5000"
workers = 4
worker_class = "sync"
timeout = 30
keepalive = 2
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"
```

### 2. 使用 systemd (Linux)

创建服务文件: `/etc/systemd/system/kb-bot.service`

```ini
[Unit]
Description=Product Knowledge Base Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/product-knowledge-base
Environment="PATH=/usr/local/bin"
ExecStart=/usr/local/bin/gunicorn -w 4 -b 0.0.0.0:5000 bot.main:app
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务:
```bash
sudo systemctl daemon-reload
sudo systemctl enable kb-bot
sudo systemctl start kb-bot
sudo systemctl status kb-bot
```

### 3. 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 4. HTTPS 配置

推荐使用 Let's Encrypt + Certbot:

```bash
sudo certbot --nginx -d your-domain.com
```

## 监控建议

1. **健康检查**
   - 使用 `/health` 端点
   - 配置负载均衡器健康检查
   - 设置告警（服务不可用时）

2. **日志监控**
   - 监控错误日志数量
   - 跟踪响应时间
   - 分析搜索查询模式

3. **数据库监控**
   - 查询性能
   - 连接池使用情况
   - search_logs 表增长

## 下一步优化 (Phase 2)

- [ ] 富文本卡片消息
- [ ] AI 智能问答
- [ ] 快速回复按钮
- [ ] 消息队列异步处理
- [ ] Redis 缓存
- [ ] 事件去重机制
- [ ] 用户 ID 映射

---

**版本:** 1.0.0 (Phase 1 MVP)
**更新日期:** 2026-04-27
