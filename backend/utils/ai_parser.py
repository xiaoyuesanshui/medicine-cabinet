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
4. is_prescription: 是否处方药（true/false）
5. expiry_date: 有效期/过期日期（格式：YYYY-MM-DD，如果只有年月，用该月最后一天）
6. category: 分类（internal=内服, external=外用, topical=局部用药, supplement=保健品, other=其他）
7. manufacturer: 生产厂家
8. dosage: 用法用量
9. approval_number: 批准文号（如国药准字HXXXXXXXX）

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
    """调用AI视觉API直接识别药盒图片"""
    
    # 读取图片并转为base64
    with open(image_path, 'rb') as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    system_prompt = """你是一个药品信息识别专家。请仔细查看这张药盒图片，提取以下信息：

1. name: 药品名称（通用名）
2. ingredients: 主要成分/配料
3. indications: 适应症/功能主治
4. is_prescription: 是否处方药（true/false）
5. expiry_date: 有效期（格式：YYYY-MM-DD）
6. category: 分类（internal=内服, external=外用, topical=局部用药, supplement=保健品, other=其他）
7. manufacturer: 生产厂家
8. dosage: 用法用量
9. approval_number: 批准文号（如国药准字HXXXXXXXX）

请严格返回JSON格式，不要包含任何其他文字。如果某个字段无法从图片中识别，使用null。"""
    
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
        'ingredients': data.get('ingredients', ''),
        'indications': data.get('indications', ''),
        'is_prescription': data.get('is_prescription'),
        'expiry_date': data.get('expiry_date'),
        'category': data.get('category', 'other'),
        'manufacturer': data.get('manufacturer', ''),
        'dosage': data.get('dosage', ''),
        'approval_number': data.get('approval_number', '')
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
