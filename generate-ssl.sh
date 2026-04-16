#!/bin/bash
# 生成自签名SSL证书

set -e

echo "🔐 生成自签名SSL证书..."

# 项目目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSL_DIR="$PROJECT_DIR/ssl"

# 创建SSL目录
mkdir -p "$SSL_DIR"

# 生成私钥
openssl genrsa -out "$SSL_DIR/server.key" 2048

# 生成证书签名请求
openssl req -new -key "$SSL_DIR/server.key" -out "$SSL_DIR/server.csr" -subj "/C=CN/ST=Beijing/L=Beijing/O=MedicineCabinet/OU=IT/CN=192.168.50.50"

# 生成自签名证书（有效期365天）
openssl x509 -req -days 365 -in "$SSL_DIR/server.csr" -signkey "$SSL_DIR/server.key" -out "$SSL_DIR/server.crt"

# 删除CSR文件
rm "$SSL_DIR/server.csr"

echo "✅ SSL证书生成完成！"
echo ""
echo "📁 证书位置:"
echo "  证书: $SSL_DIR/server.crt"
echo "  私钥: $SSL_DIR/server.key"
echo ""
echo "⚠️  注意:"
echo "  1. 浏览器会提示证书不安全，点击'高级'->'继续访问'即可"
echo "  2. iPhone需要在Safari中打开，并信任证书"
echo "  3. 证书有效期365天"
