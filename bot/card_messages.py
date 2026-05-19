"""
飞书交互式卡片消息模块
用于AI建议答案的审核交互
"""
import json
import logging
from typing import Dict, Any
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, PatchMessageRequest, PatchMessageRequestBody

logger = logging.getLogger(__name__)


def build_ai_suggestion_card(
    question: str,
    ai_answer: str,
    log_id: str,
    model: str = "DeepSeek",
    latency_ms: int = 0
) -> Dict[str, Any]:
    """
    构建AI建议答案的交互式卡片

    Args:
        question: 客户问题
        ai_answer: AI生成的答案
        log_id: ai_suggestion_log表的记录ID
        model: 使用的AI模型
        latency_ms: 生成耗时

    Returns:
        飞书卡片消息的JSON结构
    """
    card = {
        "config": {
            "wide_screen_mode": True,  # 宽屏模式
            "enable_forward": False     # 禁止转发（避免AI答案被滥用）
        },
        "header": {
            "template": "orange",  # 橙色警告样式
            "title": {
                "tag": "plain_text",
                "content": "💡 AI建议答案（需审核）"
            }
        },
        "elements": [
            # 警告提示
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": "⚠️ 以下是AI生成的建议答案，可能存在错误，请客服仔细审核后再决定是否采纳\n\n📌 提示：点击按钮后可能显示错误提示（飞书已知问题），但操作已成功完成，数据已正常保存，请忽略错误提示"
                }
            },
            # 分隔线
            {
                "tag": "hr"
            },
            # 客户问题
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**客户问题：**\n{question}"
                        }
                    }
                ]
            },
            # 分隔线
            {
                "tag": "hr"
            },
            # AI答案
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**AI建议答案：**\n\n{ai_answer}"
                }
            },
            # 分隔线
            {
                "tag": "hr"
            },
            # 元信息
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"模型: {model} | 生成耗时: {latency_ms}ms | 记录ID: {log_id[:8]}..."
                    }
                ]
            },
            # 分隔线
            {
                "tag": "hr"
            },
            # 操作按钮
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "✅ 答案正确，加入知识库"
                        },
                        "type": "primary",  # 主要按钮（绿色）
                        "value": {
                            "action": "approve",
                            "log_id": log_id,
                            "question": question,
                            "answer": ai_answer
                        }
                    },
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "❌ 答案错误，丢弃并记录"
                        },
                        "type": "danger",  # 危险按钮（红色）
                        "value": {
                            "action": "reject",
                            "log_id": log_id,
                            "question": question,
                            "answer": ai_answer
                        }
                    },
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "⏭️ 仅本次回复，不入库"
                        },
                        "type": "default",  # 默认按钮（灰色）
                        "value": {
                            "action": "ignore",
                            "log_id": log_id
                        }
                    }
                ]
            }
        ]
    }

    return card


def build_action_result_card(action: str, success: bool, message: str) -> Dict[str, Any]:
    """
    构建操作结果卡片（用于更新原卡片）

    Args:
        action: 操作类型 ('approved', 'rejected', 'ignored')
        success: 是否成功
        message: 提示消息

    Returns:
        飞书卡片消息的JSON结构
    """
    action_labels = {
        'approved': '✅ 已采纳',
        'rejected': '❌ 已拒绝',
        'ignored': '⏭️ 已忽略'
    }

    colors = {
        'approved': 'green',
        'rejected': 'red',
        'ignored': 'grey'
    }

    template = colors.get(action, 'grey') if success else 'red'
    title = action_labels.get(action, '处理完成') if success else '操作失败'

    card = {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": False
        },
        "header": {
            "template": template,
            "title": {
                "tag": "plain_text",
                "content": title
            }
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": message
                }
            }
        ]
    }

    return card


def send_interactive_card(client, chat_id: str, card: Dict[str, Any]) -> bool:
    """
    发送交互式卡片消息到飞书群聊

    Args:
        client: 飞书SDK客户端
        chat_id: 群聊ID
        card: 卡片JSON结构

    Returns:
        是否发送成功
    """
    try:
        # 构建请求
        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(json.dumps(card))
                .build()
            ) \
            .build()

        # 发送消息
        response = client.im.v1.message.create(request)

        if response.success():
            logger.info(f"Interactive card sent to chat_id: {chat_id}")
            return True
        else:
            logger.error(f"Failed to send card: {response.code}, {response.msg}")
            return False

    except Exception as e:
        logger.error(f"Error sending interactive card: {e}", exc_info=True)
        return False


def update_card_message(client, message_id: str, card: Dict[str, Any]) -> bool:
    """
    更新已发送的卡片消息（用于显示操作结果）

    Args:
        client: 飞书SDK客户端
        message_id: 消息ID
        card: 新的卡片JSON结构

    Returns:
        是否更新成功
    """
    try:
        # 构建请求
        request = PatchMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(
                PatchMessageRequestBody.builder()
                .content(json.dumps(card))
                .build()
            ) \
            .build()

        # 更新消息
        response = client.im.v1.message.patch(request)

        if response.success():
            logger.info(f"Card message updated: {message_id}")
            return True
        else:
            logger.error(f"Failed to update card: {response.code}, {response.msg}")
            return False

    except Exception as e:
        logger.error(f"Error updating card message: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    # 测试卡片生成
    import json

    test_card = build_ai_suggestion_card(
        question="CBC008-657的水龙头漏水怎么办？",
        ai_answer="根据常见的水龙头漏水问题，建议按以下步骤排查：\n\n1. 检查连接处是否松动\n2. 查看密封圈是否老化\n3. 如果是内部零件损坏，建议联系售后更换\n\n⚠️ 此为通用建议，具体问题请联系售后确认。",
        log_id="550e8400-e29b-41d4-a716-446655440000",
        model="DeepSeek",
        latency_ms=1234
    )

    print("=== AI建议卡片 ===")
    print(json.dumps(test_card, ensure_ascii=False, indent=2))
    print()

    test_result = build_action_result_card(
        action="approved",
        success=True,
        message="AI答案已成功保存到知识库，客服可以搜索到此答案了。"
    )

    print("=== 操作结果卡片 ===")
    print(json.dumps(test_result, ensure_ascii=False, indent=2))
