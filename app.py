import os
import json
import sqlite3
import secrets
import random
import shutil
import requests
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, g, jsonify, Response
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "novin.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, "documents")
CHAT_FOLDER = os.path.join(UPLOAD_FOLDER, "chat")
BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(CHAT_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)

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

FIELD_LABELS = {
    "name": "نام و نام خانوادگی",
    "phone": "شماره موبایل",
    "national_id": "کد ملی",
    "customer_note": "توضیحات مشتری",
    "discount_code": "کد تخفیف",
}


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
        CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT DEFAULT '', national_id TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT DEFAULT '', description TEXT DEFAULT '', price INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1, fields_json TEXT DEFAULT '[]', documents_json TEXT DEFAULT '[]', form_code TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, service_id INTEGER, expert_id INTEGER, tracking_code TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'در انتظار بررسی', customer_note TEXT DEFAULT '', admin_note TEXT DEFAULT '', estimated_time TEXT DEFAULT '', total_price INTEGER DEFAULT 0, paid_price INTEGER DEFAULT 0, discount_code TEXT DEFAULT '', discount_amount INTEGER DEFAULT 0, form_data TEXT DEFAULT '{}', is_paid INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, request_id INTEGER, sender TEXT NOT NULL, message TEXT NOT NULL, file_path TEXT DEFAULT '', original_name TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL, customer_id INTEGER, file_path TEXT NOT NULL, original_name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS discounts (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, kind TEXT NOT NULL DEFAULT 'percent', value INTEGER NOT NULL DEFAULT 0, max_uses INTEGER DEFAULT 1, used_count INTEGER DEFAULT 0, start_date TEXT DEFAULT '', end_date TEXT DEFAULT '', active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_type TEXT NOT NULL, user_id INTEGER, request_id INTEGER, title TEXT NOT NULL, body TEXT DEFAULT '', is_read INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
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
        "site_name": SITE_NAME, "manager": MANAGER, "phone": PHONE,
        "manager_text": "ارائه کلیه خدمات اینترنتی به صورت آنلاین و غیر حضوری",
        "home_text": "", "footer_text": "", "logo": "",
        "sms_enabled": "0", "sms_api_key": "", "sms_sender": "",
        "payment_enabled": "0", "payment_merchant": "", "payment_callback": "",
        "force_change_password": "1", "backup_email": "",
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))

    days = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
    for d in days:
        if not conn.execute("SELECT id FROM work_hours WHERE day_name=?", (d,)).fetchone():
            conn.execute("INSERT INTO work_hours (day_name, start_time, end_time, is_rest) VALUES (?, '09:00', '18:00', 0)", (d,))

    if not conn.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone():
        conn.execute("INSERT INTO users (username, password, role, active) VALUES (?, ?, 'admin', 1)",
                     ("admin", generate_password_hash("ChangeMe123!")))
    conn.commit()


def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    user = conn.execute("SELECT id, username, role, active, phone, allowed_services FROM users WHERE id = ?", (uid,)).fetchone()
    if not user or not user["active"]:
        return None
    return user


def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("admin_login"))
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
    try:
        return int(str(v).replace(",", "").strip())
    except:
        return default


def parse_json(v, default=None):
    if default is None:
        default = []
    try:
        return json.loads(v) if v else default
    except:
        return default


def to_latin_digits(text):
    if text is None:
        return ""
    persian = "۰۱۲۳۴۵۶۷۸۹"
    arabic = "٠١٢٣٤٥٦٧٨٩"
    latin = "0123456789"
    return str(text).translate(str.maketrans(persian + arabic, latin + latin))


def get_field_label(key):
    return FIELD_LABELS.get(key, key)


def create_notification(user_type, user_id, request_id, title, body=""):
    conn = get_db()
    conn.execute("INSERT INTO notifications (user_type, user_id, request_id, title, body) VALUES (?, ?, ?, ?, ?)",
                 (user_type, user_id, request_id, title, body))
    conn.commit()


def send_sms(mobile, message):
    try:
        mobile = to_latin_digits(str(mobile or "").strip())

        if not mobile:
            return False

        if mobile.startswith("+98"):
            mobile = "0" + mobile[3:]

        if mobile.startswith("98") and len(mobile) == 12:
            mobile = "0" + mobile[2:]

        settings = get_settings()

        if settings.get("sms_enabled") != "1":
            return False

        api_key = str(settings.get("sms_api_key", "") or "").strip()
        sender = str(settings.get("sms_sender", "") or "").strip()

        if not api_key or not sender:
            return False

        url = "https://api.sms.ir/v1/send/bulk"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": api_key
        }

        payload = {
            "lineNumber": int(sender),
            "MessageText": str(message),
            "Mobiles": [mobile]
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        if 200 <= response.status_code < 300:
            try:
                result = response.json()
                return bool(result.get("status", True))
            except Exception:
                return True

        return False

    except Exception:
        return False


def auto_backup():
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_FOLDER, f"novin_auto_{ts}.db")
        shutil.copy2(DATABASE, backup_path)
        files = sorted([f for f in os.listdir(BACKUP_FOLDER) if f.startswith("novin_auto_")], reverse=True)
        for old in files[10:]:
            os.remove(os.path.join(BACKUP_FOLDER, old))
    except Exception:
        pass


@app.context_processor
def inject_globals():
    s = get_settings()
    return {
        "site_settings": s,
        "site_name": s.get("site_name", SITE_NAME),
        "manager": s.get("manager", MANAGER),
        "phone": s.get("phone", PHONE),
        "current_user": get_current_user(),
        "logo": s.get("logo", ""),
        "get_field_label": get_field_label,
    }


@app.route("/")
def home():
    conn = get_db()
    services = conn.execute("SELECT * FROM services WHERE active = 1 ORDER BY sort_order ASC, id DESC").fetchall()
    return render_template("index.html", services=services, settings=get_settings())


@app.route("/service/<int:service_id>")
def service(service_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    if not row:
        abort(404)
    fields = parse_json(row["fields_json"])
    documents = parse_json(row["documents_json"])
    return render_template("service.html", service=row, fields=fields, documents=documents, settings=get_settings())


@app.route("/create-request/<int:service_id>", methods=["POST"])
def create_request(service_id):
    conn = get_db()
    service_row = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    if not service_row:
        abort(404)

    name = to_latin_digits(request.form.get("name", "").strip())
    phone = to_latin_digits(request.form.get("phone", "").strip())
    national_id = to_latin_digits(request.form.get("national_id", "").strip())
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
            form_data[k] = to_latin_digits(request.form.get(k))

    base_price = to_int(service_row["price"])
    discount_amount = 0
    is_paid = 0

    if discount_code:
        d = conn.execute("SELECT * FROM discounts WHERE code=? AND active=1", (discount_code,)).fetchone()
        if d:
            today = datetime.now().strftime("%Y-%m-%d")
            valid = True
            if d["start_date"] and today < d["start_date"]:
                valid = False
            if d["end_date"] and today > d["end_date"]:
                valid = False
            if d["max_uses"] > 0 and d["used_count"] >= d["max_uses"]:
                valid = False
            if valid:
                if d["kind"] == "percent":
                    discount_amount = int(base_price * d["value"] / 100)
                    if d["value"] >= 100:
                        is_paid = 1
                else:
                    discount_amount = min(base_price, d["value"])
                conn.execute("UPDATE discounts SET used_count = used_count + 1 WHERE id=?", (d["id"],))

    final_price = max(0, base_price - discount_amount)
    tracking = generate_tracking_code()

    cur = conn.execute("""
        INSERT INTO requests (customer_id, service_id, tracking_code, status, customer_note,
            total_price, paid_price, discount_code, discount_amount, form_data, is_paid)
        VALUES (?,?,?,?,?,?,0,?,?,?,?)
    """, (customer_id, service_id, tracking, "در انتظار بررسی", customer_note,
          final_price, discount_code, discount_amount, json.dumps(form_data, ensure_ascii=False), is_paid))
    rid = cur.lastrowid

    for f in request.files.getlist("documents"):
        if f and f.filename:
            fn = secure_filename(f.filename)
            ext = os.path.splitext(fn)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                newn = secrets.token_hex(8) + "_" + fn
                f.save(os.path.join(DOCUMENTS_FOLDER, newn))
                conn.execute("INSERT INTO documents (request_id, customer_id, file_path, original_name) VALUES (?,?,?,?)",
                             (rid, customer_id, newn, fn))

    conn.execute("INSERT INTO messages (customer_id, request_id, sender, message) VALUES (?,?,?,?)",
                 (customer_id, rid, "system", "درخواست شما با موفقیت ثبت شد."))
    create_notification("admin", None, rid, "درخواست جدید", f"کد پیگیری: {tracking}")
    create_notification("expert", None, rid, "درخواست جدید", f"کد پیگیری: {tracking}")
    conn.commit()

    send_sms(
        phone,
        f"{name} عزیز، درخواست شما در {SITE_NAME} با موفقیت ثبت شد.\nکد پیگیری: {tracking}"
    )

    auto_backup()
    flash(f"درخواست ثبت شد. کد پیگیری شما: {tracking}", "success")
    return redirect(url_for("tracking", code=tracking))


@app.route("/tracking", methods=["GET", "POST"])
def tracking():
    result = None
    code = request.args.get("code") or request.form.get("tracking_code", "").strip()
    if code:
        conn = get_db()
        result = conn.execute("""
            SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name,
                   u.username AS expert_name, u.role AS expert_role
            FROM requests r
            LEFT JOIN customers c ON c.id = r.customer_id
            LEFT JOIN services s ON s.id = r.service_id
            LEFT JOIN users u ON u.id = r.expert_id
            WHERE r.tracking_code = ?
        """, (code,)).fetchone()
        if not result:
            flash("کد پیگیری پیدا نشد.", "error")
    return render_template("tracking.html", result=result, settings=get_settings())


@app.route("/upload-missing/<tracking_code>", methods=["POST"])
def upload_missing_docs(tracking_code):
    conn = get_db()
    req = conn.execute("SELECT * FROM requests WHERE tracking_code = ?", (tracking_code,)).fetchone()
    if not req or req["status"] != "نقص مدارک":
        flash("امکان ارسال مدارک وجود ندارد.", "error")
        return redirect(url_for("tracking", code=tracking_code))

    for f in request.files.getlist("documents"):
        if f and f.filename:
            fn = secure_filename(f.filename)
            ext = os.path.splitext(fn)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                newn = secrets.token_hex(8) + "_" + fn
                f.save(os.path.join(DOCUMENTS_FOLDER, newn))
                conn.execute("INSERT INTO documents (request_id, customer_id, file_path, original_name) VALUES (?,?,?,?)",
                             (req["id"], req["customer_id"], newn, fn))

    conn.execute("UPDATE requests SET status = 'در انتظار بررسی', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (req["id"],))
    conn.commit()
    create_notification("admin", None, req["id"], "مدارک ناقص ارسال شد", f"کد پیگیری: {tracking_code}")
    if req["expert_id"]:
        create_notification("expert", req["expert_id"], req["id"], "مدارک ناقص ارسال شد", f"کد پیگیری: {tracking_code}")

    send_sms(
        req["customer_phone"] if "customer_phone" in req.keys() else "",
        f"مدارک پرونده {tracking_code} دریافت شد و پرونده مجدداً در انتظار بررسی قرار گرفت."
    )

    auto_backup()
    flash("مدارک با موفقیت ارسال شد.", "success")
    return redirect(url_for("tracking", code=tracking_code))


@app.route("/customer/request/<tracking_code>", methods=["GET", "POST"])
def customer_request(tracking_code):
    conn = get_db()
    req = conn.execute("""
        SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name,
               u.username AS expert_name, u.role AS expert_role
        FROM requests r
        LEFT JOIN customers c ON c.id = r.customer_id
        LEFT JOIN services s ON s.id = r.service_id
        LEFT JOIN users u ON u.id = r.expert_id
        WHERE r.tracking_code = ?
    """, (tracking_code,)).fetchone()
    if not req:
        abort(404)

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
            conn.execute("INSERT INTO messages (customer_id, request_id, sender, message, file_path, original_name) VALUES (?,?,?,?,?,?)",
                         (req["customer_id"], req["id"], "customer", message or "فایل ارسال شد", file_path, original_name))
            conn.commit()
            flash("پیام ارسال شد.", "success")
        return redirect(url_for("customer_request", tracking_code=tracking_code))

    messages = conn.execute("SELECT * FROM messages WHERE request_id = ? ORDER BY id ASC", (req["id"],)).fetchall()
    documents = conn.execute("SELECT * FROM documents WHERE request_id = ?", (req["id"],)).fetchall()
    work_hours = conn.execute("SELECT * FROM work_hours ORDER BY id").fetchall()
    return render_template("chat.html", request_row=req, messages=messages, documents=documents,
                           work_hours=work_hours, settings=get_settings())


@app.route("/support", methods=["GET", "POST"])
def support():
    conn = get_db()
    experts = conn.execute("SELECT id, username, role FROM users WHERE active = 1 AND role IN ('admin','expert') ORDER BY role DESC, id").fetchall()

    if request.method == "POST":
        expert_id = request.form.get("expert_id") or None
        name = to_latin_digits(request.form.get("name", "").strip())
        phone = to_latin_digits(request.form.get("phone", "").strip())
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

        file_path = original_name = ""
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                new_name = secrets.token_hex(8) + "_" + filename
                file.save(os.path.join(CHAT_FOLDER, new_name))
                file_path = new_name
                original_name = filename

        conn.execute("INSERT INTO messages (customer_id, request_id, sender, message, file_path, original_name) VALUES (?, NULL, 'customer', ?, ?, ?)",
                     (customer_id, message, file_path, original_name))
        create_notification("admin", None, None, "پیام پشتیبانی جدید", f"از {name} - {phone}")
        if expert_id:
            create_notification("expert", to_int(expert_id), None, "پیام پشتیبانی جدید", f"از {name} - {phone}")
        conn.commit()
        flash("پیام شما با موفقیت ارسال شد.", "success")
        return redirect(url_for("support"))

    return render_template("support.html", experts=experts, settings=get_settings())


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if get_current_user():
        return redirect(url_for("admin"))
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


@app.route("/admin")
@login_required
def admin():
    conn = get_db()
    user = get_current_user()

    if user["role"] == "expert":
        requests_rows = conn.execute("""
            SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
            FROM requests r
            LEFT JOIN customers c ON c.id = r.customer_id
            LEFT JOIN services s ON s.id = r.service_id
            WHERE (r.expert_id = ? OR r.expert_id IS NULL)
              AND (r.is_paid = 1 OR r.total_price = 0)
            ORDER BY r.id DESC
        """, (user["id"],)).fetchall()
    else:
        requests_rows = conn.execute("""
            SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
            FROM requests r
            LEFT JOIN customers c ON c.id = r.customer_id
            LEFT JOIN services s ON s.id = r.service_id
            ORDER BY r.id DESC
        """).fetchall()

    customers = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    services = conn.execute("SELECT * FROM services ORDER BY sort_order ASC, id DESC").fetchall()
    discounts = conn.execute("SELECT * FROM discounts ORDER BY id DESC").fetchall()
    users = conn.execute("SELECT id, username, role, active, phone, allowed_services, created_at FROM users ORDER BY id DESC").fetchall()
    work_hours = conn.execute("SELECT * FROM work_hours ORDER BY id").fetchall()
    total_income = conn.execute("SELECT COALESCE(SUM(paid_price),0) FROM requests").fetchone()[0]
    total_debt = conn.execute("SELECT COALESCE(SUM(CASE WHEN total_price > paid_price THEN total_price - paid_price ELSE 0 END),0) FROM requests").fetchone()[0]
    unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0").fetchone()[0]

    return render_template("admin.html", requests=requests_rows, customers=customers, services=services,
                           discounts=discounts, users=users, work_hours=work_hours,
                           total_income=total_income, total_debt=total_debt,
                           settings=get_settings(), current_user=user, unread_count=unread)


@app.route("/admin/settings/save", methods=["POST"])
@login_required
def admin_settings_save():
    set_setting("site_name", request.form.get("site_name", "").strip())
    set_setting("manager", request.form.get("manager", "").strip())
    set_setting("phone", request.form.get("phone", "").strip())
    set_setting("manager_text", request.form.get("manager_text", "").strip())
    set_setting("home_text", request.form.get("home_text", "").strip())
    set_setting("footer_text", request.form.get("footer_text", "").strip())
    set_setting("backup_email", request.form.get("backup_email", "").strip())
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
    row = conn.execute("""
        SELECT r.*, c.name AS customer_name, c.phone AS customer_phone,
               c.national_id AS customer_national_id, s.name AS service_name,
               u.username AS expert_name, u.role AS expert_role
        FROM requests r
        LEFT JOIN customers c ON c.id = r.customer_id
        LEFT JOIN services s ON s.id = r.service_id
        LEFT JOIN users u ON u.id = r.expert_id
        WHERE r.id = ?
    """, (rid,)).fetchone()
    if not row:
        abort(404)

    if user["role"] == "expert" and row["expert_id"] and row["expert_id"] != user["id"]:
        flash("این پرونده به کارشناس دیگری اختصاص دارد.", "error")
        return redirect(url_for("admin"))

    if request.method == "POST":
        status = request.form.get("status", row["status"]).strip()
        estimated_time = request.form.get("estimated_time", "").strip()
        admin_note = request.form.get("admin_note", "").strip()
        total_price = to_int(request.form.get("total_price", row["total_price"]))
        paid_price = to_int(request.form.get("paid_price", row["paid_price"]))

        expert_id = row["expert_id"]
        if status == "پذیرش شد" and not expert_id:
            expert_id = user["id"]

        paid_price = max(0, min(paid_price, total_price))
        conn.execute("""
            UPDATE requests SET status=?, estimated_time=?, admin_note=?,
                total_price=?, paid_price=?, expert_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (status, estimated_time, admin_note, total_price, paid_price, expert_id, rid))
        conn.commit()

        create_notification("customer", row["customer_id"], rid, "تغییر وضعیت پرونده", f"وضعیت جدید: {status}")

        send_sms(
            row["customer_phone"],
            f"{row['customer_name']} عزیز، وضعیت پرونده شما در {SITE_NAME} تغییر کرد.\nوضعیت جدید: {status}\nکد پیگیری: {row['tracking_code']}"
        )

        auto_backup()
        flash("پرونده به‌روزرسانی شد.", "success")
        return redirect(url_for("admin_request", rid=rid))

    messages = conn.execute("SELECT * FROM messages WHERE request_id=? ORDER BY id", (rid,)).fetchall()
    documents = conn.execute("SELECT * FROM documents WHERE request_id=?", (rid,)).fetchall()
    form_data = parse_json(row["form_data"] or "{}", {})
    return render_template("admin_request.html", req=row, messages=messages, documents=documents,
                           form_data=form_data, settings=get_settings())


@app.route("/admin/request/status", methods=["POST"])
@login_required
def admin_request_status():
    rid = to_int(request.form.get("id"))
    status = request.form.get("status", "").strip()
    if status not in ALLOWED_STATUSES:
        flash("وضعیت نامعتبر است.", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    user = get_current_user()
    row = conn.execute("""
        SELECT r.*, c.phone AS customer_phone, c.name AS customer_name
        FROM requests r
        LEFT JOIN customers c ON c.id = r.customer_id
        WHERE r.id=?
    """, (rid,)).fetchone()

    if not row:
        abort(404)

    expert_id = row["expert_id"]
    if status == "پذیرش شد" and not expert_id:
        expert_id = user["id"]

    conn.execute("UPDATE requests SET status=?, expert_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                 (status, expert_id, rid))
    conn.commit()

    create_notification("customer", row["customer_id"], rid, "تغییر وضعیت", f"وضعیت جدید: {status}")

    send_sms(
        row["customer_phone"],
        f"{row['customer_name']} عزیز، وضعیت پرونده شما در {SITE_NAME} تغییر کرد.\nوضعیت جدید: {status}\nکد پیگیری: {row['tracking_code']}"
    )

    auto_backup()
    flash("وضعیت پرونده تغییر کرد.", "success")
    return redirect(url_for("admin_request", rid=rid))


@app.route("/admin/request/update", methods=["POST"])
@login_required
def admin_request_update():
    rid = to_int(request.form.get("id"))
    total_price = to_int(request.form.get("total_price"))
    paid_price = to_int(request.form.get("paid_price"))
    estimated_time = request.form.get("estimated_time", "").strip()
    admin_note = request.form.get("admin_note", "").strip()
    paid_price = max(0, min(paid_price, total_price))
    conn = get_db()
    conn.execute("""
        UPDATE requests SET total_price=?, paid_price=?, estimated_time=?,
            admin_note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
    """, (total_price, paid_price, estimated_time, admin_note, rid))
    conn.commit()
    auto_backup()
    flash("اطلاعات پرونده ذخیره شد.", "success")
    return redirect(url_for("admin_request", rid=rid))


@app.route("/admin/message", methods=["POST"])
@login_required
def admin_message():
    rid = to_int(request.form.get("id"))
    message = request.form.get("message", "").strip()
    if not message:
        return redirect(url_for("admin_request", rid=rid))
    conn = get_db()
    row = conn.execute("SELECT customer_id FROM requests WHERE id=?", (rid,)).fetchone()
    if row:
        conn.execute("INSERT INTO messages (customer_id, request_id, sender, message) VALUES (?,?,?,?)",
                     (row["customer_id"], rid, "admin", message))
        conn.commit()
    flash("پیام ارسال شد.", "success")
    return redirect(url_for("admin_request", rid=rid))


@app.route("/admin/service/save", methods=["POST"])
@login_required
def admin_service_save():
    name = request.form.get("name", "").strip()
    if not name:
        flash("نام خدمت الزامی است.", "error")
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("""
        INSERT INTO services (name, category, description, price, sort_order, active, fields_json, documents_json)
        VALUES (?,?,?,?,?,?,?,?)
    """, (name, request.form.get("category", "").strip(), request.form.get("description", "").strip(),
          to_int(request.form.get("price")), to_int(request.form.get("sort_order")),
          1 if request.form.get("active", "1") == "1" else 0,
          request.form.get("fields_json", "[]"), request.form.get("documents_json", "[]")))
    conn.commit()
    flash("خدمت جدید اضافه شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/service/<int:sid>/toggle", methods=["POST"])
@login_required
def toggle_service(sid):
    conn = get_db()
    conn.execute("UPDATE services SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (sid,))
    conn.commit()
    return redirect(url_for("admin"))


@app.route("/admin/service/<int:sid>/delete", methods=["POST"])
@login_required
def delete_service(sid):
    conn = get_db()
    conn.execute("DELETE FROM services WHERE id=?", (sid,))
    conn.commit()
    flash("خدمت حذف شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "expert")
    phone = request.form.get("phone", "").strip()
    allowed = request.form.getlist("allowed_services")
    if role not in ("admin", "expert"):
        role = "expert"
    if not username or len(password) < 6:
        flash("اطلاعات نامعتبر است.", "error")
        return redirect(url_for("admin"))
    conn = get_db()
    if conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        flash("نام کاربری تکراری است.", "error")
        return redirect(url_for("admin"))
    conn.execute("INSERT INTO users (username, password, role, phone, allowed_services, active) VALUES (?,?,?,?,?,1)",
                 (username, generate_password_hash(password), role, phone, json.dumps([to_int(x) for x in allowed])))
    conn.commit()
    flash("کاربر ایجاد شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:uid>/toggle", methods=["POST"])
@admin_required
def toggle_user(uid):
    if uid == session.get("user_id"):
        flash("نمی‌توانید خودتان را غیرفعال کنید.", "error")
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("UPDATE users SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (uid,))
    conn.commit()
    return redirect(url_for("admin"))


@app.route("/admin/password", methods=["POST"])
@login_required
def admin_password():
    password = request.form.get("password", "")
    if len(password) < 6:
        flash("رمز عبور باید حداقل ۶ کاراکتر باشد.", "error")
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(password), session["user_id"]))
    conn.commit()
    set_setting("force_change_password", "0")
    flash("رمز عبور با موفقیت تغییر کرد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/discount/create", methods=["POST"])
@login_required
def create_discount():
    code = request.form.get("code", "").strip().upper()
    kind = request.form.get("kind", "percent")
    value = to_int(request.form.get("value"))
    if not code or value < 0 or (kind == "percent" and value > 100):
        flash("اطلاعات کد تخفیف صحیح نیست.", "error")
        return redirect(url_for("admin"))
    conn = get_db()
    if conn.execute("SELECT id FROM discounts WHERE code=?", (code,)).fetchone():
        flash("این کد تخفیف قبلاً وجود دارد.", "error")
        return redirect(url_for("admin"))
    conn.execute("""
        INSERT INTO discounts (code, kind, value, max_uses, start_date, end_date, active)
        VALUES (?,?,?,?,?,?,1)
    """, (code, kind, value, to_int(request.form.get("max_uses", 0)),
          request.form.get("start_date", ""), request.form.get("end_date", "")))
    conn.commit()
    flash("کد تخفیف ایجاد شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/discount/<int:did>/toggle", methods=["POST"])
@login_required
def toggle_discount(did):
    conn = get_db()
    conn.execute("UPDATE discounts SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (did,))
    conn.commit()
    return redirect(url_for("admin"))


@app.route("/admin/discount/<int:did>/delete", methods=["POST"])
@login_required
def delete_discount(did):
    conn = get_db()
    conn.execute("DELETE FROM discounts WHERE id=?", (did,))
    conn.commit()
    flash("کد تخفیف حذف شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/workhours/save", methods=["POST"])
@admin_required
def save_work_hours():
    conn = get_db()
    for day_id in request.form.getlist("day_id"):
        start = request.form.get(f"start_{day_id}", "")
        end = request.form.get(f"end_{day_id}", "")
        is_rest = 1 if request.form.get(f"rest_{day_id}") else 0
        conn.execute("UPDATE work_hours SET start_time=?, end_time=?, is_rest=? WHERE id=?",
                     (start, end, is_rest, day_id))
    conn.commit()
    flash("ساعات کاری ذخیره شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/backup")
@admin_required
def admin_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_FOLDER, f"novin_manual_{ts}.db")
    shutil.copy2(DATABASE, backup_path)
    flash(f"پشتیبان‌گیری انجام شد: novin_manual_{ts}.db", "success")
    return redirect(url_for("admin"))


@app.route("/admin/notifications")
@login_required
def admin_notifications():
    conn = get_db()
    rows = conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 50").fetchall()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    return jsonify([{"title": r["title"], "body": r["body"], "created_at": r["created_at"]} for r in rows])


@app.route("/17886038.txt")
def enamad_file():
    return Response("", status=200, mimetype="text/plain")


@app.route("/download/document/<int:doc_id>")
@login_required
def download_document(doc_id):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        abort(404)
    return send_from_directory(DOCUMENTS_FOLDER, doc["file_path"], as_attachment=True, download_name=doc["original_name"])


@app.route("/download/chat/<path:filename>")
@login_required
def download_chat_file(filename):
    return send_from_directory(CHAT_FOLDER, filename, as_attachment=True)


@app.errorhandler(404)
def not_found(e):
    return render_template("base.html", content="صفحه مورد نظر پیدا نشد."), 404


@app.errorhandler(413)
def too_large(e):
    flash("حجم فایل بیش از حد مجاز است.", "error")
    return redirect(request.referrer or url_for("home"))


@app.errorhandler(500)
def server_error(e):
    return "خطای داخلی سرور. لطفاً لاگ را بررسی کنید.", 500


with app.app_context():
    create_tables()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
```0
