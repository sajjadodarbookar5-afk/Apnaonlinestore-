"""
apnaonlinestore E-Commerce Application - مین ایپلیکیشن فائل
"""

import os
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO

import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv
from flask import (Flask, render_template, request, redirect, url_for, 
                   flash, session, jsonify, send_file, abort)
from flask_login import (LoginManager, login_user, logout_user, 
                         login_required, current_user)

from models import db, User, Product, Order, OrderItem, PurchaseList

# ============================================
# CONFIGURATION
# ============================================
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///instance/wholesale.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# instance فولڈر بنائیں تاکہ ڈیٹابیس محفوظ رہے
os.makedirs('instance', exist_ok=True)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'customer_login'
login_manager.login_message = 'براہ کرم پہلے لاگ ان کریں'

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME', ''),
    api_key=os.getenv('CLOUDINARY_API_KEY', ''),
    api_secret=os.getenv('CLOUDINARY_API_SECRET', '')
)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('آپ کو اس صفحے تک رسائی کی اجازت نہیں ہے', 'error')
            return redirect(url_for('customer_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_globals():
    return {'now': datetime.utcnow(), 'current_year': datetime.utcnow().year}

def upload_to_cloudinary(file):
    try:
        result = cloudinary.uploader.upload(
            file,
            folder='wholesale_products',
            transformation=[
                {'width': 500, 'height': 500, 'crop': 'limit'},
                {'quality': 'auto', 'fetch_format': 'auto'}
            ]
        )
        return result['secure_url']
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

def get_dashboard_stats():
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    today_sales = db.session.query(db.func.sum(Order.total_amount)).filter(
        db.func.date(Order.created_at) == today,
        Order.status != 'cancelled'
    ).scalar() or 0
    
    week_sales = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.created_at >= datetime.combine(week_ago, datetime.min.time()),
        Order.status != 'cancelled'
    ).scalar() or 0
    
    month_sales = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.created_at >= datetime.combine(month_ago, datetime.min.time()),
        Order.status != 'cancelled'
    ).scalar() or 0
    
    total_sales = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.status != 'cancelled'
    ).scalar() or 0
    
    pending_orders = Order.query.filter_by(status='pending').count()
    confirmed_orders = Order.query.filter_by(status='confirmed').count()
    delivered_orders = Order.query.filter_by(status='delivered').count()
    total_orders = Order.query.count()
    total_customers = User.query.filter_by(is_admin=False).count()
    
    low_stock = Product.query.filter(
        Product.stock_quantity <= 10,
        Product.is_active == True
    ).all()
    
    daily_sales = []
    for i in range(7):
        date = today - timedelta(days=i)
        sales = db.session.query(db.func.sum(Order.total_amount)).filter(
            db.func.date(Order.created_at) == date,
            Order.status != 'cancelled'
        ).scalar() or 0
        daily_sales.append({'date': date.strftime('%d %b'), 'sales': sales})
    daily_sales.reverse()
    
    return {
        'today_sales': today_sales, 'week_sales': week_sales,
        'month_sales': month_sales, 'total_sales': total_sales,
        'pending_orders': pending_orders, 'confirmed_orders': confirmed_orders,
        'delivered_orders': delivered_orders, 'total_orders': total_orders,
        'total_customers': total_customers, 'low_stock': low_stock,
        'daily_sales': daily_sales
    }

# ============================================
# CUSTOMER ROUTES
# ============================================
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('customer_dashboard'))
    return redirect(url_for('customer_login'))

@app.route('/login', methods=['GET', 'POST'])
def customer_login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('customer_dashboard'))
    
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(phone=phone).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('خوش آمدید!', 'success')
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('customer_dashboard'))
        else:
            flash('فون نمبر یا پاس ورڈ غلط ہے', 'error')
    
    return render_template('customer_login.html')

@app.route('/register', methods=['GET', 'POST'])
def customer_register():
    if current_user.is_authenticated:
        return redirect(url_for('customer_dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        shop_name = request.form.get('shop_name', '').strip()
        address = request.form.get('address', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([name, phone, password]):
            flash('براہ کرم تمام ضروری فیلڈز پُر کریں', 'error')
            return render_template('customer_register.html')
        
        if password != confirm_password:
            flash('پاس ورڈز مماثل نہیں ہیں', 'error')
            return render_template('customer_register.html')
        
        if len(password) < 6:
            flash('پاس ورڈ کم از کم 6 حروف کا ہونا چاہیے', 'error')
            return render_template('customer_register.html')
        
        if User.query.filter_by(phone=phone).first():
            flash('یہ فون نمبر پہلے سے رجسٹرڈ ہے', 'error')
            return render_template('customer_register.html')
        
        user = User(name=name, phone=phone, shop_name=shop_name, address=address, is_admin=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('رجسٹریشن کامیاب! اب لاگ ان کریں', 'success')
        return redirect(url_for('customer_login'))
    
    return render_template('customer_register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('آپ کامیابی سے لاگ آؤٹ ہو گئے', 'success')
    return redirect(url_for('customer_login'))

@app.route('/dashboard')
@login_required
def customer_dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
    
    cart = session.get('cart', {})
    cart_items = []
    cart_total = 0
    
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product and product.is_active:
            item_total = product.selling_price * quantity
            cart_items.append({'product': product, 'quantity': quantity, 'total': item_total})
            cart_total += item_total
    
    return render_template('customer_dashboard.html',
                         products=products, orders=orders,
                         cart_items=cart_items, cart_total=cart_total)

@app.route('/products')
@login_required
def products_list():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    
    query = Product.query.filter_by(is_active=True)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    if category:
        query = query.filter_by(category=category)
    
    products = query.order_by(Product.name).all()
    categories = db.session.query(Product.category).filter(
        Product.is_active == True, Product.category != ''
    ).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('products.html', products=products,
                         categories=categories, search=search,
                         selected_category=category)

@app.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    
    if not product.is_active:
        flash('یہ پروڈکٹ دستیاب نہیں ہے', 'error')
        return redirect(url_for('products_list'))
    
    quantity = int(request.form.get('quantity', 1))
    
    if quantity > product.stock_quantity:
        flash(f'صرف {product.stock_quantity} عدد دستیاب ہیں', 'error')
        return redirect(url_for('products_list'))
    
    cart = session.get('cart', {})
    product_id_str = str(product_id)
    
    if product_id_str in cart:
        new_qty = cart[product_id_str] + quantity
        if new_qty > product.stock_quantity:
            flash(f'صرف {product.stock_quantity} عدد دستیاب ہیں', 'error')
            return redirect(url_for('products_list'))
        cart[product_id_str] = new_qty
    else:
        cart[product_id_str] = quantity
    
    session['cart'] = cart
    session.modified = True
    flash(f'{product.name} کارٹ میں شامل ہو گیا', 'success')
    return redirect(request.referrer or url_for('products_list'))

@app.route('/cart/update/<int:product_id>', methods=['POST'])
@login_required
def update_cart(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 0))
    
    cart = session.get('cart', {})
    product_id_str = str(product_id)
    
    if quantity <= 0:
        cart.pop(product_id_str, None)
    else:
        if quantity > product.stock_quantity:
            flash(f'صرف {product.stock_quantity} عدد دستیاب ہیں', 'error')
            return redirect(url_for('customer_dashboard'))
        cart[product_id_str] = quantity
    
    session['cart'] = cart
    session.modified = True
    flash('کارٹ اپ ڈیٹ ہو گیا', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/cart/remove/<int:product_id>', methods=['POST'])
@login_required
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    cart.pop(str(product_id), None)
    session['cart'] = cart
    session.modified = True
    flash('آئٹم کارٹ سے نکل گیا', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/cart/clear', methods=['POST'])
@login_required
def clear_cart():
    session.pop('cart', None)
    flash('کارٹ خالی ہو گیا', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/order/place', methods=['POST'])
@login_required
def place_order():
    cart = session.get('cart', {})
    
    if not cart:
        flash('کارٹ خالی ہے', 'error')
        return redirect(url_for('customer_dashboard'))
    
    total_amount = 0
    order_items = []
    
    for product_id_str, quantity in cart.items():
        product = Product.query.get(int(product_id_str))
        if not product or not product.is_active:
            flash('کچھ پروڈکٹس دستیاب نہیں ہیں', 'error')
            return redirect(url_for('customer_dashboard'))
        
        if quantity > product.stock_quantity:
            flash(f'{product.name} کے صرف {product.stock_quantity} عدد دستیاب ہیں', 'error')
            return redirect(url_for('customer_dashboard'))
        
        total_amount += product.selling_price * quantity
        order_items.append({'product': product, 'quantity': quantity, 'price': product.selling_price})
    
    order = Order(customer_id=current_user.id, total_amount=total_amount, status='pending')
    db.session.add(order)
    db.session.flush()
    
    for item in order_items:
        order_item = OrderItem(
            order_id=order.id, product_id=item['product'].id,
            quantity=item['quantity'], price=item['price']
        )
        db.session.add(order_item)
        item['product'].stock_quantity -= item['quantity']
    
    for item in order_items:
        existing = PurchaseList.query.filter_by(
            product_id=item['product'].id, is_purchased=False
        ).first()
        
        if existing:
            existing.quantity_needed += item['quantity']
        else:
            purchase_item = PurchaseList(
                product_id=item['product'].id,
                quantity_needed=item['quantity']
            )
            db.session.add(purchase_item)
    
    db.session.commit()
    session.pop('cart', None)
    flash('آرڈر کامیابی سے بھیج دیا گیا!', 'success')
    return redirect(url_for('order_detail', order_id=order.id))

@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if not current_user.is_admin and order.customer_id != current_user.id:
        abort(403)
    return render_template('order_detail.html', order=order)

@app.route('/orders')
@login_required
def order_history():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('order_history.html', orders=orders)

@app.route('/order/<int:order_id>/whatsapp')
@login_required
def order_whatsapp(order_id):
    order = Order.query.get_or_404(order_id)
    if not current_user.is_admin and order.customer_id != current_user.id:
        abort(403)
    
    message = f"*نیا آرڈر #{order.id}*\n\n"
    message += f"*صارف:* {order.customer.name}\n"
    message += f"*دکان:* {order.customer.shop_name}\n"
    message += f"*فون:* {order.customer.phone}\n"
    message += f"*پتہ:* {order.customer.address}\n\n"
    message += "*آرڈر کی تفصیلات:*\n━━━━━━━━━━━━━━━━━━\n"
    
    for item in order.items:
        message += f"• {item.product.name}\n  مقدار: {item.quantity} × Rs.{item.price:.0f} = Rs.{item.quantity * item.price:.0f}\n"
    
    message += f"━━━━━━━━━━━━━━━━━━\n*کل رقم: Rs.{order.total_amount:.0f}*\n"
    message += f"*اسٹیٹس:* {order.status_display}\n"
    message += f"*تاریخ:* {order.created_at.strftime('%d-%m-%Y %I:%M %p')}"
    
    order.whatsapp_sent = True
    db.session.commit()
    
    return redirect(f"https://wa.me/?text={message}")

# ============================================
# ADMIN ROUTES
# ============================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(phone=phone, is_admin=True).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('خوش آمدید ایڈمن!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('ایڈمن کی تفصیلات غلط ہیں', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    stats = get_dashboard_stats()
    return render_template('admin_dashboard.html', stats=stats)

@app.route('/admin/products')
@admin_required
def admin_products():
    search = request.args.get('search', '').strip()
    query = Product.query
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    products = query.order_by(Product.created_at.desc()).all()
    return render_template('admin_products.html', products=products, search=search)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_product_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        purchase_price = float(request.form.get('purchase_price', 0))
        selling_price = float(request.form.get('selling_price', 0))
        stock_quantity = int(request.form.get('stock_quantity', 0))
        
        if not name or selling_price <= 0:
            flash('براہ کرم نام اور فروخت کی قیمت درج کریں', 'error')
            return render_template('admin_product_form.html', product=None)
        
        image_url = ''
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                uploaded_url = upload_to_cloudinary(file)
                if uploaded_url:
                    image_url = uploaded_url
        
        product = Product(
            name=name, description=description, category=category,
            purchase_price=purchase_price, selling_price=selling_price,
            stock_quantity=stock_quantity, image_url=image_url, is_active=True
        )
        db.session.add(product)
        db.session.commit()
        flash('پروڈکٹ کامیابی سے شامل ہو گئی', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin_product_form.html', product=None)

@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        product.name = request.form.get('name', '').strip()
        product.description = request.form.get('description', '').strip()
        product.category = request.form.get('category', '').strip()
        product.purchase_price = float(request.form.get('purchase_price', 0))
        product.selling_price = float(request.form.get('selling_price', 0))
        product.stock_quantity = int(request.form.get('stock_quantity', 0))
        
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                uploaded_url = upload_to_cloudinary(file)
                if uploaded_url:
                    product.image_url = uploaded_url
        
        db.session.commit()
        flash('پروڈکٹ اپ ڈیٹ ہو گئی', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin_product_form.html', product=product)

@app.route('/admin/products/<int:product_id>/toggle', methods=['POST'])
@admin_required
def admin_product_toggle(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active
    db.session.commit()
    status = 'فعال' if product.is_active else 'غیر فعال'
    flash(f'پروڈکٹ {status} کر دی گئی', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@admin_required
def admin_product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('پروڈکٹ حذف ہو گئی', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/customers')
@admin_required
def admin_customers():
    search = request.args.get('search', '').strip()
    query = User.query.filter_by(is_admin=False)
    if search:
        query = query.filter(
            db.or_(User.name.ilike(f'%{search}%'), User.phone.ilike(f'%{search}%'),
                   User.shop_name.ilike(f'%{search}%'))
        )
    customers = query.order_by(User.created_at.desc()).all()
    
    customer_data = []
    for customer in customers:
        total_orders = Order.query.filter_by(customer_id=customer.id).count()
        total_spent = db.session.query(db.func.sum(Order.total_amount)).filter(
            Order.customer_id == customer.id, Order.status != 'cancelled'
        ).scalar() or 0
        customer_data.append({'customer': customer, 'total_orders': total_orders, 'total_spent': total_spent})
    
    return render_template('admin_customers.html', customers=customer_data, search=search)

@app.route('/admin/customers/<int:customer_id>/delete', methods=['POST'])
@admin_required
def admin_customer_delete(customer_id):
    customer = User.query.get_or_404(customer_id)
    if customer.is_admin:
        flash('ایڈمن کو حذف نہیں کیا جا سکتا', 'error')
        return redirect(url_for('admin_customers'))
    db.session.delete(customer)
    db.session.commit()
    flash('صارف حذف ہو گیا', 'success')
    return redirect(url_for('admin_customers'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '').strip()
    query = Order.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if search:
        query = query.join(User).filter(
            db.or_(User.name.ilike(f'%{search}%'), User.phone.ilike(f'%{search}%'))
        )
    orders = query.order_by(Order.created_at.desc()).all()
    return render_template('admin_orders.html', orders=orders,
                         status_filter=status_filter, search=search)

@app.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@admin_required
def admin_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status', '')
    
    if new_status in ['pending', 'confirmed', 'delivered', 'cancelled']:
        if new_status == 'cancelled' and order.status != 'cancelled':
            for item in order.items:
                item.product.stock_quantity += item.quantity
                purchase_item = PurchaseList.query.filter_by(
                    product_id=item.product_id, is_purchased=False
                ).first()
                if purchase_item:
                    purchase_item.quantity_needed = max(0, purchase_item.quantity_needed - item.quantity)
        
        if order.status == 'cancelled' and new_status != 'cancelled':
            for item in order.items:
                item.product.stock_quantity -= item.quantity
        
        order.status = new_status
        db.session.commit()
        flash('آرڈر کی اسٹیٹس تبدیل ہو گئی', 'success')
    else:
        flash('غلط اسٹیٹس', 'error')
    
    return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/orders/<int:order_id>')
@admin_required
def admin_order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('admin_order_detail.html', order=order)

@app.route('/admin/orders/<int:order_id>/whatsapp')
@admin_required
def admin_order_whatsapp(order_id):
    order = Order.query.get_or_404(order_id)
    message = f"*آرڈر #{order.id} - {order.status_display}*\n\n"
    message += f"السلام علیکم {order.customer.name} صاحب!\n\n"
    message += f"آپ کا آرڈر {order.status_display} ہو گیا ہے۔\n\n*آرڈر کی تفصیلات:*\n"
    
    for item in order.items:
        message += f"• {item.product.name} × {item.quantity} = Rs.{item.quantity * item.price:.0f}\n"
    
    message += f"\n*کل رقم: Rs.{order.total_amount:.0f}*\nشکریہ!"
    
    phone = order.customer.phone.replace('+', '').replace(' ', '')
    if not phone.startswith('92'):
        phone = '92' + phone.lstrip('0')
    
    return redirect(f"https://wa.me/{phone}?text={message}")

@app.route('/admin/purchase-list')
@admin_required
def admin_purchase_list():
    items = PurchaseList.query.filter_by(is_purchased=False).join(Product).order_by(Product.name).all()
    purchased = PurchaseList.query.filter_by(is_purchased=True).order_by(
        PurchaseList.purchase_date.desc()).limit(50).all()
    return render_template('admin_purchase_list.html', items=items, purchased=purchased)

@app.route('/admin/purchase-list/<int:item_id>/toggle', methods=['POST'])
@admin_required
def admin_purchase_toggle(item_id):
    item = PurchaseList.query.get_or_404(item_id)
    item.is_purchased = not item.is_purchased
    
    if item.is_purchased:
        item.purchase_date = datetime.utcnow()
        item.product.stock_quantity += item.quantity_needed
    else:
        item.purchase_date = None
        item.product.stock_quantity = max(0, item.product.stock_quantity - item.quantity_needed)
    
    db.session.commit()
    flash('خریداری کی فہرست اپ ڈیٹ ہو گئی', 'success')
    return redirect(url_for('admin_purchase_list'))

@app.route('/admin/purchase-list/<int:item_id>/delete', methods=['POST'])
@admin_required
def admin_purchase_delete(item_id):
    item = PurchaseList.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('آئٹم حذف ہو گیا', 'success')
    return redirect(url_for('admin_purchase_list'))

@app.route('/admin/purchase-list/clear-purchased', methods=['POST'])
@admin_required
def admin_purchase_clear():
    PurchaseList.query.filter_by(is_purchased=True).delete()
    db.session.commit()
    flash('خرید شدہ آئٹمز صاف ہو گئے', 'success')
    return redirect(url_for('admin_purchase_list'))

@app.route('/admin/purchase-list/export')
@admin_required
def admin_purchase_export():
    try:
        from openpyxl import Workbook
        items = PurchaseList.query.filter_by(is_purchased=False).all()
        wb = Workbook()
        ws = wb.active
        ws.title = "Purchase List"
        headers = ['Product', 'Quantity', 'Purchase Price', 'Total', 'Notes']
        ws.append(headers)
        
        total = 0
        for item in items:
            product = item.product
            cost = item.quantity_needed * product.purchase_price
            total += cost
            ws.append([product.name, item.quantity_needed, product.purchase_price, cost, item.notes])
        
        ws.append([])
        ws.append(['Total', '', '', total, ''])
        
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        filename = f"purchase_list_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'ایکسپورٹ میں خرابی: {str(e)}', 'error')
        return redirect(url_for('admin_purchase_list'))

@app.route('/admin/stats/api')
@admin_required
def admin_stats_api():
    stats = get_dashboard_stats()
    return jsonify({'daily_sales': stats['daily_sales'], 'total_sales': stats['total_sales']})

# ============================================
# DATABASE INITIALIZATION
# ============================================
def init_db():
    with app.app_context():
        db.create_all()
        admin_phone = os.getenv('ADMIN_PHONE', '03001234567')
        if not User.query.filter_by(phone=admin_phone, is_admin=True).first():
            admin = User(
                name=os.getenv('ADMIN_NAME', 'Admin'),
                phone=admin_phone,
                shop_name=os.getenv('ADMIN_SHOP', 'Main Admin'),
                address='', is_admin=True
            )
            admin.set_password(os.getenv('ADMIN_PASSWORD', 'admin123'))
            db.session.add(admin)
            db.session.commit()
            print(f"Admin created: {admin_phone}")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
