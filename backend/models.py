"""
数据库模型 - 药品管理
"""

import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'medicines.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
SessionLocal = sessionmaker(bind=engine)


class Medicine(Base):
    __tablename__ = 'medicines'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)  # 药品名称
    ingredients = Column(Text, default='')  # 成分
    indications = Column(Text, default='')  # 适应症
    is_prescription = Column(Boolean, default=False)  # 是否处方药
    expiry_date = Column(DateTime, nullable=True)  # 过期日期
    category = Column(String(50), default='other')  # 分类
    manufacturer = Column(String(200), default='')  # 生产厂家
    dosage = Column(Text, default='')  # 用法用量
    notes = Column(Text, default='')  # 备注
    image_path = Column(String(500), default='')  # 用户上传的图片路径
    created_at = Column(DateTime, default=datetime.now)  # 创建时间
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)  # 更新时间
    
    # 极速数据 API 返回的扩展字段
    medicine_id = Column(String(50), default='')  # 极速数据药品ID
    barcode = Column(String(50), default='')  # 商品条码
    approval_number = Column(String(100), default='')  # 批准文号
    specification = Column(String(200), default='')  # 规格
    drug_type = Column(String(100), default='')  # 剂型
    unit = Column(String(50), default='')  # 单位
    disease = Column(Text, default='')  # 适应疾病
    prescription_type = Column(Integer, default=0)  # 处方类型: 0=未知, 1=Rx, 2=OTC
    retail_price = Column(String(50), default='')  # 零售价
    drug_image = Column(String(500), default='')  # 药品官方图片URL
    description = Column(Text, default='')  # 完整说明书
    alias = Column(String(200), default='')  # 别名/用户自定义名称
    location_col = Column(Integer, default=None)  # 位置列 (1-19)
    location_row = Column(String(1), default=None)  # 位置行 (A-Z)
    
    # 说明书解析的额外字段
    adverse_reactions = Column(Text, default='')  # 不良反应
    contraindications = Column(Text, default='')  # 禁忌
    precautions = Column(Text, default='')  # 注意事项
    storage = Column(Text, default='')  # 贮藏
    shelf_life = Column(String(50), default='')  # 有效期
    shelf_life_after_opening = Column(Integer, default=None)  # 开封后保质期（天）
    opened_date = Column(DateTime, default=None)  # 开封日期
    
    # API缓存相关字段
    api_cache_time = Column(DateTime, default=None)  # API数据缓存时间
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'ingredients': self.ingredients,
            'indications': self.indications,
            'is_prescription': self.is_prescription,
            'expiry_date': self.expiry_date.strftime('%Y-%m-%d') if self.expiry_date else None,
            'category': self.category,
            'manufacturer': self.manufacturer,
            'dosage': self.dosage,
            'notes': self.notes,
            'image_path': self.image_path,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
            # 计算字段
            'days_until_expiry': self._days_until_expiry(),
            'expiry_status': self._expiry_status(),
            'effective_expiry_date': self._effective_expiry_date().strftime('%Y-%m-%d') if self._effective_expiry_date() else None,
            'is_opened': self.opened_date is not None,
            # 极速数据扩展字段
            'medicine_id': self.medicine_id,
            'barcode': self.barcode,
            'approval_number': self.approval_number,
            'specification': self.specification,
            'drug_type': self.drug_type,
            'unit': self.unit,
            'disease': self.disease,
            'prescription_type': self.prescription_type,
            'retail_price': self.retail_price,
            'drug_image': self.drug_image,
            'description': self.description,
            'alias': self.alias,
            'location_col': self.location_col,
            'location_row': self.location_row,
            'location': self._format_location(),
            # 说明书解析字段
            'adverse_reactions': self.adverse_reactions,
            'contraindications': self.contraindications,
            'precautions': self.precautions,
            'storage': self.storage,
            'shelf_life': self.shelf_life,
            'shelf_life_after_opening': self.shelf_life_after_opening,
            'opened_date': self.opened_date.strftime('%Y-%m-%d') if self.opened_date else None,
            'api_cache_time': self.api_cache_time.strftime('%Y-%m-%d %H:%M:%S') if self.api_cache_time else None
        }
    
    def _format_location(self):
        """格式化位置显示，如 A3"""
        if self.location_row and self.location_col:
            return f"{self.location_row}{self.location_col}"
        return None
    
    def _effective_expiry_date(self):
        """计算实际有效期：如果已开封且有开封后保质期，则取开封日期+保质期天数与原有效期的较早者"""
        if not self.expiry_date:
            return None
        
        if self.opened_date and self.shelf_life_after_opening:
            opened_expiry = self.opened_date + timedelta(days=self.shelf_life_after_opening)
            # 取两个日期中较早的
            return min(self.expiry_date, opened_expiry)
        
        return self.expiry_date
    
    def _days_until_expiry(self):
        effective = self._effective_expiry_date()
        if not effective:
            return None
        delta = effective - datetime.now()
        return delta.days
    
    def _expiry_status(self):
        """返回过期状态: safe, warning, danger, expired, opened_expired"""
        effective = self._effective_expiry_date()
        if not effective and not self.expiry_date:
            return 'unknown'
        
        if not effective:
            effective = self.expiry_date
        
        days = (effective - datetime.now()).days
        
        # 如果已开封且按开封保质期过期
        if self.opened_date and self.shelf_life_after_opening:
            opened_expiry = self.opened_date + timedelta(days=self.shelf_life_after_opening)
            if opened_expiry <= self.expiry_date:
                # 开封后保质期更短，使用开封相关的状态
                if days < 0:
                    return 'opened_expired'
                elif days <= 3:
                    return 'danger'
                elif days <= 7:
                    return 'warning'
                else:
                    return 'safe'
        
        if days < 0:
            return 'expired'
        elif days <= 7:
            return 'danger'
        elif days <= 30:
            return 'warning'
        else:
            return 'safe'


def init_db():
    """初始化数据库"""
    Base.metadata.create_all(engine)


@contextmanager
def db_session():
    """数据库会话上下文管理器"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_db():
    """获取数据库会话（用于SQLAlchemy ORM操作）"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class MedicineDB:
    """药品数据库操作类"""
    
    @staticmethod
    def create(data):
        """创建新药品"""
        with db_session() as db:
            medicine = Medicine(**data)
            db.add(medicine)
            db.flush()
            return medicine.id
    
    @staticmethod
    def get_by_id(medicine_id):
        """根据ID获取药品"""
        with db_session() as db:
            medicine = db.query(Medicine).filter_by(id=medicine_id).first()
            return medicine.to_dict() if medicine else None
    
    @staticmethod
    def get_by_barcode(barcode):
        """根据条码获取药品"""
        with db_session() as db:
            medicine = db.query(Medicine).filter_by(barcode=barcode).first()
            return medicine
    
    @staticmethod
    def get_all(limit=None, offset=None):
        """获取所有药品"""
        with db_session() as db:
            query = db.query(Medicine).order_by(Medicine.created_at.desc())
            if limit:
                query = query.limit(limit)
            if offset:
                query = query.offset(offset)
            return [m.to_dict() for m in query.all()]
    
    @staticmethod
    def update(medicine_id, data):
        """更新药品信息"""
        with db_session() as db:
            medicine = db.query(Medicine).filter_by(id=medicine_id).first()
            if not medicine:
                return False
            for key, value in data.items():
                if hasattr(medicine, key):
                    setattr(medicine, key, value)
            medicine.updated_at = datetime.now()
            return True
    
    @staticmethod
    def delete(medicine_id):
        """删除药品"""
        with db_session() as db:
            medicine = db.query(Medicine).filter_by(id=medicine_id).first()
            if not medicine:
                return False
            db.delete(medicine)
            return True
    
    @staticmethod
    def search(keyword):
        """搜索药品"""
        with db_session() as db:
            medicines = db.query(Medicine).filter(
                (Medicine.name.contains(keyword)) |
                (Medicine.manufacturer.contains(keyword)) |
                (Medicine.alias.contains(keyword))
            ).all()
            return [m.to_dict() for m in medicines]
    
    @staticmethod
    def get_by_category(category):
        """根据分类获取药品"""
        with db_session() as db:
            medicines = db.query(Medicine).filter_by(category=category).all()
            return [m.to_dict() for m in medicines]
    
    @staticmethod
    def get_expiring_soon(days=30):
        """获取即将过期的药品"""
        with db_session() as db:
            from datetime import timedelta
            expiry_threshold = datetime.now() + timedelta(days=days)
            medicines = db.query(Medicine).filter(
                Medicine.expiry_date <= expiry_threshold,
                Medicine.expiry_date >= datetime.now()
            ).all()
            return [m.to_dict() for m in medicines]
    
    @staticmethod
    def get_expired():
        """获取已过期的药品"""
        with db_session() as db:
            medicines = db.query(Medicine).filter(
                Medicine.expiry_date < datetime.now()
            ).all()
            return [m.to_dict() for m in medicines]
    
    @staticmethod
    def get_stats():
        """获取统计信息"""
        with db_session() as db:
            total = db.query(Medicine).count()
            expiring_soon = len(MedicineDB.get_expiring_soon(30))
            expired = len(MedicineDB.get_expired())
            return {
                'total': total,
                'expiring_soon': expiring_soon,
                'expired': expired
            }
