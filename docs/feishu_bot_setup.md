# 飞书机器人设置指南

本文档详细说明如何创建和配置飞书机器人，用于产品知识库系统。

## 前置条件

- 拥有飞书企业管理员权限
- 已完成 Supabase 数据库初始化
- 已准备好产品信息表和技术群组

## 第一步：创建飞书应用

### 1.1 访问飞书开放平台

访问 [https://open.feishu.cn/app](https://open.feishu.cn/app)，使用企业管理员账号登录。

### 1.2 创建企业自建应用

1. 点击「创建企业自建应用」
2. 填写应用信息：
   - **应用名称**: 产品知识库
   - **应用描述**: 电商产品技术知识库查询机器人
   - **应用图标**: 上传应用图标（可选）

3. 点击「创建」完成应用创建

### 1.3 获取应用凭证

创建完成后，在「凭证与基础信息」页面获取：

- **App ID**: 格式为 `cli_xxxxxxxxxx`
- **App Secret**: 点击「查看」获取密钥

**保存这两个值，稍后需要配置到 .env 文件中。**

## 第二步：配置应用权限

### 2.1 申请必需权限

在「权限管理」页面，搜索并申请以下权限：

#### 消息与群组权限

- `im:message` - 获取与发送单聊、群组消息
- `im:message.group_msg` - 接收群聊消息
- `im:chat` - 获取群组信息

**用途**: 接收技术群消息，发送知识库查询结果

#### 多维表格权限

- `bitable:app` - 查看、编辑和管理多维表格

**用途**: 同步飞书产品信息表到 Supabase

#### 通讯录权限

- `contact:user.id:readonly` - 获取用户 user ID

**用途**: 识别消息发送者，记录搜索日志

### 2.2 权限申请说明

申请权限时，建议填写以下说明：

```
本应用用于电商产品知识库系统，需要：
1. 接收技术群的产品问题讨论消息
2. 同步飞书产品信息表到数据库
3. 识别用户身份以记录搜索日志
4. 发送产品知识查询结果到群组
```

### 2.3 等待审批

提交权限申请后，等待企业管理员审批。审批通过后才能使用相应功能。

## 第三步：配置事件订阅

### 3.1 获取 Verification Token 和 Encrypt Key

在「事件订阅」页面：

1. 获取 **Verification Token**
2. 获取 **Encrypt Key**（用于消息加密）

**保存这两个值，稍后需要配置到 .env 文件中。**

### 3.2 配置 Webhook URL（暂时跳过）

在完成机器人服务部署后，再回来配置：

1. 配置请求地址: `https://your-domain.com/webhook/feishu`
2. 飞书会发送验证请求，机器人需要正确响应才能完成配置

**Phase 1 MVP 暂时跳过此步骤，后续部署时再配置。**

### 3.3 订阅事件

在「事件订阅」页面，添加以下事件：

#### 消息事件

- `im.message.receive_v1` - 接收消息
  - **用途**: 接收技术群消息，提取产品知识

#### 群组事件（可选）

- `im.chat.updated_v1` - 群组信息变更
  - **用途**: 监控技术群组状态

## 第四步：配置环境变量

### 4.1 复制环境变量模板

```bash
cd ~/Projects/product-knowledge-base
cp .env.example .env
```

### 4.2 编辑 .env 文件

使用文本编辑器打开 `.env` 文件，填入以下配置：

```bash
# Supabase 配置
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here
SUPABASE_SERVICE_KEY=your-service-role-key-here

# 飞书配置
FEISHU_APP_ID=cli_xxxxxxxxxx              # 从第一步获取
FEISHU_APP_SECRET=xxxxxxxxxxxxxx          # 从第一步获取
FEISHU_VERIFICATION_TOKEN=xxxxxxxxxx      # 从第三步获取
FEISHU_ENCRYPT_KEY=xxxxxxxxxx             # 从第三步获取

# 飞书产品信息表
FEISHU_PRODUCT_APP_TOKEN=bascnxxx         # 产品表的 app_token
FEISHU_PRODUCT_TABLE_ID=tblxxx            # 产品表的 table_id

# 飞书技术群组 ID（多个用逗号分隔）
FEISHU_TECH_GROUP_IDS=oc_xxx,oc_yyy      # 技术群的 chat_id

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
```

### 4.3 获取产品表信息

#### 获取 App Token

1. 打开飞书多维表格
2. 查看浏览器地址栏 URL：
   ```
   https://xxx.feishu.cn/base/bascnXXXXXXXXXXXXXXXXXX?table=tblXXXXXXXXXXXXXXX
   ```
3. `basc` 开头的部分就是 `app_token`

#### 获取 Table ID

1. 在同一个 URL 中
2. `table=` 后面的部分就是 `table_id`

### 4.4 获取技术群组 ID

#### 方法一：通过群设置

1. 打开技术群
2. 点击右上角「...」-> 「设置」
3. 查看群 ID（格式为 `oc_xxxxxxxxxx`）

#### 方法二：通过 API

使用飞书开放平台的「在线调试」功能：

1. 访问 [https://open.feishu.cn/api-explorer](https://open.feishu.cn/api-explorer)
2. 选择 `im/v1/chats` 接口
3. 调用获取群组列表
4. 找到对应技术群的 `chat_id`

### 4.5 验证配置

```bash
python3 bot/config.py
```

如果所有配置正确，会显示：

```
============================================================
配置验证: 通过
============================================================
所有配置项已正确加载
```

如果有错误，会列出缺少的配置项。

## 第五步：发布应用

### 5.1 创建应用版本

1. 在「版本管理与发布」页面
2. 点击「创建版本」
3. 填写版本信息：
   - **版本号**: 1.0.0
   - **版本说明**: Phase 1 MVP - 产品知识库基础功能
   - **更新说明**: 支持技术群消息采集、产品信息同步、知识库查询

4. 点击「保存」

### 5.2 申请发布

1. 提交版本审核
2. 等待企业管理员审批

### 5.3 发布应用

审批通过后，点击「全网发布」或「指定范围发布」。

**建议**: Phase 1 先发布到测试群组，验证功能后再全网发布。

## 第六步：添加机器人到群组

### 6.1 添加到技术群

1. 打开需要监控的技术群
2. 点击右上角「...」-> 「设置」
3. 点击「添加成员」-> 「添加机器人」
4. 搜索「产品知识库」，选择并添加

### 6.2 配置机器人权限

在群设置中，确保机器人有以下权限：

- 接收群消息
- 发送群消息
- @机器人时响应

### 6.3 测试机器人

发送测试消息到群组：

```
@产品知识库 查询 SKU12345
```

如果机器人正常工作，会返回查询结果。

## 第七步：测试完整流程

### 7.1 测试产品表同步

```bash
python3 scripts/sync_products.py
```

检查 Supabase `products` 表，确认数据已同步。

### 7.2 测试消息接收

在技术群发送包含产品问题的消息，检查日志文件：

```bash
tail -f logs/app.log
```

确认机器人能够接收并处理消息。

### 7.3 测试知识查询

在技术群 @机器人，发送查询命令：

```
@产品知识库 如何解决 XXX 产品的 YYY 问题？
```

确认机器人能够查询并返回相关知识。

## 常见问题

### Q1: 权限申请失败怎么办？

**A**: 联系企业管理员，说明应用用途和需要的权限。提供详细的权限说明和使用场景。

### Q2: 机器人收不到消息？

**A**: 检查以下项：

1. 是否已申请 `im:message.group_msg` 权限
2. 是否已订阅 `im.message.receive_v1` 事件
3. Webhook URL 是否配置正确
4. 机器人是否已添加到群组

### Q3: 无法同步产品表？

**A**: 检查以下项：

1. 是否已申请 `bitable:app` 权限
2. `FEISHU_PRODUCT_APP_TOKEN` 和 `FEISHU_PRODUCT_TABLE_ID` 是否正确
3. 机器人是否有访问该表的权限

### Q4: 如何查看机器人日志？

**A**: 查看日志文件：

```bash
tail -f logs/app.log
```

或查看飞书开放平台的「事件日志」。

## 下一步

完成飞书机器人配置后，继续进行：

- Task 4: 飞书产品表同步
- Task 5: 群消息监听和知识提取
- Task 6: 知识库查询功能

## 参考文档

- [飞书开放平台文档](https://open.feishu.cn/document/home/index)
- [飞书机器人开发指南](https://open.feishu.cn/document/home/develop-a-bot-in-5-minutes/introduction)
- [飞书事件订阅](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)
- [飞书多维表格 API](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app/list)
