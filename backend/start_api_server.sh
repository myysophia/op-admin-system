#!/bin/bash

set -e

# 确保在脚本所在目录执行，避免相对路径导致的文件缺失问题
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "OP Admin System - Backend API Server"
echo "================================================"
echo ""

# Check Python version
PYTHON_CMD=""
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Python not found! Please install Python 3.11+"
    exit 1
fi

echo "Using Python: $PYTHON_CMD"
$PYTHON_CMD --version

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Virtual environment not found!"
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo ""
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip -q

# Install dependencies
echo "📦 Installing dependencies..."
if ! pip install -r "${SCRIPT_DIR}/requirements.txt"; then
    echo "❌ 依赖安装失败，请检查 requirements.txt 配置"
    exit 1
fi

echo ""
echo "================================================"
echo "✅ Setup Complete! Starting API Server..."
echo "================================================"
echo ""
echo "📡 Swagger UI: http://localhost:8000/api/docs"
echo "📚 ReDoc: http://localhost:8000/api/redoc"
echo "❤️  Health Check: http://localhost:8000/health"
echo ""
echo "🎯 User API Endpoints:"
echo "  GET    /api/v1/users          - Get user list"
echo "  GET    /api/v1/users/{uid}    - Get user detail"
echo "  POST   /api/v1/users/{uid}/ban   - Ban user"
echo "  POST   /api/v1/users/{uid}/unban - Unban user"
echo ""
echo "Press Ctrl+C to stop the server"
echo "================================================"
echo ""

# Start server (using python -m to ensure it runs in venv)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
