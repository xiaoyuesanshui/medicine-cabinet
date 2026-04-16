"""
AI解析模块 - 将OCR识别的文字解析为结构化药品信息
支持：OpenAI兼容API（DeepSeek, Moonshot, 智谱等）
"""

import os
import json
import base64
import requests
from datetime import datetime


def parse_medicine_info(raw_text: str, image_path: str = None) -> dict:
    """
    使用AI解析药品信息
    如果提供了图片路径，优先使用AI视觉识别
    返回结构化字典
    """
    api_key = os.getenv('AI_API_KEY')
    base_url = os.getenv('AI_BASE_URL', 'https://api.openai.com/v1')
    model = os.getenv('AI_MODEL', 'gpt-4o')
    
    if not api_key:
        # 没有API Key时返回基础解析
        return fallback_parse(raw_text)
    
    try:
        # 如果提供了图片且模型支持视觉，使用视觉识别
        if image_path and os.path.exists(image_path):
            return call_ai_vision(image_path, api_key, base_url, model)
        else:
            return call_ai_api(raw_text, api_key, base_url, model)
    except Exception as e:
        print(f"AI API调用失败: {e}")
        return fallback_parse(raw_text)


def extract_codes_from_image(image_path: str, api_key: str, base_url: str, model: str) -> dict:
    """
    使用AI从图片中提取追溯码和批准文号
    专门用于识别数字/字母编码
    """
    import base64
    
    with open(image_path, 'rb') as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    system_prompt = """你是一个药品编码识别专家。请仔细查看这张药品包装图片，提取以下信息：

1. 追溯码：20位数字，通常以869开头，可能在条形码下方
2. 批准文号：格式为"国药准字"+1位字母(H/Z/S/J)+8位数字
3. 药品名称
4. 生产厂家

请严格返回JSON格式：
{
    "traceability_code": "追溯码或null",
    "approval_number": "批准文号或null", 
    "name": "药品名称或null",
    "manufacturer": "厂家或null"
}

只返回JSON，不要其他文字。如果某个信息找不到，用null。"""
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{image_base64}'}}
            ]}
        ],
        'temperature': 0.1,
        'max_tokens': 500
    }
    
    response = requests.post(
        f'{base_url}/chat/completions',
        headers=headers,
        json=payload,
        timeout=30
    )
    
    response.raise_for_status()
    result = response.json()
    content = result['choices'][0]['message']['content']
    
    # 解析JSON
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            raise Exception(f"无法解析AI返回: {content}")
    
    return {
        'traceability_code': parsed.get('traceability_code'),
        'approval_number': parsed.get('approval_number'),
        'name': parsed.get('name', ''),
        'manufacturer': parsed.get('manufacturer', '')
    }


def call_ai_api(raw_text: str, api_key: str, base_url: str, model: str) -> dict:
    """调用AI API解析药品信息"""
    
    system_prompt = """你是一个药品信息提取专家。请从用户提供的药盒OCR文字中，提取以下字段：

1. name: 药品名称（通用名，不是商品名）
2. ingredients: 主要成分
3. indications: 适应症/功能主治
4. is_prescription: 是否处方药（判断规则：看到"OTC"标识或"非处方药"字样→填false；看到"RX"标识或"处方药"字样→填true；无法确定→填null）
5. expiry_date: 有效期/过期日期（格式：YYYY-MM-DD，如果只有年月，用该月最后一天）
6. category: 分类（internal=内服, external=外用, topical=局部用药, supplement=保健品, other=其他）
7. manufacturer: 生产厂家
8. dosage: 用法用量
9. approval_number: 批准文号（如国药准字HXXXXXXXX）

【重要】alias（别名）是用户自定义标签，AI不要填写此字段。

请严格返回JSON格式，不要包含任何其他文字。如果某个字段无法确定，使用null或空字符串。
"""
    
    user_prompt = f"请从以下药盒文字中提取药品信息：\n\n{raw_text}"
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'temperature': 0.3,
        'response_format': {'type': 'json_object'}
    }
    
    response = requests.post(
        f'{base_url}/chat/completions',
        headers=headers,
        json=payload,
        timeout=30
    )
    
    response.raise_for_status()
    result = response.json()
    
    # 解析返回的JSON
    content = result['choices'][0]['message']['content']
    parsed = json.loads(content)
    
    # 标准化字段
    return normalize_parsed_data(parsed)


def fallback_parse(raw_text: str) -> dict:
    """没有AI API时的备用解析（基于规则）"""
    import re
    
    result = {
        'name': '',
        'ingredients': '',
        'indications': '',
        'is_prescription': None,
        'expiry_date': None,
        'category': 'other',
        'manufacturer': '',
        'dosage': '',
        'approval_number': ''
    }
    
    lines = raw_text.split('\n')
    
    # 尝试提取药品名称（通常在第一行或包含"片"、"胶囊"、"颗粒"等）
    for line in lines[:5]:
        if any(suffix in line for suffix in ['片', '胶囊', '颗粒', '口服液', '注射液', '软膏', '滴眼液']):
            result['name'] = line.strip()
            break
    
    if not result['name'] and lines:
        result['name'] = lines[0].strip()
    
    # 提取批准文号
    approval_match = re.search(r'国药准字[HZSJ][a-zA-Z0-9]+', raw_text)
    if approval_match:
        result['approval_number'] = approval_match.group()
        # 根据批准文号判断处方药
        if 'H' in result['approval_number'] or 'Z' in result['approval_number']:
            # 化学药和中成药，需要进一步判断
            pass
    
    # 提取有效期
    date_patterns = [
        r'有效期[至到]?\s*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})',
        r'(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})\s*至',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, raw_text)
        if match:
            year, month, day = match.groups()
            result['expiry_date'] = f"{year}-{int(month):02d}-{int(day):02d}"
            break
    
    # 提取生产厂家（通常包含"公司"、"厂"、"药业"等）
    for line in lines:
        if any(keyword in line for keyword in ['公司', '药业', '制药厂', '集团']):
            if len(line) < 50:  # 厂家名通常不会太长
                result['manufacturer'] = line.strip()
                break
    
    # 判断分类
    if any(word in raw_text for word in ['外用', '软膏', '乳膏', '喷剂', '贴膏']):
        result['category'] = 'external'
    elif any(word in raw_text for word in ['滴眼液', '滴鼻液', '滴耳液', '栓剂']):
        result['category'] = 'topical'
    elif any(word in raw_text for word in ['维生素', '钙片', '保健品', '保健食品']):
        result['category'] = 'supplement'
    elif any(word in raw_text for word in ['口服', '片', '胶囊', '颗粒', '口服液']):
        result['category'] = 'internal'
    
    # 判断是否处方药（简单规则）
    if 'RX' in raw_text.upper() or '处方药' in raw_text or '凭处方' in raw_text:
        result['is_prescription'] = True
    elif 'OTC' in raw_text.upper() or '非处方药' in raw_text:
        result['is_prescription'] = False
    
    return result


def call_ai_vision(image_path: str, api_key: str, base_url: str, model: str) -> dict:
    """调用AI视觉API直接识别药盒图片（完整版）"""
    
    # 读取图片并转为base64
    with open(image_path, 'rb') as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    system_prompt = """你是一个专业的药品信息识别专家，专门用于识别中国药品包装并提取完整信息。

## 识别原则（重要！请严格按此优先级执行）
- **第一优先级：找到批准文号！** 这是最关键的字段。批准文号格式固定为"国药准字"+1位字母(H/Z/S/J)+8位数字，如"国药准字H20230001"。图片上通常在正面或侧面，字体较小。务必仔细寻找。
- 药品名称通常是包装正面最大最醒目的文字
- 如果图片只拍到部分包装（如只有批准文号区域），也要尽力提取可见信息
- 批准文号比条码更重要——即使没有药品名称，只要有批准文号就能查到完整信息
- 条形码通常为13位数字（EAN-13，以69开头），或20位药品本位码（以869开头）
- 有效期通常标注为"有效期XX个月"
- 如果图片模糊或文字被遮挡，尽量推断但标记为低置信度

## 需要提取的字段（共18个）

### 基础信息（6个）
1. name: 药品通用名（必填，如"阿莫西林胶囊"、"布洛芬缓释胶囊"）
2. alias: ⚠️⚠️⚠️ 严格禁止！此字段必须始终填 null。绝对不要填任何文字。alias是用户个人记忆标签（如"感冒药1"、"爸爸的胃药"），与药品包装上的商品名/品牌名/商标完全无关。无论包装上写什么商品名，都不要填入此字段。此字段永远为null。
3. specification: 包装规格（如"0.25g×12粒/盒"、"10ml×10支"、"15g:15mg×6袋/盒"）
4. drug_type: 剂型标准名称（选值：片剂/胶囊剂/颗粒剂/口服溶液剂/注射剂/软膏剂/乳膏剂/凝胶剂/滴眼剂/栓剂/散剂/酊剂/气雾剂/其他）
5. barcode: 条形码或药品本位码（纯数字，没有则填null）
6. approval_number: 批准文号（完整字符串，没有则填null）

### 生产与分类（3个）
7. manufacturer: 生产厂家全称（如"华润三九医药股份有限公司"）
8. is_prescription: 是否处方药（判断规则：看到"OTC"标识或"非处方药"字样→填false；看到"RX"标识或"处方药"字样→填true；无法确定→填null）
9. category: 用药途径分类（internal=口服内服 / external=皮肤外用 / topical=黏膜局部(眼耳鼻口肛) / supplement=保健食品 / other=其他）

### 成分与功效（2个）
10. ingredients: 主要成分及含量（如"每片含布洛芬0.3g"）
11. indications: 适应症或功能主治（简洁描述治什么病，不超过100字）

### 用法与安全（5个）
12. dosage: 用法用量（如"口服，成人一次1片，一日3次，饭后服用"）
13. adverse_reactions: 不良反应（列出已知副作用，没有则填null）
14. contraindications: 禁忌（禁用人群和情况，没有则填null）
15. precautions: 注意事项（重要提醒，没有则填null）
16. storage: 贮藏条件（如"密封，在干燥处保存"）

### 保质期（2个）
17. shelf_life: 有效期时长（如"36个月"、"24个月"，只写数字+单位）
18. description: 完整说明书原文（尽可能保留图片上所有说明性文字，包含用法用量、不良反应、禁忌、注意事项、贮藏、包装等信息。如果文字太多可省略重复内容，但保留关键信息。用换行符分隔不同段落）

## 返回要求
- 严格返回合法JSON格式，不要加markdown代码块标记
- 所有字段均为字符串，布尔字段(is_prescription)使用true/false/null
- 无法识别的字段填null，不要编造或猜测
- name是唯一必须字段，如果完全无法识别药品名称，name填"未知药品"
"""
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': model,
        'messages': [
            {
                'role': 'system',
                'content': system_prompt
            },
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:image/jpeg;base64,{image_base64}'
                        }
                    }
                ]
            }
        ],
        'temperature': 0.3,
        'max_tokens': 2000
    }
    
    response = requests.post(
        f'{base_url}/chat/completions',
        headers=headers,
        json=payload,
        timeout=60
    )
    
    response.raise_for_status()
    result = response.json()
    
    # 解析返回的内容
    content = result['choices'][0]['message']['content']
    
    # 尝试提取JSON
    try:
        # 如果返回的是JSON字符串
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # 尝试从文本中提取JSON
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            raise Exception(f"无法解析AI返回的内容: {content}")
    
    return normalize_parsed_data(parsed)


def normalize_parsed_data(data: dict) -> dict:
    """标准化解析后的数据"""
    # 确保所有字段存在
    result = {
        'name': data.get('name', ''),
        'alias': data.get('alias', ''),
        'specification': data.get('specification', ''),
        'drug_type': data.get('drug_type', ''),
        'ingredients': data.get('ingredients', ''),
        'indications': data.get('indications', ''),
        'description': data.get('description', ''),
        'is_prescription': data.get('is_prescription'),
        'expiry_date': data.get('expiry_date'),
        'category': data.get('category', 'other'),
        'manufacturer': data.get('manufacturer', ''),
        'dosage': data.get('dosage', ''),
        'approval_number': data.get('approval_number', ''),
        'barcode': data.get('barcode', ''),
        'shelf_life': data.get('shelf_life', ''),
        'adverse_reactions': data.get('adverse_reactions', ''),
        'contraindications': data.get('contraindications', ''),
        'precautions': data.get('precautions', ''),
        'storage': data.get('storage', ''),
    }
    
    # 验证日期格式
    if result['expiry_date']:
        try:
            datetime.strptime(result['expiry_date'], '%Y-%m-%d')
        except ValueError:
            result['expiry_date'] = None
    
    # 验证分类
    valid_categories = ['internal', 'external', 'topical', 'supplement', 'other']
    if result['category'] not in valid_categories:
        result['category'] = 'other'
    
    # 标准化is_prescription
    if result['is_prescription'] is not None:
        result['is_prescription'] = bool(result['is_prescription'])
    
    return result
