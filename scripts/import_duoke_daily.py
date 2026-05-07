#!/usr/bin/env python3
"""
多客客服日报导入脚本

功能：
- 从 data/duoke/ 目录读取多客客服Excel汇总文件
- 解析客服对话数据
- 提取 SKU、问题、客户意图等信息
- 导入到 knowledge_entries 表
- 自动去重（避免重复导入）
- 处理完成后移动到 archive 目录

使用方法：
1. 从飞书群下载多客汇总文件到 data/duoke/ 目录
2. 运行: python3 scripts/import_duoke_daily.py
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime
from pathlib import Path
import shutil
import re
# from deep_translator import GoogleTranslator  # TODO Phase 2: 添加翻译功能

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_supabase_client, extract_sku
from scripts.clean_content import clean_customer_service_content

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 文件路径
DATA_DIR = Path(__file__).parent.parent / 'data' / 'duoke'
ARCHIVE_DIR = DATA_DIR / 'archive'

def translate_portuguese_to_chinese(text: str, max_length: int = 4500) -> str:
    """
    将葡萄牙语翻译为中文

    Args:
        text: 葡语文本
        max_length: 最大翻译长度（Google Translate 限制约5000字符）

    Returns:
        中文翻译（如果翻译失败，返回原文）
    """
    if not text or pd.isna(text) or len(text.strip()) == 0:
        return ''

    try:
        # 截断过长文本
        text_to_translate = text[:max_length] if len(text) > max_length else text

        # 使用 Google Translator 翻译为中文
        translator = GoogleTranslator(source='pt', target='zh-CN')
        translated = translator.translate(text_to_translate)

        # 如果文本被截断，添加省略号
        if len(text) > max_length:
            translated += '...'

        logger.debug(f"翻译完成: {text[:50]}... -> {translated[:50]}...")
        return translated

    except Exception as e:
        logger.warning(f"翻译失败: {e}，保留原文")
        return text


def find_latest_excel_file():
    """查找最新的 Excel 文件"""
    excel_files = list(DATA_DIR.glob('*.xlsx')) + list(DATA_DIR.glob('*.xls'))
    excel_files = [f for f in excel_files if f.is_file()]

    if not excel_files:
        return None

    # 按修改时间排序，返回最新的
    latest_file = max(excel_files, key=lambda f: f.stat().st_mtime)
    return latest_file


def extract_customer_intent(messages: str, intent: str, key_issue: str) -> tuple:
    """
    从对话中提取客户问题和客服回复

    Args:
        messages: 完整对话消息
        intent: 客户意图
        key_issue: 关键问题

    Returns:
        (问题描述, 完整对话内容)
    """
    if not messages or pd.isna(messages):
        return ('', '')

    # 提取问题描述
    question_parts = []

    # 使用客户意图作为问题标题
    if intent and not pd.isna(intent):
        question_parts.append(intent)

    # 使用关键问题作为补充
    if key_issue and not pd.isna(key_issue):
        question_parts.append(key_issue)

    question = ' | '.join(question_parts) if question_parts else '客户咨询'

    # 完整对话作为内容（保留原始格式）
    content = str(messages)

    return (question, content)


def extract_skus_from_text(text: str) -> list:
    """从文本中提取所有 SKU (包括 JSON 结构中的 skuValue)"""
    if not text or pd.isna(text):
        return []

    text = str(text)
    skus = set()

    # 1. 优先从 JSON 结构中提取 skuValue
    # 匹配 'skuValue': 'CBC004-744' 或 'skuValue': 'CBC004-1300/1306/1308'
    json_sku_pattern = r"['\"]skuValue['\"]:\s*['\"]([A-Z0-9/-]+)['\"]"
    json_matches = re.findall(json_sku_pattern, text, re.IGNORECASE)

    for sku_value in json_matches:
        # 处理组合 SKU 格式: CBC004-1300/1306/1308
        if '/' in sku_value:
            # 提取前缀 (例如: CBC004-)
            prefix_match = re.match(r'^([A-Z]+\d+-)', sku_value)
            if prefix_match:
                prefix = prefix_match.group(1)
                # 分割并重组 SKU
                parts = sku_value.split('/')
                skus.add(parts[0])  # 第一个完整 SKU
                for part in parts[1:]:
                    if part.isdigit():  # 如果是纯数字后缀
                        skus.add(prefix + part)
                    else:
                        skus.add(part)  # 否则当作完整 SKU
            else:
                skus.add(sku_value)
        else:
            skus.add(sku_value)

    # 2. 使用通用 SKU 提取函数
    sku = extract_sku(text)
    if sku:
        skus.add(sku)

    # 3. 提取所有可能的 SKU 模式（CBC004-123, BRME0123, OSA813 等）
    patterns = [
        r'\b[A-Z]{2,4}\d{3,4}-\d{1,4}\b',  # CBC004-1234
        r'\b[A-Z]{4}\d{4}\b',               # BRME0123
        r'\b[A-Z]{3}\d{3,4}\b',             # OSA813, ABC1234
        r'\b[A-Z]\d{3,4}-\d{1,4}\b',       # S004-1234
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        skus.update(matches)

    return list(skus)


def process_duoke_record(row, file_date: str) -> dict:
    """
    处理单条多客记录

    Args:
        row: pandas DataFrame 行
        file_date: 文件日期（用于标识数据来源）

    Returns:
        知识库条目字典
    """
    # 提取 SKU
    product_sku = row.get('productSku', '')
    variation_sku = row.get('variationSku', '')
    messages = row.get('与买家沟通消息', '')

    # 从各字段中提取 SKU
    all_skus = set()
    for field in [product_sku, variation_sku, messages]:
        skus = extract_skus_from_text(str(field))
        all_skus.update(skus)

    # 取第一个 SKU 作为主 SKU
    main_sku = list(all_skus)[0] if all_skus else None

    # 提取问题和对话
    intent = row.get('客户意图', '')
    key_issue = row.get('关键问题', '')
    question, content = extract_customer_intent(messages, intent, key_issue)

    # 构建标题
    title_parts = []
    if main_sku:
        title_parts.append(f"[{main_sku}]")
    title_parts.append(question[:100])
    title = ' '.join(title_parts)

    # TODO Phase 2: 添加葡语翻译功能
    # 当前版本：保留葡语原文 + 客户意图（中文）作为搜索依据

    # 添加元数据到内容
    metadata = []

    buyer = row.get('买家昵称', '')
    if buyer and not pd.isna(buyer):
        metadata.append(f"买家: {buyer}")

    platform = row.get('平台', '')
    if platform and not pd.isna(platform):
        metadata.append(f"平台: {platform}")

    # 客户意图和关键问题（已经是中文）可作为搜索依据
    if intent and not pd.isna(intent):
        metadata.append(f"客户意图: {intent}")

    if key_issue and not pd.isna(key_issue):
        metadata.append(f"关键问题: {key_issue}")

    follow_up = row.get('建议跟进', '')
    if follow_up and not pd.isna(follow_up):
        metadata.append(f"跟进建议: {follow_up}")

    # 组合内容：元数据 + 原始对话
    content_parts = []

    if metadata:
        content_parts.append('\n'.join(metadata))

    content_parts.append(f"## 对话记录\n{content}")

    full_content = '\n\n'.join(content_parts)

    # 清洗内容（移除 JSON 系统消息和无用信息）
    full_content = clean_customer_service_content(full_content)

    # 构建知识库条目
    entry = {
        'sku': main_sku,
        'title': title,
        'content': full_content,
        'source_group': f'多客客服 - {file_date}',
        'source_type': 'customer_service',
        'keywords': list(all_skus)[:5],  # 最多5个关键词
        'status': 'approved'
    }

    return entry


def check_duplicate(client, entry: dict) -> bool:
    """
    检查是否已存在相同记录（基于 title 和 source_group）

    Returns:
        True: 已存在（重复）
        False: 不存在（新数据）
    """
    response = client.table('knowledge_entries') \
        .select('id') \
        .eq('title', entry['title']) \
        .eq('source_group', entry['source_group']) \
        .limit(1) \
        .execute()

    return len(response.data) > 0


def import_duoke_file(file_path: Path):
    """导入多客客服文件"""
    logger.info(f"开始处理文件: {file_path.name}")

    # 读取 Excel 文件
    try:
        # Excel 结构：第0行空，第1行标题，第2行列名，第3行开始数据
        df = pd.read_excel(file_path, header=2)
        logger.info(f"文件包含 {len(df)} 条记录")
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return False

    # 提取文件日期
    file_date = file_path.stem.split('_')[-1] if '_' in file_path.stem else datetime.now().strftime('%Y%m%d')

    # 获取 Supabase 客户端
    client = get_supabase_client()

    # 处理每条记录
    imported = 0
    skipped = 0
    errors = 0

    for idx, row in df.iterrows():
        try:
            # 跳过空行或无效行
            if pd.isna(row.get('与买家沟通消息')):
                continue

            # 处理记录
            entry = process_duoke_record(row, file_date)

            # 检查重复
            if check_duplicate(client, entry):
                skipped += 1
                continue

            # 插入数据库
            response = client.table('knowledge_entries').insert(entry).execute()

            if response.data:
                imported += 1
                if imported % 100 == 0:
                    logger.info(f"已导入 {imported} 条记录...")

        except Exception as e:
            errors += 1
            logger.error(f"处理第 {idx+2} 行失败: {e}")
            continue

    logger.info("=" * 60)
    logger.info(f"导入完成！")
    logger.info(f"  新增: {imported} 条")
    logger.info(f"  跳过: {skipped} 条（重复）")
    logger.info(f"  错误: {errors} 条")
    logger.info("=" * 60)

    # 移动文件到 archive 目录
    try:
        archive_path = ARCHIVE_DIR / file_path.name
        shutil.move(str(file_path), str(archive_path))
        logger.info(f"文件已移动到: {archive_path}")
    except Exception as e:
        logger.warning(f"移动文件失败: {e}")

    return imported > 0


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("多客客服数据导入工具")
    logger.info("=" * 60)

    # 确保目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 查找最新文件
    excel_file = find_latest_excel_file()

    if not excel_file:
        logger.error(f"未在 {DATA_DIR} 目录中找到 Excel 文件")
        logger.info("请将多客客服汇总文件放入该目录后再运行")
        return 1

    logger.info(f"找到文件: {excel_file.name}")
    logger.info(f"文件大小: {excel_file.stat().st_size / 1024 / 1024:.2f} MB")
    logger.info("")

    # 导入文件
    success = import_duoke_file(excel_file)

    if success:
        logger.info("✅ 导入成功！")
        logger.info("现在可以通过飞书机器人搜索客服对话记录了。")
        return 0
    else:
        logger.error("❌ 导入失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())
