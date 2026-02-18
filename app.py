from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from functools import wraps
from models import db, Company, Customer, Document, DocumentItem, DOC_TYPES, DOC_STATUSES
from playwright.sync_api import sync_playwright
from datetime import datetime, date, timedelta
import os
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flowaccount-local-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///flowaccount.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

# Flask-Mail Configuration
# Gmail ต้องใช้ App Password ที่สร้างจาก Google Account
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'pattanuan.ppcloud@gmail.com'
# แก้ไขบนที่นี่เป็น App Password จริง ไม่ใช่รหัสผ่านปกติ
# ??? App Password 16 ????????????? Google ????????????? (??????????????????)
# ?????????: https://myaccount.google.com/apppasswords
app.config['MAIL_PASSWORD'] = 'mfan cfti kclo nnnu'  # ??????????????? App Password ?????

app.config['MAIL_DEFAULT_SENDER'] = ('FlowAccount', 'pattanuan.ppcloud@gmail.com')

mail = Mail(app)
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'กรุณาเข้าสู่ระบบก่อน'
login_manager.login_message_category = 'warning'

# Simple user class for Flask-Login
class User:
    def __init__(self, username):
        self.id = username
        self.username = username
        self.is_active = True
        self.is_authenticated = True
        self.is_anonymous = False
    
    def get_id(self):
        return self.id

@login_manager.user_loader
def load_user(user_id):
    if user_id == 'Admin':
        return User('Admin')
    return None

# Make doc_types available to all templates
@app.context_processor
def inject_doc_types():
    return dict(doc_types=DOC_TYPES, doc_statuses=DOC_STATUSES, now=datetime.now, current_user=current_user)


def generate_doc_number(doc_type):
    """Generate document number like QT2026020001"""
    prefix = DOC_TYPES[doc_type]['prefix']
    now = datetime.now()
    year_month = now.strftime('%Y%m')
    prefix_pattern = f"{prefix}{year_month}"

    last_doc = Document.query.filter(
        Document.doc_number.like(f"{prefix_pattern}%")
    ).order_by(Document.doc_number.desc()).first()

    if last_doc:
        last_num = int(last_doc.doc_number[-4:])
        new_num = last_num + 1
    else:
        new_num = 1

    return f"{prefix_pattern}{new_num:04d}"


# ==================== AUTHENTICATION ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if username == 'Admin' and password == 'Tongza17':
            user = User('Admin')
            login_user(user, remember=True)
            next_page = request.args.get('next')
            flash('เข้าสู่ระบบสำเร็จ', 'success')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'error')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ออกจากระบบเรียบร้อย', 'success')
    return redirect(url_for('login'))


# ==================== DASHBOARD ====================
@app.route('/')
@login_required
def dashboard():
    stats = {}
    for doc_type, info in DOC_TYPES.items():
        count = Document.query.filter_by(doc_type=doc_type).count()
        total = db.session.query(db.func.sum(Document.grand_total)).filter_by(doc_type=doc_type).scalar() or 0
        stats[doc_type] = {'count': count, 'total': total, **info}

    recent_docs = Document.query.order_by(Document.created_at.desc()).limit(10).all()
    return render_template('dashboard.html', stats=stats, recent_docs=recent_docs)


# ==================== DOCUMENT LIST ====================
@app.route('/documents/<doc_type>')
@login_required
def document_list(doc_type):
    if doc_type not in DOC_TYPES:
        flash('ประเภทเอกสารไม่ถูกต้อง', 'error')
        return redirect(url_for('dashboard'))

    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)

    query = Document.query.filter_by(doc_type=doc_type)
    if search:
        query = query.join(Customer, isouter=True).filter(
            db.or_(
                Document.doc_number.contains(search),
                Customer.name.contains(search),
            )
        )

    documents = query.order_by(Document.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    # Build related documents map for each document on the page
    related_map = {}
    for doc in documents.items:
        related_map[doc.id] = get_document_chain(doc)

    return render_template('documents.html',
                           doc_type=doc_type,
                           doc_info=DOC_TYPES[doc_type],
                           documents=documents,
                           search=search,
                           related_map=related_map)


def get_document_chain(doc):
    """Find all related documents in the conversion chain for a given document."""
    # Walk up to the root
    root = doc
    while root.source_document_id:
        parent = Document.query.get(root.source_document_id)
        if parent:
            root = parent
        else:
            break

    # Collect all docs from root downward
    chain = []
    _collect_descendants(root, chain)

    # Return all docs except the current one, keyed by (doc_type, id)
    related = []
    for d in chain:
        if d.id != doc.id:
            related.append({
                'id': d.id,
                'doc_type': d.doc_type,
                'doc_number': d.doc_number,
                'icon': DOC_TYPES[d.doc_type]['icon'],
                'color': DOC_TYPES[d.doc_type]['color'],
                'prefix': DOC_TYPES[d.doc_type]['prefix'],
                'name_th': DOC_TYPES[d.doc_type]['name_th'],
            })
    return related


def _collect_descendants(doc, chain):
    """Recursively collect a document and all its descendants."""
    chain.append(doc)
    for child in doc.child_documents:
        _collect_descendants(child, chain)


# ==================== CREATE DOCUMENT ====================
@app.route('/documents/<doc_type>/new', methods=['GET', 'POST'])
@login_required
def document_new(doc_type):
    if doc_type not in DOC_TYPES:
        flash('ประเภทเอกสารไม่ถูกต้อง', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        return save_document(doc_type, None)

    doc_number = generate_doc_number(doc_type)
    company = Company.query.first()
    customers = Customer.query.order_by(Customer.name).all()
    today = date.today()

    return render_template('document_form.html',
                           doc_type=doc_type,
                           doc_info=DOC_TYPES[doc_type],
                           doc_number=doc_number,
                           document=None,
                           company=company,
                           customers=customers,
                           today=today)


# ==================== EDIT DOCUMENT ====================
@app.route('/documents/<doc_type>/<int:doc_id>/edit', methods=['GET', 'POST'])
@login_required
def document_edit(doc_type, doc_id):
    if doc_type not in DOC_TYPES:
        flash('ประเภทเอกสารไม่ถูกต้อง', 'error')
        return redirect(url_for('dashboard'))

    document = Document.query.get_or_404(doc_id)

    if request.method == 'POST':
        return save_document(doc_type, document)

    company = Company.query.first()
    customers = Customer.query.order_by(Customer.name).all()

    return render_template('document_form.html',
                           doc_type=doc_type,
                           doc_info=DOC_TYPES[doc_type],
                           doc_number=document.doc_number,
                           document=document,
                           company=company,
                           customers=customers,
                           today=date.today())


def save_document(doc_type, document):
    """Save or update a document from form data"""
    try:
        data = request.form
        is_new = document is None

        if is_new:
            document = Document()
            document.doc_type = doc_type
            document.doc_number = data.get('doc_number', generate_doc_number(doc_type))

        # Customer handling
        customer_id = data.get('customer_id')
        customer_name = data.get('customer_name', '').strip()
        customer_address = data.get('customer_address', '').strip()
        customer_phone = data.get('customer_phone', '').strip()
        customer_tax_id = data.get('customer_tax_id', '').strip()
        customer_branch = data.get('customer_branch', '').strip()

        if customer_name:
            if customer_id and customer_id != 'new':
                customer = Customer.query.get(int(customer_id))
                if customer:
                    customer.name = customer_name
                    customer.address = customer_address
                    customer.phone = customer_phone
                    customer.tax_id = customer_tax_id
                    customer.branch = customer_branch
            else:
                customer = Customer(
                    name=customer_name,
                    address=customer_address,
                    phone=customer_phone,
                    tax_id=customer_tax_id,
                    branch=customer_branch,
                )
                db.session.add(customer)
                db.session.flush()
            document.customer_id = customer.id

        # Document fields
        doc_date_str = data.get('doc_date', '')
        if doc_date_str:
            document.doc_date = datetime.strptime(doc_date_str, '%Y-%m-%d').date()
        document.credit_days = int(data.get('credit_days', 0))
        due_date_str = data.get('due_date', '')
        if due_date_str:
            document.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        else:
            document.due_date = document.doc_date + timedelta(days=document.credit_days)

        document.reference_number = data.get('reference_number', '')
        document.salesperson = data.get('salesperson', '')
        document.project = data.get('project', '')
        document.price_type = data.get('price_type', 'ราคาไม่รวมภาษี')

        # Totals
        document.subtotal = float(data.get('subtotal', 0))
        document.discount_percent = float(data.get('discount_percent', 0))
        document.discount_amount = float(data.get('discount_amount', 0))
        document.after_discount = float(data.get('after_discount', 0))
        document.vat_enabled = data.get('vat_enabled') == 'on'
        document.vat_amount = float(data.get('vat_amount', 0))
        document.grand_total = float(data.get('grand_total', 0))
        document.withholding_tax_enabled = data.get('withholding_tax_enabled') == 'on'
        document.withholding_tax_percent = float(data.get('withholding_tax_percent', 7))
        document.withholding_tax_amount = float(data.get('withholding_tax_amount', 0))
        document.net_total = float(data.get('net_total', 0))

        document.notes = data.get('notes', '')
        document.internal_notes = data.get('internal_notes', '')

        # Status
        document.status = data.get('status', 'saved')

        if is_new:
            db.session.add(document)
        db.session.flush()

        # Items - remove old, add new
        DocumentItem.query.filter_by(document_id=document.id).delete()

        item_descriptions = request.form.getlist('item_description[]')
        item_quantities = request.form.getlist('item_quantity[]')
        item_units = request.form.getlist('item_unit[]')
        item_prices = request.form.getlist('item_unit_price[]')
        item_amounts = request.form.getlist('item_amount[]')

        for i in range(len(item_descriptions)):
            desc = item_descriptions[i].strip()
            if not desc:
                continue
            item = DocumentItem(
                document_id=document.id,
                order=i + 1,
                description=desc,
                details=request.form.getlist('item_details[]')[i] if i < len(request.form.getlist('item_details[]')) else '',
                quantity=float(item_quantities[i]) if i < len(item_quantities) and item_quantities[i] else 0,
                unit=item_units[i] if i < len(item_units) else '',
                unit_price=float(item_prices[i]) if i < len(item_prices) and item_prices[i] else 0,
                amount=float(item_amounts[i]) if i < len(item_amounts) and item_amounts[i] else 0,
            )
            db.session.add(item)

        db.session.commit()
        flash(f'บันทึก{DOC_TYPES[doc_type]["name_th"]}เรียบร้อย', 'success')
        return redirect(url_for('document_view', doc_type=doc_type, doc_id=document.id))

    except Exception as e:
        db.session.rollback()
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')
        return redirect(url_for('document_list', doc_type=doc_type))


# ==================== VIEW DOCUMENT ====================
@app.route('/documents/<doc_type>/<int:doc_id>')
@login_required
def document_view(doc_type, doc_id):
    if doc_type not in DOC_TYPES:
        flash('ประเภทเอกสารไม่ถูกต้อง', 'error')
        return redirect(url_for('dashboard'))

    document = Document.query.get_or_404(doc_id)
    company = Company.query.first()

    # Find linked documents
    linked_docs = Document.query.filter_by(source_document_id=document.id).all()
    source_doc = document.source_document if document.source_document_id else None

    return render_template('document_view.html',
                           doc_type=doc_type,
                           doc_info=DOC_TYPES[doc_type],
                           document=document,
                           company=company,
                           linked_docs=linked_docs,
                           source_doc=source_doc)


# ==================== EMAIL DOCUMENT ====================
@app.route('/documents/<doc_type>/<int:doc_id>/email', methods=['GET', 'POST'])
@login_required
def document_email(doc_type, doc_id):
    if doc_type not in DOC_TYPES:
        flash('ประเภทเอกสารไม่ถูกต้อง', 'error')
        return redirect(url_for('dashboard'))
    
    document = Document.query.get_or_404(doc_id)
    company = Company.query.first()
    
    if request.method == 'POST':
        to_email = request.form.get('to_email', '').strip()
        cc_email = request.form.get('cc_email', '').strip()
        subject = request.form.get('subject', '').strip()
        message_body = request.form.get('message', '').strip()
        
        if not to_email:
            flash('กรุณาระบุอีเมลผู้รับ', 'error')
            return redirect(url_for('document_email', doc_type=doc_type, doc_id=doc_id))
        
        try:
            # Generate PDF using Playwright (Chromium)
            html_content = render_template('document_pdf.html',
                                           doc_type=doc_type,
                                           doc_info=DOC_TYPES[doc_type],
                                           document=document,
                                           company=company)
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.set_content(html_content)
                pdf_bytes = page.pdf(format='A4', print_background=True)
                browser.close()
            
            pdf_buffer = io.BytesIO(pdf_bytes)
            
            # Create email
            msg = Message(
                subject=subject or f"{DOC_TYPES[doc_type]['name_th']} {document.doc_number}",
                recipients=[to_email],
                cc=[cc_email] if cc_email else [],
                body=message_body,
                sender=('FlowAccount', 'pattanuan.ppcloud@gmail.com')
            )
            
            # Attach PDF
            filename = f"{document.doc_number}.pdf"
            msg.attach(filename, 'application/pdf', pdf_buffer.read())
            
            # Send email
            mail.send(msg)
            
            flash('ส่งอีเมลสำเร็จ', 'success')
            return redirect(url_for('document_view', doc_type=doc_type, doc_id=doc_id))
            
        except Exception as e:
            error_msg = str(e)
            if 'Authentication unsuccessful' in error_msg or '5.7.3' in error_msg:
                flash('การเข้าสู่ระบบอีเมลล้มแ้ลว: กรุณาตรวจสอบรหัสผ่าน (App Password) ในไฟล์ app.py', 'error')
            elif '535' in error_msg:
                flash('การเข้าสู่ระบบอีเมลล้มแ้ลว: App Password ไม่ถูกต้อง หรือต้องใช้ App Password แทนที่รหัสผ่านปกติ', 'error')
            else:
                flash(f'เกิดข้อผิดพลาด: {error_msg}', 'error')
            return redirect(url_for('document_email', doc_type=doc_type, doc_id=doc_id))
    
    # GET request - show email form
    default_subject = f"{DOC_TYPES[doc_type]['name_th']} {document.doc_number} จาก {company.name if company else 'บริษัทของคุณ'}"
    default_message = f"เรียน {document.customer.name if document.customer else 'ลูกค้า'}\n\n{company.name if company else 'บริษัทของคุณ'} ได้แนบเอกสาร {DOC_TYPES[doc_type]['name_th']} เลขที่ {document.doc_number} มาให้พิจารณา\n\nด้วยความเคารพ\n{company.name if company else ''}"
    
    return render_template('document_email.html',
                           doc_type=doc_type,
                           doc_info=DOC_TYPES[doc_type],
                           document=document,
                           company=company,
                           default_subject=default_subject,
                           default_message=default_message)


# ==================== DELETE DOCUMENT ====================
@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def document_delete(doc_id):
    document = Document.query.get_or_404(doc_id)
    doc_type = document.doc_type
    db.session.delete(document)
    db.session.commit()
    return jsonify({'success': True, 'message': 'ลบเอกสารเรียบร้อย'})


# ==================== STATUS UPDATE ====================
@app.route('/api/documents/<int:doc_id>/status', methods=['POST'])
@login_required
def document_update_status(doc_id):
    document = Document.query.get_or_404(doc_id)
    data = request.json
    new_status = data.get('status', '')
    if new_status not in DOC_STATUSES:
        return jsonify({'success': False, 'message': 'สถานะไม่ถูกต้อง'}), 400
    document.status = new_status
    db.session.commit()
    status_info = DOC_STATUSES[new_status]
    return jsonify({
        'success': True,
        'status': new_status,
        'name_th': status_info['name_th'],
        'color': status_info['color'],
        'bg': status_info['bg'],
    })


# ==================== CONVERT DOCUMENT ====================
@app.route('/documents/<doc_type>/<int:doc_id>/convert/<target_type>')
@login_required
def document_convert(doc_type, doc_id, target_type):
    """Convert a document to another type (e.g. quotation → billing)"""
    if doc_type not in DOC_TYPES or target_type not in DOC_TYPES:
        flash('ประเภทเอกสารไม่ถูกต้อง', 'error')
        return redirect(url_for('dashboard'))

    source = Document.query.get_or_404(doc_id)

    # Check if already converted
    existing = Document.query.filter_by(source_document_id=source.id, doc_type=target_type).first()
    if existing:
        flash(f'เอกสารนี้ถูกสร้าง{DOC_TYPES[target_type]["name_th"]}แล้ว ({existing.doc_number})', 'error')
        return redirect(url_for('document_view', doc_type=target_type, doc_id=existing.id))

    try:
        new_doc = Document()
        new_doc.doc_type = target_type
        new_doc.doc_number = generate_doc_number(target_type)
        new_doc.status = 'saved'
        new_doc.customer_id = source.customer_id
        new_doc.source_document_id = source.id
        new_doc.doc_date = date.today()
        new_doc.credit_days = source.credit_days
        new_doc.due_date = date.today() + timedelta(days=source.credit_days)
        new_doc.reference_number = source.doc_number  # Reference back to source
        new_doc.salesperson = source.salesperson
        new_doc.project = source.project
        new_doc.price_type = source.price_type
        new_doc.subtotal = source.subtotal
        new_doc.discount_percent = source.discount_percent
        new_doc.discount_amount = source.discount_amount
        new_doc.after_discount = source.after_discount
        new_doc.vat_enabled = source.vat_enabled
        new_doc.vat_amount = source.vat_amount
        new_doc.grand_total = source.grand_total
        new_doc.withholding_tax_enabled = source.withholding_tax_enabled
        new_doc.withholding_tax_percent = source.withholding_tax_percent
        new_doc.withholding_tax_amount = source.withholding_tax_amount
        new_doc.net_total = source.net_total
        new_doc.notes = source.notes
        new_doc.internal_notes = source.internal_notes

        db.session.add(new_doc)
        db.session.flush()

        # Copy items
        for item in source.items:
            new_item = DocumentItem(
                document_id=new_doc.id,
                order=item.order,
                description=item.description,
                details=item.details,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                amount=item.amount,
            )
            db.session.add(new_item)

        # Mark source as converted
        source.status = 'converted'

        msg = f'สร้าง{DOC_TYPES[target_type]["name_th"]} {new_doc.doc_number} จาก {source.doc_number} เรียบร้อย'

        # 2. Special Case: Quotation -> Billing Note => Auto-create Delivery Note
        if doc_type == 'quotation' and target_type == 'billing':
            # Check if DV already exists (to avoid duplicates if re-clicking)
            existing_dv = Document.query.filter_by(source_document_id=source.id, doc_type='delivery_note').first()
            if not existing_dv:
                dv_doc = Document()
                dv_doc.doc_type = 'delivery_note'
                dv_doc.doc_number = generate_doc_number('delivery_note')
                dv_doc.status = 'saved'
                dv_doc.customer_id = source.customer_id
                dv_doc.source_document_id = source.id  # Sibling to Billing Note
                dv_doc.doc_date = date.today()
                dv_doc.credit_days = source.credit_days
                dv_doc.due_date = date.today() + timedelta(days=source.credit_days)
                dv_doc.reference_number = source.doc_number
                dv_doc.salesperson = source.salesperson
                dv_doc.project = source.project
                dv_doc.price_type = source.price_type
                dv_doc.subtotal = source.subtotal
                dv_doc.discount_percent = source.discount_percent
                dv_doc.discount_amount = source.discount_amount
                dv_doc.after_discount = source.after_discount
                dv_doc.vat_enabled = source.vat_enabled
                dv_doc.vat_amount = source.vat_amount
                dv_doc.grand_total = source.grand_total
                dv_doc.withholding_tax_enabled = source.withholding_tax_enabled
                dv_doc.withholding_tax_percent = source.withholding_tax_percent
                dv_doc.withholding_tax_amount = source.withholding_tax_amount
                dv_doc.net_total = source.net_total
                dv_doc.notes = source.notes
                dv_doc.internal_notes = source.internal_notes

                db.session.add(dv_doc)
                db.session.flush()

                for item in source.items:
                    dv_item = DocumentItem(
                        document_id=dv_doc.id,
                        order=item.order,
                        description=item.description,
                        details=item.details,
                        quantity=item.quantity,
                        unit=item.unit,
                        unit_price=item.unit_price,
                        amount=item.amount,
                    )
                    db.session.add(dv_item)
                
                msg += f' และสร้างใบส่งสินค้า {dv_doc.doc_number} แล้ว'

        db.session.commit()
        flash(msg, 'success')
        return redirect(url_for('document_view', doc_type=target_type, doc_id=new_doc.id))

    except Exception as e:
        db.session.rollback()
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')
        return redirect(url_for('document_view', doc_type=doc_type, doc_id=doc_id))


# ==================== SETTINGS ====================
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    company = Company.query.first()

    if request.method == 'POST':
        if not company:
            company = Company()
            db.session.add(company)

        company.name = request.form.get('name', '')
        company.address = request.form.get('address', '')
        company.phone = request.form.get('phone', '')
        company.email = request.form.get('email', '')
        company.tax_id = request.form.get('tax_id', '')
        company.branch = request.form.get('branch', 'สำนักงานใหญ่')

        # Handle logo upload
        if 'logo' in request.files:
            logo = request.files['logo']
            if logo.filename:
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                logo_filename = 'company_logo' + os.path.splitext(logo.filename)[1]
                logo_path = os.path.join(app.config['UPLOAD_FOLDER'], logo_filename)
                logo.save(logo_path)
                logo_path = os.path.join(app.config['UPLOAD_FOLDER'], logo_filename)
                logo.save(logo_path)
                company.logo_path = f'/static/uploads/{logo_filename}'

        # Handle signature upload
        if 'signature' in request.files:
            signature = request.files['signature']
            if signature.filename:
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                signature_filename = 'company_signature' + os.path.splitext(signature.filename)[1]
                signature_path = os.path.join(app.config['UPLOAD_FOLDER'], signature_filename)
                signature.save(signature_path)
                company.signature_path = f'/static/uploads/{signature_filename}'

        db.session.commit()
        flash('บันทึกข้อมูลบริษัทเรียบร้อย', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html', company=company)


# ==================== API ====================
@app.route('/api/customers')
@login_required
def api_customers():
    search = request.args.get('q', '')
    query = Customer.query
    if search:
        query = query.filter(Customer.name.contains(search))
    customers = query.order_by(Customer.name).limit(20).all()
    return jsonify([c.to_dict() for c in customers])


@app.route('/api/customers', methods=['POST'])
@login_required
def api_create_customer():
    data = request.json
    customer = Customer(
        name=data.get('name', ''),
        address=data.get('address', ''),
        phone=data.get('phone', ''),
        tax_id=data.get('tax_id', ''),
        branch=data.get('branch', 'สำนักงานใหญ่'),
        email=data.get('email', ''),
    )
    db.session.add(customer)
    db.session.commit()
    return jsonify(customer.to_dict()), 201


# ==================== TEMPLATE FILTERS ====================
@app.template_filter('format_number')
def format_number(value):
    """Format number with commas and 2 decimal places"""
    try:
        return '{:,.2f}'.format(float(value))
    except (ValueError, TypeError):
        return '0.00'


@app.template_filter('thai_date')
def thai_date(value):
    """Format date in Thai format DD/MM/YYYY"""
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m-%d').date()
    if value:
        return value.strftime('%d/%m/%Y')
    return ''


@app.template_filter('baht_text')
def baht_text(value):
    """Convert number to Thai baht text"""
    try:
        value = float(value)
    except (ValueError, TypeError):
        return ''

    thai_nums = ['', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']
    thai_pos = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน', 'ล้าน']

    def _num_to_thai(n):
        if n == 0:
            return 'ศูนย์'
        result = ''
        s = str(int(n))
        length = len(s)
        for i, digit in enumerate(s):
            d = int(digit)
            pos = length - i - 1
            if d == 0:
                continue
            if pos == 0 and d == 1 and length > 1:
                result += 'เอ็ด'
            elif pos == 1 and d == 2:
                result += 'ยี่สิบ'
            elif pos == 1 and d == 1:
                result += 'สิบ'
            else:
                result += thai_nums[d] + thai_pos[pos]
        return result

    baht = int(value)
    satang = round((value - baht) * 100)

    text = _num_to_thai(baht) + 'บาท'
    if satang == 0:
        text += 'ถ้วน'
    else:
        text += _num_to_thai(satang) + 'สตางค์'
    return text


@app.route('/document/<int:doc_id>/duplicate')
@login_required
def duplicate_document(doc_id):
    original_doc = Document.query.get_or_404(doc_id)
    
    # Only allow duplicating quotations per user request
    if original_doc.doc_type != 'quotation':
        flash('สามารถสร้างซ้ำได้เฉพาะใบเสนอราคาเท่านั้น', 'error')
        return redirect(url_for('document_view', doc_id=doc_id))

    new_doc_number = generate_doc_number(original_doc.doc_type)
    
    new_doc = Document(
        doc_type=original_doc.doc_type,
        doc_number=new_doc_number,
        status='draft',
        customer_id=original_doc.customer_id,
        salesperson=original_doc.salesperson,
        project=original_doc.project,
        price_type=original_doc.price_type,
        doc_date=date.today(),
        credit_days=original_doc.credit_days,
        due_date=date.today() + timedelta(days=original_doc.credit_days),
        reference_number=original_doc.reference_number,
        subtotal=original_doc.subtotal,
        discount_percent=original_doc.discount_percent,
        discount_amount=original_doc.discount_amount,
        after_discount=original_doc.after_discount,
        vat_enabled=original_doc.vat_enabled,
        vat_amount=original_doc.vat_amount,
        grand_total=original_doc.grand_total,
        withholding_tax_enabled=original_doc.withholding_tax_enabled,
        withholding_tax_percent=original_doc.withholding_tax_percent,
        withholding_tax_amount=original_doc.withholding_tax_amount,
        net_total=original_doc.net_total
    )
    
    db.session.add(new_doc)
    db.session.flush() # Get ID
    
    # Clone items
    for item in original_doc.items:
        new_item = DocumentItem(
            document_id=new_doc.id,
            order=item.order,
            description=item.description,
            details=item.details,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=item.unit_price,
            amount=item.amount
        )
        db.session.add(new_item)
        
    db.session.commit()
    flash(f'สร้างเอกสารซ้ำเรียบร้อยแล้ว (เลขที่ {new_doc.doc_number})', 'success')
    return redirect(url_for('document_edit', doc_type=new_doc.doc_type, doc_id=new_doc.id))


@app.route('/api/customers')
@login_required
def get_customers():
    customers = Customer.query.order_by(Customer.name).all()
    return jsonify([c.to_dict() for c in customers])


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create default company if not exists
        if not Company.query.first():
            company = Company(name='บริษัทของคุณ', branch='สำนักงานใหญ่')
            db.session.add(company)
            db.session.commit()
    app.run(debug=True, port=5000)

