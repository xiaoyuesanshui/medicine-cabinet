"""
API缓存数据库 - 独立存储极速数据API返回结果
与药品库存数据库分离，开发时删除medicines.db不会影响API缓存
"""

import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

# API缓存数据库路径（独立文件）
CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_cache.db')
os.makedirs(os.path.dirname(CACHE_DB_PATH), exist_ok=True)

engine = create_engine(f'sqlite:///{CACHE_DB_PATH}', echo=False)
SessionLocal = sessionmaker(bind=engine)


class APICache(Base):
    """API数据缓存表"""
    __tablename__ = 'api_cache'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    barcode = Column(String(50), unique=True, nullable=False, index=True)  # 商品条码
    
    # API返回的原始数据
    name = Column(String(200), default='')  # 药品名称
    specification = Column(String(200), default='')  # 规格
    drug_type = Column(String(100), default='')  # 剂型
    manufacturer = Column(String(200), default='')  # 生产厂家
    approval_number = Column(String(100), default='')  # 批准文号
    medicine_id = Column(String(50), default='')  # 极速数据药品ID
    disease = Column(Text, default='')  # 适应疾病
    prescription_type = Column(Integer, default=0)  # 处方类型: 0=未知, 1=Rx, 2=OTC
    retail_price = Column(String(50), default='')  # 零售价
    drug_image = Column(String(500), default='')  # 药品官方图片URL
    description = Column(Text, default='')  # 完整说明书
    
    # 说明书解析字段
    ingredients = Column(Text, default='')  # 主要成份
    indications = Column(Text, default='')  # 适应症
    dosage = Column(Text, default='')  # 用法用量
    adverse_reactions = Column(Text, default='')  # 不良反应
    contraindications = Column(Text, default='')  # 禁忌
    precautions = Column(Text, default='')  # 注意事项
    storage = Column(Text, default='')  # 贮藏
    shelf_life = Column(String(50), default='')  # 有效期
    
    # 缓存元数据
    cached_at = Column(DateTime, default=datetime.now)  # 缓存时间
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)  # 更新时间
    access_count = Column(Integer, default=1)  # 访问次数
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            'barcode': self.barcode,
            'name': self.name,
            'specification': self.specification,
            'drug_type': self.drug_type,
            'manufacturer': self.manufacturer,
            'approval_number': self.approval_number,
            'medicine_id': self.medicine_id,
            'disease': self.disease,
            'prescription_type': self.prescription_type,
            'retail_price': self.retail_price,
            'drug_image': self.drug_image,
            'description': self.description,
            'ingredients': self.ingredients,
            'indications': self.indications,
            'dosage': self.dosage,
            'adverse_reactions': self.adverse_reactions,
            'contraindications': self.contraindications,
            'precautions': self.precautions,
            'storage': self.storage,
            'shelf_life': self.shelf_life,
            'cached_at': self.cached_at.strftime('%Y-%m-%d %H:%M:%S') if self.cached_at else None,
            'access_count': self.access_count
        }
    
    def is_expired(self, days=180):
        """检查缓存是否过期（默认180天）"""
        if not self.cached_at:
            return True
        expiry_date = self.cached_at + timedelta(days=days)
        return datetime.now() > expiry_date


@contextmanager
def cache_session():
    """缓存数据库会话上下文管理器"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_cache_db():
    """初始化API缓存数据库"""
    Base.metadata.create_all(engine)


class APICacheManager:
    """API缓存管理器"""
    
    CACHE_VALID_DAYS = 180  # 缓存有效期180天
    
    @staticmethod
    def get_by_barcode(barcode):
        """根据条码获取缓存数据"""
        with cache_session() as db:
            cache = db.query(APICache).filter_by(barcode=barcode).first()
            if cache:
                # 更新访问次数
                cache.access_count += 1
                cache.updated_at = datetime.now()
                # 在session内转换为dict，避免session外访问
                result = cache.to_dict()
                return result
            return None
    
    @staticmethod
    def get_valid_cache(barcode):
        """获取有效的缓存数据（未过期）"""
        with cache_session() as db:
            cache = db.query(APICache).filter_by(barcode=barcode).first()
            if cache:
                # 检查是否过期
                if not cache.is_expired(APICacheManager.CACHE_VALID_DAYS):
                    # 更新访问次数
                    cache.access_count += 1
                    cache.updated_at = datetime.now()
                    # 在session内转换为dict
                    return cache.to_dict()
            return None
    
    @staticmethod
    def save_cache(barcode, data):
        """保存或更新缓存数据"""
        with cache_session() as db:
            cache = db.query(APICache).filter_by(barcode=barcode).first()
            
            if cache:
                # 更新现有缓存
                cache.name = data.get('name', cache.name)
                cache.specification = data.get('specification', cache.specification)
                cache.drug_type = data.get('drug_type', cache.drug_type)
                cache.manufacturer = data.get('manufacturer', cache.manufacturer)
                cache.approval_number = data.get('approval_number', cache.approval_number)
                cache.medicine_id = data.get('medicine_id', cache.medicine_id)
                cache.disease = data.get('disease', cache.disease)
                cache.prescription_type = data.get('prescription_type', cache.prescription_type)
                cache.retail_price = data.get('retail_price', cache.retail_price)
                cache.drug_image = data.get('drug_image', cache.drug_image)
                cache.description = data.get('description', cache.description)
                cache.ingredients = data.get('ingredients', cache.ingredients)
                cache.indications = data.get('indications', cache.indications)
                cache.dosage = data.get('dosage', cache.dosage)
                cache.adverse_reactions = data.get('adverse_reactions', cache.adverse_reactions)
                cache.contraindications = data.get('contraindications', cache.contraindications)
                cache.precautions = data.get('precautions', cache.precautions)
                cache.storage = data.get('storage', cache.storage)
                cache.shelf_life = data.get('shelf_life', cache.shelf_life)
                cache.cached_at = datetime.now()
                cache.updated_at = datetime.now()
            else:
                # 创建新缓存
                cache = APICache(
                    barcode=barcode,
                    name=data.get('name', ''),
                    specification=data.get('specification', ''),
                    drug_type=data.get('drug_type', ''),
                    manufacturer=data.get('manufacturer', ''),
                    approval_number=data.get('approval_number', ''),
                    medicine_id=data.get('medicine_id', ''),
                    disease=data.get('disease', ''),
                    prescription_type=data.get('prescription_type', 0),
                    retail_price=data.get('retail_price', ''),
                    drug_image=data.get('drug_image', ''),
                    description=data.get('description', ''),
                    ingredients=data.get('ingredients', ''),
                    indications=data.get('indications', ''),
                    dosage=data.get('dosage', ''),
                    adverse_reactions=data.get('adverse_reactions', ''),
                    contraindications=data.get('contraindications', ''),
                    precautions=data.get('precautions', ''),
                    storage=data.get('storage', ''),
                    shelf_life=data.get('shelf_life', ''),
                    cached_at=datetime.now(),
                    updated_at=datetime.now(),
                    access_count=1
                )
                db.add(cache)
            
            return cache
    
    @staticmethod
    def delete_cache(barcode):
        """删除缓存"""
        with cache_session() as db:
            cache = db.query(APICache).filter_by(barcode=barcode).first()
            if cache:
                db.delete(cache)
                return True
            return False
    
    @staticmethod
    def get_stats():
        """获取缓存统计"""
        with cache_session() as db:
            total = db.query(APICache).count()
            expired = db.query(APICache).filter(
                APICache.cached_at < datetime.now() - timedelta(days=APICacheManager.CACHE_VALID_DAYS)
            ).count()
            return {
                'total': total,
                'expired': expired,
                'valid': total - expired
            }


# 初始化数据库
init_cache_db()
