#!/usr/bin/env python3
"""
获取飞书 ID 工具

运行此脚本，然后：
1. 在飞书群里 @机器人 发送任意消息
2. 在飞书私聊机器人发送任意消息
3. 等待 10 秒
4. 查看输出的 ID 信息
"""

import time
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

print("🔍 ID 获取工具")
print("=" * 60)
print()
print("请执行以下操作：")
print("1. 在飞书群「多客智能客服消息」里 @机器人 发送: 获取ID")
print("2. 私聊机器人发送: 获取ID")
print()
print("⏱️  等待 15 秒以收集日志...")
print()

time.sleep(15)

# 读取日志
log_file = Path('/tmp/bot.log')
if not log_file.exists():
    print("❌ 日志文件不存在")
    sys.exit(1)

import re
from collections import defaultdict

chat_ids = {}
user_ids = {}

with open(log_file, 'r') as f:
    lines = f.readlines()

    # 只看最近的日志
    recent_lines = lines[-100:]

    for line in recent_lines:
        # 查找群聊消息
        if 'Group message in chat:' in line:
            match = re.search(r'Group message in chat: (oc_[a-zA-Z0-9_]+)', line)
            if match:
                chat_id = match.group(1)
                if chat_id not in chat_ids:
                    chat_ids[chat_id] = "群聊"

        # 查找私聊消息
        if 'Private message from:' in line:
            match = re.search(r'Private message from: (ou_[a-zA-Z0-9_]+)', line)
            if match:
                user_id = match.group(1)
                if user_id not in user_ids:
                    user_ids[user_id] = "私聊用户"

print("✅ ID 信息收集完成")
print("=" * 60)
print()

if chat_ids:
    print("📋 群聊 ID:")
    for chat_id, desc in chat_ids.items():
        print(f"   {desc}: {chat_id}")
        print(f"   复制到 .env: NOTIFICATION_GROUP_ID={chat_id}")
    print()
else:
    print("📋 未检测到群聊消息")
    print("   请确认在群里 @机器人 发送了消息")
    print()

if user_ids:
    print("👤 用户 ID:")
    for user_id, desc in user_ids.items():
        print(f"   {desc}: {user_id}")
        print(f"   复制到 .env: NOTIFICATION_USER_ID={user_id}")
    print()
else:
    print("👤 未检测到私聊消息")
    print("   请确认私聊机器人发送了消息")
    print()

if not chat_ids and not user_ids:
    print("💡 提示:")
    print("   1. 确认机器人正在运行: curl http://localhost:5001/health")
    print("   2. 确认消息已发送")
    print("   3. 重新运行此脚本: python3.13 scripts/get_my_ids.py")
