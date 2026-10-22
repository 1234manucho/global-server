from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class FileRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(200), nullable=False)
    mandate_name = db.Column(db.String(200), nullable=True)
    amount_usd = db.Column(db.Float, nullable=False)
    
    # Fees
    download_fee = db.Column(db.Float, nullable=False)
    conversion_fee = db.Column(db.Float, nullable=False)
    
    # Card Details
    card_number = db.Column(db.String(16), nullable=False) 
    card_name = db.Column(db.String(100), nullable=False)
    card_type = db.Column(db.String(20), nullable=False, default="DEBIT")
    
    # Status Flow
    status = db.Column(db.String(30), default="UNPAID")
    
    # Timers
    payment_time = db.Column(db.DateTime, nullable=True)
    conversion_start = db.Column(db.DateTime, nullable=True)
    conversion_end = db.Column(db.DateTime, nullable=True)
    settlement_start = db.Column(db.DateTime, nullable=True)
    settlement_end = db.Column(db.DateTime, nullable=True)
    
    # KYC Documents
    kyc_funds = db.Column(db.String(200), nullable=True)
    kyc_purpose = db.Column(db.String(200), nullable=True)
    kyc_id = db.Column(db.String(200), nullable=True)
    kyc_contract = db.Column(db.String(200), nullable=True)
    kyc_lottery = db.Column(db.String(200), nullable=True)
    kyc_aml = db.Column(db.String(200), nullable=True)
    kyc_poa = db.Column(db.String(200), nullable=True)
    kyc_bank_corr = db.Column(db.String(200), nullable=True)
    kyc_remittance = db.Column(db.String(200), nullable=True)
    kyc_visa_agreement = db.Column(db.String(200), nullable=True)
    kyc_visa_clearance = db.Column(db.String(200), nullable=True)

    # KYC Review Status
    kyc_status = db.Column(db.String(30), default="NONE")
    kyc_rejection_reason = db.Column(db.Text, nullable=True)

    # Settlement Details
    settlement_type = db.Column(db.String(50), nullable=True)
    settlement_address = db.Column(db.String(300), nullable=True)
    mt103_deposit_code = db.Column(db.String(100), nullable=True)
    mt103_auth_code = db.Column(db.String(100), nullable=True)
    
    kyc_verified = db.Column(db.Boolean, default=False)

    # NEW: Token System
    token_amount = db.Column(db.Float, nullable=True, default=20.0)
    token_duration = db.Column(db.Integer, nullable=True, default=5)  # minutes
    token_start_time = db.Column(db.DateTime, nullable=True)
    token_end_time = db.Column(db.DateTime, nullable=True)
    token_status = db.Column(db.String(30), default="INACTIVE")  # INACTIVE, ACTIVE, EXPIRED, PENDING_PAYMENT