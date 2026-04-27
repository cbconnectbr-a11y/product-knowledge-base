"""
飞书机器人 Webhook 服务
Flask 应用，接收飞书消息事件并处理
"""
import os
import json
import logging
from flask import Flask, request, jsonify
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from bot.config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_VERIFICATION_TOKEN,
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

        # 记录请求日志
        logger.info(f"Received webhook event: {data.get('type', 'unknown')}")

        # 1. 处理 URL 验证事件（飞书配置 Webhook 时的验证）
        if data.get('type') == 'url_verification':
            challenge = data.get('challenge', '')
            logger.info(f"URL verification challenge: {challenge}")
            return jsonify({'challenge': challenge}), 200

        # 2. 验证 Token（可选，增强安全性）
        token = data.get('token')
        if token and token != FEISHU_VERIFICATION_TOKEN:
            logger.warning(f"Invalid verification token: {token}")
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

        # 提取发送者信息
        sender_id = sender.get('sender_id', {})
        user_id = sender_id.get('user_id') or sender_id.get('open_id')

        # 只处理文本消息
        if message_type != 'text':
            logger.info(f"Ignored non-text message type: {message_type}")
            return jsonify({'message': 'Only text messages are supported'}), 200

        # 解析消息内容
        try:
            content_json = json.loads(content_str)
            message_text = content_json.get('text', '').strip()
        except json.JSONDecodeError:
            logger.error(f"Failed to parse message content: {content_str}")
            return jsonify({'error': 'Invalid message content'}), 400

        if not message_text:
            logger.info("Received empty message")
            return jsonify({'message': 'Empty message ignored'}), 200

        logger.info(f"Processing message from user {user_id}: {message_text}")

        # 处理消息并获取回复
        response_text = handle_message(message_text, user_id=user_id)

        # 发送回复消息
        send_reply(user_id, response_text)

        return jsonify({'message': 'Message processed successfully'}), 200

    except Exception as e:
        logger.error(f"Error handling message event: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


def send_reply(user_id: str, text: str) -> None:
    """
    发送回复消息给用户

    Args:
        user_id: 飞书用户 ID
        text: 回复文本内容

    Raises:
        Exception: 发送失败时抛出异常
    """
    try:
        client = get_lark_client()

        # 构建消息内容
        content = json.dumps({'text': text})

        # 创建消息请求
        request_obj = CreateMessageRequest.builder() \
            .receive_id_type("user_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(user_id)
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
            raise Exception(f"Feishu API error: {response.msg}")

        logger.info(f"Reply sent successfully to user {user_id}")

    except Exception as e:
        logger.error(f"Error sending reply: {e}", exc_info=True)
        raise


def init_app():
    """初始化应用"""
    try:
        # 验证配置
        validate_config()
        logger.info("Configuration validated successfully")

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
