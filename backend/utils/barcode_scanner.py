"""
条形码/二维码扫描模块
使用 zbar 进行识别
"""

import os
import shutil
import subprocess
import re
from typing import Optional, List, Dict


def get_zbarimg_cmd():
    """自动检测 zbarimg 路径"""
    paths = [
        '/opt/homebrew/bin/zbarimg',   # macOS Homebrew (Apple Silicon)
        '/usr/local/bin/zbarimg',       # macOS Homebrew (Intel)
        '/usr/bin/zbarimg',             # Linux
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return shutil.which('zbarimg') or 'zbarimg'


def scan_barcode(image_path: str) -> List[Dict]:
    """
    使用 zbar 扫描图片中的条形码/二维码
    返回识别到的所有码
    """
    try:
        zbar_cmd = get_zbarimg_cmd()
        result = subprocess.run(
            [zbar_cmd, '--quiet', image_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        # zbarimg 返回码 0 表示成功，但即使没有识别到码也可能返回 0
        # 只要有 stdout 输出就处理
        if not result.stdout.strip():
            return []

        codes = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if ':' in line:
                # 格式: CODE-128:81773220288616423835
                barcode_type, data = line.split(':', 1)
                codes.append({
                    'type': barcode_type.strip(),
                    'data': data.strip()
                })

        return codes

    except subprocess.TimeoutExpired:
        print("zbar 扫描超时")
        return []
    except FileNotFoundError:
        print(f"zbarimg 未安装 (查找路径: {get_zbarimg_cmd()})")
        print("Linux: sudo apt-get install zbar-tools")
        print("macOS: brew install zbar")
        return []
    except Exception as e:
        print(f"条形码扫描失败: {e}")
        return []


def extract_traceability_from_barcode(barcode_data: str) -> Optional[str]:
    """
    从条形码数据中判断是否是追溯码
    追溯码通常是20位数字
    """
    # 移除所有非数字字符
    digits = re.sub(r'\D', '', barcode_data)
    
    # 检查是否是20位数字（追溯码）
    if len(digits) == 20:
        return digits
    
    return None


def scan_and_extract(image_path: str) -> Dict:
    """
    扫描图片并提取药品相关编码
    返回包含追溯码、条形码等信息的字典
    """
    codes = scan_barcode(image_path)
    
    result = {
        'barcodes': codes,
        'traceability_code': None,
        'barcode': None
    }
    
    for code in codes:
        data = code['data']
        
        # 检查是否是追溯码
        traceability = extract_traceability_from_barcode(data)
        if traceability:
            result['traceability_code'] = traceability
        else:
            # 普通条形码
            result['barcode'] = data
    
    return result
