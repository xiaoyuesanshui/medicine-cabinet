"""
扫描识别API路由
处理药盒拍照上传和识别

流程（v2 - 去掉Tesseract OCR，纯AI视觉+API）：
1. 接收上传的图片
2. zbar扫条形码/追溯码（有则优先查API）
3. AI视觉识别图片（直接从图片提取18个字段）
4. 根据AI结果多路API补全（批准文号/条码/名称）
5. 返回识别结果供用户确认后保存
"""
import os
import sys
import uuid
import re
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

# 强制刷新stdout，确保print日志实时写入journald
sys.stdout.reconfigure(line_buffering=True)

from utils.ai_parser import parse_medicine_info, fallback_parse
from utils.drug_lookup import parse_medicine_by_approval
from utils.barcode_scanner import scan_and_extract
from utils.drug_api import query_by_barcode, query_by_name, query_by_approval, is_domestic_barcode
from api_cache import APICacheManager

scan_bp = Blueprint('scan', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@scan_bp.route('/api/scan', methods=['POST'])
def scan_medicine():
    """上传药盒照片并识别"""
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

        # ===== 步骤1：zbar 扫描条形码/追溯码 =====
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

        # 如果识别到国内商品条码(69开头)，直接查API返回
        barcode = barcode_result.get('barcode')
        if barcode and is_domestic_barcode(barcode):
            print(f"识别到国内商品条码: {barcode}")
            
            cache_data = APICacheManager.get_valid_cache(barcode)
            
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
                        'source': 'cache',
                        'is_ai_generated': False
                    }
                })
            
            # 缓存不存在，调用API
            print(f"条码 {barcode} 调用API查询...")
            api_result = query_by_barcode(barcode)

            if api_result['success']:
                drug_info = api_result['data']
                APICacheManager.save_cache(barcode, drug_info)
                
                return jsonify({
                    'success': True,
                    'data': {
                        'parsed': drug_info,
                        'raw_text': '',
                        'key_info': {'barcode': barcode},
                        'image_path': unique_name,
                        'needs_review': True,
                        'source': 'barcode_api',
                        'is_ai_generated': False
                    }
                })
            else:
                print(f"条码API查询失败: {api_result.get('error')}")

        # ===== 步骤2：AI视觉识别（核心） =====
        api_key = os.getenv('AI_API_KEY')
        ai_parsed = None
        ai_generated = False
        
        if api_key:
            try:
                print("调用AI视觉识别药盒图片...")
                # 不传OCR文本了，AI直接看图
                ai_parsed = parse_medicine_info('', upload_path)
                if isinstance(ai_parsed, str):
                    import json
                    ai_parsed = json.loads(ai_parsed) if ai_parsed.startswith('{') else {}
                
                print(f"AI视觉识别结果: name={ai_parsed.get('name')}, approval={ai_parsed.get('approval_number')}, barcode={ai_parsed.get('barcode')}")
                
                # 兜底：强制清空AI填的alias（这是用户自定义字段，AI永远不该填）
                if 'alias' in ai_parsed:
                    del ai_parsed['alias']
                
                if ai_parsed.get('name'):
                    ai_generated = True
            except Exception as e:
                print(f"AI视觉识别失败: {e}")
                import traceback
                traceback.print_exc()

        # ===== 步骤3：AI识别后的API补全（优先批准文号，不再重复查条码） =====
        
        if ai_parsed:
            api_hit = False
            
            # ★ 第一优先级：AI识别到批准文号 → 直接查API覆盖全部字段
            ai_approval = (ai_parsed.get('approval_number') or '').strip()
            if re.match(r'国药准字[HSZJ]\d{8}', ai_approval):
                print(f"步骤3a [第一优先]: AI识别到批准文号 {ai_approval}，查询API...")
                try:
                    r = query_by_approval(ai_approval)
                    if r['success']:
                        info = r['data']
                        APICacheManager.save_cache(ai_approval, info)
                        # 用API完整数据替换，保留AI的name
                        saved_name = ai_parsed.get('name')
                        ai_parsed.update(info)
                        if saved_name and not info.get('name'):
                            ai_parsed['name'] = saved_name
                        ai_parsed['_source'] = 'approval_api'
                        api_hit = True
                        print(f"  ✓ 批准文号API成功: {info.get('name')}")
                    else:
                        print(f"  ✗ 批准文号API未找到: {r.get('error')}")
                except Exception as e:
                    print(f"  ✗ 批准文号API异常: {e}")
            
            # ★ 第二优先级：无批准文号但有名称 → 按名称查API补全缺失信息
            if not api_hit and ai_parsed.get('name'):
                name = ai_parsed.get('name', '')
                key_fields_ok = bool(
                    ai_parsed.get('ingredients') 
                    and (ai_parsed.get('dosage') or ai_parsed.get('description'))
                )
                if not key_fields_ok:
                    print(f"步骤3b [第二优先]: 名称'{name}'关键信息不完整，按名称查询API...")
                    try:
                        r = query_by_name(name)
                        if r['success']:
                            info = r['data']
                            for k, v in info.items():
                                if not ai_parsed.get(k) and v: ai_parsed[k] = v
                            ai_parsed['_source'] = 'ai_vision_plus_name_api'
                            api_hit = True
                            print(f"  ✓ 名称API成功: {info.get('name')}")
                        else:
                            print(f"  ✗ 名称API未找到")
                    except Exception as e:
                        print(f"  ✗ 名称API异常: {e}")

        # ===== 步骤4：AI没识别到名称，fallback处理 =====
        if not ai_parsed or not ai_parsed.get('name'):
            print("AI未能识别药品名称")
            if not ai_parsed:
                ai_parsed = {}

        # 合并zbar条码结果
        if barcode_result.get('barcode') and not ai_parsed.get('barcode'):
            ai_parsed['barcode'] = barcode_result['barcode']

        # 返回结果
        source = ai_parsed.pop('_source', 'ai_vision') if '_source' in ai_parsed else ('ai_vision' if ai_generated else 'unknown')

        return jsonify({
            'success': True,
            'data': {
                'parsed': ai_parsed,
                'raw_text': '',  # 已无OCR
                'key_info': {},
                'image_path': unique_name,
                'needs_review': True,
                'source': source,
                'is_ai_generated': ai_generated
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
    仅OCR提取文字，不调用AI（已废弃，保留兼容）
    用于快速查看图片中的文字内容
    """
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '没有上传图片'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    
    try:
        filename = secure_filename(file.filename)
        unique_name = f"temp_{uuid.uuid4().hex}_{filename}"
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
        file.save(upload_path)
        
        # 调用AI提取文字
        api_key = os.getenv('AI_API_KEY')
        if api_key:
            result = parse_medicine_info('', upload_path)
            text = f"name: {result.get('name','')}\napproval: {result.get('approval_number','')}\nmanufacturer: {result.get('manufacturer','')}\n\n{result.get('description','')}"
        else:
            text = "AI服务未配置"
        
        # 删除临时文件
        try:
            os.remove(upload_path)
        except:
            pass
        
        return jsonify({
            'success': True,
            'data': {
                'text': text,
                'key_info': {}
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
