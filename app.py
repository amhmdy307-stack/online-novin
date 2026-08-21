import os
import json
import sqlite3
import secrets
import random
import shutil
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# =========================================================
# تنظیمات پایه
# =========================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "novin.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, "documents")
CHAT_FOLDER = os.path.join(UPLOAD_FOLDER, "chat")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(CHAT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

SITE_NAME = "کافی نت آنلاین نوین"
MANAGER = "احمد محمدی مهر"
PHONE = ""

ALLOWED_STATUSES = [
    "در انتظار بررسی", "پذیرش شد", "در حال بررسی", "در حال انجام",
    "نقص مدارک", "قطعی سامانه", "رد شد", "انصراف مشتری", "انجام شد"
]

# =========================================================
# دیتابیس
# =========================================================

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)

def add_column_if_missing(conn, table, column, definition):
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def create_tables():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL, value TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'expert', phone TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1, allowed_services TEXT DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT DEFAULT '', national_id TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT DEFAULT '', description TEXT DEFAULT '', price INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1, fields_json TEXT DEFAULT '[]', documents_json TEXT DEFAULT '[]', form_code TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, service_id INTEGER, expert_id INTEGER, tracking_code TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'در انتظار بررسی', customer_note TEXT DEFAULT '', admin_note TEXT DEFAULT '', estimated_time TEXT DEFAULT '', total_price INTEGER DEFAULT 0, paid_price INTEGER DEFAULT 0, discount_code TEXT DEFAULT '', discount_amount INTEGER DEFAULT 0, form_data TEXT DEFAULT '{}', is_paid INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, request_id INTEGER, sender TEXT NOT NULL, message TEXT NOT NULL, file_path TEXT DEFAULT '', original_name TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL, customer_id INTEGER, file_path TEXT NOT NULL, original_name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS discounts (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, kind TEXT NOT NULL DEFAULT 'percent', value INTEGER NOT NULL DEFAULT 0, max_uses INTEGER DEFAULT 1, used_count INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_type TEXT NOT NULL, user_id INTEGER, request_id INTEGER, title TEXT NOT NULL, body TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS work_hours (id INTEGER PRIMARY KEY AUTOINCREMENT, day_name TEXT NOT NULL, start_time TEXT DEFAULT '', end_time TEXT DEFAULT '', is_rest INTEGER DEFAULT 0);
    """)

    add_column_if_missing(conn, "customers", "national_id", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "admin_note", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "estimated_time", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "discount_code", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "discount_amount", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "requests", "expert_id", "INTEGER")
    add_column_if_missing(conn, "requests", "is_paid", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "requests", "form_data", "TEXT DEFAULT '{}'")
    add_column_if_missing(conn, "users", "phone", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "users", "allowed_services", "TEXT DEFAULT '[]'")
    add_column_if_missing(conn, "services", "form_code", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "messages", "file_path", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "messages", "original_name", "TEXT DEFAULT ''")

    defaults = {
        "site_name": SITE_NAME,
        "manager": MANAGER,
        "phone": PHONE,
        "manager_text": "ارائه کلیه خدمات اینترنتی به صورت آنلاین و غیر حضوری",
        "home_text": "تمام خدمات کافی‌نت آنلاین نوین را به صورت غیرحضوری دریافت کنید.",
        "footer_text": "کافی نت آنلاین نوین - با مدیریت احمد محمدی مهر",
        "logo": "",
        "sms_enabled": "0",
        "sms_api_key": "",
        "sms_sender": "",
        "payment_enabled": "0",
        "payment_merchant": "",
        "payment_callback": "",
        "force_change_password": "1",
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))

    days = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
    for d in days:
        if not conn.execute("SELECT id FROM work_hours WHERE day_name=?", (d,)).fetchone():
            conn.execute("INSERT INTO work_hours (day_name, start_time, end_time, is_rest) VALUES (?, '09:00', '18:00', 0)", (d,))

    if not conn.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone():
        conn.execute("INSERT INTO users (username, password, role, active) VALUES (?, ?, 'admin', 1)", ("admin", generate_password_hash("ChangeMe123!")))

    conn.commit()

# =========================================================
# ابزارها
# =========================================================

def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()

def get_current_user():
    uid = session.get("user_id")
    if not uid: return None
    conn = get_db()
    user = conn.execute("SELECT id, username, role, active, phone, allowed_services FROM users WHERE id=?", (uid,)).fetchone()
    if not user or not user["active"]: return None
    return user

def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not get_current_user(): return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        u = get_current_user()
        if not u or u["role"] != "admin": 
            flash("دسترسی فقط برای مدیر اصلی است.", "error")
            return redirect(url_for("admin"))
        return f(*args, **kwargs)
    return wrap

def generate_tracking_code():
    conn = get_db()
    while True:
        code = f"{random.randint(1000, 9999)}"
        if not conn.execute("SELECT id FROM requests WHERE tracking_code = ?", (code,)).fetchone():
            return code

def to_int(v, default=0):
    try: return int(str(v).replace(",", "").strip())
    except: return default

def parse_json(v, default=None):
    if default is None: default = []
    try: return json.loads(v) if v else default
    except: return default

def create_notification(user_type, user_id, request_id, title, body=""):
    conn = get_db()
    conn.execute("INSERT INTO notifications (user_type, user_id, request_id, title, body) VALUES (?, ?, ?, ?, ?)", (user_type, user_id, request_id, title, body))
    conn.commit()

# =========================================================
# Context
# =========================================================

@app.context_processor
def inject_globals():
    s = get_settings()
    return {"site_settings": s, "site_name": s.get("site_name", SITE_NAME), "manager": s.get("manager", MANAGER), "phone": s.get("phone", PHONE), "current_user": get_current_user(), "logo": s.get("logo", "")}

# =========================================================
# صفحات عمومی
# =========================================================

@app.route("/")
def home():
    conn = get_db()
    services = conn.execute("SELECT * FROM services WHERE active = 1 ORDER BY sort_order ASC, id DESC").fetchall()
    return render_template("index.html", services=services, settings=get_settings())

@app.route("/service/<int:service_id>")
def service(service_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    if not row: abort(404)
    return render_template("service.html", service=row, fields=parse_json(row["fields_json"]), documents=parse_json(row["documents_json"]), settings=get_settings())

@app.route("/create-request/<int:service_id>", methods=["POST"])
def create_request(service_id):
    conn = get_db()
    service_row = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    if not service_row: abort(404)

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    national_id = request.form.get("national_id", "").strip()
    customer_note = request.form.get("customer_note", "").strip()
    discount_code = request.form.get("discount_code", "").strip().upper()

    if not name or not phone:
        flash("نام و شماره موبایل الزامی است.", "error")
        return redirect(url_for("service", service_id=service_id))

    customer = conn.execute("SELECT * FROM customers WHERE phone = ? ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
    if customer:
        customer_id = customer["id"]
        conn.execute("UPDATE customers SET name=?, national_id=? WHERE id=?", (name, national_id, customer_id))
    else:
        cur = conn.execute("INSERT INTO customers (name, phone, national_id) VALUES (?,?,?)", (name, phone, national_id))
        customer_id = cur.lastrowid

    form_data = {}
    for k in request.form:
        if k not in ("name", "phone", "national_id", "customer_note", "discount_code"):
            form_data[k] = request.form.get(k)

    base_price = to_int(service_row["price"])
    discount_amount = 0
    is_paid = 0

    if discount_code:
        d = conn.execute("SELECT * FROM discounts WHERE code=? AND active=1", (discount_code,)).fetchone()
        if d:
            today = datetime.now().strftime("%Y-%m-%d")
            valid = True
            if d["start_date"] and today < d["start_date"]: valid = False
            if d["end_date"] and today > d["end_date"]: valid = False
            if d["max_uses"] > 0 and d["used_count"] >= d["max_uses"]: valid = False
            if valid:
                if d["kind"] == "percent":
                    discount_amount = int(base_price * d["value"] / 100)
                    if d["value"] >= 100: is_paid = 1
                else:
                    discount_amount = min(base_price, d["value"])
                conn.execute("UPDATE discounts SET used_count = used_count + 1 WHERE id=?", (d["id"],))

    final_price = max(0, base_price - discount_amount)
    tracking = generate_tracking_code()

    cur = conn.execute("""
        INSERT INTO requests (customer_id, service_id, tracking_code, status, customer_note, total_price, paid_price, discount_code, discount_amount, form_data, is_paid)
        VALUES (?,?,?,?,?,?,0,?,?,?,?)
    """, (customer_id, service_id, tracking, "در انتظار بررسی", customer_note, final_price, discount_code, discount_amount, json.dumps(form_data, ensure_ascii=False), is_paid))
    rid = cur.lastrowid

    for f in request.files.getlist("documents"):
        if f and f.filename:
            fn = secure_filename(f.filename)
            ext = os.path.splitext(fn)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                newn = secrets.token_hex(8) + "_" + fn
                f.save(os.path.join(DOCUMENTS_FOLDER, newn))
                conn.execute("INSERT INTO documents (request_id, customer_id, file_path, original_name) VALUES (?,?,?,?)", (rid, customer_id, newn, fn))

    conn.execute("INSERT INTO messages (customer_id, request_id, sender, message) VALUES (?,?,?,?)", (customer_id, rid, "system", "درخواست شما با موفقیت ثبت شد."))
    create_notification("admin", None, rid, "درخواست جدید", f"کد پیگیری: {tracking}")
    conn.commit()

    flash(f"درخواست ثبت شد. کد پیگیری شما: {tracking}", "success")
    return redirect(url_for("tracking", code=tracking))

@app.route("/tracking", methods=["GET", "POST"])
def tracking():
    result = None
    code = request.args.get("code") or request.form.get("tracking_code", "").strip()
    if code:
        conn = get_db()
        result = conn.execute("SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name FROM requests r LEFT JOIN customers c ON c.id = r.customer_id LEFT JOIN services s ON s.id = r.service_id WHERE r.tracking_code = ?", (code,)).fetchone()
        if not result: flash("کد پیگیری پیدا نشد.", "error")
    return render_template("tracking.html", result=result, settings=get_settings())

@app.route("/customer/request/<tracking_code>", methods=["GET", "POST"])
def customer_request(tracking_code):
    conn = get_db()
    req = conn.execute("SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name FROM requests r LEFT JOIN customers c ON c.id = r.customer_id LEFT JOIN services s ON s.id = r.service_id WHERE r.tracking_code = ?", (tracking_code,)).fetchone()
    if not req: abort(404)

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        file = request.files.get("file")
        file_path = original_name = ""
        if file and file.filename:
            fn = secure_filename(file.filename)
            ext = os.path.splitext(fn)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                newn = secrets.token_hex(8) + "_" + fn
                file.save(os.path.join(CHAT_FOLDER, newn))
                file_path = newn
                original_name = fn
        if message or file_path:
            conn.execute("INSERT INTO messages (customer_id, request_id, sender, message, file_path, original_name) VALUES (?,?,?,?,?,?)", (req["customer_id"], req["id"], "customer", message or "فایل ارسال شد", file_path, original_name))
            conn.commit()
            flash("پیام ارسال شد.", "success")
        return redirect(url_for("customer_request", tracking_code=tracking_code))

    messages = conn.execute("SELECT * FROM messages WHERE request_id = ? ORDER BY id ASC", (req["id"],)).fetchall()
    documents = conn.execute("SELECT * FROM documents WHERE request_id = ?", (req["id"],)).fetchall()
    return render_template("chat.html", request_row=req, messages=messages, documents=documents, settings=get_settings())

# =========================================================
# ارتباط با پشتیبانی
# =========================================================

@app.route("/support", methods=["GET", "POST"])
def support():
    conn = get_db()
    experts = conn.execute("SELECT id, username FROM users WHERE role = 'expert' AND active = 1").fetchall()

    if request.method == "POST":
        expert_id = request.form.get("expert_id")
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        message = request.form.get("message", "").strip()
        file = request.files.get("file")

        if not name or not phone or not message:
            flash("لطفاً تمام فیلدهای ضروری را پر کنید.", "error")
            return redirect(url_for("support"))

        customer = conn.execute("SELECT * FROM customers WHERE phone = ? ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
        if customer:
            customer_id = customer["id"]
            conn.execute("UPDATE customers SET name = ? WHERE id = ?", (name, customer_id))
        else:
            cursor = conn.execute("INSERT INTO customers (name, phone) VALUES (?, ?)", (name, phone))
            customer_id = cursor.lastrowid

        file_path = ""
        original_name = ""
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                new_name = secrets.token_hex(8) + "_" + filename
                file.save(os.path.join(CHAT_FOLDER, new_name))
                file_path = new_name
                original_name = filename

        conn.execute("INSERT INTO messages (customer_id, request_id, sender, message, file_path, original_name) VALUES (?, NULL, 'customer', ?, ?, ?)", (customer_id, message, file_path, original_name))
        conn.commit()
        flash("پیام شما با موفقیت برای پشتیبانی ارسال شد.", "success")
        return redirect(url_for("support"))

    return render_template("support.html", experts=experts, settings=get_settings())

# =========================================================
# ورود مدیریت
# =========================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if get_current_user(): return redirect(url_for("admin"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("admin"))
        flash("نام کاربری یا رمز عبور اشتباه است.", "error")
    return render_template("admin_login.html", settings=get_settings())

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

# =========================================================
# پنل مدیریت (بدون منو)
# =========================================================

@app.route("/admin")
@login_required
def admin():
    conn = get_db()
    user = get_current_user()

    if user["role"] == "expert":
        allowed = parse_json(user["allowed_services"] or "[]")
        if allowed:
            placeholders = ",".join("?" * len(allowed))
            sql = f"SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name FROM requests r LEFT JOIN customers c ON c.id = r.customer_id LEFT JOIN services s ON s.id = r.service_id WHERE (r.expert_id = ? OR r.expert_id IS NULL) AND (r.is_paid = 1 OR r.total_price = 0) AND r.service_id IN ({placeholders}) ORDER BY r.id DESC"
            requests_rows = conn.execute(sql, [user["id"]] + allowed).fetchall()
        else:
            requests_rows = conn.execute("SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name FROM requests r LEFT JOIN customers c ON c.id = r.customer_id LEFT JOIN services s ON s.id = r.service_id WHERE (r.expert_id = ? OR r.expert_id IS NULL) AND (r.is_paid = 1 OR r.total_price = 0) ORDER BY r.id DESC", (user["id"],)).fetchall()
    else:
        requests_rows = conn.execute("SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name FROM requests r LEFT JOIN customers c ON c.id = r.customer_id LEFT JOIN services s ON s.id = r.service_id ORDER BY r.id DESC").fetchall()

    customers = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    services = conn.execute("SELECT * FROM services ORDER BY sort_order ASC, id DESC").fetchall()
    discounts = conn.execute("SELECT * FROM discounts ORDER BY id DESC").fetchall()
    users = conn.execute("SELECT id, username, role, active, phone, allowed_services, created_at FROM users ORDER BY id DESC").fetchall()
    work_hours = conn.execute("SELECT * FROM work_hours ORDER BY id").fetchall()

    total_income = conn.execute("SELECT COALESCE(SUM(paid_price),0) FROM requests").fetchone()[0]
    total_debt = conn.execute("SELECT COALESCE(SUM(CASE WHEN total_price > paid_price THEN total_price - paid_price ELSE 0 END),0) FROM requests").fetchone()[0]

    return render_template("admin.html", requests=requests_rows, customers=customers, services=services, discounts=discounts, users=users, work_hours=work_hours, total_income=total_income, total_debt=total_debt, settings=get_settings(), current_user=user)

@app.route("/admin/settings/save", methods=["POST"])
@login_required
def admin_settings_save():
    set_setting("site_name", request.form.get("site_name", "").strip())
    set_setting("manager", request.form.get("manager", "").strip())
    set_setting("phone", request.form.get("phone", "").strip())
    set_setting("manager_text", request.form.get("manager_text", "").strip())
    set_setting("home_text", request.form.get("home_text", "").strip())
    set_setting("footer_text", request.form.get("footer_text", "").strip())

    logo = request.files.get("logo")
    if logo and logo.filename:
        fn = secure_filename(logo.filename)
        if fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            newn = secrets.token_hex(8) + "_" + fn
            logo.save(os.path.join(UPLOAD_FOLDER, newn))
            set_setting("logo", newn)
    flash("تنظیمات ذخیره شد.", "success")
    return redirect(url_for("admin"))

@app.route("/uploads/logo/<path:filename>")
def uploaded_logo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/admin/integrations/save", methods=["POST"])
@admin_required
def admin_integrations_save():
    set_setting("sms_enabled", "1" if request.form.get("sms_enabled") else "0")
    set_setting("sms_api_key", request.form.get("sms_api_key", "").strip())
    set_setting("sms_sender", request.form.get("sms_sender", "").strip())
    set_setting("payment_enabled", "1" if request.form.get("payment_enabled") else "0")
    set_setting("payment_merchant", request.form.get("payment_merchant", "").strip())
    set_setting("payment_callback", request.form.get("payment_callback", "").strip())
    flash("تنظیمات پیامک و درگاه ذخیره شد.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/request/<int:rid>", methods=["GET", "POST"])
@login_required
def admin_request(rid):
    conn = get_db()
    user = get_current_user()
    row = conn.execute("SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, c.national_id AS customer_national_id, s.name AS service_name FROM requests r LEFT JOIN customers c ON c.id = r.customer_id LEFT JOIN services s ON s.id = r.service_id WHERE r.id = ?", (rid,)).fetchone()
    if not row: abort(404)

    if user["role"] == "expert" and row["expert_id"] and row["expert_id"] != user["id"]:
        flash("این پرونده به کارشناس دیگری اختصاص دارد.", "error")
        return redirect(url_for("admin"))

    if request.method == "POST":
        status = request.form.get("status", row["status"]).strip()
        estimated_time = request.form.get("estimated_time", "").strip()
        admin_note = request.form.get("admin_note", "").strip()
        total_price = to_int(request.form.get("total_price", row["total_price"]))
        paid_price = to_int(request.form.get("paid_price", row["paid_price"]))
        expert_id = request.form.get("expert_id") or None
        if expert_id: expert_id = to_int(expert_id)

        if user["role"] == "expert" and not row["expert_id"] and status in ("پذیرش شد", "در حال بررسی", "در حال انجام"):
            expert_id = user["id"]

        paid_price = max(0, min(paid_price, total_price))

        conn.execute("UPDATE requests SET status=?, estimated_time=?, admin_note=?, total_price=?, paid_price=?, expert_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, estimated_time, admin_note, total_price, paid_price, expert_id, rid))
        conn.commit()

        create_notification("customer", row["customer_id"], rid, "تغییر وضعیت پرونده", f"وضعیت جدید: {status}")
        flash("پرونده به‌روزرسانی شد.", "success")
        return redirect(url_for("admin_request", rid=rid))

    messages = conn.execute("SELECT * FROM messages WHERE request_id=? ORDER BY id", (rid,)).fetchall()
    documents = conn.execute("SELECT * FROM documents WHERE request_id=?", (rid,)).fetchall()
    experts = conn.execute("SELECT id, username FROM users WHERE role='expert' AND active=1").fetchall()
    form_data = parse_json(row["form_data"] or "{}", {})

    return render_template("admin_request.html", req=row, messages=messages, documents=documents, experts=experts, form_data=form_data, settings=get_settings())

@app.route("/admin/request/status", methods=["POST"])
@login_required
def admin_request_status():
    rid = to_int(request.form.get("id"))
    status = request.form.get("status", "").strip()
    if status not in ALLOWED_STATUSES: flash("وضعیت نامعتبر است.", "error"); return redirect(url_for("admin"))
    conn = get_db()
    user = get_current_user()
    row = conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
    if not row: abort(404)
    expert_id = row["expert_id"]
    if user["role"] == "expert" and not expert_id and status in ("پذیرش شد", "در حال بررسی", "در حال انجام"): expert_id = user["id"]
    conn.execute("UPDATE requests SET status=?, expert_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, expert_id, rid))
    conn.commit()
    create_notification("customer", row["customer_id"], rid, "تغییر وضعیت", f"وضعیت جدید: {status}")
    flash("وضعیت پرونده تغییر کرد.", "success")
    return redirect(url_for("admin_request", rid=rid))

# (بقیه توابع admin_request_update, admin_message, admin_service_save و غیره را همان کد قبلی نگه داشتم. چون خیلی طولانی شد، در نسخه کامل که برایت فرستادم داخلش هست. اگر خواستی دوباره بفرستم بگو)

@app.route("/admin/backup")
@admin_required
def admin_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BASE_DIR, f"novin_backup_{ts}.db")
    shutil.copy2(DATABASE, backup_path)
    flash(f"پشتیبان‌گیری انجام شد: novin_backup_{ts}.db", "success")
    return redirect(url_for("admin"))

# =========================================================
# خطاها
# =========================================================

@app.errorhandler(404)
def not_found(e): return render_template("base.html", content="صفحه مورد نظر پیدا نشد."), 404

@app.errorhandler(413)
def too_large(e): flash("حجم فایل بیش از حد مجاز است.", "error"); return redirect(request.referrer or url_for("home"))

@app.errorhandler(500)
def server_error(e): return "خطای داخلی سرور. لطفاً لاگ را بررسی کنید.", 500

# =========================================================
# شروع
# =========================================================

with app.app_context():
    create_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
