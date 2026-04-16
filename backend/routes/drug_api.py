#!/usr/bin/env python3
"""
极速数据药品信息查询接口
API 文档: https://www.jisuapi.com/api/medicine/
支持通过条码、批准文号、medicine_id 查询
"""

import os
import requests
from typing import Dict, Optional

JISU_DETAIL_URL = "https://api.jisuapi.com/medicine/detail"
JISU_QUERY_URL  = "https://api.jisuapi.com/medicine/query"


def _get_api_key() -> str:
    """每次调用时实时读取，确保 load_dotenv() 已执行后才取值"""
    return os.environ.get('JISU_API_KEY', '')


def _get(url: str, params: dict) -> Dict:
    """通用 GET 请求，统一处理超时和网络错误"""
    api_key = _get_api_key()
    if not api_key:
        return {'success': False, 'data': None, 'error': '未配置 JISU_API_KEY 环境变量'}
    params['appkey'] = api_key
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        # 极速数据：status=0 表示成功
        if str(result.get('status')) != '0':
            return {'success': False, 'data': None, 'error': result.get('msg', '查询失败')}
        return {'success': True, 'data': result.get('result', {}), 'error': None}
    except requests.exceptions.Timeout:
        return {'success': False, 'data': None, 'error': 'API 请求超时'}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'data': None, 'error': f'网络请求失败: {e}'}
    except Exception as e:
        return {'success': False, 'data': None, 'error': f'异常: {e}'}


def _parse_description(desc: str) -> dict:
    """从药品描述中解析额外字段"""
    if not desc:
        return {}
    
    result = {}
    lines = desc.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 用法用量
        if '用法用量' in line or '用法' in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['dosage'] = parts[1].strip()
        
        # 成分/主要成份
        elif '成份' in line or '成分' in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['ingredients'] = parts[1].strip()
        
        # 适应症
        elif '适应症' in line or '功能主治' in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['indications'] = parts[1].strip()
        
        # 不良反应
        elif '不良反应' in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['adverse_reactions'] = parts[1].strip()
        
        # 禁忌
        elif '禁忌' in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['contraindications'] = parts[1].strip()
        
        # 注意事项
        elif '注意事项' in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['precautions'] = parts[1].strip()
        
        # 药物相互作用
        elif '药物相互作用' in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['interactions'] = parts[1].strip()
        
        # 贮藏
        elif '贮藏' in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['storage'] = parts[1].strip()
        
        # 有效期
        elif '有效期' in line and '有效期至' not in line:
            if '：' in line or ':' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                if len(parts) > 1:
                    result['shelf_life'] = parts[1].strip()
    
    return result


def _standardize(raw: dict) -> dict:
    """将极速数据返回字段标准化为内部统一格式"""
    # 从描述中解析额外字段
    parsed = _parse_description(raw.get('desc', ''))
    
    return {
        'medicine_id':    raw.get('medicine_id', ''),
        'name':           raw.get('name', ''),
        'spec':           raw.get('spec', ''),
        'type':           raw.get('type', ''),
        'unit':           raw.get('unit', ''),
        'approval_number': raw.get('approval_num', ''),
        'reference_code': raw.get('reference_code', ''),
        'manufacturer':   raw.get('manufacturer', ''),
        'barcode':        raw.get('barcode', ''),
        'disease':        raw.get('disease', ''),
        'desc':           raw.get('desc', ''),
        'prescription':   raw.get('prescription', ''),  # 1=处方药 2=OTC
        'image':          raw.get('image', ''),
        # 从描述中解析的字段
        'dosage':         parsed.get('dosage', ''),
        'ingredients':    parsed.get('ingredients', ''),
        'indications':    parsed.get('indications', raw.get('disease', '')),  # 优先使用解析的适应症
        'adverse_reactions': parsed.get('adverse_reactions', ''),
        'contraindications': parsed.get('contraindications', ''),
        'precautions':    parsed.get('precautions', ''),
        'interactions':   parsed.get('interactions', ''),
        'storage':        parsed.get('storage', ''),
        'shelf_life':     parsed.get('shelf_life', ''),
        'raw':            raw,
    }


def query_by_barcode(barcode: str) -> Dict:
    """通过商品条码查询药品详情（优先 detail 接口，回退 query）"""
    if not barcode:
        return {'success': False, 'data': None, 'error': '条码为空'}

    # 先用 detail 接口（字段更全）
    result = _get(JISU_DETAIL_URL, {'barcode': barcode})
    if result['success'] and result['data']:
        return {'success': True, 'data': _standardize(result['data']), 'error': None}

    # detail 查不到时，用 query 接口搜索
    result2 = _get(JISU_QUERY_URL, {'barcode': barcode})
    if result2['success'] and result2['data']:
        # query 返回列表，取第一条
        items = result2['data']
        if isinstance(items, list) and items:
            first = items[0]
            # 再用 medicine_id 取完整详情
            mid = first.get('medicine_id')
            if mid:
                detail = _get(JISU_DETAIL_URL, {'medicine_id': mid})
                if detail['success'] and detail['data']:
                    return {'success': True, 'data': _standardize(detail['data']), 'error': None}
            return {'success': True, 'data': _standardize(first), 'error': None}

    # 全部失败，返回最后一次错误
    return result2 if not result2['success'] else result


def query_by_approval(approval_num: str) -> Dict:
    """通过批准文号查询药品详情"""
    if not approval_num:
        return {'success': False, 'data': None, 'error': '批准文号为空'}
    result = _get(JISU_DETAIL_URL, {'approval_num': approval_num})
    if result['success'] and result['data']:
        return {'success': True, 'data': _standardize(result['data']), 'error': None}
    return result


def is_domestic_barcode(barcode: str) -> bool:
    """是否为中国商品条码（69开头，EAN-13）"""
    return bool(barcode) and barcode.startswith('69') and len(barcode) >= 8


def format_drug_info(d: dict) -> str:
    """格式化为可读文本"""
    if not d:
        return "未获取到药品信息"
    lines = [
        f"药品名称: {d.get('name', '-')}",
        f"规　　格: {d.get('spec', '-')}",
        f"剂　　型: {d.get('type', '-')}",
        f"生产厂家: {d.get('manufacturer', '-')}",
        f"批准文号: {d.get('approval_number', '-')}",
        f"是否处方: {'处方药' if d.get('prescription') == 1 else 'OTC' if d.get('prescription') == 2 else '-'}",
    ]
    if d.get('disease'):
        lines.append(f"适应疾病: {d['disease']}")
    return '\n'.join(lines)


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) < 2:
        print("用法: python drug_api.py <条码或批准文号>")
        print("需先设置: export JISU_API_KEY='你的密钥'")
        sys.exit(1)
    code = sys.argv[1]
    print(f"查询: {code}")
    print("-" * 50)
    if code.startswith('69'):
        r = query_by_barcode(code)
    else:
        r = query_by_approval(code)
    if r['success']:
        print("✓ 查询成功")
        print(format_drug_info(r['data']))
    else:
        print(f"✗ 失败: {r['error']}")
