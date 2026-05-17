# 飞书Webhook自动文件导入配置指南

## 问题现象

群里上传Excel文件后，机器人没有自动下载和导入。

## 根本原因

飞书开放平台的事件订阅配置不完整，机器人没有收到文件上传事件。

---

## 配置步骤

### 1. 登录飞书开放平台

访问：https://open.feishu.cn/app

### 2. 找到你的应用

**应用名称：** 知识问答机器人  
**App ID：** `cli_***`（在.env文件中的FEISHU_APP_ID）

### 3. 配置事件订阅 ⭐

#### 3.1 进入事件订阅页面

左侧菜单：**开发配置 > 事件订阅**

#### 3.2 配置请求网址

**请求网址（Request URL）：**
```
https://gripier-jonas-wannest.ngrok-free.dev/webhook
```

**说明：** 这是你的ngrok隧道地址 + `/webhook` 路径

#### 3.3 订阅事件

点击 **"添加事件"** 按钮，搜索并添加以下事件：

##### ✅ 必需事件

1. **接收消息 v2.0**
   - 事件名称：`im.message.receive_v1`
   - 权限：读取用户发送的消息
   - **用途：** 接收文本消息和文件消息

**重要：** 这个事件会同时包含文本消息和文件消息！

##### 📋 事件配置截图参考

```
事件名称：接收消息 v2.0
事件 ID： im.message.receive_v1
版本：    v1
状态：    ✅ 已启用
```

#### 3.4 验证配置

1. 点击 **"保存"** 按钮
2. 飞书会向你的webhook发送验证请求
3. 如果配置正确，状态会显示 ✅ **已验证**

### 4. 配置权限 ⭐

#### 4.1 进入权限管理

左侧菜单：**开发配置 > 权限管理**

#### 4.2 确保以下权限已开启

##### 消息与群组权限

- ✅ **获取与发送单聊、群组消息**
  - `im:message`
  - `im:message:send_as_bot`

- ✅ **读取用户发送给机器人的单聊消息**
  - `im:message:read_user`

- ✅ **获取群组中所有消息**
  - `im:message:group`

- ✅ **以应用身份读取群组中用户发送的消息**
  - `im:message:group:reader`

##### 文件权限

- ✅ **获取聊天中的资源文件**
  - `im:resource`
  - `im:resource:read`

### 5. 发布应用版本

如果修改了配置，需要发布新版本：

1. 左侧菜单：**版本管理与发布**
2. 点击 **"创建版本"**
3. 填写版本说明
4. 提交审核（如果需要）
5. 发布到群组

---

## 验证配置

### 测试1：检查Webhook连接

```bash
# 查看最近的webhook日志
tail -50 /tmp/bot.log | grep "Received webhook event"
```

应该能看到事件记录。

### 测试2：上传测试文件

1. 在飞书群上传一个测试文件：`汇总_20260517_0800.xlsx`
2. 查看日志：

```bash
tail -f /tmp/bot.log | grep -E "file|File|Received"
```

**预期看到：**
```
INFO - Received webhook event: unknown
INFO - Received file: 汇总_20260517_0800.xlsx (key: xxx)
INFO - Detected Duoke summary file: 汇总_20260517_0800.xlsx
INFO - File downloaded successfully: data/duoke/汇总_20260517_0800.xlsx
```

### 测试3：检查文件是否下载

```bash
ls -lh data/duoke/汇总_20260517_0800.xlsx
```

如果文件存在且大小正常，说明配置成功！

---

## 常见问题

### Q1: Webhook验证失败

**可能原因：**
- ngrok隧道地址错误
- FEISHU_VERIFICATION_TOKEN配置错误
- 机器人服务未启动

**解决方法：**
```bash
# 1. 检查服务是否运行
curl http://localhost:5001/health

# 2. 检查ngrok隧道
curl https://gripier-jonas-wannest.ngrok-free.dev/health

# 3. 查看webhook日志
tail -20 /tmp/bot.log | grep verification
```

### Q2: 收到消息但没有处理文件

**可能原因：**
- 文件名格式不匹配（必须是 `汇总_YYYYMMDD_HHMM.xlsx`）
- 文件权限未配置

**解决方法：**
```bash
# 查看文件处理日志
tail -50 /tmp/bot.log | grep "file"
```

如果看到 "Ignored non-summary file"，说明文件名格式不匹配。

### Q3: 文件下载失败

**可能原因：**
- 文件权限未配置（im:resource）
- file_key无效

**解决方法：**
1. 检查权限配置
2. 查看错误日志：
```bash
tail -50 /tmp/bot.log | grep "Error downloading file"
```

---

## 配置完成后的效果

### 自动导入流程

```
1. 用户在飞书群上传 汇总_20260517_0800.xlsx
   ↓
2. 飞书发送文件消息事件到webhook
   ↓
3. 机器人接收事件，识别为汇总文件
   ↓
4. 自动从飞书下载文件到 data/duoke/
   ↓
5. 自动添加到导入队列
   ↓
6. 发送确认消息到群：
   "📥 检测到多客汇总文件: 汇总_20260517_0800.xlsx
    📊 文件大小: 1.2 MB
    ✅ 已加入队列 (第 1 个)
    📋 队列状态: 待处理 0 | 处理中 1 | 已完成 0"
   ↓
7. 队列处理器自动开始导入
   ↓
8. 导入完成，内容出现在知识库
```

### 用户体验

**之前（手动）：**
1. 从飞书下载文件
2. 复制到项目目录
3. 运行命令添加到队列
4. 等待导入

**现在（自动）：**
1. 直接在飞书群上传文件 ✨
2. 其他全自动 🎉

---

## 总结

配置完成后，只需要：
1. ✅ 在飞书群上传 `汇总_YYYYMMDD_HHMM.xlsx` 格式的文件
2. ✅ 机器人自动下载
3. ✅ 自动加入队列
4. ✅ 自动导入到知识库

**完全无需手动操作！** 🎉

---

**作者**: Cindy + Claude Sonnet 4.5  
**最后更新**: 2026-05-17  
**相关文档**: [自动导入系统文档](auto-import-setup.md)
