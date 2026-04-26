"""
飞书机器人配置管理模块
加载环境变量和飞书表格配置
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ============================================================================
# Supabase 配置
# ============================================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# ============================================================================
# 飞书配置
# ============================================================================

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY")

# 飞书产品信息表
FEISHU_PRODUCT_APP_TOKEN = os.getenv("FEISHU_PRODUCT_APP_TOKEN")
FEISHU_PRODUCT_TABLE_ID = os.getenv("FEISHU_PRODUCT_TABLE_ID")

# 飞书技术群组 ID
FEISHU_TECH_GROUP_IDS_STR = os.getenv("FEISHU_TECH_GROUP_IDS", "")
FEISHU_TECH_GROUP_IDS = [
    gid.strip() for gid in FEISHU_TECH_GROUP_IDS_STR.split(",") if gid.strip()
]

# ============================================================================
# 日志配置
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")

# ============================================================================
# 飞书表格配置加载
# ============================================================================

def load_feishu_tables_config() -> Dict[str, Any]:
    """
    加载飞书表格配置文件

    Returns:
        Dict[str, Any]: 飞书表格配置字典

    Raises:
        FileNotFoundError: 如果配置文件不存在
        json.JSONDecodeError: 如果配置文件格式错误
    """
    config_path = Path(__file__).parent.parent / "config" / "feishu_tables.json"

    if not config_path.exists():
        raise FileNotFoundError(f"飞书表格配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 替换环境变量占位符
    config_str = json.dumps(config)
    config_str = config_str.replace(
        "${FEISHU_PRODUCT_APP_TOKEN}",
        FEISHU_PRODUCT_APP_TOKEN or ""
    )
    config_str = config_str.replace(
        "${FEISHU_PRODUCT_TABLE_ID}",
        FEISHU_PRODUCT_TABLE_ID or ""
    )
    config_str = config_str.replace(
        "${FEISHU_TECH_GROUP_IDS}",
        FEISHU_TECH_GROUP_IDS_STR
    )

    return json.loads(config_str)


# 全局配置实例
try:
    FEISHU_TABLES_CONFIG = load_feishu_tables_config()
except Exception as e:
    print(f"警告: 无法加载飞书表格配置: {e}")
    FEISHU_TABLES_CONFIG = {}

# ============================================================================
# 配置验证
# ============================================================================

def validate_config() -> tuple[bool, List[str]]:
    """
    验证所有必需的配置项

    Returns:
        tuple[bool, List[str]]: (是否有效, 错误消息列表)
    """
    errors = []

    # 验证 Supabase 配置
    if not SUPABASE_URL:
        errors.append("缺少 SUPABASE_URL 环境变量")
    if not SUPABASE_KEY:
        errors.append("缺少 SUPABASE_KEY 环境变量")
    if not SUPABASE_SERVICE_KEY:
        errors.append("缺少 SUPABASE_SERVICE_KEY 环境变量")

    # 验证飞书配置
    if not FEISHU_APP_ID:
        errors.append("缺少 FEISHU_APP_ID 环境变量")
    if not FEISHU_APP_SECRET:
        errors.append("缺少 FEISHU_APP_SECRET 环境变量")
    if not FEISHU_VERIFICATION_TOKEN:
        errors.append("缺少 FEISHU_VERIFICATION_TOKEN 环境变量")
    if not FEISHU_ENCRYPT_KEY:
        errors.append("缺少 FEISHU_ENCRYPT_KEY 环境变量")

    # 验证飞书产品表配置
    if not FEISHU_PRODUCT_APP_TOKEN:
        errors.append("缺少 FEISHU_PRODUCT_APP_TOKEN 环境变量")
    if not FEISHU_PRODUCT_TABLE_ID:
        errors.append("缺少 FEISHU_PRODUCT_TABLE_ID 环境变量")

    # 验证技术群组配置
    if not FEISHU_TECH_GROUP_IDS:
        errors.append("缺少 FEISHU_TECH_GROUP_IDS 环境变量或格式错误")

    # 验证飞书表格配置文件
    if not FEISHU_TABLES_CONFIG:
        errors.append("飞书表格配置文件加载失败")

    return len(errors) == 0, errors


def print_config_summary():
    """打印配置摘要（不显示敏感信息）"""
    print("=" * 60)
    print("配置加载摘要")
    print("=" * 60)

    print("\n[Supabase]")
    print(f"  URL: {SUPABASE_URL[:30]}..." if SUPABASE_URL else "  URL: 未配置")
    print(f"  Key: {'已配置' if SUPABASE_KEY else '未配置'}")
    print(f"  Service Key: {'已配置' if SUPABASE_SERVICE_KEY else '未配置'}")

    print("\n[飞书应用]")
    print(f"  App ID: {FEISHU_APP_ID if FEISHU_APP_ID else '未配置'}")
    print(f"  App Secret: {'已配置' if FEISHU_APP_SECRET else '未配置'}")
    print(f"  Verification Token: {'已配置' if FEISHU_VERIFICATION_TOKEN else '未配置'}")
    print(f"  Encrypt Key: {'已配置' if FEISHU_ENCRYPT_KEY else '未配置'}")

    print("\n[飞书产品表]")
    print(f"  App Token: {FEISHU_PRODUCT_APP_TOKEN if FEISHU_PRODUCT_APP_TOKEN else '未配置'}")
    print(f"  Table ID: {FEISHU_PRODUCT_TABLE_ID if FEISHU_PRODUCT_TABLE_ID else '未配置'}")

    print("\n[飞书技术群组]")
    print(f"  群组数量: {len(FEISHU_TECH_GROUP_IDS)}")
    for i, gid in enumerate(FEISHU_TECH_GROUP_IDS, 1):
        print(f"    群组 {i}: {gid}")

    print("\n[日志配置]")
    print(f"  日志级别: {LOG_LEVEL}")
    print(f"  日志文件: {LOG_FILE}")

    print("\n[飞书表格配置]")
    if FEISHU_TABLES_CONFIG:
        print(f"  产品表配置: {'已加载' if 'product_table' in FEISHU_TABLES_CONFIG else '未加载'}")
        print(f"  技术群配置: {'已加载' if 'tech_groups' in FEISHU_TABLES_CONFIG else '未加载'}")
        print(f"  知识提取配置: {'已加载' if 'knowledge_extraction' in FEISHU_TABLES_CONFIG else '未加载'}")
    else:
        print("  配置文件: 未加载")

    print("\n" + "=" * 60)

    # 验证配置
    is_valid, errors = validate_config()

    if is_valid:
        print("配置验证: 通过")
    else:
        print("配置验证: 失败")
        print("\n错误列表:")
        for error in errors:
            print(f"  - {error}")

    print("=" * 60 + "\n")

    return is_valid


# ============================================================================
# 主程序 - 用于测试配置
# ============================================================================

if __name__ == "__main__":
    """测试配置加载"""
    is_valid = print_config_summary()

    if not is_valid:
        print("请检查 .env 文件和 config/feishu_tables.json 文件")
        exit(1)
    else:
        print("所有配置项已正确加载")
        exit(0)
