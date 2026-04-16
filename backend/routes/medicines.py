"""
药品管理API路由
"""
from flask import Blueprint, request, jsonify
from models import MedicineDB, Medicine, init_db

medicines_bp = Blueprint('medicines', __name__)


@medicines_bp.route('/api/medicines', methods=['GET'])
def get_medicines():
    """获取药品列表"""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    medicines = MedicineDB.get_all(limit=limit, offset=offset)
    return jsonify({
        'success': True,
        'data': [m.to_dict() for m in medicines]
    })


@medicines_bp.route('/api/medicines/<int:medicine_id>', methods=['GET'])
def get_medicine(medicine_id):
    """获取单个药品详情"""
    medicine = MedicineDB.get_by_id(medicine_id)
    if not medicine:
        return jsonify({'success': False, 'error': '药品不存在'}), 404
    
    return jsonify({
        'success': True,
        'data': medicine.to_dict()
    })


@medicines_bp.route('/api/medicines', methods=['POST'])
def create_medicine():
    """创建新药品"""
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({'success': False, 'error': '药品名称不能为空'}), 400
    
    try:
        # 如果同名药品已存在，复制其基本信息（规格、剂型、成分等）
        existing = MedicineDB.get_by_name(data['name'])
        if existing:
            # 复制现有药品的基本信息（如果新数据中没有）
            fields_to_copy = ['specification', 'drug_type', 'ingredients', 'indications', 
                            'manufacturer', 'approval_number', 'barcode', 'dosage',
                            'adverse_reactions', 'contraindications', 'precautions', 
                            'storage', 'shelf_life', 'description', 'drug_image',
                            'medicine_id', 'unit', 'reference_code', 'interactions']
            for field in fields_to_copy:
                if not data.get(field) and getattr(existing, field, None):
                    data[field] = getattr(existing, field)
        
        medicine_id = MedicineDB.create(data)
        return jsonify({
            'success': True,
            'data': {'id': medicine_id}
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@medicines_bp.route('/api/medicines/<int:medicine_id>', methods=['PUT'])
def update_medicine(medicine_id):
    """更新药品信息"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': '没有提供更新数据'}), 400
    
    medicine = MedicineDB.get_by_id(medicine_id)
    if not medicine:
        return jsonify({'success': False, 'error': '药品不存在'}), 404
    
    try:
        success = MedicineDB.update(medicine_id, data)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '更新失败'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@medicines_bp.route('/api/medicines/<int:medicine_id>', methods=['DELETE'])
def delete_medicine(medicine_id):
    """删除药品"""
    medicine = MedicineDB.get_by_id(medicine_id)
    if not medicine:
        return jsonify({'success': False, 'error': '药品不存在'}), 404
    
    try:
        success = MedicineDB.delete(medicine_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '删除失败'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@medicines_bp.route('/api/medicines/<int:medicine_id>/open', methods=['POST'])
def open_medicine(medicine_id):
    """开封药品批次"""
    medicine = MedicineDB.get_by_id(medicine_id)
    if not medicine:
        return jsonify({'success': False, 'error': '药品不存在'}), 404
    
    if medicine.opened_date:
        return jsonify({'success': False, 'error': '该批次已开封'}), 400
    
    if not medicine.shelf_life_after_opening:
        return jsonify({'success': False, 'error': '未设置开封后保质期'}), 400
    
    try:
        from datetime import datetime
        success = MedicineDB.update(medicine_id, {'opened_date': datetime.now()})
        if success:
            return jsonify({'success': True, 'message': '开封成功'})
        else:
            return jsonify({'success': False, 'error': '开封失败'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@medicines_bp.route('/api/medicines/<int:medicine_id>/unopen', methods=['POST'])
def unopen_medicine(medicine_id):
    """取消开封状态"""
    medicine = MedicineDB.get_by_id(medicine_id)
    if not medicine:
        return jsonify({'success': False, 'error': '药品不存在'}), 404
    
    if not medicine.opened_date:
        return jsonify({'success': False, 'error': '该批次未开封'}), 400
    
    try:
        success = MedicineDB.update(medicine_id, {'opened_date': None})
        if success:
            return jsonify({'success': True, 'message': '已取消开封状态'})
        else:
            return jsonify({'success': False, 'error': '取消开封失败'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@medicines_bp.route('/api/medicines/search', methods=['GET'])
def search_medicines():
    """搜索药品"""
    keyword = request.args.get('q', '').strip()
    
    if not keyword:
        return jsonify({'success': False, 'error': '搜索关键词不能为空'}), 400
    
    medicines = MedicineDB.search(keyword)
    return jsonify({
        'success': True,
        'data': [m.to_dict() for m in medicines]
    })


@medicines_bp.route('/api/medicines/category/<category>', methods=['GET'])
def get_by_category(category):
    """按分类获取药品"""
    medicines = MedicineDB.get_by_category(category)
    return jsonify({
        'success': True,
        'data': [m.to_dict() for m in medicines]
    })


@medicines_bp.route('/api/medicines/expiring', methods=['GET'])
def get_expiring():
    """获取即将过期的药品"""
    days = request.args.get('days', 30, type=int)
    medicines = MedicineDB.get_expiring_soon(days)
    return jsonify({
        'success': True,
        'data': [m.to_dict() for m in medicines]
    })


@medicines_bp.route('/api/medicines/expired', methods=['GET'])
def get_expired():
    """获取已过期的药品"""
    medicines = MedicineDB.get_expired()
    return jsonify({
        'success': True,
        'data': [m.to_dict() for m in medicines]
    })


@medicines_bp.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计信息"""
    stats = MedicineDB.get_stats()
    return jsonify({
        'success': True,
        'data': stats
    })
