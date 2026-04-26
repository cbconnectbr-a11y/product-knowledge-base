"""
配置管理模块
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Supabase 配置
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 飞书配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
FEISHU_VERIFICATION_TOKEN = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.environ.get("FEISHU_ENCRYPT_KEY", "")

# 飞书表格配置
FEISHU_PRODUCT_TABLE_APP_TOKEN = os.environ.get("FEISHU_PRODUCT_TABLE_APP_TOKEN")
FEISHU_PRODUCT_TABLE_TABLE_ID = os.environ.get("FEISHU_PRODUCT_TABLE_TABLE_ID")

# 技术支持群
FEISHU_TECH_GROUPS = [g.strip() for g in os.environ.get("FEISHU_TECH_GROUP_IDS", "").split(",") if g.strip()]

# 日志配置
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE = os.environ.get("LOG_FILE", "logs/app.log")

# 加载飞书表格配置
CONFIG_DIR = Path(__file__).parent.parent / "config"
FEISHU_TABLES_CONFIG_PATH = CONFIG_DIR / "feishu_tables.json"

def load_feishu_tables_config():
    """加载飞书表格配置"""
    if FEISHU_TABLES_CONFIG_PATH.exists():
        with open(FEISHU_TABLES_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

FEISHU_TABLES_CONFIG = load_feishu_tables_config()

# 验证必需配置
def validate_config():
    """验证必需的配置项"""
    required = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
        "FEISHU_APP_ID": FEISHU_APP_ID,
        "FEISHU_APP_SECRET": FEISHU_APP_SECRET,
    }

    missing = [k for k, v in required.items() if not v]

    if missing:
        raise ValueError(f"缺少必需的配置项：{', '.join(missing)}")

    return True

if __name__ == "__main__":
    # 测试配置加载
    try:
        validate_config()
        print("✅ 配置验证通过")
        print(f"   Supabase URL: {SUPABASE_URL}")
        print(f"   Feishu App ID: {FEISHU_APP_ID}")
        print(f"   Tech Groups: {len(FEISHU_TECH_GROUPS)}")
    except ValueError as e:
        print(f"❌ 配置错误：{e}")
        exit(1)
