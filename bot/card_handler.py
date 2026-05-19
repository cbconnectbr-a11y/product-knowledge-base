"""
飞书卡片回调处理模块
处理AI建议答案卡片的用户操作（approve/reject/ignore）
"""
import json
import logging
from typing import Dict, Any, Optional
from bot.ai_suggestion import (
    record_user_action,
    save_approved_answer,
    save_rejected_answer
)
from bot.card_messages import build_action_result_card

logger = logging.getLogger(__name__)


def handle_card_callback(callback_data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    处理卡片按钮点击回调

    Args:
        callback_data: 飞书回调数据
        user_id: 点击按钮的用户ID

    Returns:
        响应数据（包含更新后的卡片）
    """
    try:
        # 解析action value
        action_value = callback_data.get('action', {}).get('value', {})

        # 如果value是字符串，解析为JSON
        if isinstance(action_value, str):
            action_value = json.loads(action_value)

        action = action_value.get('action')
        log_id = action_value.get('log_id')
        question = action_value.get('question', '')
        answer = action_value.get('answer', '')

        logger.info(f"Card callback received: action={action}, log_id={log_id}, user={user_id}")

        # 根据action执行不同操作
        if action == 'approve':
            return handle_approve(log_id, question, answer, user_id)

        elif action == 'reject':
            return handle_reject(log_id, question, answer, user_id)

        elif action == 'ignore':
            return handle_ignore(log_id, user_id)

        else:
            logger.warning(f"Unknown action: {action}")
            return build_error_response("未知的操作类型")

    except Exception as e:
        logger.error(f"Error handling card callback: {e}", exc_info=True)
        return build_error_response(f"处理失败: {str(e)}")


def handle_approve(log_id: str, question: str, answer: str, user_id: Optional[str]) -> Dict[str, Any]:
    """
    处理"采纳"操作：保存到知识库 + 记录日志

    Returns:
        响应数据（包含更新后的卡片）
    """
    try:
        # 1. 保存到知识库
        entry_id = save_approved_answer(
            question=question,
            answer=answer,
            user_id=user_id,
            source='ai_approved'
        )

        if not entry_id:
            logger.error("Failed to save approved answer to knowledge base")
            return build_error_response("保存到知识库失败，请稍后重试")

        # 2. 记录用户操作到日志
        record_user_action(
            log_id=log_id,
            action='approved',
            user_id=user_id
        )

        # 3. 构建成功响应卡片
        success_message = f"""✅ AI答案已成功保存到知识库！

**问题：** {question[:100]}...

**知识库ID：** {entry_id[:8]}...

客服现在可以通过搜索找到此答案了。"""

        result_card = build_action_result_card(
            action='approved',
            success=True,
            message=success_message
        )

        logger.info(f"AI answer approved and saved: log_id={log_id}, entry_id={entry_id}")

        # 飞书卡片回调返回空对象（尝试避免200341错误）
        # Toast提示会在飞书客户端自动显示
        return {}

    except Exception as e:
        logger.error(f"Error in handle_approve: {e}", exc_info=True)
        return build_error_response(f"采纳失败: {str(e)}")


def handle_reject(log_id: str, question: str, answer: str, user_id: Optional[str]) -> Dict[str, Any]:
    """
    处理"拒绝"操作：记录到拒绝列表 + 记录日志

    Returns:
        响应数据（包含更新后的卡片）
    """
    try:
        # 1. 保存到拒绝列表（避免重复生成）
        save_rejected_answer(
            question=question,
            answer=answer,
            user_id=user_id
        )

        # 2. 记录用户操作到日志
        record_user_action(
            log_id=log_id,
            action='rejected',
            user_id=user_id
        )

        # 3. 构建响应卡片
        reject_message = f"""❌ AI答案已标记为错误

**问题：** {question[:100]}...

该问题已记录，系统不会再为相同问题生成AI建议。

💡 提示：您可以手动回答客户，或等待知识库补充相关信息。"""

        result_card = build_action_result_card(
            action='rejected',
            success=True,
            message=reject_message
        )

        logger.info(f"AI answer rejected: log_id={log_id}")

        return {}

    except Exception as e:
        logger.error(f"Error in handle_reject: {e}", exc_info=True)
        return build_error_response(f"拒绝操作失败: {str(e)}")


def handle_ignore(log_id: str, user_id: Optional[str]) -> Dict[str, Any]:
    """
    处理"忽略"操作：仅记录日志，不做任何持久化

    Returns:
        响应数据（包含更新后的卡片）
    """
    try:
        # 只记录用户操作到日志
        record_user_action(
            log_id=log_id,
            action='ignored',
            user_id=user_id
        )

        # 构建响应卡片
        ignore_message = """⏭️ 已忽略此AI建议

此答案仅用于本次回复，不会保存到知识库。

💡 提示：如果后续需要，您可以手动添加相关知识。"""

        result_card = build_action_result_card(
            action='ignored',
            success=True,
            message=ignore_message
        )

        logger.info(f"AI answer ignored: log_id={log_id}")

        return {}

    except Exception as e:
        logger.error(f"Error in handle_ignore: {e}", exc_info=True)
        return build_error_response(f"忽略操作失败: {str(e)}")


def build_error_response(error_message: str) -> Dict[str, Any]:
    """
    构建错误响应

    Args:
        error_message: 错误消息

    Returns:
        响应数据
    """
    error_card = build_action_result_card(
        action='error',
        success=False,
        message=error_message
    )

    return {
        "toast": {
            "type": "error",
            "content": "操作失败"
        },
        "card": error_card
    }
