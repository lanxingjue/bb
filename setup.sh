#!/usr/bin/env bash
# setup.sh — 新机器一键部署
# 用法: bash setup.sh

set -e

echo "========================================"
echo "  策略回测系统 — 一键部署"
echo "========================================"
echo ""

# 检测 Python
if ! command -v python3 &>/dev/null; then
    echo "❌ 需要 Python 3.10+"
    exit 1
fi
echo "✅ Python $(python3 --version | cut -d' ' -f2)"

# 检测 Node.js
if ! command -v node &>/dev/null; then
    echo "❌ 需要 Node.js 18+"
    exit 1
fi
echo "✅ Node.js $(node --version | cut -d'v' -f2)"

echo ""

# 1. Freqtrade 引擎
echo "📥 安装 Freqtrade 引擎..."
cd btc/freqtrade
if [ ! -f ".venv/bin/python" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt -q
pip install -e . -q
echo "   ✅ Freqtrade 就绪"
cd ../..

# 2. 前端依赖
echo "📥 安装前端依赖..."
npm --prefix btc/frontend install --silent 2>/dev/null
echo "   ✅ 前端就绪"

# 3. 数据
echo ""
echo "📊 检查数据..."
DATA_DIR="btc/freqtrade/user_data/data"
if ls $DATA_DIR/*/*.feather 2>/dev/null | head -1 >/dev/null 2>&1; then
    echo "   ✅ 已有数据"
else
    echo "   ⚠️  无数据，生成模拟数据..."
    cd btc
    source freqtrade/.venv/bin/activate
    python scripts/generate_data.py
    cd ..
    echo "   ✅ 模拟数据已生成"
fi

echo ""
echo "========================================"
echo "  ✅ 部署完成！启动系统："
echo "========================================"
echo ""
echo "  # 终端 1: 后端"
echo "  cd btc && source freqtrade/.venv/bin/activate && python backend/main.py"
echo ""
echo "  # 终端 2: 前端"
echo "  cd btc && npm --prefix frontend run dev"
echo ""
echo "  浏览器打开 http://localhost:3000"
echo "========================================"
