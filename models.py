"""
Database Models for Apna Online Store E-Commerce Application
تمام ڈیٹابیس ماڈلز
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """صارف کا ماڈل"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.String(500), default='')
    shop_name = db.Column(db.String(200), default='')
    is_admin = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    orders = db.relationship('Order', backref='customer', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Product(db.Model):
    """پروڈکٹ کا ماڈل"""
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    category = db.Column(db.String(100), default='')
    purchase_price = db.Column(db.Float, default=0.0)
    selling_price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500), default='')
    stock_quantity = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    purchase_list = db.relationship('PurchaseList', backref='product', lazy=True)


class Order(db.Model):
    """آرڈر کا ماڈل"""
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    total_amount = db.Column(db.Float, default=0.0)
    whatsapp_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    
    @property
    def status_display(self):
        status_map = {
            'pending': 'زیر التواء',
            'confirmed': 'تصدیق شدہ',
            'delivered': 'ترسیل شدہ',
            'cancelled': 'منسوخ'
        }
        return status_map.get(self.status, self.status)


class OrderItem(db.Model):
    """آرڈر کی ہر شے"""
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Float, nullable=False)


class PurchaseList(db.Model):
    """خریداری کی فہرست"""
    __tablename__ = 'purchase_list'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_needed = db.Column(db.Integer, nullable=False, default=0)
    is_purchased = db.Column(db.Boolean, default=False)
    purchase_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
