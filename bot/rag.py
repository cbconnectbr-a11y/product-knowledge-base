"""
RAG (Retrieval-Augmented Generation) 智能问答模块
支持 DeepSeek 和 OpenAI 模型
"""
import os
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# 全局客户端（延迟初始化）
_client: Optional[OpenAI] = None
_model_name: Optional[str] = None


def _get_client():
    """获取 LLM 客户端（延迟初始化）"""
    global _client, _model_name

    if _client is None:
        api_provider = os.environ.get('LLM_PROVIDER', 'deepseek').lower()

        if api_provider == 'deepseek':
            api_key = os.environ.get('DEEPSEEK_API_KEY')
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY not found in environment variables")
            _client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            _model_name = "deepseek-chat"
        else:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            _client = OpenAI(api_key=api_key)
            _model_name = "gpt-4o"

        logger.info(f"RAG initialized with provider: {api_provider}, model: {_model_name}")

    return _client, _model_name


def generate_answer(user_question: str, search_results: List[Dict[str, Any]]) -> str:
    """
    使用 GPT-4o 基于检索结果生成精准答案

    Args:
        user_question: 用户的原始问题
        search_results: 搜索结果列表

    Returns:
        GPT-4o 生成的答案
    """
    if not search_results:
        return None

    # 构建上下文：将搜索结果整理为结构化文本
    context_parts = []
    for i, result in enumerate(search_results[:5], 1):  # 最多使用前5条结果
        context_parts.append(
            f"【参考资料 {i}】\n"
            f"SKU: {result.get('sku', 'N/A')}\n"
            f"标题: {result.get('title', 'N/A')}\n"
            f"内容: {result.get('content', 'N/A')}\n"
            f"来源: {result.get('source_group', 'N/A')}"
        )

    context = "\n\n".join(context_parts)

    # 构建提示词
    system_prompt = """你是一个专业的电商客服助手，专门回答产品相关问题。

你的职责：
1. 根据用户的问题，从提供的参考资料中提取相关信息
2. 只回答用户具体提出的问题，不要输出所有信息
3. 如果参考资料中没有相关信息，明确告知用户
4. 回答要简洁、准确、专业

回答要求：
- 如果用户问尺寸，只回答尺寸信息
- 如果用户问价格，只回答价格信息
- 如果用户问功能，只回答功能信息
- 如果用户问故障，只回答故障解决方案
- 不要输出与问题无关的内容
- 如果参考资料中有多个相关 SKU，分别说明"""

    user_prompt = f"""用户问题：{user_question}

参考资料：
{context}

请基于上述参考资料回答用户的问题。记住：只回答用户问的内容，不要列出所有信息。"""

    try:
        # 获取客户端
        client, model_name = _get_client()

        # 调用 LLM API
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # 较低的温度以获得更确定的答案
            max_tokens=800
        )

        answer = response.choices[0].message.content.strip()
        logger.info(f"{model_name} answer generated for question: {user_question[:50]}")

        return answer

    except Exception as e:
        logger.error(f"Error calling LLM API: {e}", exc_info=True)
        return None


def format_rag_response(user_question: str, answer: str, search_results: List[Dict[str, Any]]) -> str:
    """
    格式化 RAG 回答结果

    Args:
        user_question: 用户问题
        answer: GPT-4o 生成的答案
        search_results: 原始搜索结果

    Returns:
        格式化后的回复消息
    """
    output = f"💬 **你的问题**：{user_question}\n\n"
    output += f"✅ **回答**：\n{answer}\n\n"
    output += f"📚 **参考来源**：基于 {len(search_results)} 条相关知识\n"

    # 列出引用的 SKU
    skus = [r.get('sku') for r in search_results[:3] if r.get('sku')]
    if skus:
        output += f"📦 **相关 SKU**：{', '.join(skus)}"

    return output


if __name__ == "__main__":
    # 测试 RAG 功能
    from dotenv import load_dotenv
    load_dotenv()

    # 模拟搜索结果
    test_results = [
        {
            'sku': 'CBC004-1234',
            'title': '水龙头产品规格',
            'content': '产品尺寸：高度 25cm，宽度 15cm，深度 10cm。材质：304不锈钢。颜色：银色。重量：800g。',
            'source_group': '产品信息'
        }
    ]

    # 测试问题1：只问尺寸
    question1 = "CBC004-1234 的尺寸是多少？"
    answer1 = generate_answer(question1, test_results)
    if answer1:
        print("=" * 70)
        print("测试 1：只问尺寸")
        print("=" * 70)
        print(format_rag_response(question1, answer1, test_results))
        print()

    # 测试问题2：问材质
    question2 = "这个水龙头是什么材质的？"
    answer2 = generate_answer(question2, test_results)
    if answer2:
        print("=" * 70)
        print("测试 2：问材质")
        print("=" * 70)
        print(format_rag_response(question2, answer2, test_results))
