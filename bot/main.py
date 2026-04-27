"""
飞书机器人 Webhook 服务
Flask 应用，接收飞书消息事件并处理
"""
import os
import json
import logging
import threading
import time
from flask import Flask, request, jsonify
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
from lark_oapi.core import AESCipher

from bot.config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_VERIFICATION_TOKEN,
    FEISHU_ENCRYPT_KEY,
    validate_config
)
from bot.handlers import handle_message

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建 Flask 应用
app = Flask(__name__)

# 初始化飞书客户端
lark_client = None


def get_lark_client():
    """获取飞书客户端（延迟初始化）"""
    global lark_client
    if lark_client is None:
        lark_client = lark.Client.builder() \
            .app_id(FEISHU_APP_ID) \
            .app_secret(FEISHU_APP_SECRET) \
            .build()
    return lark_client


# 消息去重缓存（5分钟内的 message_id）
processed_messages = {}
CACHE_EXPIRE_SECONDS = 300
message_cache_lock = threading.Lock()


def is_message_processed(message_id: str) -> bool:
    """检查消息是否已处理（去重）- 线程安全"""
    with message_cache_lock:
        current_time = time.time()

        # 清理过期缓存
        expired_keys = [k for k, v in processed_messages.items() if current_time - v > CACHE_EXPIRE_SECONDS]
        for k in expired_keys:
            del processed_messages[k]

        # 检查是否处理过
        if message_id in processed_messages:
            return True

        processed_messages[message_id] = current_time
        return False


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        'status': 'healthy',
        'service': 'product-knowledge-base-bot',
        'version': '1.0.0'
    }), 200


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    飞书事件 Webhook 端点

    处理流程：
    1. 验证飞书签名
    2. 处理 url_verification 事件（返回 challenge）
    3. 处理 im.message.receive_v1 事件（接收和回复消息）
    """
    try:
        # 获取请求数据
        data = request.get_json()

        if not data:
            logger.warning("Received empty request body")
            return jsonify({'error': 'Empty request body'}), 400

        # 处理加密事件
        if 'encrypt' in data and FEISHU_ENCRYPT_KEY:
            cipher = AESCipher(FEISHU_ENCRYPT_KEY)
            decrypted = cipher.decrypt_str(data['encrypt'])
            data = json.loads(decrypted)
            logger.info("Decrypted event received")

        # 记录请求日志
        logger.info(f"Received webhook event: {data.get('type', 'unknown')}")

        # 1. 处理 URL 验证事件（飞书配置 Webhook 时的验证）
        if data.get('type') == 'url_verification':
            challenge = data.get('challenge', '')
            logger.info(f"URL verification challenge: {challenge}")
            return jsonify({'challenge': challenge}), 200

        # 2. 验证 Token（兼容 v1 和 v2 事件）
        token = data.get('token') or data.get('header', {}).get('token')
        if FEISHU_VERIFICATION_TOKEN and token != FEISHU_VERIFICATION_TOKEN:
            logger.warning(f"Invalid verification token")
            return jsonify({'error': 'Invalid token'}), 403

        # 3. 处理消息事件
        event_type = data.get('header', {}).get('event_type')

        if event_type == 'im.message.receive_v1':
            return handle_message_event(data)
        else:
            # 其他事件类型暂不处理
            logger.info(f"Ignored event type: {event_type}")
            return jsonify({'message': 'Event received'}), 200

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


def process_message_async(receive_id: str, receive_id_type: str, message_text: str, message_id: str):
    """
    异步处理消息（在后台线程中运行）

    Args:
        receive_id: 接收者 ID
        receive_id_type: ID 类型
        message_text: 消息文本
        message_id: 消息 ID
    """
    try:
        # 处理消息（传递 receive_id 作为 user_id 用于日志）
        response_text = handle_message(message_text, user_id=receive_id)

        # 发送回复
        send_reply(receive_id, receive_id_type, response_text)

        logger.info(f"Message {message_id} processed successfully")
    except Exception as e:
        logger.error(f"Error processing message {message_id}: {e}", exc_info=True)


def handle_message_event(event_data: dict) -> tuple:
    """
    处理消息接收事件

    Args:
        event_data: 飞书事件数据

    Returns:
        Flask response tuple (response, status_code)
    """
    try:
        # 提取事件内容
        event = event_data.get('event', {})
        message = event.get('message', {})
        sender = event.get('sender', {})

        # 提取消息信息
        message_id = message.get('message_id')
        message_type = message.get('message_type')
        content_str = message.get('content', '{}')

        # 提取发送者信息并确定 receive_id 和类型（优先使用 open_id，更通用）
        sender_id = sender.get('sender_id', {})
        if sender_id.get('open_id'):
            receive_id = sender_id['open_id']
            receive_id_type = 'open_id'
        elif sender_id.get('user_id'):
            receive_id = sender_id['user_id']
            receive_id_type = 'user_id'
        elif sender_id.get('union_id'):
            receive_id = sender_id['union_id']
            receive_id_type = 'union_id'
        else:
            logger.error("No valid sender id found")
            return jsonify({'msg': 'ok'}), 200

        # 只处理文本消息
        if message_type != 'text':
            logger.info(f"Ignored non-text message type: {message_type}")
            return jsonify({'msg': 'ok'}), 200

        # 解析消息内容
        try:
            content_json = json.loads(content_str)
            message_text = content_json.get('text', '').strip()
        except json.JSONDecodeError:
            logger.error(f"Failed to parse message content: {content_str}")
            return jsonify({'msg': 'ok'}), 200

        if not message_text:
            logger.info("Received empty message")
            return jsonify({'msg': 'ok'}), 200

        logger.info(f"Received message: {message_text}")

        # 消息去重
        if is_message_processed(message_id):
            logger.info(f"Message {message_id} already processed, skipping")
            return jsonify({'msg': 'ok'}), 200

        # 异步处理消息（立即返回 200）
        thread = threading.Thread(
            target=process_message_async,
            args=(receive_id, receive_id_type, message_text, message_id)
        )
        thread.daemon = True
        thread.start()

        # 立即返回 200
        return jsonify({'msg': 'ok'}), 200

    except Exception as e:
        logger.error(f"Error handling message event: {e}", exc_info=True)
        return jsonify({'msg': 'ok'}), 200


def send_reply(receive_id: str, receive_id_type: str, text: str) -> bool:
    """
    发送回复消息给用户

    Args:
        receive_id: 接收者 ID
        receive_id_type: ID 类型 ('user_id', 'open_id', 'union_id')
        text: 回复文本内容

    Returns:
        bool: 发送成功返回 True，失败返回 False
    """
    try:
        client = get_lark_client()

        # 构建消息内容
        content = json.dumps({'text': text})

        # 创建消息请求
        request_obj = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(content)
                .build()
            ) \
            .build()

        # 发送消息
        response = client.im.v1.message.create(request_obj)

        # 检查响应
        if response.code != 0:
            logger.error(
                f"Failed to send message: code={response.code}, "
                f"msg={response.msg}"
            )
            return False

        logger.info(f"Reply sent successfully to {receive_id_type}={receive_id}")
        return True

    except Exception as e:
        logger.error(f"Error sending reply: {e}", exc_info=True)
        return False


def init_app():
    """初始化应用"""
    try:
        # 验证配置
        validate_config()
        logger.info("Configuration validated successfully")

        # 检查加密配置
        if not FEISHU_ENCRYPT_KEY:
            logger.warning("FEISHU_ENCRYPT_KEY not set - ensure Feishu webhook encryption is disabled")

        # 预初始化飞书客户端
        get_lark_client()
        logger.info("Lark client initialized successfully")

        return True
    except Exception as e:
        logger.error(f"Failed to initialize app: {e}")
        return False


if __name__ == '__main__':
    # 初始化应用
    if not init_app():
        logger.error("Application initialization failed, exiting...")
        exit(1)

    # 获取端口配置
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'

    logger.info(f"Starting Flask server on port {port}...")
    logger.info(f"Debug mode: {debug}")

    # 启动 Flask 服务
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
