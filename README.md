# 💊 药品管理系统

基于 Flask + 手机拍照的药品管理应用，帮你整理家里的一抽屉药。

## 功能特点

- 📷 **拍照识别**：手机拍药盒，OCR + AI 自动提取药品信息
- 💊 **药品管理**：增删改查，支持手动编辑
- ⏰ **过期提醒**：首页显示即将过期（30天内）和已过期药品
- 🔍 **全文搜索**：药名、成分、适应症快速查找
- 📂 **分类浏览**：内服/外用/局部/保健品分类管理

## 技术栈

- **后端**：Python Flask + SQLAlchemy + SQLite
- **OCR**：Tesseract（本地）+ 腾讯云OCR（可选）
- **AI解析**：OpenAI兼容API（支持 DeepSeek / Moonshot / 智谱等）
- **前端**：原生 JavaScript，移动端优化

## 部署到 Debian 12

### 1. 上传项目到服务器

```bash
scp -r medicine-cabinet/ user@192.168.50.50:/opt/
ssh user@192.168.50.50
```

### 2. 运行部署脚本

```bash
cd /opt/medicine-cabinet
chmod +x deploy.sh
./deploy.sh
```

### 3. 配置环境变量

```bash
sudo nano /opt/medicine-cabinet/backend/.env
```

填入你的 AI API Key：

```env
# AI API配置（OpenAI兼容格式）
AI_API_KEY=your-api-key-here
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o

# 可选：腾讯云OCR（提高中文识别准确率）
TENCENT_SECRET_ID=your-secret-id
TENCENT_SECRET_KEY=your-secret-key
```

### 4. 重启服务

```bash
sudo systemctl restart medicine-cabinet
```

### 5. 手机访问

浏览器访问：`http://192.168.50.50:5000`

## 服务管理

```bash
# 查看状态
sudo systemctl status medicine-cabinet

# 重启服务
sudo systemctl restart medicine-cabinet

# 查看日志
sudo journalctl -u medicine-cabinet -f
```

## 项目结构

```
medicine-cabinet/
├── backend/
│   ├── app.py              # Flask主入口
│   ├── models.py           # 数据库模型
│   ├── utils/
│   │   ├── ocr.py          # OCR识别
│   │   └── ai_parser.py    # AI解析
│   ├── requirements.txt    # Python依赖
│   ├── .env.example        # 环境变量模板
│   └── .gitignore
├── frontend/
│   ├── index.html          # 主页面
│   ├── css/style.css       # 样式
│   └── js/app.js           # 前端逻辑
├── data/                   # 数据库目录
├── uploads/                # 上传图片目录
├── deploy.sh               # 部署脚本
└── README.md
```

## API说明

### 药品管理

- `GET /api/medicines` - 获取药品列表（支持search、category过滤）
- `GET /api/medicines/:id` - 获取单个药品
- `POST /api/medicines` - 创建药品
- `PUT /api/medicines/:id` - 更新药品
- `DELETE /api/medicines/:id` - 删除药品

### 扫描识别

- `POST /api/scan` - 上传图片，OCR+AI识别

### 统计

- `GET /api/stats` - 获取统计信息

## 支持的AI API

任何 OpenAI 兼容格式的 API 都可以使用：

| 服务商 | Base URL |
|--------|----------|
| OpenAI | https://api.openai.com/v1 |
| DeepSeek | https://api.deepseek.com/v1 |
| Moonshot | https://api.moonshot.cn/v1 |
| 智谱AI | https://open.bigmodel.cn/api/paas/v4 |
| 本地部署 | http://localhost:8000/v1 |

## 注意事项

1. **API Key 安全**：通过 `.env` 文件配置，不要硬编码在代码中
2. **图片存储**：上传的药盒照片保存在 `uploads/` 目录
3. **数据库**：SQLite 数据库保存在 `data/medicines.db`
4. **OCR精度**：中文识别需要安装 `tesseract-ocr-chi-sim` 包

## License

MIT
