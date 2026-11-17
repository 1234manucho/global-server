import os
import json
import random
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session, jsonify
from werkzeug.utils import secure_filename
from models import db, FileRecord
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask_migrate import Migrate

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default-secret-key')

# ==========================================
# --- PRODUCTION DATABASE CONFIGURATION ---
# ==========================================
db_url = os.getenv('DATABASE_URL', 'postgresql://visa_yqla_user:DYguQGdSGspIDSeeQ5IrV6TjmOPkABd2@dpg-dba428fbtjjs73dn2tn0-a/visa_yqla')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url

# ==========================================
# --- FILE UPLOAD CONFIGURATION ---
# ==========================================
DATA_DIR = '/var/data' if os.path.exists('/var/data') else os.getcwd()
app.config['UPLOAD_FOLDER'] = os.path.join(DATA_DIR, 'uploads')

db.init_app(app)
migrate = Migrate(app, db)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

with app.app_context():
    db.create_all()

# Helper function to save KYC files
def save_kyc_files(request_files):
    def save_file(field_name):
        f = request_files.get(field_name)
        if f and f.filename:
            fname = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            return fname
        return None
    
    return {
        'kyc_funds': save_file('kyc_funds'), 'kyc_purpose': save_file('kyc_purpose'), 'kyc_id': save_file('kyc_id'),
        'kyc_contract': save_file('kyc_contract'), 'kyc_lottery': save_file('kyc_lottery'), 'kyc_aml': save_file('kyc_aml'),
        'kyc_poa': save_file('kyc_poa'), 'kyc_bank_corr': save_file('kyc_bank_corr'), 'kyc_remittance': save_file('kyc_remittance'),
        'kyc_visa_agreement': save_file('kyc_visa_agreement'), 'kyc_visa_clearance': save_file('kyc_visa_clearance')
    }

# ==========================================
# --- SIDEBAR MODULE ROUTES ---
# ==========================================
@app.route('/payment_messages')
def payment_messages(): return render_template('payment_messages.html')
@app.route('/transaction_processing')
def transaction_processing(): return render_template('transaction_processing.html')
@app.route('/system_logs')
def system_logs(): return render_template('system_logs.html')
@app.route('/mt101_workflow')
def mt101_workflow(): return render_template('mt101_workflow.html')
@app.route('/authorization')
def authorization(): return render_template('authorization.html')
@app.route('/compliance')
def compliance(): return render_template('compliance.html')
@app.route('/reports')
def reports(): return render_template('reports.html')
@app.route('/settings')
def settings(): return render_template('settings.html')
@app.route('/user_management')
def user_management(): return render_template('user_management.html')

@app.route('/card_management')
def card_management():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    records = FileRecord.query.order_by(FileRecord.id.desc()).all()
    return render_template('card_management.html', records=records)

@app.route('/admin/card_details/<int:id>')
def card_details(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    return render_template('card_details.html', record=record)

# ==========================================
# --- USER ROUTES ---
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        card = request.form.get('card_number').replace(" ", "")
        record = FileRecord.query.filter_by(card_number=card).order_by(FileRecord.id.desc()).first()
        if record:
            session['user_card'] = card
            return redirect(url_for('dashboard'))
        flash("Card not found in the system.", "error")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_card' not in session: return redirect(url_for('login'))
    
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if not record:
        session.pop('user_card', None)
        return redirect(url_for('login'))
    
    # --- SAFETY FIX FOR OLD RECORDS ---
    updated = False
    if record.kyc_status is None:
        record.kyc_status = "NONE"
        updated = True
    if record.token_status is None:
        record.token_status = "INACTIVE"
        updated = True
    if record.token_amount is None:
        record.token_amount = 20.0
        updated = True
    if record.token_duration is None:
        record.token_duration = 5
        updated = True
    if record.mandate_name is None:
        record.mandate_name = "Not Provided"
        updated = True
    if updated:
        db.session.commit()

    if record.status == "CONVERTING" and record.conversion_end and datetime.utcnow() > record.conversion_end:
        record.status = "COMPLETED"
        db.session.commit()

    if record.status == "SETTLING" and record.settlement_end and datetime.utcnow() > record.settlement_end:
        record.status = "READY_FOR_CASHOUT"
        db.session.commit()

    # TOKEN EXPIRATION CHECK
    if record.token_status == "ACTIVE" and record.token_end_time and datetime.utcnow() > record.token_end_time:
        record.token_status = "EXPIRED"
        db.session.commit()

    total_fee = record.download_fee + record.conversion_fee
    return render_template('dashboard.html', file=record, total_fee=total_fee, wallet=os.getenv('USDT_TRC20_WALLET'))

@app.route('/user_upload_kyc', methods=['POST'])
def user_upload_kyc():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.kyc_status in ['NONE', 'REJECTED']:
        kyc_data = save_kyc_files(request.files)
        for key, value in kyc_data.items():
            if value: setattr(record, key, value)
        record.kyc_status = "PENDING_REVIEW"
        record.kyc_rejection_reason = None
        db.session.commit()
        flash("KYC Documents submitted successfully. Awaiting Admin Review.", "success")
    return redirect(url_for('dashboard'))

@app.route('/user_confirm_payment', methods=['POST'])
def user_confirm_payment():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.status == "UNPAID":
        record.status = "AWAITING_SERVER"
        db.session.commit()
        flash("Payment submitted. Awaiting Server Confirmation.", "success")
    return redirect(url_for('dashboard'))

@app.route('/user_pay_token', methods=['POST'])
def user_pay_token():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.token_status == "EXPIRED":
        record.token_status = "PENDING_PAYMENT"
        db.session.commit()
        flash(f"Token payment of ${record.token_amount} submitted. Awaiting Admin confirmation.", "success")
    return redirect(url_for('dashboard'))

@app.route('/initiate_settlement', methods=['POST'])
def initiate_settlement():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.status == "COMPLETED":
        record.status = "SETTLING"
        record.settlement_start = datetime.utcnow()
        record.settlement_end = datetime.utcnow() + timedelta(days=2)
        db.session.commit()
        flash("T+2 Settlement Phase Initiated. Please wait 48 hours.", "success")
    return redirect(url_for('dashboard'))

@app.route('/submit_cashout', methods=['POST'])
def submit_cashout():
    if 'user_card' not in session: return jsonify({"status": "error", "message": "Session expired."})
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    
    if record.kyc_status != 'APPROVED':
        return jsonify({"status": "error", "message": "KYC Verification is pending or rejected. You cannot cash out yet."})

    if record.status == "READY_FOR_CASHOUT":
        record.settlement_type = request.form.get('settlement_type')
        record.settlement_address = request.form.get('settlement_address')
        record.mt103_deposit_code = request.form.get('mt103_deposit_code')
        record.mt103_auth_code = request.form.get('mt103_auth_code')
        record.status = "CASHOUT_REQUESTED"
        db.session.commit()
        return jsonify({"status": "error", "message": "Wallet or account not compatible. Please check your details and try again."})
    
    return jsonify({"status": "error", "message": "Invalid transaction state."})

@app.route('/receipt')
def receipt():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.status not in ['CONVERTING', 'COMPLETED', 'SETTLING', 'READY_FOR_CASHOUT', 'CASHOUT_REQUESTED', 'CASHED_OUT']:
        flash("Receipt is not available yet.", "error")
        return redirect(url_for('dashboard'))
    total_fee = record.download_fee + record.conversion_fee
    return render_template('receipt.html', file=record, total_fee=total_fee, wallet=os.getenv('USDT_TRC20_WALLET'))

@app.route('/download')
def download():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.status in ["COMPLETED", "SETTLING", "READY_FOR_CASHOUT", "CASHOUT_REQUESTED", "CASHED_OUT"]:
        output_filename = f"MT103_ACK_{record.id}.json"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        mt103_data = {
            "swift_header": {"message_type": "MT103", "sender_bic": "VISAUS33XXX", "receiver_bic": "KCOOKENAXXX", "session_number": f"2026-{record.id}-{random.randint(1000, 9999)}", "priority": "NORMAL", "delivery_status": "NETWORK ACK"},
            "message_text": {"F20": {"tag": "Transaction Reference Number", "value": f"GSB-{record.id}-VISA-2026"}, "F32A": {"tag": "Value Date", "date": record.payment_time.strftime('%Y/%m/%d') if record.payment_time else datetime.utcnow().strftime('%Y/%m/%d'), "currency": "USD", "amount": f"{record.amount_usd:,.2f}"}, "F50A": {"tag": "Ordering Customer", "account_name": record.card_name, "account_number": record.card_number}, "F59": {"tag": "Beneficiary Customer", "account_name": "JUAN FX TRADERS LIMITED", "account_number": "01102085712001"}}
        }
        with open(filepath, "w") as f: json.dump(mt103_data, f, indent=4)
        return send_from_directory(app.config['UPLOAD_FOLDER'], output_filename, as_attachment=True)
    return "Access Denied: File is not ready yet.", 403

@app.route('/logout')
def logout():
    session.pop('user_card', None)
    session.pop('admin_logged_in', None)
    return redirect(url_for('login'))

# ==========================================
# --- ADMIN ROUTES ---
# ==========================================
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        file = request.files.get('file')
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            kyc_data = save_kyc_files(request.files)
            has_kyc = any(kyc_data.values())

            try:
                new_record = FileRecord(
                    filename=filename, 
                    file_path=filename, 
                    mandate_name=request.form.get('mandate_name'),
                    amount_usd=float(request.form['amount']),
                    download_fee=float(request.form['d_fee']), 
                    conversion_fee=float(request.form['c_fee']),
                    card_number=request.form['card'].replace(" ", ""), 
                    card_name=request.form['card_name'], 
                    card_type=request.form['card_type'],
                    kyc_status="PENDING_REVIEW" if has_kyc else "NONE",
                    token_amount=float(request.form.get('token_amount', 20)),
                    token_duration=int(request.form.get('token_duration', 5)),
                    token_status="INACTIVE",
                    **kyc_data
                )
                db.session.add(new_record)
                db.session.commit()
                flash("Transaction Created successfully.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Database Error: {str(e)}", "error")
                
    records = FileRecord.query.order_by(FileRecord.id.desc()).all()
    return render_template('admin.html', records=records)

@app.route('/admin/upload_kyc_for_user', methods=['POST'])
def admin_upload_kyc():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    card_number = request.form.get('card_number').replace(" ", "")
    record = FileRecord.query.filter_by(card_number=card_number).order_by(FileRecord.id.desc()).first()
    if record:
        kyc_data = save_kyc_files(request.files)
        for key, value in kyc_data.items():
            if value: setattr(record, key, value)
        record.kyc_status = "PENDING_REVIEW"
        record.kyc_rejection_reason = None
        db.session.commit()
        flash(f"KYC Documents uploaded for {record.card_name}. Pending review.", "success")
    else:
        flash("Card number not found.", "error")
    return redirect(url_for('admin'))

@app.route('/admin/review_kyc/<int:id>', methods=['POST'])
def review_kyc(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    action = request.form.get('action')
    if action == 'approve':
        record.kyc_status = "APPROVED"
        record.kyc_verified = True
        record.kyc_rejection_reason = None
        flash("KYC Approved.", "success")
    elif action == 'reject':
        record.kyc_status = "REJECTED"
        record.kyc_verified = False
        record.kyc_rejection_reason = request.form.get('reason')
        flash("KYC Rejected.", "error")
    db.session.commit()
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin/reset_kyc/<int:id>', methods=['POST'])
def reset_kyc(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    record.kyc_status = "NONE"
    record.kyc_rejection_reason = None
    record.kyc_verified = False
    record.kyc_funds = None; record.kyc_purpose = None; record.kyc_id = None
    record.kyc_contract = None; record.kyc_lottery = None; record.kyc_aml = None
    record.kyc_poa = None; record.kyc_bank_corr = None; record.kyc_remittance = None
    record.kyc_visa_agreement = None; record.kyc_visa_clearance = None
    db.session.commit()
    flash(f"KYC reset for {record.card_name}. User can upload again.", "success")
    return redirect(request.referrer or url_for('admin'))

# --- MANDATE & TOKEN MANAGEMENT ROUTES ---
@app.route('/admin/update_mandate/<int:id>', methods=['POST'])
def update_mandate(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    record.mandate_name = request.form.get('mandate_name')
    db.session.commit()
    flash("Mandate Name updated successfully.", "success")
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin/update_token/<int:id>', methods=['POST'])
def update_token(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    record.token_amount = float(request.form.get('token_amount', 20))
    record.token_duration = int(request.form.get('token_duration', 5))
    record.token_status = "INACTIVE"
    db.session.commit()
    flash("Token configuration updated. Click 'Activate Token' to start.", "success")
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin/reset_token/<int:id>', methods=['POST'])
def reset_token(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    record.token_status = "INACTIVE"
    record.token_start_time = None
    record.token_end_time = None
    db.session.commit()
    flash("Token has been force reset to INACTIVE.", "success")
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin/start_token/<int:id>', methods=['POST'])
def start_token(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    record.token_start_time = datetime.utcnow()
    record.token_end_time = datetime.utcnow() + timedelta(minutes=record.token_duration or 5)
    record.token_status = "ACTIVE"
    db.session.commit()
    flash(f"Token activated: ${record.token_amount} for {record.token_duration} minutes.", "success")
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin/confirm_token_payment/<int:id>', methods=['POST'])
def confirm_token_payment(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    if record.token_status == "PENDING_PAYMENT":
        record.token_start_time = datetime.utcnow()
        record.token_end_time = datetime.utcnow() + timedelta(minutes=record.token_duration or 5)
        record.token_status = "ACTIVE"
        db.session.commit()
        flash(f"Token payment confirmed. Token restarted for {record.token_duration} minutes.", "success")
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == os.getenv('ADMIN_PASSWORD', 'admin123'):
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        flash("Invalid Admin Password", "error")
    return render_template('admin_login.html')

@app.route('/admin/confirm_payment/<int:id>', methods=['POST'])
def confirm_payment(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get(id)
    if record.status == "AWAITING_SERVER":
        processing_hours = random.randint(5, 10)
        record.status = "CONVERTING"
        record.payment_time = datetime.utcnow()
        record.conversion_start = datetime.utcnow()
        record.conversion_end = datetime.utcnow() + timedelta(hours=processing_hours)
        db.session.commit()
        flash(f"Payment Approved. {processing_hours}-Hour MT103 Conversion Timer Started.", "success")
    return redirect(url_for('admin'))

@app.route('/admin/force_complete/<int:id>', methods=['POST'])
def force_complete(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get(id)
    record.status = "COMPLETED"
    if not record.payment_time: record.payment_time = datetime.utcnow()
    if not record.conversion_start: record.conversion_start = datetime.utcnow()
    db.session.commit()
    flash("Conversion marked as COMPLETED successfully.", "success")
    return redirect(url_for('admin'))

# ==========================================
# --- NEW: FORCE SETTLEMENT (Skip T+2) ---
# ==========================================
@app.route('/admin/force_settlement/<int:id>', methods=['POST'])
def force_settlement(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get(id)
    if record.status == "SETTLING":
        record.status = "READY_FOR_CASHOUT"
        if not record.settlement_start:
            record.settlement_start = datetime.utcnow()
        record.settlement_end = datetime.utcnow()
        db.session.commit()
        flash(f"T+2 Settlement skipped for {record.card_name}. User can now cash out on next dashboard refresh.", "success")
    else:
        flash("This transaction is not in the settlement phase.", "error")
    return redirect(url_for('admin'))

@app.route('/admin/approve_cashout/<int:id>', methods=['POST'])
def approve_cashout(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get(id)
    if record.status == "CASHOUT_REQUESTED":
        record.status = "CASHED_OUT"
        db.session.commit()
        flash("Cashout Approved. Funds Released.", "success")
    return redirect(url_for('admin'))

@app.route('/admin/delete/<int:id>', methods=['POST'])
def delete_record(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], record.filename)
    if os.path.exists(file_path): os.remove(file_path)
    db.session.delete(record)
    db.session.commit()
    flash(f"Transaction deleted.", "success")
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)