#!/usr/bin/env python3
"""
Historical Data Import Script for Product Knowledge Base

This script imports historical knowledge entries from JSON files in ~/客服知识库/
into the Supabase knowledge_entries table.

Supported file formats:
1. Tech issues (tech_issues_filtered_final.json) - SKU-specific technical problems
2. Tech support Q&A (技术支持问答知识库_*.json) - Question/answer pairs with categories
3. Complete tech issues (技术问题汇总_完整版.json) - Comprehensive tech issue summaries

Usage:
    # Import all suitable historical data files
    python3 scripts/import_historical_data.py

    # Import specific file
    python3 scripts/import_historical_data.py --file ~/客服知识库/tech_issues_filtered_final.json

    # Dry run (preview without importing)
    python3 scripts/import_historical_data.py --dry-run

    # Verbose output
    python3 scripts/import_historical_data.py --verbose
"""

import json
import hashlib
import argparse
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import sys

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.utils import get_supabase_client, extract_sku


def load_json_file(file_path: str) -> Optional[Dict]:
    """
    Load and parse JSON file with UTF-8 encoding.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data or None if error
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load {file_path}: {e}")
        return None


def create_source_id(title: str, content: str) -> str:
    """
    Generate unique source ID from title and content hash.

    Args:
        title: Entry title
        content: Entry content

    Returns:
        Source ID in format: historical_{hash}
    """
    combined = f"{title}::{content}"
    hash_value = hashlib.md5(combined.encode('utf-8')).hexdigest()[:16]
    return f"historical_{hash_value}"


def extract_entries_from_tech_issues(data: Dict, source_file: str) -> List[Dict]:
    """
    Extract entries from tech_issues_filtered_final.json format.

    Structure:
    {
      "tech_issues": [
        {
          "group": "CBC004",
          "sku": "S004-1191",
          "question": "客户投诉收到产品的时候包装完好，但内部断裂了",
          "message_id": "...",
          ...
        }
      ]
    }

    Args:
        data: Parsed JSON data
        source_file: Source filename for tracking

    Returns:
        List of standardized entry dicts
    """
    entries = []

    if 'tech_issues' not in data:
        print(f"WARNING: No 'tech_issues' key found in {source_file}")
        return entries

    for issue in data['tech_issues']:
        sku = issue.get('sku')
        question = issue.get('question', '').strip()

        if not question:
            continue

        # Use question as both title and content (no answer in this format)
        title = f"{sku} - 技术问题" if sku else "技术问题"
        content = question

        entry = {
            'sku': sku,
            'title': title,
            'content': content,
            'source_type': 'manual',
            'source_id': create_source_id(title, content),
            'source_group': f"历史数据导入 - {source_file}",
            'category': ['技术问题', issue.get('group', '')],
            'keywords': [],
            'status': 'pending',
        }

        entries.append(entry)

    return entries


def extract_entries_from_tech_qa(data: Dict, source_file: str) -> List[Dict]:
    """
    Extract entries from 技术支持问答知识库_*.json format.

    Structure:
    {
      "metadata": {...},
      "questions": [
        {
          "sku": "BRME0341",
          "product": "SV608高端真空机120V 60Hz",
          "question": "客户反馈真空泵会启动...",
          "reply": "食物装的太满了...",
          "category": "使用方法问题",
          "group": "CBC006"
        }
      ]
    }

    Args:
        data: Parsed JSON data
        source_file: Source filename for tracking

    Returns:
        List of standardized entry dicts
    """
    entries = []

    if 'questions' not in data:
        print(f"WARNING: No 'questions' key found in {source_file}")
        return entries

    for qa in data['questions']:
        sku = qa.get('sku')
        product = qa.get('product', '')
        question = qa.get('question', '').strip()
        reply = qa.get('reply', '').strip()
        category = qa.get('category', '')
        group = qa.get('group', '')

        if not question:
            continue

        # Create title from SKU and product
        if sku and product:
            title = f"{sku} - {product}"
        elif sku:
            title = f"{sku} - 技术支持"
        else:
            title = "技术支持问答"

        # Combine question and reply as content
        if reply and reply != "待补充":
            content = f"问题：{question}\n\n解答：{reply}"
        else:
            content = f"问题：{question}\n\n解答：待补充"

        # Build category list
        categories = []
        if category:
            categories.append(category)
        if group:
            categories.append(group)

        entry = {
            'sku': sku,
            'title': title,
            'content': content,
            'source_type': 'manual',
            'source_id': create_source_id(title, content),
            'source_group': f"历史数据导入 - {source_file}",
            'category': categories if categories else [],
            'keywords': [],
            'status': 'pending',
        }

        entries.append(entry)

    return entries


def extract_entries_from_complete_tech_issues(data: Dict, source_file: str) -> List[Dict]:
    """
    Extract entries from 技术问题汇总_完整版.json format.

    Structure:
    {
      "统计概览": {...},
      "技术问题列表": [
        {
          "序号": 1,
          "群组": "CBC004",
          "SKU": "S004-1191",
          "产品名": "紫色带跪垫多功能健腹板",
          "问题描述": "客户投诉...",
          "问题类型": "运输损坏/产品质量",
          ...
        }
      ]
    }

    Args:
        data: Parsed JSON data
        source_file: Source filename for tracking

    Returns:
        List of standardized entry dicts
    """
    entries = []

    if '技术问题列表' not in data:
        print(f"WARNING: No '技术问题列表' key found in {source_file}")
        return entries

    for issue in data['技术问题列表']:
        sku = issue.get('SKU')
        product_name = issue.get('产品名', '')
        problem_desc = issue.get('问题描述', '').strip()
        problem_type = issue.get('问题类型', '')
        group = issue.get('群组', '')

        if not problem_desc:
            continue

        # Create title
        if sku and product_name:
            title = f"{sku} - {product_name}"
        elif sku:
            title = f"{sku} - 技术问题"
        else:
            title = "技术问题"

        # Content is the problem description
        content = problem_desc

        # Build category list
        categories = []
        if problem_type:
            categories.append(problem_type)
        if group:
            categories.append(group)

        entry = {
            'sku': sku,
            'title': title,
            'content': content,
            'source_type': 'manual',
            'source_id': create_source_id(title, content),
            'source_group': f"历史数据导入 - {source_file}",
            'category': categories if categories else [],
            'keywords': [],
            'status': 'pending',
        }

        entries.append(entry)

    return entries


def validate_entry(entry: Dict, verbose: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate entry before import.

    Args:
        entry: Entry dict to validate
        verbose: Print validation details

    Returns:
        (is_valid, error_message)
    """
    # Required fields
    if not entry.get('title'):
        return False, "Missing title"
    if not entry.get('content'):
        return False, "Missing content"
    if not entry.get('source_id'):
        return False, "Missing source_id"

    # Warn on long content (not error)
    content_len = len(entry['content'])
    if content_len > 5000 and verbose:
        print(f"  WARNING: Content length {content_len} chars (title: {entry['title'][:50]}...)")

    return True, None


def import_entries(
    entries: List[Dict],
    source_description: str,
    dry_run: bool = False,
    verbose: bool = False
) -> Dict[str, int]:
    """
    Batch insert entries into Supabase knowledge_entries table.

    Args:
        entries: List of entry dicts
        source_description: Description for logging
        dry_run: If True, don't actually insert
        verbose: Print detailed progress

    Returns:
        Dict with statistics: {'inserted': N, 'skipped': N, 'errors': N}
    """
    stats = {'inserted': 0, 'skipped': 0, 'errors': 0}

    if not entries:
        print(f"  No entries to import from {source_description}")
        return stats

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Importing {len(entries)} entries from {source_description}...")

    if dry_run:
        for entry in entries:
            is_valid, error = validate_entry(entry, verbose)
            if is_valid:
                stats['inserted'] += 1
                if verbose:
                    print(f"  [VALID] {entry['title']}")
            else:
                stats['errors'] += 1
                print(f"  [INVALID] {entry['title']}: {error}")
        return stats

    # Real import
    try:
        supabase = get_supabase_client()

        for i, entry in enumerate(entries, 1):
            # Validate first
            is_valid, error = validate_entry(entry, verbose)
            if not is_valid:
                stats['errors'] += 1
                print(f"  ERROR: Skipping invalid entry: {error}")
                continue

            try:
                # Try to insert
                supabase.table('knowledge_entries').insert(entry).execute()
                stats['inserted'] += 1

                if verbose or (i % 10 == 0):
                    print(f"  [{i}/{len(entries)}] Inserted: {entry['title'][:60]}...")

            except Exception as e:
                error_msg = str(e)
                # Check if it's a duplicate (unique constraint violation)
                if 'unique_source' in error_msg or 'duplicate' in error_msg.lower():
                    stats['skipped'] += 1
                    if verbose:
                        print(f"  [SKIP] Duplicate: {entry['title'][:60]}...")
                else:
                    stats['errors'] += 1
                    print(f"  ERROR: Failed to insert {entry['title'][:60]}: {error_msg}")

    except Exception as e:
        print(f"ERROR: Failed to connect to Supabase: {e}")
        stats['errors'] = len(entries)
        return stats

    # Print summary for this file
    print(f"  ✓ Inserted: {stats['inserted']}, Skipped (duplicates): {stats['skipped']}, Errors: {stats['errors']}")

    return stats


def find_suitable_files(knowledge_base_dir: Path) -> List[Tuple[str, str]]:
    """
    Find suitable JSON files for import in knowledge base directory.

    Returns:
        List of (file_path, file_type) tuples
    """
    suitable_files = []

    # Define file patterns and their types
    file_patterns = [
        ('tech_issues_filtered_final.json', 'tech_issues'),
        ('技术支持问答知识库_*.json', 'tech_qa'),
        ('技术问题汇总_完整版.json', 'complete_tech_issues'),
    ]

    for pattern, file_type in file_patterns:
        if '*' in pattern:
            # Glob pattern
            prefix = pattern.split('*')[0]
            for file_path in knowledge_base_dir.glob(pattern):
                suitable_files.append((str(file_path), file_type))
        else:
            # Exact match
            file_path = knowledge_base_dir / pattern
            if file_path.exists():
                suitable_files.append((str(file_path), file_type))

    return suitable_files


def main():
    parser = argparse.ArgumentParser(
        description='Import historical knowledge entries from JSON files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--file',
        help='Import specific JSON file (default: auto-discover suitable files)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview import without actually inserting data'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed progress'
    )

    args = parser.parse_args()

    # Determine knowledge base directory
    knowledge_base_dir = Path.home() / '客服知识库'
    if not knowledge_base_dir.exists():
        print(f"ERROR: Knowledge base directory not found: {knowledge_base_dir}")
        return 1

    print(f"{'='*70}")
    print(f"Historical Data Import - Product Knowledge Base")
    print(f"{'='*70}")
    print(f"Knowledge base directory: {knowledge_base_dir}")
    print(f"Mode: {'DRY RUN (preview only)' if args.dry_run else 'LIVE IMPORT'}")
    print(f"{'='*70}\n")

    # Determine files to process
    if args.file:
        # Single file mode
        if not os.path.exists(args.file):
            print(f"ERROR: File not found: {args.file}")
            return 1

        # Auto-detect file type from filename
        filename = os.path.basename(args.file)
        if 'tech_issues_filtered' in filename:
            file_type = 'tech_issues'
        elif '技术支持问答知识库' in filename:
            file_type = 'tech_qa'
        elif '技术问题汇总' in filename:
            file_type = 'complete_tech_issues'
        else:
            print(f"ERROR: Cannot determine file type for: {filename}")
            print("Supported files: tech_issues_filtered_final.json, 技术支持问答知识库_*.json, 技术问题汇总_完整版.json")
            return 1

        files_to_process = [(args.file, file_type)]
    else:
        # Auto-discovery mode
        files_to_process = find_suitable_files(knowledge_base_dir)

        if not files_to_process:
            print("WARNING: No suitable files found for import.")
            print(f"Looking for: tech_issues_filtered_final.json, 技术支持问答知识库_*.json, 技术问题汇总_完整版.json")
            return 0

    print(f"Found {len(files_to_process)} file(s) to process:\n")
    for file_path, file_type in files_to_process:
        print(f"  - {os.path.basename(file_path)} [{file_type}]")
    print()

    # Process each file
    total_stats = {'inserted': 0, 'skipped': 0, 'errors': 0}

    for file_path, file_type in files_to_process:
        filename = os.path.basename(file_path)
        print(f"\n{'='*70}")
        print(f"Processing: {filename}")
        print(f"{'='*70}")

        # Load JSON
        data = load_json_file(file_path)
        if data is None:
            print(f"  ERROR: Failed to load file, skipping...")
            total_stats['errors'] += 1
            continue

        # Extract entries based on file type
        if file_type == 'tech_issues':
            entries = extract_entries_from_tech_issues(data, filename)
        elif file_type == 'tech_qa':
            entries = extract_entries_from_tech_qa(data, filename)
        elif file_type == 'complete_tech_issues':
            entries = extract_entries_from_complete_tech_issues(data, filename)
        else:
            print(f"  ERROR: Unknown file type: {file_type}")
            continue

        print(f"  Extracted {len(entries)} entries")

        # Import entries
        if entries:
            stats = import_entries(entries, filename, args.dry_run, args.verbose)
            total_stats['inserted'] += stats['inserted']
            total_stats['skipped'] += stats['skipped']
            total_stats['errors'] += stats['errors']

    # Final summary
    print(f"\n{'='*70}")
    print(f"FINAL SUMMARY")
    print(f"{'='*70}")
    print(f"Files processed: {len(files_to_process)}")
    print(f"Entries inserted: {total_stats['inserted']}")
    print(f"Entries skipped (duplicates): {total_stats['skipped']}")
    print(f"Errors: {total_stats['errors']}")
    print(f"{'='*70}\n")

    if args.dry_run:
        print("NOTE: This was a dry run. No data was actually imported.")
        print("Run without --dry-run to perform actual import.\n")

    return 0 if total_stats['errors'] == 0 else 1


if __name__ == '__main__':
    exit(main())
