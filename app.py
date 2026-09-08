import os
import json
import sqlite3
import secrets
import shutil
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
    abort,
    jsonify,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# =========================================================
# تنظیمات
# =========================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "novin.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "novin-secret-key-change-this-immediately")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

SITE_NAME = "کافی نت آنلاین نوین"
MANAGER = "احمد محمدی مهر"
PHONE = ""

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "123456")


# =========================================================
# دیتابیس
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def add_column_if_missing(conn, table, column, definition):
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_tables():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT DEFAULT ''
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'expert',
            active INTEGER NOT NULL DEFAULT 1,
            allowed_services TEXT DEFAULT '[]',
            allowed_sections TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            national_id TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT '',
            description TEXT DEFAULT '',
            price INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            payment_mode TEXT DEFAULT 'gateway',
            fields_json TEXT DEFAULT '[]',
            documents_json TEXT DEFAULT '[]',
            form_code TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
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
            payment_mode TEXT DEFAULT 'gateway',
            payment_status TEXT DEFAULT 'pending',
            form_data TEXT DEFAULT '{}',
            documents TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            accepted_at TEXT DEFAULT '',
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE SET NULL,
            FOREIGN KEY(expert_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            request_id INTEGER,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
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
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            customer_id INTEGER,
            title TEXT,
            body TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # سازگاری با نسخه‌های قبلی
    add_column_if_missing(conn, "customers", "national_id", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "admin_note", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "estimated_time", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "discount_code", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "discount_amount", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "requests", "expert_id", "INTEGER")
    add_column_if_missing(conn, "requests", "payment_mode", "TEXT DEFAULT 'gateway'")
    add_column_if_missing(conn, "requests", "payment_status", "TEXT DEFAULT 'pending'")
    add_column_if_missing(conn, "requests", "accepted_at", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "services", "payment_mode", "TEXT DEFAULT 'gateway'")
    add_column_if_missing(conn, "services", "form_code", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "users", "allowed_services", "TEXT DEFAULT '[]'")
    add_column_if_missing(conn, "users", "allowed_sections", "TEXT DEFAULT '[]'")
    add_column_if_missing(conn, "messages", "is_read", "INTEGER DEFAULT 0")

    # تنظیمات پیش‌فرض
    defaults = {
        "site_name": SITE_NAME,
        "manager": MANAGER,
        "phone": PHONE,
        "manager_text": "ارائه کلیه خدمات کافی‌نت به صورت غیرحضوری",
        "home_text": "تمام خدمات کافی‌نت آنلاین نوین را به صورت غیرحضوری دریافت کنید.",
        "footer_text": "کافی نت آنلاین نوین - با مدیریت احمد محمدی مهر",
        "logo": "",
        "default_payment_mode": "gateway",
        "sms_enabled": "0",
        "notification_sound": "1",
    }

    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            (key, value)
        )

    # ساخت مدیر اصلی
    admin = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users(username, password, role, active, allowed_sections) VALUES (?, ?, 'admin', 1, ?)",
            ("admin", generate_password_hash(ADMIN_PASSWORD), json.dumps(["all"]))
        )

    conn.commit()
    conn.close()


# =========================================================
# ابزارها
# =========================================================

def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
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
    conn.close()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, role, active, allowed_services, allowed_sections FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    if not user or not user["active"]:
        return None
    return user


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("admin_login"))
        if user["role"] != "admin":
            flash("دسترسی فقط برای مدیر امکان‌پذیر است.", "error")
            return redirect(url_for("admin"))
        return func(*args, **kwargs)
    return wrapper


def generate_tracking_code():
    """کد پیگیری ۴ رقمی عددی"""
    while True:
        code = str(secrets.randbelow(9000) + 1000)
        conn = get_db()
        exists = conn.execute("SELECT id FROM requests WHERE tracking_code = ?", (code,)).fetchone()
        conn.close()
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


def safe_json(value, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(value)
    except Exception:
        return default


def create_notification(user_id=None, customer_id=None, title="", body=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO notifications (user_id, customer_id, title, body) VALUES (?, ?, ?, ?)",
        (user_id, customer_id, title, body)
    )
    conn.commit()
    conn.close()


def send_status_message(request_row, new_status, estimated_time=""):
    """آماده‌سازی پیام وضعیت برای ارسال بعدی به پیامک"""
    tracking = request_row["tracking_code"]
    msg = f"وضعیت پرونده شما: {new_status}\nکد پیگیری: {tracking}"
    if estimated_time:
        msg += f"\nمدت زمان تقریبی: {estimated_time}"
    return msg


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
# صفحه اصلی و خدمات
# =========================================================

@app.route("/")
def index():
    conn = get_db()
    services = conn.execute(
        "SELECT * FROM services WHERE active = 1 ORDER BY sort_order ASC, id DESC"
    ).fetchall()
    conn.close()
    return render_template("index.html", services=services, settings=get_settings())


@app.route("/service/<int:service_id>", methods=["GET", "POST"])
def service(service_id):
    conn = get_db()
    service_row = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    conn.close()

    if not service_row:
        abort(404)

    fields = parse_json_list(service_row["fields_json"])
    documents = parse_json_list(service_row["documents_json"])
    payment_mode = service_row["payment_mode"] or get_settings().get("default_payment_mode", "gateway")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        national_id = request.form.get("national_id", "").strip()
        customer_note = request.form.get("customer_note", "").strip()
        discount_code = request.form.get("discount_code", "").strip().upper()

        if not name or not phone:
            flash("نام و شماره موبایل الزامی است.", "error")
            return redirect(url_for("service", service_id=service_id))

        conn = get_db()

        # مشتری
        customer = conn.execute(
            "SELECT * FROM customers WHERE phone = ? ORDER BY id DESC LIMIT 1", (phone,)
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

        # داده‌های فرم
        form_data = {}
        for key in request.form.keys():
            if key not in ("name", "phone", "national_id", "customer_note", "discount_code"):
                form_data[key] = request.form.get(key)

        base_price = to_int(service_row["price"])
        discount_amount = 0

        if discount_code:
            discount = conn.execute(
                "SELECT * FROM discounts WHERE code = ? AND active = 1", (discount_code,)
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

        final_price = max(0, base_price - discount_amount)
        tracking_code = generate_tracking_code()

        # وضعیت اولیه بر اساس حالت پرداخت
        if payment_mode == "gateway" and final_price > 0 and discount_amount < base_price:
            status = "در انتظار پرداخت"
            payment_status = "pending"
        else:
            status = "در انتظار بررسی"
            payment_status = "paid" if final_price == 0 else "pending"

        cursor = conn.execute(
            """
            INSERT INTO requests
            (customer_id, service_id, tracking_code, status, customer_note,
             total_price, paid_price, discount_code, discount_amount,
             payment_mode, payment_status, form_data, documents)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id, service_id, tracking_code, status, customer_note,
                final_price, discount_code, discount_amount,
                payment_mode, payment_status,
                json.dumps(form_data, ensure_ascii=False),
                json.dumps([], ensure_ascii=False)
            )
        )
        request_id = cursor.lastrowid

        # پیام سیستم
        conn.execute(
            "INSERT INTO messages (customer_id, request_id, sender, message) VALUES (?, ?, 'system', ?)",
            (customer_id, request_id, f"درخواست شما با کد پیگیری {tracking_code} ثبت شد.")
        )

        conn.commit()
        conn.close()

        # اعلان
        create_notification(customer_id=customer_id, title="ثبت درخواست", body=f"کد پیگیری: {tracking_code}")

        return render_template(
            "tracking.html",
            result={
                "tracking_code": tracking_code,
                "status": status,
                "total_price": final_price,
                "estimated_time": "",
                "customer_name": name,
                "service_name": service_row["name"],
                "admin_note": "",
            },
            created=True,
            settings=get_settings(),
        )

    return render_template(
        "service.html",
        service=service_row,
        fields=fields,
        documents=documents,
        payment_mode=payment_mode,
        settings=get_settings(),
    )


# =========================================================
# پیگیری
# =========================================================

@app.route("/tracking", methods=["GET", "POST"])
def tracking():
    result = None
    if request.method == "POST":
        tracking_code = request.form.get("tracking_code", "").strip()
        conn = get_db()
        result = conn.execute(
            """
            SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
            FROM requests r
            LEFT JOIN customers c ON c.id = r.customer_id
            LEFT JOIN services s ON s.id = r.service_id
            WHERE r.tracking_code = ?
            """,
            (tracking_code,)
        ).fetchone()
        conn.close()
        if not result:
            flash("کد پیگیری پیدا نشد.", "error")

    return render_template("tracking.html", result=result, settings=get_settings())


# =========================================================
# پنل مدیریت
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
            "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
        ).fetchone()
        conn.close()

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
    user = get_current_user()
    conn = get_db()

    # فیلتر درخواست‌ها بر اساس دسترسی کارشناس
    if user["role"] == "admin":
        requests_rows = conn.execute(
            """
            SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
            FROM requests r
            LEFT JOIN customers c ON c.id = r.customer_id
            LEFT JOIN services s ON s.id = r.service_id
            ORDER BY r.id DESC
            """
        ).fetchall()
    else:
        allowed = parse_json_list(user["allowed_services"])
        if allowed:
            placeholders = ",".join("?" * len(allowed))
            requests_rows = conn.execute(
                f"""
                SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
                FROM requests r
                LEFT JOIN customers c ON c.id = r.customer_id
                LEFT JOIN services s ON s.id = r.service_id
                WHERE r.service_id IN ({placeholders})
                  AND (r.expert_id IS NULL OR r.expert_id = ?)
                ORDER BY r.id DESC
                """,
                (*allowed, user["id"])
            ).fetchall()
        else:
            requests_rows = []

    customers = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    services = conn.execute("SELECT * FROM services ORDER BY sort_order ASC, id DESC").fetchall()
    discounts = conn.execute("SELECT * FROM discounts ORDER BY id DESC").fetchall()
    users = conn.execute(
        "SELECT id, username, role, active, allowed_services, allowed_sections, created_at FROM users ORDER BY id DESC"
    ).fetchall()

    total_income = conn.execute("SELECT COALESCE(SUM(paid_price), 0) FROM requests").fetchone()[0]
    total_debt = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN total_price > paid_price THEN total_price - paid_price ELSE 0 END), 0)
        FROM requests
        """
    ).fetchone()[0]

    conn.close()

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


# =========================================================
# مدیریت خدمت (افزودن + ویرایش)
# =========================================================

@app.route("/admin/service/save", methods=["POST"])
@login_required
def admin_service_save():
    service_id = request.form.get("service_id")
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    price = to_int(request.form.get("price"))
    sort_order = to_int(request.form.get("sort_order"))
    active = 1 if request.form.get("active", "1") == "1" else 0
    payment_mode = request.form.get("payment_mode", "gateway")
    fields_json = request.form.get("fields_json", "[]")
    documents_json = request.form.get("documents_json", "[]")
    form_code = request.form.get("form_code", "")

    if not name:
        flash("نام خدمت الزامی است.", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    if service_id:
        conn.execute(
            """
            UPDATE services SET
                name=?, category=?, description=?, price=?, sort_order=?,
                active=?, payment_mode=?, fields_json=?, documents_json=?, form_code=?
            WHERE id=?
            """,
            (name, category, description, price, sort_order, active,
             payment_mode, fields_json, documents_json, form_code, service_id)
        )
        flash("خدمت با موفقیت ویرایش شد.", "success")
    else:
        conn.execute(
            """
            INSERT INTO services
            (name, category, description, price, sort_order, active, payment_mode, fields_json, documents_json, form_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, category, description, price, sort_order, active,
             payment_mode, fields_json, documents_json, form_code)
        )
        flash("خدمت جدید اضافه شد.", "success")

    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/service/<int:service_id>/toggle", methods=["POST"])
@login_required
def toggle_service(service_id):
    conn = get_db()
    conn.execute("UPDATE services SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (service_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/service/<int:service_id>/delete", methods=["POST"])
@login_required
def delete_service(service_id):
    conn = get_db()
    conn.execute("DELETE FROM services WHERE id=?", (service_id,))
    conn.commit()
    conn.close()
    flash("خدمت حذف شد.", "success")
    return redirect(url_for("admin"))


# =========================================================
# مدیریت درخواست و وضعیت
# =========================================================

@app.route("/admin/request/<int:rid>", methods=["GET", "POST"])
@login_required
def admin_request(rid):
    conn = get_db()
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
        conn.close()
        abort(404)

    current = get_current_user()

    # قفل پرونده: اگر کارشناس دیگری پذیرفته باشد
    if current["role"] != "admin" and row["expert_id"] and row["expert_id"] != current["id"]:
        flash("این پرونده توسط کارشناس دیگری پذیرش شده است.", "error")
        conn.close()
        return redirect(url_for("admin"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "status":
            new_status = request.form.get("status", row["status"]).strip()
            estimated_time = request.form.get("estimated_time", "").strip()
            admin_note = request.form.get("admin_note", "").strip()

            # پذیرش توسط کارشناس
            expert_id = row["expert_id"]
            accepted_at = row["accepted_at"]
            if new_status == "پذیرش شد" and not expert_id:
                expert_id = current["id"]
                accepted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn.execute(
                """
                UPDATE requests SET
                    status=?, estimated_time=?, admin_note=?,
                    expert_id=?, accepted_at=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (new_status, estimated_time, admin_note, expert_id, accepted_at, rid)
            )
            conn.commit()

            # پیام وضعیت
            msg = send_status_message(row, new_status, estimated_time)
            conn.execute(
                "INSERT INTO messages (customer_id, request_id, sender, message) VALUES (?, ?, 'admin', ?)",
                (row["customer_id"], rid, msg)
            )
            conn.commit()

            create_notification(
                customer_id=row["customer_id"],
                title="تغییر وضعیت پرونده",
                body=f"وضعیت جدید: {new_status} | کد: {row['tracking_code']}"
            )

            flash("وضعیت پرونده به‌روزرسانی شد.", "success")

        elif action == "message":
            message = request.form.get("message", "").strip()
            if message:
                conn.execute(
                    "INSERT INTO messages (customer_id, request_id, sender, message) VALUES (?, ?, 'admin', ?)",
                    (row["customer_id"], rid, message)
                )
                conn.commit()
                create_notification(customer_id=row["customer_id"], title="پیام جدید", body=message[:50])
                flash("پیام ارسال شد.", "success")

        return redirect(url_for("admin_request", rid=rid))

    messages = conn.execute(
        "SELECT * FROM messages WHERE request_id = ? ORDER BY id ASC", (rid,)
    ).fetchall()

    experts = conn.execute(
        "SELECT id, username FROM users WHERE role IN ('admin','expert') AND active=1"
    ).fetchall()

    conn.close()

    return render_template(
        "admin_request.html",
        req=row,
        messages=messages,
        experts=experts,
        settings=get_settings(),
    )


# =========================================================
# کاربران و دسترسی‌ها
# =========================================================

@app.route("/admin/user/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "expert")
    allowed_services = request.form.getlist("allowed_services")
    allowed_sections = request.form.getlist("allowed_sections")

    if not username or len(password) < 6:
        flash("نام کاربری و رمز عبور معتبر وارد کنید.", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    exists = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if exists:
        conn.close()
        flash("این نام کاربری قبلاً ثبت شده است.", "error")
        return redirect(url_for("admin"))

    conn.execute(
        """
        INSERT INTO users (username, password, role, active, allowed_services, allowed_sections)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        (
            username,
            generate_password_hash(password),
            role,
            json.dumps([int(x) for x in allowed_services]),
            json.dumps(allowed_sections),
        )
    )
    conn.commit()
    conn.close()
    flash("کاربر جدید ایجاد شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    if user_id == session.get("user_id"):
        flash("نمی‌توانید حساب خودتان را غیرفعال کنید.", "error")
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("UPDATE users SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
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
    conn.close()
    flash("رمز عبور با موفقیت تغییر کرد.", "success")
    return redirect(url_for("admin"))


# =========================================================
# تنظیمات + پشتیبان‌گیری
# =========================================================

@app.route("/admin/settings/save", methods=["POST"])
@login_required
def admin_settings_save():
    for key in ["site_name", "manager", "phone", "manager_text", "home_text", "footer_text", "default_payment_mode"]:
        value = request.form.get(key, "").strip()
        set_setting(key, value)

    logo = request.files.get("logo")
    if logo and logo.filename:
        filename = secure_filename(logo.filename)
        if filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            filename = secrets.token_hex(8) + "_" + filename
            logo.save(os.path.join(UPLOAD_FOLDER, filename))
            set_setting("logo", filename)

    flash("تنظیمات ذخیره شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/backup", methods=["POST"])
@admin_required
def create_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_FOLDER, f"novin_backup_{timestamp}.db")
    shutil.copy2(DATABASE, backup_path)
    flash(f"پشتیبان‌گیری با موفقیت انجام شد: {os.path.basename(backup_path)}", "success")
    return redirect(url_for("admin"))


@app.route("/admin/restore", methods=["POST"])
@admin_required
def restore_backup():
    file = request.files.get("backup_file")
    if not file or not file.filename.endswith(".db"):
        flash("فایل پشتیبان معتبر نیست.", "error")
        return redirect(url_for("admin"))

    temp_path = os.path.join(BACKUP_FOLDER, "temp_restore.db")
    file.save(temp_path)
    shutil.copy2(temp_path, DATABASE)
    os.remove(temp_path)
    flash("بازیابی اطلاعات با موفقیت انجام شد.", "success")
    return redirect(url_for("admin"))


@app.route("/uploads/logo/<path:filename>")
def uploaded_logo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# =========================================================
# کد تخفیف
# =========================================================

@app.route("/admin/discount/create", methods=["POST"])
@login_required
def create_discount():
    code = request.form.get("code", "").strip().upper()
    kind = request.form.get("kind", "percent")
    value = to_int(request.form.get("value"))
    max_uses = to_int(request.form.get("max_uses", 0))
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()

    if not code or value < 0:
        flash("اطلاعات کد تخفیف صحیح نیست.", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    exists = conn.execute("SELECT id FROM discounts WHERE code = ?", (code,)).fetchone()
    if exists:
        conn.close()
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
    conn.close()
    flash("کد تخفیف ایجاد شد.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/discount/<int:discount_id>/toggle", methods=["POST"])
@login_required
def toggle_discount(discount_id):
    conn = get_db()
    conn.execute("UPDATE discounts SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (discount_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/discount/<int:discount_id>/delete", methods=["POST"])
@login_required
def delete_discount(discount_id):
    conn = get_db()
    conn.execute("DELETE FROM discounts WHERE id=?", (discount_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


# =========================================================
# خطاها و شروع
# =========================================================

@app.errorhandler(404)
def not_found(error):
    return render_template("base.html", content="صفحه مورد نظر پیدا نشد."), 404


@app.errorhandler(413)
def too_large(error):
    flash("حجم فایل بیش از حد مجاز است.", "error")
    return redirect(request.referrer or url_for("index"))


@app.errorhandler(500)
def internal_error(error):
    app.logger.exception("Internal server error")
    return "خطای داخلی سرور.", 500


create_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
