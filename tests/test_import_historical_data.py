"""
Tests for historical data import script
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.import_historical_data import (
    create_source_id,
    extract_entries_from_tech_issues,
    extract_entries_from_tech_qa,
    extract_entries_from_complete_tech_issues,
    validate_entry,
)


class TestSourceIdGeneration:
    """Test source ID generation for deduplication"""

    def test_create_source_id_deterministic(self):
        """Same input should produce same source ID"""
        title = "Test Title"
        content = "Test Content"

        id1 = create_source_id(title, content)
        id2 = create_source_id(title, content)

        assert id1 == id2
        assert id1.startswith("historical_")

    def test_create_source_id_unique(self):
        """Different input should produce different source IDs"""
        id1 = create_source_id("Title 1", "Content 1")
        id2 = create_source_id("Title 2", "Content 2")

        assert id1 != id2


class TestTechIssuesExtraction:
    """Test extraction from tech_issues_filtered_final.json format"""

    def test_extract_basic_issue(self):
        """Test extracting a basic tech issue"""
        data = {
            "tech_issues": [
                {
                    "group": "CBC004",
                    "sku": "S004-1191",
                    "question": "客户投诉收到产品的时候包装完好，但内部断裂了",
                    "message_id": "om_xxx",
                }
            ]
        }

        entries = extract_entries_from_tech_issues(data, "test.json")

        assert len(entries) == 1
        entry = entries[0]

        assert entry['sku'] == "S004-1191"
        assert "S004-1191" in entry['title']
        assert "断裂" in entry['content']
        assert entry['source_type'] == 'manual'
        assert entry['status'] == 'pending'
        assert 'CBC004' in entry['category']

    def test_extract_issue_without_sku(self):
        """Test extracting issue without SKU"""
        data = {
            "tech_issues": [
                {
                    "group": "CBC006",
                    "question": "客户反馈产品有问题",
                }
            ]
        }

        entries = extract_entries_from_tech_issues(data, "test.json")

        assert len(entries) == 1
        assert entries[0]['sku'] is None
        assert "技术问题" in entries[0]['title']

    def test_skip_empty_questions(self):
        """Test that empty questions are skipped"""
        data = {
            "tech_issues": [
                {"sku": "TEST-001", "question": ""},
                {"sku": "TEST-002", "question": "   "},
                {"sku": "TEST-003", "question": "Valid question"},
            ]
        }

        entries = extract_entries_from_tech_issues(data, "test.json")

        assert len(entries) == 1
        assert entries[0]['sku'] == "TEST-003"

    def test_missing_tech_issues_key(self):
        """Test handling missing 'tech_issues' key"""
        data = {"other_key": "value"}

        entries = extract_entries_from_tech_issues(data, "test.json")

        assert len(entries) == 0


class TestTechQAExtraction:
    """Test extraction from 技术支持问答知识库_*.json format"""

    def test_extract_qa_with_reply(self):
        """Test extracting Q&A with reply"""
        data = {
            "questions": [
                {
                    "sku": "BRME0341",
                    "product": "SV608高端真空机120V",
                    "question": "客户反馈真空泵会启动但封口前空气重新进入",
                    "reply": "食物装的太满了，让客户少装点",
                    "category": "使用方法问题",
                    "group": "CBC006",
                }
            ]
        }

        entries = extract_entries_from_tech_qa(data, "test.json")

        assert len(entries) == 1
        entry = entries[0]

        assert entry['sku'] == "BRME0341"
        assert "BRME0341" in entry['title']
        assert "SV608" in entry['title']
        assert "问题：" in entry['content']
        assert "解答：" in entry['content']
        assert "使用方法问题" in entry['category']
        assert "CBC006" in entry['category']

    def test_extract_qa_without_reply(self):
        """Test extracting Q&A without reply"""
        data = {
            "questions": [
                {
                    "sku": "TEST-001",
                    "question": "这是一个问题",
                    "reply": "待补充",
                }
            ]
        }

        entries = extract_entries_from_tech_qa(data, "test.json")

        assert len(entries) == 1
        assert "待补充" in entries[0]['content']

    def test_extract_qa_without_sku(self):
        """Test extracting Q&A without SKU"""
        data = {
            "questions": [
                {
                    "question": "一般性问题",
                    "reply": "一般性回答",
                }
            ]
        }

        entries = extract_entries_from_tech_qa(data, "test.json")

        assert len(entries) == 1
        assert entries[0]['sku'] is None
        assert "技术支持问答" in entries[0]['title']


class TestCompleteTechIssuesExtraction:
    """Test extraction from 技术问题汇总_完整版.json format"""

    def test_extract_complete_issue(self):
        """Test extracting complete tech issue"""
        data = {
            "技术问题列表": [
                {
                    "序号": 1,
                    "群组": "CBC004",
                    "SKU": "S004-1191",
                    "产品名": "紫色带跪垫多功能健腹板",
                    "问题描述": "客户投诉收到产品时包装完好但内部断裂",
                    "问题类型": "运输损坏/产品质量",
                }
            ]
        }

        entries = extract_entries_from_complete_tech_issues(data, "test.json")

        assert len(entries) == 1
        entry = entries[0]

        assert entry['sku'] == "S004-1191"
        assert "健腹板" in entry['title']
        assert "断裂" in entry['content']
        assert "运输损坏/产品质量" in entry['category']
        assert "CBC004" in entry['category']

    def test_skip_empty_descriptions(self):
        """Test that empty descriptions are skipped"""
        data = {
            "技术问题列表": [
                {"SKU": "TEST-001", "问题描述": ""},
                {"SKU": "TEST-002", "问题描述": "Valid description"},
            ]
        }

        entries = extract_entries_from_complete_tech_issues(data, "test.json")

        assert len(entries) == 1
        assert entries[0]['sku'] == "TEST-002"


class TestEntryValidation:
    """Test entry validation logic"""

    def test_valid_entry(self):
        """Test validation of a valid entry"""
        entry = {
            'title': 'Test Title',
            'content': 'Test Content',
            'source_id': 'historical_abc123',
            'sku': 'TEST-001',
        }

        is_valid, error = validate_entry(entry)

        assert is_valid is True
        assert error is None

    def test_missing_title(self):
        """Test validation fails for missing title"""
        entry = {
            'content': 'Test Content',
            'source_id': 'historical_abc123',
        }

        is_valid, error = validate_entry(entry)

        assert is_valid is False
        assert "title" in error

    def test_missing_content(self):
        """Test validation fails for missing content"""
        entry = {
            'title': 'Test Title',
            'source_id': 'historical_abc123',
        }

        is_valid, error = validate_entry(entry)

        assert is_valid is False
        assert "content" in error

    def test_missing_source_id(self):
        """Test validation fails for missing source_id"""
        entry = {
            'title': 'Test Title',
            'content': 'Test Content',
        }

        is_valid, error = validate_entry(entry)

        assert is_valid is False
        assert "source_id" in error

    def test_long_content_warning(self, capsys):
        """Test warning for very long content"""
        entry = {
            'title': 'Test Title',
            'content': 'x' * 6000,  # Over 5000 chars
            'source_id': 'historical_abc123',
        }

        is_valid, error = validate_entry(entry, verbose=True)

        # Should still be valid, just warning
        assert is_valid is True
        assert error is None

        # Check for warning in output
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "6000" in captured.out


class TestDataIntegrity:
    """Test data integrity and deduplication"""

    def test_same_content_produces_same_source_id(self):
        """Test that identical content produces same source_id for deduplication"""
        # Extract same issue twice
        data = {
            "tech_issues": [
                {
                    "sku": "TEST-001",
                    "question": "Duplicate question",
                }
            ]
        }

        entries1 = extract_entries_from_tech_issues(data, "file1.json")
        entries2 = extract_entries_from_tech_issues(data, "file2.json")

        # Should produce same source_id
        assert entries1[0]['source_id'] == entries2[0]['source_id']

    def test_different_content_produces_different_source_id(self):
        """Test that different content produces different source_ids"""
        data1 = {
            "tech_issues": [
                {"sku": "TEST-001", "question": "Question 1"}
            ]
        }
        data2 = {
            "tech_issues": [
                {"sku": "TEST-001", "question": "Question 2"}
            ]
        }

        entries1 = extract_entries_from_tech_issues(data1, "file1.json")
        entries2 = extract_entries_from_tech_issues(data2, "file2.json")

        assert entries1[0]['source_id'] != entries2[0]['source_id']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
