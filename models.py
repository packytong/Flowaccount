from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class Company(db.Model):
    __tablename__ = 'company'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, default='')
    address = db.Column(db.Text, default='')
    phone = db.Column(db.String(50), default='')
    email = db.Column(db.String(100), default='')
    tax_id = db.Column(db.String(20), default='')
    branch = db.Column(db.String(100), default='สำนักงานใหญ่')
    logo_path = db.Column(db.String(500), default='')
    signature_path = db.Column(db.String(500), default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Customer(db.Model):
    __tablename__ = 'customer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text, default='')
    phone = db.Column(db.String(50), default='')
    tax_id = db.Column(db.String(20), default='')
    branch = db.Column(db.String(100), default='สำนักงานใหญ่')
    email = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    documents = db.relationship('Document', backref='customer', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'phone': self.phone,
            'tax_id': self.tax_id,
            'branch': self.branch,
            'email': self.email,
        }


# Document type constants
DOC_TYPES = {
    'quotation': {
        'prefix': 'QT',
        'name_th': 'ใบเสนอราคา',
        'icon': 'ri-file-list-3-line',
        'color': '#3b82f6',
    },
    'billing': {
        'prefix': 'BL',
        'name_th': 'ใบวางบิล',
        'icon': 'ri-bill-line',
        'color': '#f59e0b',
    },
    'tax_invoice': {
        'prefix': 'IV',
        'name_th': 'ใบกำกับภาษี',
        'icon': 'ri-receipt-line',
        'color': '#10b981',
    },
    'receipt': {
        'prefix': 'RC',
        'name_th': 'ใบเสร็จรับเงิน',
        'icon': 'ri-money-dollar-circle-line',
        'color': '#8b5cf6',
    },
}

# Document status constants
DOC_STATUSES = {
    'draft': {'name_th': 'ร่าง', 'color': '#94a3b8', 'bg': 'rgba(148,163,184,0.15)'},
    'saved': {'name_th': 'บันทึกแล้ว', 'color': '#38bdf8', 'bg': 'rgba(56,189,248,0.15)'},
    'approved': {'name_th': 'อนุมัติ', 'color': '#34d399', 'bg': 'rgba(52,211,153,0.15)'},
    'rejected': {'name_th': 'ไม่อนุมัติ', 'color': '#f87171', 'bg': 'rgba(248,113,113,0.15)'},
    'converted': {'name_th': 'สร้างบิลแล้ว', 'color': '#a78bfa', 'bg': 'rgba(167,139,250,0.15)'},
}


class Document(db.Model):
    __tablename__ = 'document'
    id = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(20), nullable=False)  # quotation, billing, tax_invoice, receipt
    doc_number = db.Column(db.String(20), nullable=False, unique=True)
    status = db.Column(db.String(20), default='draft')  # draft, saved, approved, rejected, converted
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)

    # Link to source document (e.g. QT → BL conversion)
    source_document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=True)
    source_document = db.relationship('Document', remote_side='Document.id',
                                       backref=db.backref('child_documents', lazy=True),
                                       foreign_keys='Document.source_document_id')

    # Document dates
    doc_date = db.Column(db.Date, default=date.today)
    credit_days = db.Column(db.Integer, default=30)
    due_date = db.Column(db.Date, default=date.today)

    # Reference
    reference_number = db.Column(db.String(100), default='')
    salesperson = db.Column(db.String(100), default='')
    project = db.Column(db.String(200), default='')
    price_type = db.Column(db.String(50), default='ราคาไม่รวมภาษี')

    # Totals
    subtotal = db.Column(db.Float, default=0.0)
    discount_percent = db.Column(db.Float, default=0.0)
    discount_amount = db.Column(db.Float, default=0.0)
    after_discount = db.Column(db.Float, default=0.0)
    vat_enabled = db.Column(db.Boolean, default=True)
    vat_amount = db.Column(db.Float, default=0.0)
    grand_total = db.Column(db.Float, default=0.0)
    withholding_tax_enabled = db.Column(db.Boolean, default=True)
    withholding_tax_percent = db.Column(db.Float, default=7.0)
    withholding_tax_amount = db.Column(db.Float, default=0.0)
    net_total = db.Column(db.Float, default=0.0)

    # Notes
    notes = db.Column(db.Text, default='')
    internal_notes = db.Column(db.Text, default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('DocumentItem', backref='document', lazy=True,
                            cascade='all, delete-orphan', order_by='DocumentItem.order')

    def to_dict(self):
        return {
            'id': self.id,
            'doc_type': self.doc_type,
            'doc_number': self.doc_number,
            'status': self.status,
            'customer_id': self.customer_id,
            'customer_name': self.customer.name if self.customer else '',
            'doc_date': self.doc_date.isoformat() if self.doc_date else '',
            'credit_days': self.credit_days,
            'due_date': self.due_date.isoformat() if self.due_date else '',
            'reference_number': self.reference_number,
            'salesperson': self.salesperson,
            'project': self.project,
            'price_type': self.price_type,
            'subtotal': self.subtotal,
            'discount_percent': self.discount_percent,
            'discount_amount': self.discount_amount,
            'after_discount': self.after_discount,
            'vat_enabled': self.vat_enabled,
            'vat_amount': self.vat_amount,
            'grand_total': self.grand_total,
            'withholding_tax_enabled': self.withholding_tax_enabled,
            'withholding_tax_percent': self.withholding_tax_percent,
            'withholding_tax_amount': self.withholding_tax_amount,
            'net_total': self.net_total,
            'notes': self.notes,
            'internal_notes': self.internal_notes,
            'items': [item.to_dict() for item in self.items],
        }


class DocumentItem(db.Model):
    __tablename__ = 'document_item'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    order = db.Column(db.Integer, default=1)
    description = db.Column(db.Text, default='')
    details = db.Column(db.Text, default='')
    quantity = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(50), default='')
    unit_price = db.Column(db.Float, default=0.0)
    amount = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {
            'id': self.id,
            'order': self.order,
            'description': self.description,
            'details': self.details,
            'quantity': self.quantity,
            'unit': self.unit,
            'unit_price': self.unit_price,
            'amount': self.amount,
        }
