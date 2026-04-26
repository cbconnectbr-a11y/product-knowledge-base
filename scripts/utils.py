"""
共用工具函数
"""
import re
import os
from typing import Optional, List
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# 初始化 Supabase 客户端
def get_supabase_client() -> Client:
    """获取 Supabase 客户端"""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")
    return create_client(url, key)

# SKU 提取正则表达式（从 tech-qa-extraction 复用）
SKU_PATTERNS = [
    r'([A-Z]{1,4}\d{3,4}[-_]\d{3,4})',  # CBC004-1234, K004-5678
    r'([A-Z]{4}\d{4})',                  # BRME0341
    r'([A-Z]\d{3}[-_]\d{3})',           # K004-123
    r'([A-Z]{3}\d{3})',                 # YMX018, SUB154
]

def extract_sku(text: str) -> Optional[str]:
    """
    从文本中提取 SKU

    Args:
        text: 输入文本

    Returns:
        提取到的 SKU（大写），如果未找到返回 None
    """
    if not text:
        return None

    for pattern in SKU_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None

# 技术问题关键词（从 tech-qa-extraction 复用）
TECH_KEYWORDS = [
    '客户反馈', '客户投诉', '客户说', '客户问', '客户智能投诉',
    '故障', '问题', '损坏', '破损', '缺少', '漏水', '缺失', '断裂',
    '不能', '无法', '不工作', '不加热', '不拉纸', '不升温',
    '什么原因', '如何', '怎么', '可以吗', '怎样', '维修', '解决', '处理',
]

NON_TECH_KEYWORDS = [
    '货柜入仓', '货柜盘点', '找货', '配货异常',
    '要求发', '实际发', '货件', '迟发', '取消'
]

def is_tech_question(text: str) -> bool:
    """
    判断是否为技术问题

    Args:
        text: 输入文本

    Returns:
        是否为技术问题
    """
    if not text:
        return False

    # 先排除非技术关键词
    for keyword in NON_TECH_KEYWORDS:
        if keyword in text:
            return False

    # 检查是否包含技术关键词
    for keyword in TECH_KEYWORDS:
        if keyword in text:
            return True

    return False

def extract_keywords(text: str, max_keywords: int = 5) -> List[str]:
    """
    从文本中提取关键词（简单版本，Phase 1 不使用 AI）

    Args:
        text: 输入文本
        max_keywords: 最大关键词数量

    Returns:
        关键词列表
    """
    if not text:
        return []

    keywords = []

    # 提取技术关键词
    for kw in TECH_KEYWORDS:
        if kw in text and kw not in keywords:
            keywords.append(kw)
            if len(keywords) >= max_keywords:
                break

    # 如果不够，提取常见词汇（简单分词）
    if len(keywords) < max_keywords:
        # 简单分词：按常见分隔符切分
        words = re.findall(r'[一-龥]{2,}', text)
        for word in words:
            if word not in keywords and word not in NON_TECH_KEYWORDS:
                keywords.append(word)
                if len(keywords) >= max_keywords:
                    break

    return keywords[:max_keywords]


# 测试代码
if __name__ == "__main__":
    # 测试用例
    test_text = "客户反馈 CBC004-1234 加热杯漏水，无法正常使用"

    print(f"测试文本: {test_text}")
    print(f"SKU: {extract_sku(test_text)}")
    print(f"是技术问题: {is_tech_question(test_text)}")
    print(f"关键词: {extract_keywords(test_text)}")
