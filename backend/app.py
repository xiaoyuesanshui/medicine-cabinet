#!/usr/bin/env python3
"""
药品管理系统 - Flask后端
支持：OCR识别、AI解析、药品CRUD、过期提醒
"""

import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from models import init_db, Medicine, db_session
from utils.ocr import extract_text_from_image
from utils.ai_parser import parse_medicine_info
from routes.scan import scan_bp

# 加载环境变量
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), '..', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# 版本信息
__version__ = '1.0.0'

CORS(app)

# 注册蓝图
app.register_blueprint(scan_bp)

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 初始化数据库
init_db()

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')


@app.route('/api/version', methods=['GET'])
def get_version():
    """获取系统版本信息"""
    return jsonify({
        'version': __version__,
        'name': '药品管理系统',
        'release_date': '2026-04-16'
    })


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('../frontend', path)


# ========== 药品管理API ==========

@app.route('/api/medicines', methods=['GET'])
def get_medicines():
    """获取药品列表，支持搜索和过滤（聚合展示）"""
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    location = request.args.get('location', '')
    expiring_soon = request.args.get('expiring_soon', 'false').lower() == 'true'
    
    with db_session() as session:
        query = session.query(Medicine)
        
        if search:
            search_filter = f'%{search}%'
            query = query.filter(
                (Medicine.name.like(search_filter)) |
                (Medicine.ingredients.like(search_filter)) |
                (Medicine.indications.like(search_filter))
            )
        
        if category:
            query = query.filter(Medicine.category == category)
        
        # 位置搜索 - 支持 A3 格式
        if location:
            location = location.upper().strip()
            # 解析位置格式如 A3, B12
            import re
            match = re.match(r'^([A-Z])(\d{1,2})$', location)
            if match:
                row = match.group(1)
                col = int(match.group(2))
                query = query.filter(
                    (Medicine.location_row == row) &
                    (Medicine.location_col == col)
                )
        
        if expiring_soon:
            threshold = datetime.now() + timedelta(days=30)
            query = query.filter(Medicine.expiry_date <= threshold)
        
        # 按过期日期排序（最近的在前）
        query = query.order_by(Medicine.expiry_date)
        
        medicines = query.all()
        
        # 按药品名称聚合
        grouped = {}
        for m in medicines:
            key = m.name  # 使用药品名称作为聚合键
            if key not in grouped:
                grouped[key] = {
                    'name': m.name,
                    'count': 0,
                    'batches': [],
                    'info': m.to_dict()  # 保存第一个批次的完整信息用于展示
                }
            grouped[key]['count'] += 1
            grouped[key]['batches'].append({
                'id': m.id,
                'expiry_date': m.expiry_date.strftime('%Y-%m-%d') if m.expiry_date else None,
                'expiry_status': m._expiry_status(),
                'days_until_expiry': m._days_until_expiry(),
                'effective_expiry_date': m._effective_expiry_date().strftime('%Y-%m-%d') if m._effective_expiry_date() else None,
                'is_opened': m.opened_date is not None,
                'opened_date': m.opened_date.strftime('%Y-%m-%d') if m.opened_date else None,
                'shelf_life_after_opening': m.shelf_life_after_opening,
                'location': m._format_location(),
                'location_row': m.location_row,
                'location_col': m.location_col,
                'notes': m.notes,
                'created_at': m.created_at.strftime('%Y-%m-%d %H:%M:%S') if m.created_at else None
            })
        
        # 转换为列表并按名称排序
        result = list(grouped.values())
        result.sort(key=lambda x: x['name'])
        
        return jsonify(result)


@app.route('/api/medicines/<name>/batches', methods=['GET'])
def get_medicine_batches(name):
    """获取某个药品的所有批次详情"""
    with db_session() as session:
        medicines = session.query(Medicine).filter(Medicine.name == name).all()
        if not medicines:
            return jsonify({'error': '药品不存在'}), 404
        
        # 获取第一个药品的完整信息作为基础信息
        base_info = medicines[0].to_dict()
        
        # 收集所有批次
        batches = []
        for m in medicines:
            batches.append({
                'id': m.id,
                'expiry_date': m.expiry_date.strftime('%Y-%m-%d') if m.expiry_date else None,
                'expiry_status': m._expiry_status(),
                'days_until_expiry': m._days_until_expiry(),
                'effective_expiry_date': m._effective_expiry_date().strftime('%Y-%m-%d') if m._effective_expiry_date() else None,
                'is_opened': m.opened_date is not None,
                'opened_date': m.opened_date.strftime('%Y-%m-%d') if m.opened_date else None,
                'shelf_life_after_opening': m.shelf_life_after_opening,
                'location': m._format_location(),
                'location_row': m.location_row,
                'location_col': m.location_col,
                'notes': m.notes,
                'created_at': m.created_at.strftime('%Y-%m-%d %H:%M:%S') if m.created_at else None
            })
        
        # 按过期日期排序
        batches.sort(key=lambda x: x['expiry_date'] or '9999-12-31')
        
        return jsonify({
            'name': name,
            'count': len(batches),
            'info': base_info,
            'batches': batches
        })


@app.route('/api/medicines/<int:medicine_id>', methods=['GET'])
def get_medicine(medicine_id):
    """获取单个药品详情"""
    with db_session() as session:
        medicine = session.query(Medicine).get(medicine_id)
        if not medicine:
            return jsonify({'error': '药品不存在'}), 404
        return jsonify(medicine.to_dict())


@app.route('/api/medicines', methods=['POST'])
def create_medicine():
    """创建新药品记录"""
    data = request.get_json()
    
    with db_session() as session:
        medicine = Medicine(
            name=data.get('name', ''),
            ingredients=data.get('ingredients', ''),
            indications=data.get('indications', ''),
            is_prescription=data.get('is_prescription', False),
            expiry_date=datetime.strptime(data['expiry_date'], '%Y-%m-%d') if data.get('expiry_date') else None,
            category=data.get('category', 'other'),
            manufacturer=data.get('manufacturer', ''),
            dosage=data.get('dosage', ''),
            notes=data.get('notes', ''),
            image_path=data.get('image_path', ''),
            # 极速数据 API 扩展字段
            medicine_id=str(data.get('medicine_id', '')),
            barcode=data.get('barcode', ''),
            approval_number=data.get('approval_number', ''),
            specification=data.get('specification', ''),
            drug_type=data.get('drug_type', ''),
            unit=data.get('unit', ''),
            disease=data.get('disease', ''),
            prescription_type=data.get('prescription_type', 0),
            retail_price=data.get('retail_price', ''),
            drug_image=data.get('drug_image', ''),
            description=data.get('description', ''),
            alias=data.get('alias', ''),
            location_col=data.get('location_col'),
            location_row=data.get('location_row'),
            shelf_life_after_opening=data.get('shelf_life_after_opening')
        )
        session.add(medicine)
        session.commit()
        return jsonify(medicine.to_dict()), 201


@app.route('/api/medicines/<int:medicine_id>', methods=['PUT'])
def update_medicine(medicine_id):
    """更新药品记录"""
    data = request.get_json()
    
    with db_session() as session:
        medicine = session.query(Medicine).get(medicine_id)
        if not medicine:
            return jsonify({'error': '药品不存在'}), 404
        
        medicine.name = data.get('name', medicine.name)
        medicine.ingredients = data.get('ingredients', medicine.ingredients)
        medicine.indications = data.get('indications', medicine.indications)
        medicine.is_prescription = data.get('is_prescription', medicine.is_prescription)
        if data.get('expiry_date'):
            medicine.expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d')
        medicine.category = data.get('category', medicine.category)
        medicine.manufacturer = data.get('manufacturer', medicine.manufacturer)
        medicine.dosage = data.get('dosage', medicine.dosage)
        medicine.notes = data.get('notes', medicine.notes)
        # 扩展字段
        medicine.barcode = data.get('barcode', medicine.barcode)
        medicine.approval_number = data.get('approval_number', medicine.approval_number)
        medicine.specification = data.get('specification', medicine.specification)
        medicine.drug_type = data.get('drug_type', medicine.drug_type)
        medicine.disease = data.get('disease', medicine.disease)
        medicine.retail_price = data.get('retail_price', medicine.retail_price)
        medicine.drug_image = data.get('drug_image', medicine.drug_image)
        medicine.description = data.get('description', medicine.description)
        medicine.alias = data.get('alias', medicine.alias)
        medicine.location_col = data.get('location_col', medicine.location_col)
        medicine.location_row = data.get('location_row', medicine.location_row)
        medicine.shelf_life_after_opening = data.get('shelf_life_after_opening', medicine.shelf_life_after_opening)
        
        session.commit()
        return jsonify(medicine.to_dict())


@app.route('/api/medicines/batches', methods=['GET'])
def get_medicine_batches_by_name():
    """获取指定药品名称的所有批次（库存记录）"""
    from urllib.parse import unquote
    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({'error': '请提供药品名称'}), 400
    
    name = unquote(name)
    
    with db_session() as session:
        # 查询所有同名药品，按过期日期排序
        medicines = session.query(Medicine).filter(
            Medicine.name == name
        ).order_by(Medicine.expiry_date.asc()).all()
        
        if not medicines:
            return jsonify({'error': '药品不存在'}), 404
        
        # 构建批次列表
        batches = []
        for idx, med in enumerate(medicines, 1):
            batches.append({
                'batch_id': idx,
                'medicine_id': med.id,
                'id': med.id,
                'expiry_date': med.expiry_date.strftime('%Y-%m-%d') if med.expiry_date else None,
                'days_until_expiry': med._days_until_expiry(),
                'expiry_status': med._expiry_status(),
                'effective_expiry_date': med._effective_expiry_date().strftime('%Y-%m-%d') if med._effective_expiry_date() else None,
                'is_opened': med.opened_date is not None,
                'opened_date': med.opened_date.strftime('%Y-%m-%d') if med.opened_date else None,
                'shelf_life_after_opening': med.shelf_life_after_opening,
                'location': med._format_location(),
                'location_row': med.location_row,
                'location_col': med.location_col,
                'notes': med.notes,
                'created_at': med.created_at.strftime('%Y-%m-%d %H:%M:%S') if med.created_at else None,
                # 药品基本信息（所有批次相同）
                'name': med.name,
                'alias': med.alias,
                'specification': med.specification,
                'drug_type': med.drug_type,
                'manufacturer': med.manufacturer,
                'approval_number': med.approval_number,
                'barcode': med.barcode,
                'is_prescription': med.is_prescription,
                'prescription_type': med.prescription_type,
                'retail_price': med.retail_price,
                'ingredients': med.ingredients,
                'indications': med.indications,
                'dosage': med.dosage,
                'adverse_reactions': med.adverse_reactions,
                'contraindications': med.contraindications,
                'precautions': med.precautions,
                'storage': med.storage,
                'description': med.description
            })
        
        return jsonify({
            'name': name,
            'total_batches': len(batches),
            'batches': batches
        })


@app.route('/api/medicines/<int:medicine_id>/open', methods=['POST'])
def open_medicine(medicine_id):
    """标记药品批次为已开封"""
    with db_session() as session:
        medicine = session.query(Medicine).get(medicine_id)
        if not medicine:
            return jsonify({'error': '药品不存在'}), 404
        
        if medicine.opened_date:
            return jsonify({'error': '该批次已开封', 'opened_date': medicine.opened_date.strftime('%Y-%m-%d')}), 400
        
        if not medicine.shelf_life_after_opening:
            return jsonify({'error': '请先设置开封后保质期'}), 400
        
        medicine.opened_date = datetime.now()
        medicine.updated_at = datetime.now()
        session.commit()
        return jsonify(medicine.to_dict())


@app.route('/api/medicines/<int:medicine_id>/unopen', methods=['POST'])
def unopen_medicine(medicine_id):
    """取消开封状态"""
    with db_session() as session:
        medicine = session.query(Medicine).get(medicine_id)
        if not medicine:
            return jsonify({'error': '药品不存在'}), 404
        
        medicine.opened_date = None
        medicine.updated_at = datetime.now()
        session.commit()
        return jsonify(medicine.to_dict())


@app.route('/api/medicines/<int:medicine_id>', methods=['DELETE'])
def delete_medicine(medicine_id):
    """删除药品记录"""
    with db_session() as session:
        medicine = session.query(Medicine).get(medicine_id)
        if not medicine:
            return jsonify({'error': '药品不存在'}), 404
        
        session.delete(medicine)
        session.commit()
        return jsonify({'message': '删除成功'})


# ========== 扫描识别API ==========

@app.route('/api/scan', methods=['POST'])
def scan_medicine():
    """
    上传药盒照片，OCR识别 + AI解析
    返回结构化药品信息
    """
    if 'image' not in request.files:
        return jsonify({'error': '请上传图片'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件格式'}), 400
    
    # 保存上传的文件
    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    try:
        # 1. OCR提取文字
        raw_text = extract_text_from_image(filepath)
        
        if not raw_text or len(raw_text.strip()) < 5:
            return jsonify({
                'success': False,
                'error': '未能识别出文字，请尝试更清晰的照片',
                'raw_text': '',
                'image_path': filename
            })
        
        # 2. AI解析结构化信息
        parsed_info = parse_medicine_info(raw_text)
        
        return jsonify({
            'success': True,
            'raw_text': raw_text,
            'parsed': parsed_info,
            'image_path': filename
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'识别失败: {str(e)}',
            'raw_text': raw_text if 'raw_text' in locals() else '',
            'image_path': filename
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计信息"""
    with db_session() as session:
        total = session.query(Medicine).count()
        
        now = datetime.now()
        threshold = now + timedelta(days=30)
        
        expiring_soon = session.query(Medicine).filter(
            Medicine.expiry_date <= threshold,
            Medicine.expiry_date >= now
        ).count()
        
        expired = session.query(Medicine).filter(
            Medicine.expiry_date < now
        ).count()
        
        # 按分类统计
        categories = {}
        for cat in ['internal', 'external', 'topical', 'supplement', 'other']:
            count = session.query(Medicine).filter(Medicine.category == cat).count()
            categories[cat] = count
        
        return jsonify({
            'total': total,
            'expiring_soon': expiring_soon,
            'expired': expired,
            'categories': categories
        })


if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    # 检查是否使用SSL
    ssl_dir = os.path.join(os.path.dirname(__file__), '..', 'ssl')
    cert_file = os.path.join(ssl_dir, 'server.crt')
    key_file = os.path.join(ssl_dir, 'server.key')
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print(f"🔐 使用HTTPS: https://{host}:{port}")
        app.run(host=host, port=port, debug=debug, ssl_context=(cert_file, key_file))
    else:
        print(f"🌐 使用HTTP: http://{host}:{port}")
        app.run(host=host, port=port, debug=debug)
