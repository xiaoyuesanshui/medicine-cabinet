"""
扫描识别API路由
处理药盒拍照上传和识别
"""
import os
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from utils.ocr import extract_text_from_image, extract_keywords
from utils.ai_parser import parse_medicine_info, fallback_parse
from utils.drug_lookup import parse_medicine_by_approval
from utils.barcode_scanner import scan_and_extract
from utils.drug_api import query_by_barcode, is_domestic_barcode
from api_cache import APICacheManager

scan_bp = Blueprint('scan', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@scan_bp.route('/api/scan', methods=['POST'])
def scan_medicine():
    """
    上传药盒照片并识别
    
    流程：
    1. 接收上传的图片
    2. OCR提取文字
    3. 尝试提取关键信息（批准文号、条码等）
    4. AI解析结构化信息
    5. 返回识别结果（供用户确认后保存）
    """
    # 检查是否有文件
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '没有上传图片'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的文件格式'}), 400
    
    try:
        # 保存上传的文件
        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
        file.save(upload_path)

        # 步骤1：尝试用 zbar 扫描条形码/追溯码
        barcode_result = scan_and_extract(upload_path)
        print(f"条形码扫描结果: {barcode_result}")

        # 如果识别到追溯码(20位)，直接返回
        if barcode_result.get('traceability_code'):
            from utils.drug_lookup import query_by_traceability
            query_info = query_by_traceability(barcode_result['traceability_code'])

            return jsonify({
                'success': True,
                'data': {
                    'parsed': {
                        'traceability_code': barcode_result['traceability_code'],
                        'barcode': barcode_result.get('barcode'),
                        'name': '',
                        'ingredients': '',
                        'indications': '',
                        'query_info': query_info
                    },
                    'raw_text': '',
                    'key_info': {},
                    'image_path': unique_name,
                    'needs_review': True,
                    'source': 'traceability'
                }
            })

        # 如果识别到国内商品条码(69开头)，先查API缓存，再调用API
        barcode = barcode_result.get('barcode')
        if barcode and is_domestic_barcode(barcode):
            print(f"识别到国内商品条码: {barcode}")
            
            # 先查API缓存数据库（独立的）
            cache_data = APICacheManager.get_valid_cache(barcode)
            need_update = False
            
            if cache_data:
                print(f"条码 {barcode} 命中API缓存")
                return jsonify({
                    'success': True,
                    'data': {
                        'parsed': cache_data,
                        'raw_text': '',
                        'key_info': {'barcode': barcode},
                        'image_path': unique_name,
                        'needs_review': True,
                        'source': 'cache'
                    }
                })
            else:
                # 检查是否有过期缓存
                from api_cache import cache_session as api_cache_session
                from api_cache import APICache
                with api_cache_session() as db:
                    expired_cache = db.query(APICache).filter_by(barcode=barcode).first()
                    if expired_cache:
                        need_update = True
                        print(f"条码 {barcode} API缓存已过期，需要更新")
            
            # 缓存不存在或已过期，调用API
            print(f"条码 {barcode} 调用API查询...")
            api_result = query_by_barcode(barcode)

            if api_result['success']:
                drug_info = api_result['data']
                
                # 保存到API缓存
                print(f"条码 {barcode} API查询成功，保存到缓存")
                APICacheManager.save_cache(barcode, drug_info)
                
                return jsonify({
                    'success': True,
                    'data': {
                        'parsed': drug_info,
                        'raw_text': '',
                        'key_info': {'barcode': barcode},
                        'image_path': unique_name,
                        'needs_review': True,
                        'source': 'barcode_api'
                    }
                })
            else:
                print(f"API查询失败: {api_result.get('error')}")
                # API失败但有缓存，返回缓存（即使已过期）
                from api_cache import cache_session as api_cache_session
                from api_cache import APICache
                with api_cache_session() as db:
                    expired_cache = db.query(APICache).filter_by(barcode=barcode).first()
                    if expired_cache:
                        print(f"条码 {barcode} API失败，返回过期缓存")
                        return jsonify({
                            'success': True,
                            'data': {
                                'parsed': expired_cache.to_dict(),
                                'raw_text': '',
                                'key_info': {'barcode': barcode},
                                'image_path': unique_name,
                                'needs_review': True,
                                'source': 'cache_expired',
                                'api_error': api_result.get('error', 'API查询失败')
                            }
                        })

        # 步骤2：OCR提取文字（条码识别失败时作为备用）
        try:
            ocr_text = extract_text_from_image(upload_path)
        except Exception as e:
            print(f"OCR失败: {e}")
            ocr_text = ""

        # 步骤3：尝试通过批准文号/追溯码查询
        approval_lookup = parse_medicine_by_approval(ocr_text)

        # 步骤4：提取关键信息
        key_info = extract_keywords(ocr_text)

        # 步骤5：解析药品信息
        api_key = os.getenv('AI_API_KEY')
        if api_key:
            try:
                parsed_info = parse_medicine_info(ocr_text, upload_path)
            except Exception as e:
                print(f"AI解析失败，使用备用方案: {e}")
                parsed_info = fallback_parse(ocr_text)
        else:
            parsed_info = fallback_parse(ocr_text)

        # 合并条形码扫描结果（优先）
        if barcode_result.get('barcode'):
            parsed_info['barcode'] = barcode_result['barcode']

        # 合并批准文号查询结果
        if approval_lookup.get('code'):
            if approval_lookup['type'] == 'traceability' and not parsed_info.get('traceability_code'):
                parsed_info['traceability_code'] = approval_lookup['code']
            elif approval_lookup['type'] == 'approval' and not parsed_info.get('approval_number'):
                parsed_info['approval_number'] = approval_lookup['code']

            if approval_lookup.get('search_urls'):
                parsed_info['search_urls'] = approval_lookup['search_urls']
            if approval_lookup.get('query_info'):
                parsed_info['query_info'] = approval_lookup['query_info']

        # 合并OCR提取的关键信息
        if not parsed_info.get('approval_number') and key_info.get('approval_numbers'):
            parsed_info['approval_number'] = key_info['approval_numbers'][0]
        if not parsed_info.get('barcode') and key_info.get('barcodes'):
            parsed_info['barcode'] = key_info['barcodes'][0]
        if not parsed_info.get('expiry_date') and key_info.get('dates'):
            parsed_info['expiry_date'] = key_info['dates'][0]

        return jsonify({
            'success': True,
            'data': {
                'parsed': parsed_info,
                'raw_text': ocr_text,
                'key_info': key_info,
                'approval_lookup': approval_lookup,
                'image_path': unique_name,
                'needs_review': True,
                'source': 'ocr'
            }
        })
        
    except Exception as e:
        import traceback
        print(f"scan_medicine error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@scan_bp.route('/api/scan/confirm', methods=['POST'])
def confirm_scan():
    """
    确认识别结果并保存到数据库
    
    请求体：
    {
        "medicine": {药品信息对象},
        "image_path": "上传的图片文件名"
    }
    """
    from models import MedicineDB
    
    data = request.get_json()
    if not data or 'medicine' not in data:
        return jsonify({'success': False, 'error': '缺少药品信息'}), 400
    
    medicine_data = data['medicine']
    
    # 验证必填字段
    if not medicine_data.get('name'):
        return jsonify({'success': False, 'error': '药品名称不能为空'}), 400
    
    try:
        # 保存到数据库
        medicine_id = MedicineDB.create(medicine_data)
        
        return jsonify({
            'success': True,
            'data': {'id': medicine_id}
        })
        
    except Exception as e:
        import traceback
        print(f"confirm_scan error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@scan_bp.route('/api/scan/text-only', methods=['POST'])
def scan_text_only():
    """
    仅OCR提取文字，不调用AI
    用于快速查看图片中的文字内容
    """
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '没有上传图片'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    
    try:
        # 保存临时文件
        filename = secure_filename(file.filename)
        unique_name = f"temp_{uuid.uuid4().hex}_{filename}"
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
        file.save(upload_path)
        
        # OCR识别
        ocr_text = extract_text_from_image(upload_path)
        key_info = extract_keywords(ocr_text)
        
        # 删除临时文件
        try:
            os.remove(upload_path)
        except:
            pass
        
        return jsonify({
            'success': True,
            'data': {
                'text': ocr_text,
                'key_info': key_info
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@scan_bp.route('/api/scan/barcode', methods=['GET'])
def scan_barcode():
    """
    根据条形码/追溯码查询药品信息
    优先从API缓存数据库读取，缓存不存在或过期则调用API
    """
    code = request.args.get('code', '').strip()
    
    if not code:
        return jsonify({'success': False, 'error': '请提供条形码'}), 400
    
    try:
        # 判断是追溯码(20位)还是普通条形码
        if len(code) == 20 and code.startswith('8'):
            # 追溯码 - 暂不支持缓存，直接查询
            from utils.drug_lookup import query_by_traceability
            result = query_by_traceability(code)
            return jsonify({
                'success': True,
                'data': {
                    'barcode': code,
                    'type': 'traceability',
                    'query_info': result
                }
            })
        else:
            # 普通条形码，先查API缓存数据库
            cache_data = APICacheManager.get_valid_cache(code)
            expired_cache = None
            
            if cache_data:
                print(f"条码 {code} 命中API缓存")
                return jsonify({
                    'success': True,
                    'data': {
                        'barcode': code,
                        'type': 'barcode',
                        'drug_info': cache_data,
                        'source': 'cache',
                        'cached_at': cache_data.get('cached_at')
                    }
                })
            else:
                # 缓存不存在或已过期，尝试获取过期缓存
                expired_cache = APICacheManager.get_by_barcode(code)
            
            # 缓存不存在或已过期，调用API查询
            if is_domestic_barcode(code):
                print(f"条码 {code} 调用API查询...")
                api_result = query_by_barcode(code)
                
                if api_result['success']:
                    drug_info = api_result['data']
                    
                    # 保存到API缓存
                    APICacheManager.save_cache(code, drug_info)
                    
                    return jsonify({
                        'success': True,
                        'data': {
                            'barcode': code,
                            'type': 'barcode',
                            'drug_info': drug_info,
                            'source': 'jisuapi'
                        }
                    })
                else:
                    # API调用失败，如果有缓存则返回缓存（即使已过期）
                    if expired_cache:
                        print(f"条码 {code} API调用失败，返回过期缓存")
                        return jsonify({
                            'success': True,
                            'data': {
                                'barcode': code,
                                'type': 'barcode',
                                'drug_info': expired_cache,
                                'source': 'cache_expired',
                                'api_error': api_result.get('error', 'API查询失败'),
                                'cached_at': expired_cache.get('cached_at')
                            }
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'error': api_result.get('error', '查询失败'),
                            'data': {'barcode': code, 'type': 'barcode'}
                        })
            else:
                return jsonify({
                    'success': True,
                    'data': {
                        'barcode': code,
                        'type': 'barcode',
                        'note': '非国内商品条码，请手动补充药品信息'
                    }
                })
            
    except Exception as e:
        import traceback
        print(f"scan_barcode error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@scan_bp.route('/api/scan/test-barcode', methods=['POST'])
def test_barcode_scan():
    """
    测试条码扫描功能（调试用）
    直接返回条码扫描结果，不进行后续处理
    """
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '没有上传图片'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    try:
        # 保存临时文件
        filename = secure_filename(file.filename)
        unique_name = f"test_{uuid.uuid4().hex}_{filename}"
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
        file.save(upload_path)

        # 只进行条码扫描
        from utils.barcode_scanner import scan_and_extract
        barcode_result = scan_and_extract(upload_path)

        return jsonify({
            'success': True,
            'data': {
                'barcode_scan': barcode_result,
                'image_path': unique_name
            }
        })

    except Exception as e:
        import traceback
        print(f"test_barcode_scan error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500
