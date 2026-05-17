"""
对话会话管理模块
管理用户的对话历史，支持上下文追问
"""
import time
from typing import Dict, List, Optional, Any
from collections import defaultdict
import threading


class ConversationSession:
    """单个对话会话"""

    def __init__(self, max_history: int = 3, expire_seconds: int = 1800):
        """
        Args:
            max_history: 保留的最大历史对话轮数
            expire_seconds: 会话过期时间（秒），默认30分钟
        """
        self.max_history = max_history
        self.expire_seconds = expire_seconds
        self.history: List[Dict[str, Any]] = []
        self.last_active = time.time()

    def add_turn(self, question: str, answer: str, search_results: List[Dict] = None):
        """
        添加一轮对话

        Args:
            question: 用户问题
            answer: 机器人回答
            search_results: 搜索结果（可选）
        """
        self.history.append({
            'question': question,
            'answer': answer,
            'search_results': search_results or [],
            'timestamp': time.time()
        })

        # 保持历史记录在限制范围内
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        self.last_active = time.time()

    def get_last_turn(self) -> Optional[Dict[str, Any]]:
        """获取最近一轮对话"""
        if self.history:
            return self.history[-1]
        return None

    def get_context(self, include_last: bool = True) -> str:
        """
        获取对话上下文（格式化为文本）

        Args:
            include_last: 是否包含最后一轮（默认True）

        Returns:
            格式化的上下文文本
        """
        context_parts = []
        history_to_use = self.history if include_last else self.history[:-1]

        for i, turn in enumerate(history_to_use, 1):
            context_parts.append(f"【历史对话 {i}】")
            context_parts.append(f"用户: {turn['question']}")
            context_parts.append(f"助手: {turn['answer'][:200]}...")  # 截断答案避免太长
            context_parts.append("")

        return "\n".join(context_parts)

    def is_expired(self) -> bool:
        """检查会话是否过期"""
        return (time.time() - self.last_active) > self.expire_seconds

    def clear(self):
        """清空会话历史"""
        self.history = []
        self.last_active = time.time()


class SessionManager:
    """全局会话管理器"""

    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = defaultdict(ConversationSession)
        self.lock = threading.Lock()

    def get_session(self, user_id: str, chat_id: str = None) -> ConversationSession:
        """
        获取或创建用户会话

        Args:
            user_id: 用户ID
            chat_id: 群聊ID（可选，用于区分不同群聊）

        Returns:
            用户的对话会话
        """
        # 使用 user_id + chat_id 作为唯一标识
        session_key = f"{user_id}:{chat_id}" if chat_id else user_id

        with self.lock:
            # 清理过期会话
            self._cleanup_expired_sessions()

            # 获取或创建会话
            session = self.sessions[session_key]

            return session

    def add_conversation(self, user_id: str, chat_id: str, question: str,
                        answer: str, search_results: List[Dict] = None):
        """
        添加一轮对话到会话中

        Args:
            user_id: 用户ID
            chat_id: 群聊ID
            question: 用户问题
            answer: 机器人回答
            search_results: 搜索结果
        """
        session = self.get_session(user_id, chat_id)
        session.add_turn(question, answer, search_results)

    def get_last_context(self, user_id: str, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户最近一轮对话

        Args:
            user_id: 用户ID
            chat_id: 群聊ID

        Returns:
            最近一轮对话，如果没有则返回None
        """
        session = self.get_session(user_id, chat_id)
        return session.get_last_turn()

    def get_context_text(self, user_id: str, chat_id: str, include_last: bool = True) -> str:
        """
        获取格式化的对话上下文

        Args:
            user_id: 用户ID
            chat_id: 群聊ID
            include_last: 是否包含最后一轮

        Returns:
            格式化的上下文文本
        """
        session = self.get_session(user_id, chat_id)
        return session.get_context(include_last)

    def clear_session(self, user_id: str, chat_id: str = None):
        """
        清空用户会话

        Args:
            user_id: 用户ID
            chat_id: 群聊ID
        """
        session_key = f"{user_id}:{chat_id}" if chat_id else user_id
        with self.lock:
            if session_key in self.sessions:
                self.sessions[session_key].clear()

    def _cleanup_expired_sessions(self):
        """清理过期的会话（内部方法）"""
        expired_keys = [
            key for key, session in self.sessions.items()
            if session.is_expired()
        ]

        for key in expired_keys:
            del self.sessions[key]


# 全局会话管理器实例
_session_manager = None


def get_session_manager() -> SessionManager:
    """获取全局会话管理器实例（单例模式）"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


# 强追问关键词（明确表示想了解更多/延续对话）
STRONG_FOLLOWUP_KEYWORDS = [
    # 中文
    '更详细', '详细一点', '更多', '还有', '继续', '补充', '具体', '展开',
    '什么意思', '怎么', '为什么', '哪里', '如何',

    # 葡语/英语
    'mais', 'more', 'detalhes', 'details', 'continue', 'explain',
    'onde', 'where', 'como', 'how', 'por que', 'why'
]

# 弱追问关键词（产品属性查询，只有在没有新SKU时才算追问）
WEAK_FOLLOWUP_KEYWORDS = [
    # 中文
    '说明书', '图片', '参数', '规格', '尺寸', '价格', '链接', '多少',

    # 葡语/英语
    'manual', 'imagem', 'image', 'especificações', 'specifications',
    'tamanho', 'size', 'preço', 'price', 'link', 'quanto', 'how much'
]


def is_followup_question(question: str, has_context: bool, last_context: Optional[Dict[str, Any]] = None) -> bool:
    """
    判断是否为追问

    Args:
        question: 用户问题
        has_context: 是否有上下文
        last_context: 上一轮对话内容（可选）

    Returns:
        是否为追问
    """
    if not has_context:
        return False

    # 去除空格和标点
    clean_question = question.strip().lower()

    # 导入SKU提取工具
    from scripts.utils import extract_sku
    current_sku = extract_sku(question)

    # 提取上次对话的SKU
    last_sku = None
    if last_context:
        last_question = last_context.get('question', '')
        last_sku = extract_sku(last_question)

    # 1. 强追问关键词 → 总是追问（即使有SKU）
    for keyword in STRONG_FOLLOWUP_KEYWORDS:
        if keyword in clean_question:
            return True

    # 2. 如果当前问题有SKU
    if current_sku:
        # 2a. 如果SKU与上次相同 → 是追问（询问同一个SKU的不同属性）
        if current_sku == last_sku:
            return True
        # 2b. 如果SKU与上次不同 → 不是追问（新的SKU查询）
        else:
            return False

    # 3. 没有SKU的情况
    # 3a. 弱追问关键词 → 追问
    for keyword in WEAK_FOLLOWUP_KEYWORDS:
        if keyword in clean_question:
            return True

    # 3b. 短问题（少于15个字符）→ 可能是追问
    if len(clean_question) < 15:
        return True

    return False


if __name__ == "__main__":
    # 测试会话管理
    manager = get_session_manager()

    # 添加对话
    manager.add_conversation(
        user_id="test_user",
        chat_id="test_chat",
        question="CBC007的尺寸是多少？",
        answer="CBC007的尺寸是25cm x 15cm x 10cm"
    )

    # 获取上下文
    context = manager.get_context_text("test_user", "test_chat")
    print("对话上下文:")
    print(context)
    print()

    # 测试追问识别
    test_questions = [
        ("更详细一点", True),
        ("还有呢？", True),
        ("说明书在哪里", True),
        ("CBC004-123的价格", False),
        ("这个产品怎么用", True),
    ]

    print("追问识别测试:")
    for q, expected in test_questions:
        result = is_followup_question(q, has_context=True)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{q}' -> {result} (期望: {expected})")
