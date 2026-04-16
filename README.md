# 💊 药品管理系统

基于 Flask + AI 视觉识别的药品管理应用，帮你整理家里的一抽屉药。

## 功能特点

- 📷 **拍照识别**：手机拍药盒，AI 自动提取药品信息（支持批准文号优先查询）
- 📊 **条码扫描**：Zbar 扫描追溯码和69条码，自动调用API获取药品信息
- 💊 **药品管理**：增删改查，支持手动编辑，自定义别名方便记忆
- ⏰ **过期提醒**：首页显示即将过期（30天内）和已过期药品
- 📦 **开封管理**：支持标记开封日期，自动计算开封后保质期
- 📍 **位置编码**：A-Z/1-19 位置编码，方便药品定位
- 🔍 **全文搜索**：药名、成分、适应症快速查找
- 📂 **分类浏览**：内服/外用/局部/保健品分类管理
- 📋 **库存总览**：纯文本列表显示，方便复制粘贴统计
- 🤖 **AI标记**：明确标识AI识别的药品，提醒核查

## 技术栈

- **后端**：Python Flask + SQLAlchemy + SQLite + gunicorn
- **OCR**：腾讯云OCR（可选，提高中文识别准确率）
- **AI解析**：OpenAI兼容API（支持 DeepSeek / Moonshot / 智谱等）
- **条码扫描**：Zbar (zbarimg)
- **药品查询**：极速数据 jisuapi.com API
- **前端**：原生 JavaScript，移动端优化

## 扫描识别流程

系统采用4步扫描流程，按优先级依次尝试：

```
① zbar 扫条码
   ↓ 有追溯码/69条码? → 调用条码API → 直接返回完整数据

② AI 视觉识别
   ↓ 提取18个字段（批准文号优先）

③ API 补全
   ├─ a. AI有批准文号? → 批准文号API覆盖全部字段 ✅
   └─ b. 无批准文号但有名称+信息不全? → 名称API补全

④ 返回结果
```

## 数据字段说明

| 字段 | 说明 | AI识别 | 手动编辑 |
|------|------|--------|---------|
| name | 药品名称 | ✅ 必填 | ✅ |
| approval_number | 批准文号 | ✅ 优先 | ✅ |
| manufacturer | 生产厂家 | ✅ | ✅ |
| specification | 规格 | ✅ | ✅ |
| drug_type | 药品类型 | ✅ | ✅ |
| category | 分类 | ✅ | ✅ |
| ingredients | 成分 | ✅ | ✅ |
| indications | 适应症 | ✅ | ✅ |
| dosage | 用法用量 | ✅ | ✅ |
| adverse_reactions | 不良反应 | ✅ | ✅ |
| contraindications | 禁忌 | ✅ | ✅ |
| precautions | 注意事项 | ✅ | ✅ |
| storage | 贮藏 | ✅ | ✅ |
| description | 说明书 | ✅ | ✅ |
| barcode | 条码 | ✅ | ✅ |
| alias | 别名 | ❌ 禁止 | ✅ 用户自定义 |
| notes | 备注 | ❌ | ✅ |
| location | 位置编码 | ❌ | ✅ |

## 部署指南

### 前置要求

- Linux 服务器（推荐 Debian 12 / Ubuntu 22.04）
- Python 3.9+
- 域名或公网IP（可选，用于HTTPS）

### 1. 克隆项目

```bash
git clone https://github.com/xiaoyuesanshui/medicine-cabinet.git
cd medicine-cabinet
```

### 2. 运行部署脚本

```bash
chmod +x deploy.sh
./deploy.sh
```

部署脚本会自动：
- 安装 Python 依赖
- 安装系统依赖（zbarimg 等）
- 创建数据库
- 配置 systemd 服务

### 3. 配置环境变量

```bash
sudo cp backend/.env.example backend/.env
sudo nano backend/.env
```

填入你的 API Keys：

```env
# AI API配置（OpenAI兼容格式）
AI_API_KEY=your-api-key-here
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o

# 药品查询API（极速数据）
JISU_API_KEY=your-jisu-api-key

# 可选：腾讯云OCR（提高中文识别准确率）
TENCENT_SECRET_ID=your-secret-id
TENCENT_SECRET_KEY=your-secret-key
```

**获取 API Keys：**
- AI API: OpenAI / DeepSeek / Moonshot / 智谱AI 官网注册
- 极速数据: https://www.jisuapi.com 注册
- 腾讯云OCR: https://cloud.tencent.com 注册

### 4. 启动服务

```bash
sudo systemctl enable medicine-cabinet
sudo systemctl start medicine-cabinet
```

### 5. 访问应用

浏览器访问：`http://your-server-ip:5002`

**可选：配置 HTTPS**

```bash
# 安装 certbot
sudo apt install certbot

# 获取证书（需要域名）
sudo certbot certonly --standalone -d yourdomain.com

# 修改 Nginx/Apache 配置使用证书
```

## 本地运行（开发模式）

```bash
# 安装依赖
cd backend
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
nano .env

# 启动开发服务器
python app.py
```

浏览器访问：`http://localhost:5000`

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
│   ├── routes/
│   │   ├── medicines.py    # 药品管理路由
│   │   └── scan.py         # 扫描识别路由
│   ├── utils/
│   │   ├── ai_parser.py    # AI解析
│   │   └── drug_api.py     # 药品API查询
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

- `POST /api/scan` - 上传图片，执行4步扫描流程

### 开封管理

- `POST /api/medicines/:id/open` - 标记药品开封
- `POST /api/medicines/:id/unopen` - 取消开封标记

### 统计

- `GET /api/stats` - 获取统计信息
- `GET /api/version` - 获取系统版本信息

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
4. **条码扫描**：需要安装 `zbarimg` (`apt install zbar-tools`)
5. **AI识别**：建议使用视觉能力强的模型（如 gpt-4o）
6. **别名字段**：AI不会填写别名，留待用户自定义方便记忆的名称

## License

MIT
