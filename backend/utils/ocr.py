"""
OCR识别模块
支持：Tesseract本地识别 + 腾讯云OCR（可选）
"""

import os
import re
import requests
import shutil
from PIL import Image
import pytesseract

# 自动检测 Tesseract 路径
_tesseract_cmd = None
def get_tesseract_cmd():
    global _tesseract_cmd
    if _tesseract_cmd is None:
        # 尝试常见路径
        paths = [
            '/opt/homebrew/bin/tesseract',  # macOS Homebrew (Apple Silicon)
            '/usr/local/bin/tesseract',      # macOS Homebrew (Intel)
            '/usr/bin/tesseract',            # Linux
        ]
        for path in paths:
            if os.path.exists(path):
                _tesseract_cmd = path
                break
        if _tesseract_cmd is None:
            # 尝试从 PATH 查找
            _tesseract_cmd = shutil.which('tesseract') or '/usr/bin/tesseract'
    return _tesseract_cmd

pytesseract.pytesseract.tesseract_cmd = get_tesseract_cmd()


def extract_text_from_image(image_path: str) -> str:
    """
    从图片中提取文字
    优先尝试腾讯云OCR（如果配置了），否则使用Tesseract
    """
    # 尝试腾讯云OCR
    tencent_secret_id = os.getenv('TENCENT_SECRET_ID')
    tencent_secret_key = os.getenv('TENCENT_SECRET_KEY')
    
    if tencent_secret_id and tencent_secret_key:
        try:
            return tencent_ocr(image_path, tencent_secret_id, tencent_secret_key)
        except Exception as e:
            print(f"腾讯云OCR失败，回退到Tesseract: {e}")
    
    # 使用Tesseract本地识别
    return tesseract_ocr(image_path)


def tesseract_ocr(image_path: str) -> str:
    """使用Tesseract进行OCR识别，带图像预处理和多角度检测（优化版）"""
    try:
        # 打开图片
        image = Image.open(image_path)

        # 转换为RGB（处理各种格式）
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # 优化：缩小图片尺寸，提高处理速度
        max_size = 1200
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            image = image.resize(new_size, Image.LANCZOS)

        # 尝试多个旋转角度和PSM模式，选择识别结果最好的
        best_text = ""
        best_score = 0
        
        angles = [0, 90, 180, 270]
        psms = [6, 3, 11]  # 尝试多种PSM模式
        
        for angle in angles:
            if angle == 0:
                rotated = image
            else:
                rotated = image.rotate(angle, expand=True)
            
            for psm in psms:
                text = pytesseract.image_to_string(
                    rotated,
                    lang='chi_sim+eng',
                    config=f'--psm {psm}'
                )
                
                # 评分：中文字符 + 英文单词 + 数字
                chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', text))
                english_words = len(re.findall(r'[a-zA-Z]{3,}', text))
                numbers = len(re.findall(r'\d+', text))
                score = chinese_chars * 3 + english_words * 2 + numbers
                
                if score > best_score:
                    best_score = score
                    best_text = text
                
                # 如果已经识别到足够多的内容，提前结束
                if score >= 40:
                    break
            
            if best_score >= 40:
                break
        
        result = clean_text(best_text)
        chinese_count = len(re.findall(r'[\u4e00-\u9fa5]', result))
        print(f"OCR结果: {len(result)}字符 (识别到{chinese_count}个汉字)")

        return result
    except Exception as e:
        raise Exception(f"Tesseract识别失败: {str(e)}")


def preprocess_optimized(image):
    """优化的预处理 - 只做必要的增强，提高速度"""
    from PIL import ImageEnhance, ImageFilter

    # 转换为灰度
    image = image.convert('L')

    # 轻微增强对比度（不要过度增强，会损失文字）
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)

    # 轻微锐化
    image = image.filter(ImageFilter.SHARPEN)

    return image


def preprocess_for_text(image):
    """标准文本预处理（保留用于兼容）"""
    return preprocess_optimized(image)


def preprocess_for_numbers(image):
    """针对数字的预处理（保留用于兼容）"""
    return preprocess_optimized(image)


def preprocess_high_contrast(image):
    """高对比度预处理（保留用于兼容）"""
    return preprocess_optimized(image)


def tencent_ocr(image_path: str, secret_id: str, secret_key: str) -> str:
    """腾讯云OCR - 通用印刷体识别"""
    import json
    import base64
    import hashlib
    import hmac
    import time
    
    # 读取图片并base64编码
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    
    # 构建请求参数
    params = {
        'ImageBase64': image_data,
    }
    
    # 腾讯云API签名（简化版，实际需要完整签名流程）
    # 这里使用通用的HTTP请求方式
    url = 'https://ocr.tencentcloudapi.com/?Action=GeneralBasicOCR'
    
    headers = {
        'Content-Type': 'application/json',
        'X-TC-Action': 'GeneralBasicOCR',
        'X-TC-Version': '2018-11-19',
        'X-TC-Timestamp': str(int(time.time())),
    }
    
    # 注意：完整实现需要腾讯云SDK或手动签名
    # 这里简化处理，实际使用建议安装 tencentcloud-sdk-python
    try:
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.ocr.v20181119 import ocr_client, models
        
        cred = credential.Credential(secret_id, secret_key)
        httpProfile = HttpProfile()
        httpProfile.endpoint = "ocr.tencentcloudapi.com"
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile
        client = ocr_client.OcrClient(cred, "ap-beijing", clientProfile)
        
        req = models.GeneralBasicOCRRequest()
        req.ImageBase64 = image_data
        
        resp = client.GeneralBasicOCR(req)
        
        # 提取文字
        texts = []
        for item in resp.TextDetections:
            texts.append(item.DetectedText)
        
        return '\n'.join(texts)
        
    except ImportError:
        raise Exception("未安装腾讯云SDK，请运行: pip install tencentcloud-sdk-python")


def clean_text(text: str) -> str:
    """清理OCR识别的文本"""
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text)
    # 移除特殊字符
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\-\(\)\[\]【】（）]', '', text)
    return text.strip()


def extract_keywords(text: str) -> dict:
    """从OCR文本中提取关键信息（改进版）"""
    keywords = {
        'names': [],
        'dates': [],
        'numbers': [],
        'batch_numbers': [],
        'approval_numbers': [],
        'specifications': [],
        'manufacturer': [],
        'brand': []
    }

    lines = text.split('\n')
    
    # 提取药品名称（中文）- 包含剂型关键词
    dosage_forms = ['片', '胶囊', '颗粒', '口服液', '注射液', '软膏', '滴眼液', '喷雾剂', 
                    '干混悬剂', '混悬剂', '分散片', '缓释片', '肠溶片', '咀嚼片']
    for line in lines:
        line = line.strip()
        if len(line) < 3 or len(line) > 50:
            continue
        # 匹配包含剂型关键词的行
        if any(form in line for form in dosage_forms):
            # 清理行首的乱码
            cleaned = re.sub(r'^[\s\W\d]+', '', line)
            if len(cleaned) > 5:
                keywords['names'].append(cleaned)
    
    # 提取英文药品名
    english_pattern = r'([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+){1,4})'
    for line in lines:
        matches = re.findall(english_pattern, line)
        for match in matches:
            # 过滤掉常见非药品词
            if match not in ['Suspension', 'Tablets', 'Capsules', 'Oral', 'Solution'] and len(match) > 5:
                keywords['names'].append(match)
    
    # 提取规格（如 0.5g:2.5mg, 14袋/盒）
    spec_patterns = [
        r'(\d+\.?\d*\s*[g克][:：]\s*\d+\.?\d*\s*[mg毫克])',  # 0.5g:2.5mg
        r'(\d+\.?\d*\s*[mg毫克g克][：:]\s*\d+\.?\d*\s*[mg毫克g克])',  # 2.5mg:0.5g
        r'(\d+\s*[袋片粒支瓶盒]+[/每]\s*[盒瓶])',  # 14袋/盒
        r'(\d+\.?\d*\s*[mg毫克g克])',  # 5mg, 0.5g
    ]
    for pattern in spec_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        keywords['specifications'].extend(matches)
    
    # 提取品牌/商标（带®或™符号的）
    brand_pattern = r'([\u4e00-\u9fa5]{2,8}[®™])'
    matches = re.findall(brand_pattern, text)
    keywords['brand'] = matches

    # 提取日期（有效期、生产日期等）- 支持多种格式
    date_patterns = [
        r'有效期[至到:：]?\s*(\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}日?)',
        r'生产日期[：:]?\s*(\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}日?)',
        r'Exp(?:iration)?[.:;]?\s*(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})',
        r'(\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}日?)',
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        keywords['dates'].extend(matches)

    # 提取批准文号（中国格式）
    approval_patterns = [
        r'(国药准字[HZSJ][a-zA-Z0-9]+)',
        r'Approval[.:;]?\s*([HZSJ]\d+)',
    ]
    for pattern in approval_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        keywords['approval_numbers'].extend(matches)

    keywords['numbers'] = keywords['approval_numbers'].copy()

    # 提取批号
    batch_patterns = [
        r'产品批号[：:]?\s*([A-Za-z0-9\-]+)',
        r'Batch(?: No)?[.:;]?\s*([A-Za-z0-9\-]+)',
        r'LOT[.:;]?\s*([A-Za-z0-9\-]+)',
        r'批号[：:]?\s*([A-Za-z0-9\-]+)',
    ]
    for pattern in batch_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        keywords['batch_numbers'].extend(matches)
    
    # 提取生产厂家
    manufacturer_pattern = r'([\u4e00-\u9fa5]{2,}(?:制药|药业|生物|医药|化学)[\u4e00-\u9fa5]*(?:股份)?有限公司)'
    matches = re.findall(manufacturer_pattern, text)
    keywords['manufacturer'] = matches

    # 去重
    for key in keywords:
        keywords[key] = list(set(keywords[key]))

    return keywords
