from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class FileRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(200), nullable=False)
    amount_usd = db.Column(db.Float, nullable=False)
    
    # Fees
    download_fee = db.Column(db.Float, nullable=False)
    conversion_fee = db.Column(db.Float, nullable=False)
    
    # Card Details
    card_number = db.Column(db.String(16), unique=True, nullable=False)
    card_name = db.Column(db.String(100), nullable=False)
    card_type = db.Column(db.String(20), nullable=False, default="DEBIT")
    
    # Status Flow: 'UNPAID' -> 'AWAITING_SERVER' -> 'PAID' -> 'CONVERTING' -> 'COMPLETED'
    status = db.Column(db.String(30), default="UNPAID")
    
    # Timers
    payment_time = db.Column(db.DateTime, nullable=True)
    conversion_start = db.Column(db.DateTime, nullable=True)
    conversion_end = db.Column(db.DateTime, nullable=True)