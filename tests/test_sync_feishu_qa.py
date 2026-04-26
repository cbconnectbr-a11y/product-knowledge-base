"""
飞书群问答同步测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import extract_sku, is_tech_question, extract_keywords

def test_extract_sku():
    """测试 SKU 提取"""
    assert extract_sku("CBC004-1234 加热杯") == "CBC004-1234"
    assert extract_sku("K004-5678漏水") == "K004-5678"
    assert extract_sku("BRME0341故障") == "BRME0341"
    assert extract_sku("YMX018不工作") == "YMX018"
    assert extract_sku("没有SKU的文本") is None
    print("✅ test_extract_sku 通过")

def test_is_tech_question():
    """测试技术问题识别"""
    assert is_tech_question("客户反馈加热杯漏水") == True
    assert is_tech_question("产品损坏无法使用") == True
    assert is_tech_question("货柜入仓通知") == False
    assert is_tech_question("普通聊天内容") == False
    print("✅ test_is_tech_question 通过")

def test_extract_keywords():
    """测试关键词提取"""
    keywords = extract_keywords("客户反馈加热杯漏水，无法使用")
    assert "客户反馈" in keywords
    assert "漏水" in keywords
    assert "无法" in keywords
    print("✅ test_extract_keywords 通过")

if __name__ == "__main__":
    test_extract_sku()
    test_is_tech_question()
    test_extract_keywords()
    print("\n所有测试通过！")
