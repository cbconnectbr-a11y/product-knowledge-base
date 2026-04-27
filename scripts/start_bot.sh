#!/bin/bash

# 飞书机器人启动脚本
# Usage: ./scripts/start_bot.sh [port]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 获取脚本所在目录的父目录（项目根目录）
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}===================================${NC}"
echo -e "${GREEN}产品知识库机器人 - 启动脚本${NC}"
echo -e "${GREEN}===================================${NC}"
echo ""

# 检查 .env 文件
if [ ! -f .env ]; then
    echo -e "${RED}错误: .env 文件不存在${NC}"
    echo -e "${YELLOW}提示: 请先复制并配置环境变量${NC}"
    echo "  cp .env.example .env"
    echo "  # 编辑 .env 文件，填入飞书和 Supabase 凭证"
    exit 1
fi

# 检查 Python 版本
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    PYTHON_CMD="python"
    if ! command -v $PYTHON_CMD &> /dev/null; then
        echo -e "${RED}错误: 未找到 Python${NC}"
        exit 1
    fi
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo -e "Python 版本: ${GREEN}$PYTHON_VERSION${NC}"

# 检查依赖
echo ""
echo "检查依赖..."

REQUIRED_PACKAGES=("flask" "lark_oapi" "supabase" "python-dotenv")
MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    if ! $PYTHON_CMD -c "import $package" 2>/dev/null; then
        MISSING_PACKAGES+=("$package")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo -e "${RED}缺少以下依赖:${NC}"
    for package in "${MISSING_PACKAGES[@]}"; do
        echo "  - $package"
    done
    echo ""
    echo -e "${YELLOW}安装依赖:${NC}"
    echo "  pip3 install -r requirements.txt"
    exit 1
fi

echo -e "${GREEN}✓ 依赖检查通过${NC}"

# 验证配置
echo ""
echo "验证配置..."

if $PYTHON_CMD -m bot.config >/dev/null 2>&1; then
    echo -e "${GREEN}✓ 配置验证通过${NC}"
else
    echo -e "${RED}✗ 配置验证失败${NC}"
    echo -e "${YELLOW}请检查 .env 文件中的配置项${NC}"
    exit 1
fi

# 获取端口（从参数或环境变量，默认 5000）
PORT="${1:-${PORT:-5000}}"

# 检查端口是否被占用
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}错误: 端口 $PORT 已被占用${NC}"
    echo "请使用其他端口或停止占用该端口的进程"
    exit 1
fi

echo ""
echo -e "${GREEN}===================================${NC}"
echo -e "服务地址: ${GREEN}http://0.0.0.0:$PORT${NC}"
echo -e "健康检查: ${GREEN}http://localhost:$PORT/health${NC}"
echo -e "Webhook:  ${GREEN}http://your-domain.com/webhook${NC}"
echo -e "${GREEN}===================================${NC}"
echo ""

# 启动服务
echo "启动飞书机器人服务..."
echo -e "${YELLOW}按 Ctrl+C 停止服务${NC}"
echo ""

export PORT=$PORT
exec $PYTHON_CMD -m bot.main
