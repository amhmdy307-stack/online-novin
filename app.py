import os
import json
import sqlite3
import secrets
import random
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# =========================================================
# تنظیمات
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
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

SITE_NAME = "کافی نت آنلاین نوین"
MANAGER = "احمد محمدی مهر"
PHONE = ""

ALLOWED_STATUSES = [
    "در انتظار بررسی",
    "پذیرش شد",
    "در حال بررسی",
    "نقص مدارک",
    "قطعی سامانه",
    "رد شد",
    "انصراف مشتری",
    "انجام شد"
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
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)

def add_column_if_missing(conn, table, column, definition):
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def create_tables():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'expert',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            national_id TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT '',
            description TEXT DEFAULT '',
            price INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            fields_json TEXT DEFAULT '[]',
            documents_json TEXT DEFAULT '[]',
            form_code TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            service_id INTEGER,
            expert_id INTEGER,
            tracking_code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'در انتظار بررسی',
            customer_note TEXT DEFAULT '',
            admin_note TEXT DEFAULT '',
            estimated_time TEXT DEFAULT '',
            total_price INTEGER DEFAULT 0,
            paid_price INTEGER DEFAULT 0,
            discount_code TEXT DEFAULT '',
            discount_amount INTEGER DEFAULT 0,
            form_data TEXT DEFAULT '{}',
            is_paid INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE SET NULL,
            FOREIGN KEY(expert_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            request_id INTEGER,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            file_path TEXT DEFAULT '',
            original_name TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            customer_id INTEGER,
            file_path TEXT NOT NULL,
            original_name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS discounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL DEFAULT 'percent',
            value INTEGER NOT NULL DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            start_date TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_type TEXT NOT NULL,
            user_id INTEGER,
            request_id INTEGER,
            title TEXT NOT NULL,
            body TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    add_column_if_missing(conn, "customers", "national_id", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "admin_note", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "estimated_time", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "discount_code", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "discount_amount", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "requests", "expert_id", "INTEGER")
    add_column_if_missing(conn, "requests", "is_paid", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "services", "form_code", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "messages", "file_path", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "messages", "original_name", "TEXT DEFAULT ''")

    defaults = {
        "site_name": SITE_NAME,
        "manager": MANAGER,
        "phone": PHONE,
        "manager_text": "ارائه کلیه خدمات کافی‌نت به صورت غیرحضوری",
        "home_text": "تمام خدمات کافی‌نت آنلاین نوین را به صورت غیرحضوری دریافت کنید.",
        "footer_text": "کافی نت آنلاین نوین - با مدیریت احمد محمدی مهر",
        "logo": "",
        "force_change_password": "1",
    }

    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            (key, value)
        )

    admin = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users(username, password, role, active) VALUES (?, ?, 'admin', 1)",
            ("admin", generate_password_hash("ChangeMe123!"))
        )

    conn.commit()

# =========================================================
# ابزارها
# =========================================================

def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}

def set_setting(key, value):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO settings(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value)
    )
    conn.commit()

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, role, active FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    if not user or not user["active"]:
        return None
    return user

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("admin_login"))
        if user["role"] != "admin":
            flash("دسترسی فقط برای مدیر امکان‌پذیر است.", "error")
            return redirect(url_for("admin"))
        return f(*args, **kwargs)
    return decorated

def generate_tracking_code():
    conn = get_db()
    while True:
        code = f"{random.randint(1000, 9999)}"
        exists = conn.execute(
            "SELECT id FROM requests WHERE tracking_code = ?", (code,)
        ).fetchone()
        if not exists:
            return code

def to_int(value, default=0):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return default

def parse_json_list(value):
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except Exception:
        return []

def create_notification(user_type, user_id, request_id, title, body=""):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO notifications (user_type, user_id, request_id, title, body)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_type, user_id, request_id, title, body)
    )
    conn.commit()

# =========================================================
# Context
# =========================================================

@app.context_processor
def inject_globals():
    settings = get_settings()
    return {
        "site_settings": settings,
        "site_name": settings.get("site_name", SITE_NAME),
        "manager": settings.get("manager", MANAGER),
        "phone": settings.get("phone", PHONE),
        "current_user": get_current_user(),
    }

# =========================================================
# صفحات عمومی
# =========================================================

@app.route("/")
def home():
    conn = get_db()
    services = conn.execute(
        "SELECT * FROM services WHERE active = 1 ORDER BY sort_order ASC, id DESC"
    ).fetchall()
    return render_template("index.html", services=services, settings=get_settings())

@app.route("/index")
def index():
    return redirect(url_for("home"))

@app.route("/service/<int:service_id>", methods=["GET", "POST"])
def service(service_id):
    conn = get_db()
    service_row = conn.execute(
        "SELECT * FROM services WHERE id = ?", (service_id,)
    ).fetchone()

    if not service_row:
        abort(404)

    fields = parse_json_list(service_row["fields_json"])
    documents = parse_json_list(service_row["documents_json"])

    return render_template(
        "service.html",
        service=service_row,
        fields=fields,
        documents=documents,
        settings=get_settings(),
    )

@app.route("/create-request/<int:service_id>", methods=["POST"])
def create_request(service_id):
    conn = get_db()
    service_row = conn.execute(
        "SELECT * FROM services WHERE id = ?", (service_id,)
    ).fetchone()

    if not service_row:
        abort(404)

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    national_id = request.form.get("national_id", "").strip()
    customer_note = request.form.get("customer_note", "").strip()
    discount_code = request.form.get("discount_code", "").strip().upper()

    if not name or not phone:
        flash("نام و شماره موبایل الزامی است.", "error")
        return redirect(url_for("service", service_id=service_id))

    customer = conn.execute(
        "SELECT * FROM customers WHERE phone = ? ORDER BY id DESC LIMIT 1",
        (phone,)
    ).fetchone()

    if customer:
        customer_id = customer["id"]
        conn.execute(
            "UPDATE customers SET name = ?, national_id = ? WHERE id = ?",
            (name, national_id, customer_id)
        )
    else:
        cursor = conn.execute(
            "INSERT INTO customers (name, phone, national_id) VALUES (?, ?, ?)",
            (name, phone, national_id)
        )
        customer_id = cursor.lastrowid

    form_data = {}
    for key in request.form:
        if key not in ("name", "phone", "national_id", "customer_note", "discount_code"):
            form_data[key] = request.form.get(key)

    base_price = to_int(service_row["price"])
    discount_amount = 0
    is_paid = 0

    if discount_code:
        discount = conn.execute(
            "SELECT * FROM discounts WHERE code = ? AND active = 1",
            (discount_code,)
        ).fetchone()

        if discount:
            today = datetime.now().strftime("%Y-%m-%d")
            valid = True
            if discount["start_date"] and today < discount["start_date"]:
                valid = False
            if discount["end_date"] and today > discount["end_date"]:
                valid = False
            if discount["max_uses"] > 0 and discount["used_count"] >= discount["max_uses"]:
                valid = False

            if valid:
                if discount["kind"] == "percent":
                    discount_amount = int(base_price * discount["value"] / 100)
                else:
                    discount_amount = min(base_price, discount["value"])

                conn.execute(
                    "UPDATE discounts SET used_count = used_count + 1 WHERE id = ?",
                    (discount["id"],)
                )

                if discount["kind"] == "percent" and discount["value"] >= 100:
                    is_paid = 1

    final_price = max(0, base_price - discount_amount)
    tracking_code = generate_tracking_code()

    cursor = conn.execute(
        """
        INSERT INTO requests (
            customer_id, service_id, tracking_code, status,
            customer_note, total_price, paid_price,
            discount_code, discount_amount, form_data, is_paid
        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """,
        (
            customer_id, service_id, tracking_code, "در انتظار بررسی",
            customer_note, final_price, discount_code, discount_amount,
            json.dumps(form_data, ensure_ascii=False), is_paid
        )
    )
    request_id = cursor.lastrowid

    files = request.files.getlist("documents")
    for f in files:
        if f and f.filename:
            filename = secure_filename(f.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                new_name = f"{secrets.token_hex(8)}_{filename}"
                path = os.path.join(DOCUMENTS_FOLDER, new_name)
                f.save(path)
                conn.execute(
                    """
                    INSERT INTO documents (request_id, customer_id, file_path, original_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (request_id, customer_id, new_name, filename)
                )

    conn.execute(
        """
        INSERT INTO messages (customer_id, request_id, sender, message)
        VALUES (?, ?, 'system', ?)
        """,
        (customer_id, request_id, "درخواست شما با موفقیت ثبت شد.")
    )

    create_notification("admin", None, request_id, "درخواست جدید", f"کد پیگیری: {tracking_code}")

    conn.commit()

    flash(f"درخواست شما ثبت شد. کد پیگیری: {tracking_code}", "success")
    return redirect(url_for("tracking", code=tracking_code))

@app.route("/tracking", methods=["GET", "POST"])
def tracking():
    result = None
    code = request.args.get("code") or request.form.get("tracking_code", "").strip()

    if code:
        conn = get_db()
        result = conn.execute(
            """
            SELECT r.*, c.name AS customer_name, c.phone AS customer_phone,
                   s.name AS service_name
            FROM requests r
            LEFT JOIN customers c ON c.id = r.customer_id
            LEFT JOIN services s ON s.id = r.service_id
            WHERE r.tracking_code = ?
            """,
            (code,)
        ).fetchone()

        if not result:
            flash("کد پیگیری پیدا نشد.", "error")

    return render_template("tracking.html", result=result, settings=get_settings())

@app.route("/customer/request/<tracking_code>", methods=["GET", "POST"])
def customer_request(tracking_code):
    conn = get_db()
    req = conn.execute(
        """
        SELECT r.*, c.name AS customer_name, c.phone AS customer_phone,
               s.name AS service_name
        FROM requests r
        LEFT JOIN customers c ON c.id = r.customer_id
        LEFT JOIN services s ON s.id = r.service_id
        WHERE r.tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()

    if not req:
        abort(404)

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        file = request.files.get("file")

        file_path = ""
        original_name = ""

        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                new_name = f"{secrets.token_hex(8)}_{filename}"
                path = os.path.join(CHAT_FOLDER, new_name)
                file.save(path)
                file_path = new_name
                original_name = filename

        if message or file_path:
            conn.execute(
                """
                INSERT INTO messages (customer_id, request_id, sender, message, file_path, original_name)
                VALUES (?, ?, 'customer', ?, ?, ?)
                """,
                (req["customer_id"], req["id"], message or "فایل ارسال شد", file_path, original_name)
            )
            conn.commit()
            flash("پیام شما ارسال شد.", "success")

        return redirect(url_for("customer_request", tracking_code=tracking_code))

    messages = conn.execute(
        "SELECT * FROM messages WHERE request_id = ? ORDER BY id ASC",
        (req["id"],)
    ).fetchall()

    documents = conn.execute(
        "SELECT * FROM documents WHERE request_id = ?",
        (req["id"],)
    ).fetchall()

    # اگر chat.html وجود نداشت از tracking استفاده می‌کنیم
    try:
        return render_template(
            "chat.html",
            request_row=req,
            messages=messages,
            documents=documents,
            settings=get_settings()
        )
    except Exception:
        return render_template(
            "tracking.html",
            result=req,
            settings=get_settings()
        )

# =========================================================
# ورود مدیریت
# =========================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if get_current_user():
        return redirect(url_for("admin"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1",
            (username,)
        ).fetchone()

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
# پنل مدیریت
# =========================================================

@app.route("/admin")
@login_required
def admin():
    conn = get_db()
    user = get_current_user()

    if user["role"] == "expert":
        requests_rows = conn.execute(
            """
            SELECT r.*, c.name AS customer_name, c.phone AS customer_phone,
                   s.name AS service_name
            FROM requests r
            LEFT JOIN customers c ON c.id = r.customer_id
            LEFT JOIN services s ON s.id = r.service_id
            WHERE (r.expert_id = ? OR r.expert_id IS NULL)
              AND (r.is_paid = 1 OR r.total_price = 0)
            ORDER BY r.id DESC
            """,
            (user["id"],)
        ).fetchall()
    else:
        requests_rows = conn.execute(
            """
            SELECT r.*, c.name AS customer_name, c.phone AS customer_phone,
                   s.name AS service_name
            FROM requests r
            LEFT JOIN customers c ON c.id = r.customer_id
            LEFT JOIN services s ON s.id = r.service_id
            ORDER BY r.id DESC
            """
        ).fetchall()

    customers = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    services = conn.execute("SELECT * FROM services ORDER BY sort_order ASC, id DESC").fetchall()
    discounts = conn.execute("SELECT * FROM discounts ORDER BY id DESC").fetchall()
    users = conn.execute(
        "SELECT id, username, role, active, created_at FROM users ORDER BY id DESC"
    ).fetchall()

    total_income = conn.execute(
        "SELECT COALESCE(SUM(paid_price), 0) FROM requests"
    ).fetchone()[0]

    total_debt = conn.execute(
        """
        SELECT COALESCE(SUM(
            CASE WHEN total_price > paid_price THEN total_price - paid_price ELSE 0 END
        ), 0) FROM requests
        """
    ).fetchone()[0]

    return render_template(
        "admin.html",
        requests=requests_rows,
        customers=customers,
        services=services,
        discounts=discounts,
        users=users,
        total_income=total_income,
        total_debt=total_debt,
        settings=get_settings(),
        current_user=user,
    )

@app.route("/admin/settings/save", methods=["POST"])
@login_required
def admin_settings_save():
    set_setting("site_name", request.form.get("site_name", SITE_NAME).strip())
    set_setting("manager", request.form.get("manager", MANAGER).strip())
    set_setting("phone", request.form.get("phone", "").strip())
    set_setting("manager_text", request.form.get("manager_text", "").strip())
    set_setting("home_text", request.form.get("home_text", "").strip())
    set_setting("footer_text", request.form.get("footer_text", "").strip())

    logo = request.files.get("logo")
    if logo and logo.filename:
        filename = secure_filename(logo.filename)
        if filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            filename = secrets.token_hex(8) + "_" + filename
            logo.save(os.path.join(UPLOAD_FOLDER, filename))
            set_setting("logo", filename)

    flash("تنظیمات سایت ذخیره شد.", "success")
    return redirect(url_for("admin"))

@app.route("/uploads/logo/<path:filename>")
def uploaded_logo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/admin/request/<int:rid>", methods=["GET", "POST"])
@login_required
def admin_request(rid):
    conn = get_db()
    user = get_current_user()

    row = conn.execute(
        """
        SELECT r.*, c.name AS customer_name, c.phone AS customer_phone,
               c.national_id AS customer_national_id, s.name AS service_name
        FROM requests r
        LEFT JOIN customers c ON c.id = r.customer_id
        LEFT JOIN services s ON s.id = r.service_id
        WHERE r.id = ?
        """,
        (rid,)
    ).fetchone()

    if not row:
        abort(404)

    # اگر کارشناس است و پرونده به کس دیگری اختصاص داده شده، دسترسی ندهد
    if user["role"] == "expert" and row["expert_id"] and row["expert_id"] != user["id"]:
        flash("این پرونده به کارشناس دیگری اختصاص داده شده است.", "error")
        return redirect(url_for("admin"))

    if request.method == "POST":
        status = request.form.get("status", row["status"]).strip()
        estimated_time = request.form.get("estimated_time", "").strip()
        admin_note = request.form.get("admin_note", "").strip()
        total_price = to_int(request.form.get("total_price", row["total_price"]))
        paid_price = to_int(request.form.get("paid_price", row["paid_price"]))
        expert_id = request.form.get("expert_id") or None

        if expert_id:
            expert_id = to_int(expert_id)

        # اگر کارشناس پذیرش می‌کند
        if user["role"] == "expert" and not row["expert_id"] and status == "پذیرش شد":
            expert_id = user["id"]

        paid_price = max(0, min(paid_price, total_price))

        conn.execute(
            """
            UPDATE requests SET
                status = ?, estimated_time = ?, admin_note = ?,
                total_price = ?, paid_price = ?, expert_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, estimated_time, admin_note, total_price, paid_price, expert_id, rid)
        )
        conn.commit()

        create_notification("customer", row["customer_id"], rid, "تغییر وضعیت پرونده", f"وضعیت جدید: {status}")

        flash("پرونده به‌روزرسانی شد.", "success")
        return redirect(url_for("admin_request", rid=rid))

    messages = conn.execute(
        "SELECT * FROM messages WHERE request_id = ? ORDER BY id ASC",
        (rid,)
    ).fetchall()

    documents = conn.execute(
        "SELECT * FROM documents WHERE request_id = ?",
        (rid,)
    ).fetchall()

    experts = conn.execute(
        "SELECT id, username FROM users WHERE role = 'expert' AND active = 1"
    ).fetchall()

    return render_template(
        "admin_request.html",
        req=row,
        messages=messages,
        documents=documents,
        experts=experts,
        settings=get_settings(),
    )

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

    row = conn.execute("SELECT * FROM requests WHERE id = ?", (rid,)).fetchone()
    if not row:
        abort(404)

    expert_id = row["expert_id"]
    if user["role"] == "expert" and not expert_id and status == "پذیرش شد":
        expert_id = user["id"]

    conn.execute(
        "UPDATE requests SET status = ?, expert_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, expert_id, rid)
    )
    conn.commit()

    create_notification("customer", row["customer_id"], rid, "تغییر وضعیت", f"وضعیت جدید: {status}")

    flash("وضعیت پرونده تغییر کرد.", "success")
    return redirect(url_for("admin_request", rid=rid))

@app.route("/admin/request/update", methods=["POST"])
@login_required
def admin_request_update():
    rid = to_int(request.form.get("id"))
    conn = get_db()

    total_price = to_int(request.form.get("total_price"))
    paid_price = to_int(request.form.get("paid_price"))
    estimated_time = request.form.get("estimated_time", "").strip()
    admin_note = request.form.get("admin_note", "").strip()
    expert_id = request.form.get("expert_id") or None

    if expert_id:
        expert_id = to_int(expert_id)

    paid_price = max(0, min(paid_price, total_price))

    conn.execute(
        """
        UPDATE requests SET
            total_price = ?, paid_price = ?, estimated_time = ?,
            admin_note = ?, expert_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (total_price, paid_price, estimated_time, admin_note, expert_id, rid)
    )
    conn.commit()

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
    row = conn.execute("SELECT customer_id FROM requests WHERE id = ?", (rid,)).fetchone()

    if row:
        conn.execute(
            """
            INSERT INTO messages (customer_id, request_id, sender, message)
            VALUES (?, ?, 'admin', ?)
            """,
            (row["customer_id"], rid, message)
        )
        conn.commit()

    flash("پیام ارسال شد.", "success")
    return redirect(url_for("admin_request", rid=rid))

@app.route("/admin/service/save", methods=["POST"])
@login_required
def admin_service_save():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    price = to_int(request.form.get("price"))
    sort_order = to_int(request.form.get("sort_order"))
    active = 1 if request.form.get("active", "1") == "1" else 0
    fields_json = request.form.get("fields_json", "[]")
    documents_json = request.form.get("documents_json", "[]")

    try:
        json.loads(fields_json)
    except Exception:
        fields_json = "[]"

    try:
        json.loads(documents_json)
    except Exception:
        documents_json = "[]"

    if not name:
        flash("نام خدمت الزامی است.", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO services (name, category, description, price, sort_order, active, fields_json, documents_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (name, category, description, price, sort_order, active, fields_json, documents_json)
    )
    conn.commit()

    flash("خدمت جدید اضافه شد.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/service/<int:service_id>/toggle", methods=["POST"])
@login_required
def toggle_service(service_id):
    conn = get_db()
    conn.execute(
        "UPDATE services SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?",
        (service_id,)
    )
    conn.commit()
    return redirect(url_for("admin"))

@app.route("/admin/service/<int:service_id>/delete", methods=["POST"])
@login_required
def delete_service(service_id):
    conn = get_db()
    conn.execute("DELETE FROM services WHERE id = ?", (service_id,))
    conn.commit()
    flash("خدمت حذف شد.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/user/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "expert")

    if role not in ("admin", "expert"):
        role = "expert"

    if not username or len(password) < 6:
        flash("نام کاربری و رمز عبور معتبر وارد کنید.", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    exists = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if exists:
        flash("این نام کاربری قبلاً ثبت شده است.", "error")
        return redirect(url_for("admin"))

    conn.execute(
        "INSERT INTO users (username, password, role, active) VALUES (?, ?, ?, 1)",
        (username, generate_password_hash(password), role)
    )
    conn.commit()

    flash("کاربر جدید ایجاد شد.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/user/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    if user_id == session.get("user_id"):
        flash("نمی‌توانید حساب خودتان را غیرفعال کنید.", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    conn.execute(
        "UPDATE users SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?",
        (user_id,)
    )
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
    conn.execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (generate_password_hash(password), session["user_id"])
    )
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
    max_uses = to_int(request.form.get("max_uses", 0))
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()

    if kind not in ("percent", "fixed"):
        kind = "percent"

    if not code or value < 0:
        flash("اطلاعات کد تخفیف صحیح نیست.", "error")
        return redirect(url_for("admin"))

    if kind == "percent" and value > 100:
        flash("درصد تخفیف نمی‌تواند بیشتر از ۱۰۰ باشد.", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    exists = conn.execute("SELECT id FROM discounts WHERE code = ?", (code,)).fetchone()
    if exists:
        flash("این کد تخفیف قبلاً وجود دارد.", "error")
        return redirect(url_for("admin"))

    conn.execute(
        """
        INSERT INTO discounts (code, kind, value, max_uses, start_date, end_date, active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (code, kind, value, max_uses, start_date, end_date)
    )
    conn.commit()

    flash("کد تخفیف ایجاد شد.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/discount/<int:discount_id>/toggle", methods=["POST"])
@login_required
def toggle_discount(discount_id):
    conn = get_db()
    conn.execute(
        "UPDATE discounts SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?",
        (discount_id,)
    )
    conn.commit()
    return redirect(url_for("admin"))

@app.route("/admin/discount/<int:discount_id>/delete", methods=["POST"])
@login_required
def delete_discount(discount_id):
    conn = get_db()
    conn.execute("DELETE FROM discounts WHERE id = ?", (discount_id,))
    conn.commit()
    return redirect(url_for("admin"))

@app.route("/download/document/<int:document_id>")
@login_required
def download_document(document_id):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not doc:
        abort(404)
    return send_from_directory(DOCUMENTS_FOLDER, doc["file_path"], as_attachment=True, download_name=doc["original_name"])

@app.route("/download/chat/<path:filename>")
@login_required
def download_chat_file(filename):
    return send_from_directory(CHAT_FOLDER, filename, as_attachment=True)

# =========================================================
# خطاها
# =========================================================

@app.errorhandler(404)
def not_found(error):
    return render_template("base.html", content="صفحه مورد نظر پیدا نشد."), 404

@app.errorhandler(413)
def too_large(error):
    flash("حجم فایل بیش از حد مجاز است.", "error")
    return redirect(request.referrer or url_for("home"))

@app.errorhandler(500)
def internal_error(error):
    return "خطای داخلی سرور. لطفاً لاگ را بررسی کنید.", 500

# =========================================================
# شروع
# =========================================================

with app.app_context():
    create_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
