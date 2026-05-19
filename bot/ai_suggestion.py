"""
AI建议答案生成模块
当知识库无答案时，生成AI建议供客服审核
"""
import hashlib
import logging
import time
from typing import Optional, Dict, Any
from scripts.utils import get_supabase_client
from bot.rag import _get_client

logger = logging.getLogger(__name__)


def _hash_question(question: str) -> str:
    """
    生成问题的hash值（用于去重）

    Args:
        question: 问题文本

    Returns:
        MD5 hash的前16位
    """
    return hashlib.md5(question.strip().encode()).hexdigest()[:16]


def check_if_rejected_before(question: str) -> Optional[Dict[str, Any]]:
    """
    检查该问题是否之前被拒绝过

    Args:
        question: 用户问题

    Returns:
        如果之前被拒绝过，返回拒绝记录；否则返回None
    """
    try:
        client = get_supabase_client()
        q_hash = _hash_question(question)

        response = client.table('ai_rejected_answers') \
            .select('*') \
            .eq('question_hash', q_hash) \
            .order('created_at', desc=True) \
            .limit(1) \
            .execute()

        if response.data and len(response.data) > 0:
            logger.info(f"Question '{question[:30]}...' was rejected before")
            return response.data[0]

        return None

    except Exception as e:
        logger.error(f"Error checking rejected answers: {e}", exc_info=True)
        return None


def generate_ai_suggestion(question: str, user_id: Optional[str] = None, chat_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    生成AI建议答案

    Args:
        question: 用户问题
        user_id: 飞书用户ID
        chat_id: 飞书群聊ID

    Returns:
        包含AI答案和元数据的字典，或None（如果生成失败）
        {
            'question': str,
            'answer': str,
            'model': str,
            'latency_ms': int,
            'question_hash': str,
            'log_id': UUID  # ai_suggestion_log表的记录ID
        }
    """
    start_time = time.time()

    try:
        # 获取LLM客户端
        client, model_name = _get_client()

        # 构建谨慎的系统提示词（降低幻觉率）
        system_prompt = """你是一个专业的电商客服助手。

⚠️ 重要注意事项：
1. 如果问题需要具体的产品规格、价格、库存、保修期等事实信息，而你不确定，请明确说"我不确定具体数字，建议查询官方资料或联系客服"
2. 不要编造或猜测产品型号、SKU、具体参数、价格等信息
3. 如果是常见的电商售后问题（退货、换货、物流等），可以提供通用流程建议
4. 如果是产品使用问题，可以提供常见的故障排查步骤，但要说明"仅供参考"

回答要求：
- 简洁专业，不超过200字
- 如果不确定，明确说明
- 提供建议时要说明"仅供参考"或"建议进一步确认"
"""

        user_prompt = f"""客户问题：{question}

请根据上述注意事项回答。如果不确定，请诚实告知，不要猜测。"""

        # 调用LLM API
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # 较低温度，减少创造性
            max_tokens=500
        )

        answer = response.choices[0].message.content.strip()
        latency_ms = int((time.time() - start_time) * 1000)

        logger.info(f"AI suggestion generated for '{question[:30]}...' in {latency_ms}ms")

        # 记录到 ai_suggestion_log 表
        log_id = _log_ai_suggestion(
            question=question,
            answer=answer,
            model=model_name,
            latency_ms=latency_ms,
            user_id=user_id,
            chat_id=chat_id
        )

        return {
            'question': question,
            'answer': answer,
            'model': model_name,
            'latency_ms': latency_ms,
            'question_hash': _hash_question(question),
            'log_id': log_id
        }

    except Exception as e:
        logger.error(f"Error generating AI suggestion: {e}", exc_info=True)
        return None


def _log_ai_suggestion(
    question: str,
    answer: str,
    model: str,
    latency_ms: int,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None
) -> Optional[str]:
    """
    记录AI建议到日志表

    Returns:
        记录的UUID ID，或None（如果失败）
    """
    try:
        client = get_supabase_client()

        log_data = {
            'question': question,
            'ai_answer': answer,
            'model': model,
            'latency_ms': latency_ms,
            'user_id': user_id,
            'chat_id': chat_id,
            'question_hash': _hash_question(question),
            'search_result_count': 0  # 触发AI建议是因为搜索结果为0
        }

        response = client.table('ai_suggestion_log').insert(log_data).execute()

        if response.data and len(response.data) > 0:
            log_id = response.data[0]['id']
            logger.info(f"AI suggestion logged with ID: {log_id}")
            return log_id

        return None

    except Exception as e:
        logger.error(f"Error logging AI suggestion: {e}", exc_info=True)
        return None


def record_user_action(
    log_id: str,
    action: str,
    user_id: Optional[str] = None,
    final_answer: Optional[str] = None
) -> bool:
    """
    记录用户对AI建议的操作

    Args:
        log_id: ai_suggestion_log表的记录ID
        action: 操作类型 ('approved', 'rejected', 'ignored', 'edited')
        user_id: 飞书用户ID
        final_answer: 如果是edited，记录最终版本

    Returns:
        是否记录成功
    """
    try:
        client = get_supabase_client()

        update_data = {
            'action': action,
            'responded_at': 'now()'
        }

        if user_id:
            update_data['user_id'] = user_id

        if final_answer and action == 'edited':
            update_data['final_answer'] = final_answer

        response = client.table('ai_suggestion_log') \
            .update(update_data) \
            .eq('id', log_id) \
            .execute()

        logger.info(f"User action '{action}' recorded for log_id: {log_id}")
        return True

    except Exception as e:
        logger.error(f"Error recording user action: {e}", exc_info=True)
        return False


def save_approved_answer(
    question: str,
    answer: str,
    user_id: Optional[str] = None,
    source: str = 'ai_approved'
) -> Optional[str]:
    """
    保存被采纳的AI答案到知识库

    Args:
        question: 问题（作为title）
        answer: 答案（作为content）
        user_id: 审核人（飞书用户ID）
        source: 来源标记 ('ai_approved' 或 'ai_edited')

    Returns:
        knowledge_entries记录的ID，或None（如果失败）
    """
    try:
        client = get_supabase_client()

        entry_data = {
            'title': question[:200],  # 限制标题长度
            'content': answer,
            'source': source,
            'source_type': 'ai_generated',  # AI生成的内容类型
            'source_group': 'AI生成 - 客服采纳',
            'status': 'approved',  # 直接approved，不需要再审核
            'reviewed_by': None,  # Phase 1暂不关联用户UUID
            'reviewed_at': 'now()',
            'sku': None  # AI生成的答案通常没有特定SKU
        }

        response = client.table('knowledge_entries').insert(entry_data).execute()

        if response.data and len(response.data) > 0:
            entry_id = response.data[0]['id']
            logger.info(f"AI answer approved and saved to knowledge base: {entry_id}")
            return entry_id

        return None

    except Exception as e:
        logger.error(f"Error saving approved answer: {e}", exc_info=True)
        return None


def save_rejected_answer(
    question: str,
    answer: str,
    user_id: Optional[str] = None
) -> bool:
    """
    保存被拒绝的AI答案（避免重复生成）

    Args:
        question: 问题
        answer: 被拒绝的AI答案
        user_id: 拒绝的用户ID

    Returns:
        是否保存成功
    """
    try:
        client = get_supabase_client()

        reject_data = {
            'question': question,
            'ai_answer': answer,
            'rejected_by': user_id,
            'question_hash': _hash_question(question)
        }

        response = client.table('ai_rejected_answers').insert(reject_data).execute()

        logger.info(f"Rejected answer saved for question: '{question[:30]}...'")
        return True

    except Exception as e:
        logger.error(f"Error saving rejected answer: {e}", exc_info=True)
        return False
