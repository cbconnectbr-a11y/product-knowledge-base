#!/bin/bash

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_DIR="/Users/cindy/Projects/product-knowledge-base"
LAUNCHD_DIR="$PROJECT_DIR/launchd"
AGENTS_DIR="$HOME/Library/LaunchAgents"

echo -e "${GREEN}=== 产品知识库定时任务安装 ===${NC}"
echo ""

# 1. 创建 logs 目录
echo "1. 创建日志目录..."
mkdir -p "$PROJECT_DIR/logs"
echo -e "   ${GREEN}✓${NC} 日志目录已创建"
echo ""

# 2. 检查 Python
echo "2. 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: python3 未安装${NC}"
    exit 1
fi
PYTHON_PATH=$(which python3)
echo -e "   ${GREEN}✓${NC} Python 路径: $PYTHON_PATH"

# 验证 Python 版本
PYTHON_VERSION=$(python3 --version)
echo -e "   ${GREEN}✓${NC} $PYTHON_VERSION"
echo ""

# 3. 检查环境变量
echo "3. 检查环境配置..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "   ${YELLOW}⚠${NC} .env 文件不存在"
    echo -e "   请确保配置了 Supabase 和飞书凭证"
else
    echo -e "   ${GREEN}✓${NC} .env 文件存在"
fi

# 检查同步脚本
if [ ! -f "$PROJECT_DIR/scripts/sync_feishu_qa.py" ]; then
    echo -e "   ${RED}✗${NC} sync_feishu_qa.py 不存在"
    exit 1
fi
if [ ! -f "$PROJECT_DIR/scripts/sync_product_table.py" ]; then
    echo -e "   ${RED}✗${NC} sync_product_table.py 不存在"
    exit 1
fi
echo -e "   ${GREEN}✓${NC} 同步脚本已就绪"
echo ""

# 4. 检查 plist 文件
echo "4. 检查 plist 文件..."
if [ ! -f "$LAUNCHD_DIR/com.product-kb.sync-feishu-qa.plist" ]; then
    echo -e "   ${RED}✗${NC} com.product-kb.sync-feishu-qa.plist 不存在"
    exit 1
fi
if [ ! -f "$LAUNCHD_DIR/com.product-kb.sync-products.plist" ]; then
    echo -e "   ${RED}✗${NC} com.product-kb.sync-products.plist 不存在"
    exit 1
fi
echo -e "   ${GREEN}✓${NC} plist 文件已就绪"
echo ""

# 5. 创建 LaunchAgents 目录
echo "5. 准备 LaunchAgents 目录..."
mkdir -p "$AGENTS_DIR"
echo -e "   ${GREEN}✓${NC} $AGENTS_DIR"
echo ""

# 6. 卸载旧任务（如果存在）
echo "6. 卸载旧任务（如果存在）..."
if launchctl list | grep -q "com.product-kb.sync-feishu-qa"; then
    launchctl unload "$AGENTS_DIR/com.product-kb.sync-feishu-qa.plist" 2>/dev/null || true
    echo -e "   ${GREEN}✓${NC} 已卸载旧的问答同步任务"
fi
if launchctl list | grep -q "com.product-kb.sync-products"; then
    launchctl unload "$AGENTS_DIR/com.product-kb.sync-products.plist" 2>/dev/null || true
    echo -e "   ${GREEN}✓${NC} 已卸载旧的产品表同步任务"
fi
echo ""

# 7. 复制 plist 文件
echo "7. 复制 plist 文件到 LaunchAgents..."
cp "$LAUNCHD_DIR/com.product-kb.sync-feishu-qa.plist" "$AGENTS_DIR/"
echo -e "   ${GREEN}✓${NC} com.product-kb.sync-feishu-qa.plist"
cp "$LAUNCHD_DIR/com.product-kb.sync-products.plist" "$AGENTS_DIR/"
echo -e "   ${GREEN}✓${NC} com.product-kb.sync-products.plist"
echo ""

# 8. 加载新任务
echo "8. 加载新任务..."
if launchctl load "$AGENTS_DIR/com.product-kb.sync-feishu-qa.plist"; then
    echo -e "   ${GREEN}✓${NC} 问答同步任务已加载"
else
    echo -e "   ${RED}✗${NC} 问答同步任务加载失败"
    exit 1
fi

if launchctl load "$AGENTS_DIR/com.product-kb.sync-products.plist"; then
    echo -e "   ${GREEN}✓${NC} 产品表同步任务已加载"
else
    echo -e "   ${RED}✗${NC} 产品表同步任务加载失败"
    exit 1
fi
echo ""

# 9. 验证任务状态
echo "9. 验证任务状态..."
echo ""
echo "飞书问答同步任务:"
if launchctl list | grep com.product-kb.sync-feishu-qa; then
    echo -e "${GREEN}✓ 任务已激活${NC}"
else
    echo -e "${RED}✗ 任务未找到${NC}"
fi
echo ""
echo "产品表同步任务:"
if launchctl list | grep com.product-kb.sync-products; then
    echo -e "${GREEN}✓ 任务已激活${NC}"
else
    echo -e "${RED}✗ 任务未找到${NC}"
fi
echo ""

# 10. 完成信息
echo -e "${GREEN}=== 安装完成 ===${NC}"
echo ""
echo "定时任务已配置:"
echo "  - 产品表同步: 每天 8:30"
echo "  - 问答同步: 每天 9:00"
echo ""
echo -e "${YELLOW}手动触发测试:${NC}"
echo "  launchctl start com.product-kb.sync-products"
echo "  launchctl start com.product-kb.sync-feishu-qa"
echo ""
echo -e "${YELLOW}查看日志:${NC}"
echo "  tail -f $PROJECT_DIR/logs/sync-products.log"
echo "  tail -f $PROJECT_DIR/logs/sync-feishu-qa.log"
echo ""
echo -e "${YELLOW}查看错误日志:${NC}"
echo "  tail -f $PROJECT_DIR/logs/sync-products.error.log"
echo "  tail -f $PROJECT_DIR/logs/sync-feishu-qa.error.log"
echo ""
echo -e "${YELLOW}卸载任务:${NC}"
echo "  launchctl unload ~/Library/LaunchAgents/com.product-kb.sync-feishu-qa.plist"
echo "  launchctl unload ~/Library/LaunchAgents/com.product-kb.sync-products.plist"
echo ""
echo -e "${YELLOW}重新加载任务:${NC}"
echo "  bash $PROJECT_DIR/scripts/setup_launchd.sh"
echo ""
