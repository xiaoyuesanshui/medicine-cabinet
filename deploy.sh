#!/bin/bash
# 药品管理系统部署脚本 for Debian 12
# 支持从任意目录部署

set -e

echo "🚀 开始部署药品管理系统..."

# 获取脚本所在目录（项目根目录）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"

echo "📁 项目目录: $PROJECT_DIR"

# 更新系统
echo "📦 更新系统包..."
sudo apt-get update

# 安装Python和依赖
echo "🐍 安装Python依赖..."
sudo apt-get install -y python3 python3-pip python3-venv tesseract-ocr tesseract-ocr-chi-sim

# 创建虚拟环境
echo "🌐 创建Python虚拟环境..."
cd "$BACKEND_DIR"
python3 -m venv venv
source venv/bin/activate

# 安装Python包
echo "📚 安装Python包..."
pip install --upgrade pip
pip install -r requirements.txt

# 创建上传目录
mkdir -p "$PROJECT_DIR/uploads"
mkdir -p "$PROJECT_DIR/data"

# 复制环境变量模板（如果不存在）
if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo "⚙️  创建环境变量文件..."
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "⚠️  请编辑 $BACKEND_DIR/.env 文件，填入你的API Key"
fi

# 读取环境变量中的端口（如果 .env 存在）
if [ -f "$BACKEND_DIR/.env" ]; then
    PORT=$(grep '^PORT=' "$BACKEND_DIR/.env" | cut -d'=' -f2 | tr -d ' ')
fi
PORT=${PORT:-5000}

# 检查SSL证书
SSL_DIR="$PROJECT_DIR/ssl"
if [ -f "$SSL_DIR/server.crt" ] && [ -f "$SSL_DIR/server.key" ]; then
    echo "🔐 检测到SSL证书，启用HTTPS..."
    SSL_ARGS="--certfile=$SSL_DIR/server.crt --keyfile=$SSL_DIR/server.key"
    PROTOCOL="https"
else
    echo "🌐 未检测到SSL证书，使用HTTP..."
    SSL_ARGS=""
    PROTOCOL="http"
fi

echo "🔧 创建系统服务（端口: $PORT）..."
sudo tee /etc/systemd/system/medicine-cabinet.service > /dev/null << EOF
[Unit]
Description=Medicine Cabinet Management System
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$BACKEND_DIR
Environment=PATH=$BACKEND_DIR/venv/bin
ExecStart=$BACKEND_DIR/venv/bin/gunicorn -w 2 -b 0.0.0.0:$PORT --timeout 120 $SSL_ARGS app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 设置权限
sudo chown -R $USER:$USER "$PROJECT_DIR"

# 重新加载systemd
sudo systemctl daemon-reload

# 启动服务
echo "▶️  启动服务..."
sudo systemctl enable medicine-cabinet
sudo systemctl start medicine-cabinet

echo ""
echo "✅ 部署完成！"
echo ""
echo "📋 后续步骤："
echo "1. 编辑配置文件: nano $BACKEND_DIR/.env"
echo "2. 填入你的AI API Key和其他配置（可选，无Key也能用）"
echo "3. 重启服务: sudo systemctl restart medicine-cabinet"
echo ""
echo "🌐 访问地址: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "📊 服务管理命令："
echo "  查看状态: sudo systemctl status medicine-cabinet"
echo "  重启服务: sudo systemctl restart medicine-cabinet"
echo "  查看日志: sudo journalctl -u medicine-cabinet -f"
