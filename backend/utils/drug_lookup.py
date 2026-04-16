"""
药品信息查询模块
通过批准文号查询国家药监局数据库
"""

import re
import requests
from typing import Optional, Dict


def extract_approval_number(text: str) -> Optional[str]:
    """
    从OCR文本中提取批准文号
    支持格式：国药准字H20041111、国药准字Z20240001等
    """
    # 批准文号格式：国药准字 + 1位字母(H/Z/S/J) + 8位数字
    pattern = r'国药准字[HZSJ]\d{8}'
    match = re.search(pattern, text)
    if match:
        return match.group()
    
    # 模糊匹配（OCR可能有误差）
    # 尝试匹配 "准字" 后面的内容
    fuzzy_pattern = r'准字\s*[HZSJ]\s*\d{8}'
    fuzzy_match = re.search(fuzzy_pattern, text)
    if fuzzy_match:
        # 还原成标准格式
        raw = fuzzy_match.group().replace(' ', '').replace('准字', '国药准字')
        return raw
    
    return None


def extract_traceability_code(text: str) -> Optional[str]:
    """
    从OCR文本中提取药品追溯码
    中国药品追溯码格式：
    - 20位数字（如86901234567890123456）
    - 或 药品标识码(7位) + 序列号(13位) = 20位
    """
    # 清理文本
    cleaned = text.replace(' ', '').replace('\n', '').replace('：', ':').replace(':', '')
    
    # 尝试匹配 "药品标识码" + "序列号" 组合
    # 如：药品标识码8177322序列号0288616423835
    combined_pattern = r'药品标识码[:：]?(\d{6,8})序列号[:：]?(\d{13,14})'
    combined_match = re.search(combined_pattern, cleaned)
    if combined_match:
        code = combined_match.group(1) + combined_match.group(2)
        if len(code) >= 20:
            return code[:20]  # 取前20位
    
    # 匹配20位数字（标准追溯码）
    pattern_20 = r'\b\d{20}\b'
    match_20 = re.search(pattern_20, cleaned)
    if match_20:
        return match_20.group()
    
    # 宽松匹配：任意19-21位连续数字
    pattern_loose = r'\b\d{19,21}\b'
    match_loose = re.search(pattern_loose, cleaned)
    if match_loose:
        return match_loose.group()
    
    return None


def query_nmpa(approval_number: str) -> Optional[Dict]:
    """
    查询国家药监局数据库
    返回药品信息字典
    
    注意：NMPA官网有反爬虫，这里使用公开的查询接口
    实际使用时可能需要处理验证码或频率限制
    """
    # NMPA公开查询接口
    # 这是模拟实现，实际接口可能需要调整
    url = "https://www.nmpa.gov.cn/datasearch/search-info.html"
    
    try:
        # 实际调用NMPA接口
        # 由于NMPA官网有反爬机制，这里提供几种备选方案：
        
        # 方案1：直接爬取（可能需要处理验证码）
        # response = requests.get(url, params={'nmpa': approval_number}, timeout=10)
        
        # 方案2：使用第三方聚合API（如药智网、丁香园等）
        # 这些平台通常有开放API或可以爬取
        
        # 方案3：本地数据库（需要预先爬取建立）
        
        # 目前返回None，表示需要手动实现查询逻辑
        # 或者用户可以手动输入批准文号后，程序提供搜索链接
        return None
        
    except Exception as e:
        print(f"查询NMPA失败: {e}")
        return None


def query_drug_info(approval_number: str) -> Optional[Dict]:
    """
    查询药品信息（综合多个数据源）
    优先使用可靠的数据源
    """
    # 先尝试NMPA官方
    result = query_nmpa(approval_number)
    if result:
        return result
    
    # 可以扩展其他数据源
    # - 药智网
    # - 丁香园用药助手
    # - 本地缓存数据库
    
    return None


def get_search_url(approval_number: str) -> str:
    """
    获取药品查询链接
    用户可点击链接手动查看药品信息
    """
    # NMPA查询链接
    nmpa_url = f"https://www.nmpa.gov.cn/datasearch/search-info.html?nmpa={approval_number}"
    
    # 药智网查询
    yaozh_url = f"https://db.yaozh.com/hmap/{approval_number}.html"
    
    return {
        'nmpa': nmpa_url,
        'yaozh': yaozh_url
    }


def query_by_traceability(code: str) -> Optional[Dict]:
    """
    通过药品追溯码查询信息
    返回药品基本信息
    """
    # 追溯码查询接口（需要接入官方平台）
    # 目前返回查询链接
    return {
        'traceability_code': code,
        'query_url': f"https://www.nmpa.gov.cn/xxgk/spypzhcjd/spypzhcjdyp/index.html",
        'note': '请使用支付宝/微信扫描追溯码，或访问国家药监局追溯平台查询'
    }


def parse_medicine_by_approval(ocr_text: str) -> Dict:
    """
    通过批准文号或追溯码解析药品信息
    返回包含识别到的码和查询链接的字典
    """
    # 优先尝试追溯码（信息更丰富）
    traceability_code = extract_traceability_code(ocr_text)
    if traceability_code:
        return {
            'type': 'traceability',
            'code': traceability_code,
            'found': True,
            'query_info': query_by_traceability(traceability_code)
        }
    
    # 尝试批准文号
    approval_number = extract_approval_number(ocr_text)
    if approval_number:
        result = {
            'type': 'approval',
            'code': approval_number,
            'found': False,
            'medicine_info': None,
            'search_urls': get_search_url(approval_number)
        }
        
        # 尝试查询详细信息
        medicine_info = query_drug_info(approval_number)
        if medicine_info:
            result['found'] = True
            result['medicine_info'] = medicine_info
        
        return result
    
    return {
        'type': None,
        'code': None,
        'found': False
    }
