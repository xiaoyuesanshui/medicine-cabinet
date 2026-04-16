"""
药品追溯码信息爬取模块
尝试从阿里健康/码上放心平台获取药品信息
"""

import requests
import json
import re
from typing import Optional, Dict


def query_traceability_alihealth(code: str) -> Optional[Dict]:
    """
    尝试从阿里健康平台查询追溯码信息
    
    追溯码格式: 20位数字 (如 81773220288616423835)
    """
    # 清理追溯码
    code = code.strip().replace(' ', '')
    
    # 阿里健康追溯平台
    # 注意: 这个接口可能需要特定的签名、token 或 headers
    # 以下 URL 是猜测的，实际需要抓包确认
    
    urls_to_try = [
        # 码上放心可能的查询接口
        f"https://www.mashangfangxin.com/api/verify?code={code}",
        f"https://www.mashangfangxin.com/query?traceCode={code}",
        # 阿里健康可能的接口
        f"https://healthapi.alipay.com/traceability/query?code={code}",
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.mashangfangxin.com/',
    }
    
    for url in urls_to_try:
        try:
            print(f"[Crawler] 尝试: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"[Crawler] 状态码: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"[Crawler] 返回数据: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
                    
                    # 如果成功获取到数据，解析并返回
                    if data.get('success') or data.get('code') == 200:
                        return parse_alihealth_response(data)
                except:
                    # 可能返回 HTML
                    print(f"[Crawler] 返回 HTML: {response.text[:500]}")
                    
        except Exception as e:
            print(f"[Crawler] 请求失败: {e}")
            continue
    
    return None


def parse_alihealth_response(data: Dict) -> Optional[Dict]:
    """解析阿里健康返回的数据"""
    try:
        # 根据实际返回结构调整
        result = {
            'name': data.get('drugName') or data.get('productName'),
            'manufacturer': data.get('manufacturer') or data.get('enterpriseName'),
            'specification': data.get('specification') or data.get('packageSpec'),
            'expiry_date': data.get('expiryDate') or data.get('validityPeriod'),
            'batch_no': data.get('batchNo') or data.get('batchNumber'),
            'traceability_code': data.get('traceCode') or data.get('code'),
            'source': 'alihealth'
        }
        return result
    except Exception as e:
        print(f"[Crawler] 解析失败: {e}")
        return None


def query_traceability_nmpa(code: str) -> Optional[Dict]:
    """
    尝试从药监局网站查询
    追溯码前7位是药品标识码，可以尝试查询
    """
    # 药监局数据查询页面
    # 这个页面是给人看的，没有 API
    # 但可以尝试爬取
    
    base_url = "https://www.nmpa.gov.cn/datasearch/search-info.html"
    
    # 追溯码前7位是药品标识码
    drug_code = code[:7] if len(code) >= 7 else code
    
    print(f"[Crawler] 尝试药监局查询，药品标识码: {drug_code}")
    
    # 药监局网站有反爬，需要更复杂的处理
    # 这里只是占位，实际需要分析页面结构
    
    return None


# 测试
if __name__ == '__main__':
    test_code = "81773220288616423835"
    result = query_traceability_alihealth(test_code)
    print(f"\n最终结果: {json.dumps(result, ensure_ascii=False, indent=2) if result else 'None'}")
