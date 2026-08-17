import os
import json
import sqlite3
import secrets
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
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# =========================================================
# تنظیمات
# =========================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "novin.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "novin-secret-key-change-this"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

SITE_NAME = "کافی نت آنلاین نوین"
MANAGER = "احمد محمدی مهر"
PHONE = ""

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "123456"
)


# =========================================================
# دیتابیس
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def column_exists(conn, table, column):
    rows = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(row["name"] == column for row in rows)


def add_column_if_missing(conn, table, column, definition):
    if not column_exists(conn, table, column):
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


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
            fields_json TEXT DEFAULT '[]',
            documents_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            service_id INTEGER,
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
            documents TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE SET NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            request_id INTEGER,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
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

    # سازگاری با نسخه‌های قبلی
    add_column_if_missing(
        conn, "customers", "national_id", "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn, "requests", "admin_note", "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn, "requests", "estimated_time", "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn, "requests", "discount_code", "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn, "requests", "discount_amount", "INTEGER DEFAULT 0"
    )

    # تنظیمات پیش‌فرض
    defaults = {
        "site_name": SITE_NAME,
        "manager": MANAGER,
        "phone": PHONE,
        "manager_text": "ارائه کلیه خدمات کافی‌نت به صورت غیرحضوری",
        "home_text": "تمام خدمات کافی‌نت آنلاین نوین را به صورت غیرحضوری دریافت کنید.",
        "footer_text": "کافی نت آنلاین نوین - با مدیریت احمد محمدی مهر",
        "logo": "",
    }

    for key, value in defaults.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )

    # ساخت مدیر اصلی در اولین اجرا
    admin = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        ("admin",)
    ).fetchone()

    if not admin:
        conn.execute(
            """
            INSERT INTO users(username, password, role, active)
            VALUES (?, ?, 'admin', 1)
            """,
            (
                "admin",
                generate_password_hash(ADMIN_PASSWORD),
            )
        )

    conn.commit()
    conn.close()


# =========================================================
# تنظیمات
# =========================================================

def get_settings():
    conn = get_db()

    rows = conn.execute(
        "SELECT key, value FROM settings"
    ).fetchall()

    conn.close()

    return {
        row["key"]: row["value"]
        for row in rows
    }


def set_setting(key, value):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (key, value)
    )

    conn.commit()
    conn.close()


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
# کاربران
# =========================================================

def get_current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute(
        """
        SELECT id, username, role, active
        FROM users
        WHERE id = ?
        """,
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


# =========================================================
# ابزارها
# =========================================================

def generate_tracking_code():
    while True:
        code = (
            datetime.now().strftime("%y%m%d")
            + "-"
            + secrets.token_hex(3).upper()
        )

        conn = get_db()

        exists = conn.execute(
            """
            SELECT id
            FROM requests
            WHERE tracking_code = ?
            """,
            (code,)
        ).fetchone()

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

        if isinstance(result, list):
            return result

        return []

    except Exception:
        return []


def safe_json(value, default=None):
    if default is None:
        default = {}

    try:
        return json.loads(value)
    except Exception:
        return default


# =========================================================
# صفحه اصلی
# =========================================================

@app.route("/")
def index():
    conn = get_db()

    services = conn.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        ORDER BY sort_order ASC, id DESC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "index.html",
        services=services,
        settings=get_settings(),
    )


# =========================================================
# صفحه خدمت
# =========================================================

@app.route("/service/<int:service_id>", methods=["GET", "POST"])
def service(service_id):
    conn = get_db()

    service_row = conn.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        """,
        (service_id,)
    ).fetchone()

    conn.close()

    if not service_row:
        abort(404)

    fields = parse_json_list(
        service_row["fields_json"]
    )

    documents = parse_json_list(
        service_row["documents_json"]
    )

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        national_id = request.form.get(
            "national_id", ""
        ).strip()

        customer_note = request.form.get(
            "customer_note", ""
        ).strip()

        if not name:
            flash("نام را وارد کنید.", "error")
            return redirect(
                url_for(
                    "service",
                    service_id=service_id
                )
            )

        conn = get_db()

        customer = None

        if phone:
            customer = conn.execute(
                """
                SELECT *
                FROM customers
                WHERE phone = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (phone,)
            ).fetchone()

        if customer:
            customer_id = customer["id"]

            conn.execute(
                """
                UPDATE customers
                SET name = ?, national_id = ?
                WHERE id = ?
                """,
                (
                    name,
                    national_id,
                    customer_id,
                )
            )

        else:
            cursor = conn.execute(
                """
                INSERT INTO customers
                (name, phone, national_id)
                VALUES (?, ?, ?)
                """,
                (
                    name,
                    phone,
                    national_id,
                )
            )

            customer_id = cursor.lastrowid

        form_data = {}

        for key in request.form.keys():
            if key not in (
                "name",
                "phone",
                "national_id",
                "customer_note",
                "discount_code",
            ):
                form_data[key] = request.form.get(key)

        discount_code = request.form.get(
            "discount_code",
            ""
        ).strip().upper()

        base_price = to_int(
            service_row["price"]
        )

        discount_amount = 0

        if discount_code:
            discount = conn.execute(
                """
                SELECT *
                FROM discounts
                WHERE code = ?
                  AND active = 1
                """,
                (discount_code,)
            ).fetchone()

            if discount:
                today = datetime.now().strftime("%Y-%m-%d")

                valid_start = (
                    not discount["start_date"]
                    or today >= discount["start_date"]
                )

                valid_end = (
                    not discount["end_date"]
                    or today <= discount["end_date"]
                )

                valid_uses = (
                    discount["max_uses"] <= 0
                    or discount["used_count"]
                    < discount["max_uses"]
                )

                if valid_start and valid_end and valid_uses:
                    if discount["kind"] == "percent":
                        discount_amount = int(
                            base_price
                            * discount["value"]
                            / 100
                        )
                    else:
                        discount_amount = min(
                            base_price,
                            discount["value"]
                        )

                    conn.execute(
                        """
                        UPDATE discounts
                        SET used_count = used_count + 1
                        WHERE id = ?
                        """,
                        (discount["id"],)
                    )

        final_price = max(
            0,
            base_price - discount_amount
        )

        tracking_code = generate_tracking_code()

        cursor = conn.execute(
            """
            INSERT INTO requests
            (
                customer_id,
                service_id,
                tracking_code,
                status,
                customer_note,
                total_price,
                paid_price,
                discount_code,
                discount_amount,
                form_data,
                documents
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                customer_id,
                service_id,
                tracking_code,
                "در انتظار بررسی",
                customer_note,
                final_price,
                discount_code,
                discount_amount,
                json.dumps(
                    form_data,
                    ensure_ascii=False
                ),
                json.dumps(
                    [],
                    ensure_ascii=False
                ),
            )
        )

        request_id = cursor.lastrowid

        conn.execute(
            """
            INSERT INTO messages
            (
                customer_id,
                request_id,
                sender,
                message
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                customer_id,
                request_id,
                "system",
                "درخواست شما با موفقیت ثبت شد.",
            )
        )

        conn.commit()
        conn.close()

        return render_template(
            "tracking.html",
            request_row={
                "tracking_code": tracking_code,
                "status": "در انتظار بررسی",
                "total_price": final_price,
                "paid_price": 0,
            },
            created=True,
            settings=get_settings(),
        )

    return render_template(
        "service.html",
        service=service_row,
        fields=fields,
        documents=documents,
        settings=get_settings(),
    )


# =========================================================
# پیگیری
# =========================================================

@app.route("/tracking", methods=["GET", "POST"])
def tracking():
    request_row = None

    if request.method == "POST":
        tracking_code = request.form.get(
            "tracking_code",
            ""
        ).strip()

        conn = get_db()

        request_row = conn.execute(
            """
            SELECT
                r.*,
                c.name AS customer_name,
                c.phone AS customer_phone,
                s.name AS service_name
            FROM requests r
            LEFT JOIN customers c
                ON c.id = r.customer_id
            LEFT JOIN services s
                ON s.id = r.service_id
            WHERE r.tracking_code = ?
            """,
            (tracking_code,)
        ).fetchone()

        conn.close()

        if not request_row:
            flash(
                "کد پیگیری پیدا نشد.",
                "error"
            )

    return render_template(
        "tracking.html",
        request_row=request_row,
        settings=get_settings(),
    )


# =========================================================
# چت مشتری
# =========================================================

@app.route(
    "/chat/<int:customer_id>",
    methods=["GET", "POST"]
)
def chat(customer_id):
    conn = get_db()

    customer = conn.execute(
        """
        SELECT *
        FROM customers
        WHERE id = ?
        """,
        (customer_id,)
    ).fetchone()

    if not customer:
        conn.close()
        abort(404)

    if request.method == "POST":
        message = request.form.get(
            "message",
            ""
        ).strip()

        request_id = request.form.get(
            "request_id"
        )

        if message:
            conn.execute(
                """
                INSERT INTO messages
                (
                    customer_id,
                    request_id,
                    sender,
                    message
                )
                VALUES (?, ?, 'customer', ?)
                """,
                (
                    customer_id,
                    to_int(request_id, None)
                    if request_id
                    else None,
                    message,
                )
            )

            conn.commit()

    messages = conn.execute(
        """
        SELECT *
        FROM messages
        WHERE customer_id = ?
        ORDER BY id ASC
        """,
        (customer_id,)
    ).fetchall()

    requests = conn.execute(
        """
        SELECT *
        FROM requests
        WHERE customer_id = ?
        ORDER BY id DESC
        """,
        (customer_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "chat.html",
        customer=customer,
        messages=messages,
        requests=requests,
        settings=get_settings(),
    )


# =========================================================
# ورود مدیریت
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():
    if get_current_user():
        return redirect(url_for("admin"))

    if request.method == "POST":
        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
              AND active = 1
            """,
            (username,)
        ).fetchone()

        conn.close()

        valid = False

        if user:
            valid = check_password_hash(
                user["password"],
                password
            )

        if valid:
            session.clear()
            session["user_id"] = user["id"]

            return redirect(
                url_for("admin")
            )

        flash(
            "نام کاربری یا رمز عبور اشتباه است.",
            "error"
        )

    return render_template(
        "admin_login.html",
        settings=get_settings(),
    )


@app.route("/admin/logout")
def admin_logout():
    session.clear()

    return redirect(
        url_for("admin_login")
    )


# =========================================================
# پنل مدیریت
# =========================================================

@app.route("/admin")
@login_required
def admin():
    conn = get_db()

    requests_rows = conn.execute(
        """
        SELECT
            r.*,
            c.name AS customer_name,
            c.phone AS customer_phone,
            s.name AS service_name
        FROM requests r
        LEFT JOIN customers c
            ON c.id = r.customer_id
        LEFT JOIN services s
            ON s.id = r.service_id
        ORDER BY r.id DESC
        """
    ).fetchall()

    customers = conn.execute(
        """
        SELECT *
        FROM customers
        ORDER BY id DESC
        """
    ).fetchall()

    services = conn.execute(
        """
        SELECT *
        FROM services
        ORDER BY sort_order ASC, id DESC
        """
    ).fetchall()

    total_income = conn.execute(
        """
        SELECT COALESCE(SUM(paid_price), 0)
        FROM requests
        """
    ).fetchone()[0]

    total_debt = conn.execute(
        """
        SELECT COALESCE(
            SUM(
                CASE
                    WHEN total_price > paid_price
                    THEN total_price - paid_price
                    ELSE 0
                END
            ),
            0
        )
        FROM requests
        """
    ).fetchone()[0]

    discounts = conn.execute(
        """
        SELECT *
        FROM discounts
        ORDER BY id DESC
        """
    ).fetchall()

    users = conn.execute(
        """
        SELECT id, username, role, active, created_at
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

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
        current_user=get_current_user(),
    )


# =========================================================
# تنظیمات
# =========================================================

# endpoint قدیمی برای سازگاری با admin.html قبلی
@app.route(
    "/admin/settings",
    methods=["GET", "POST"]
)
@login_required
def admin_settings():
    if request.method == "POST":
        return save_admin_settings()

    return redirect(url_for("admin"))


@app.route(
    "/admin/settings/save",
    methods=["POST"]
)
@login_required
def admin_settings_save():
    return save_admin_settings()


def save_admin_settings():
    site_name = request.form.get(
        "site_name",
        SITE_NAME
    ).strip()

    manager = request.form.get(
        "manager",
        MANAGER
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    manager_text = request.form.get(
        "manager_text",
        ""
    ).strip()

    home_text = request.form.get(
        "home_text",
        ""
    ).strip()

    footer_text = request.form.get(
        "footer_text",
        ""
    ).strip()

    set_setting(
        "site_name",
        site_name
    )

    set_setting(
        "manager",
        manager
    )

    set_setting(
        "phone",
        phone
    )

    set_setting(
        "manager_text",
        manager_text
    )

    set_setting(
        "home_text",
        home_text
    )

    set_setting(
        "footer_text",
        footer_text
    )

    logo = request.files.get("logo")

    if logo and logo.filename:
        filename = secure_filename(
            logo.filename
        )

        allowed = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        )

        if not filename.lower().endswith(
            allowed
        ):
            flash(
                "فرمت لوگو مجاز نیست.",
                "error"
            )

            return redirect(
                url_for("admin")
            )

        filename = (
            secrets.token_hex(8)
            + "_"
            + filename
        )

        logo.save(
            os.path.join(
                UPLOAD_FOLDER,
                filename
            )
        )

        set_setting(
            "logo",
            filename
        )

    flash(
        "تنظیمات سایت ذخیره شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


@app.route(
    "/uploads/logo/<path:filename>"
)
def uploaded_logo(filename):
    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# =========================================================
# درخواست مدیریت
# =========================================================

@app.route(
    "/admin/request/<int:rid>",
    methods=["GET", "POST"]
)
@login_required
def admin_request(rid):
    conn = get_db()

    row = conn.execute(
        """
        SELECT
            r.*,
            c.name AS customer_name,
            c.phone AS customer_phone,
            c.national_id AS customer_national_id,
            s.name AS service_name
        FROM requests r
        LEFT JOIN customers c
            ON c.id = r.customer_id
        LEFT JOIN services s
            ON s.id = r.service_id
        WHERE r.id = ?
        """,
        (rid,)
    ).fetchone()

    if not row:
        conn.close()
        abort(404)

    if request.method == "POST":
        status = request.form.get(
            "status",
            row["status"]
        ).strip()

        estimated_time = request.form.get(
            "estimated_time",
            ""
        ).strip()

        customer_note = request.form.get(
            "customer_note",
            ""
        ).strip()

        admin_note = request.form.get(
            "admin_note",
            ""
        ).strip()

        total_price = to_int(
            request.form.get(
                "total_price",
                row["total_price"]
            )
        )

        paid_price = to_int(
            request.form.get(
                "paid_price",
                row["paid_price"]
            )
        )

        paid_price = max(
            0,
            min(paid_price, total_price)
        )

        conn.execute(
            """
            UPDATE requests
            SET
                status = ?,
                estimated_time = ?,
                customer_note = ?,
                admin_note = ?,
                total_price = ?,
                paid_price = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status,
                estimated_time,
                customer_note,
                admin_note,
                total_price,
                paid_price,
                rid,
            )
        )

        conn.commit()

        flash(
            "پرونده درخواست به‌روزرسانی شد.",
            "success"
        )

        return redirect(
            url_for(
                "admin_request",
                rid=rid
            )
        )

    messages = conn.execute(
        """
        SELECT *
        FROM messages
        WHERE request_id = ?
        ORDER BY id ASC
        """,
        (rid,)
    ).fetchall()

    conn.close()

    return render_template(
        "admin_request.html",
        request_row=row,
        messages=messages,
        settings=get_settings(),
    )


# =========================================================
# پاسخ مدیریت به پیام
# =========================================================

@app.route(
    "/admin/request/<int:rid>/message",
    methods=["POST"]
)
@login_required
def admin_request_message(rid):
    message = request.form.get(
        "message",
        ""
    ).strip()

    if not message:
        return redirect(
            url_for(
                "admin_request",
                rid=rid
            )
        )

    conn = get_db()

    row = conn.execute(
        """
        SELECT customer_id
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if row:
        conn.execute(
            """
            INSERT INTO messages
            (
                customer_id,
                request_id,
                sender,
                message
            )
            VALUES (?, ?, 'admin', ?)
            """,
            (
                row["customer_id"],
                rid,
                message,
            )
        )

        conn.commit()

    conn.close()

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# افزودن خدمت
# =========================================================

@app.route(
    "/admin/service/save",
    methods=["POST"]
)
@login_required
def admin_service_save():
    name = request.form.get(
        "name",
        ""
    ).strip()

    category = request.form.get(
        "category",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    price = to_int(
        request.form.get("price")
    )

    sort_order = to_int(
        request.form.get("sort_order")
    )

    active = 1 if request.form.get(
        "active",
        "1"
    ) == "1" else 0

    fields_json = request.form.get(
        "fields_json",
        "[]"
    )

    documents_json = request.form.get(
        "documents_json",
        "[]"
    )

    try:
        fields = json.loads(
            fields_json
        )

        if not isinstance(fields, list):
            fields_json = "[]"

    except Exception:
        fields_json = "[]"

    try:
        documents = json.loads(
            documents_json
        )

        if not isinstance(
            documents,
            list
        ):
            documents_json = "[]"

    except Exception:
        documents_json = "[]"

    if not name:
        flash(
            "نام خدمت الزامی است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    conn = get_db()

    conn.execute(
        """
        INSERT INTO services
        (
            name,
            category,
            description,
            price,
            sort_order,
            active,
            fields_json,
            documents_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            category,
            description,
            price,
            sort_order,
            active,
            fields_json,
            documents_json,
        )
    )

    conn.commit()
    conn.close()

    flash(
        "خدمت جدید اضافه شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# تغییر وضعیت خدمت
# =========================================================

@app.route(
    "/admin/service/<int:service_id>/toggle",
    methods=["POST"]
)
@login_required
def toggle_service(service_id):
    conn = get_db()

    conn.execute(
        """
        UPDATE services
        SET active =
            CASE
                WHEN active = 1 THEN 0
                ELSE 1
            END
        WHERE id = ?
        """,
        (service_id,)
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# حذف خدمت
# =========================================================

@app.route(
    "/admin/service/<int:service_id>/delete",
    methods=["POST"]
)
@login_required
def delete_service(service_id):
    conn = get_db()

    conn.execute(
        """
        DELETE FROM services
        WHERE id = ?
        """,
        (service_id,)
    )

    conn.commit()
    conn.close()

    flash(
        "خدمت حذف شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# ایجاد کاربر
# =========================================================

@app.route(
    "/admin/user/create",
    methods=["POST"]
)
@admin_required
def create_user():
    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    role = request.form.get(
        "role",
        "expert"
    )

    if role not in (
        "admin",
        "expert",
    ):
        role = "expert"

    if not username or len(password) < 6:
        flash(
            "نام کاربری و رمز عبور معتبر وارد کنید.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    conn = get_db()

    exists = conn.execute(
        """
        SELECT id
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    if exists:
        conn.close()

        flash(
            "این نام کاربری قبلاً ثبت شده است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    conn.execute(
        """
        INSERT INTO users
        (
            username,
            password,
            role,
            active
        )
        VALUES (?, ?, ?, 1)
        """,
        (
            username,
            generate_password_hash(
                password
            ),
            role,
        )
    )

    conn.commit()
    conn.close()

    flash(
        "کاربر جدید ایجاد شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# endpoint سازگار با قالب قبلی
@app.route(
    "/admin/create-user",
    methods=["POST"]
)
@admin_required
def create_user_legacy():
    return create_user()


# =========================================================
# فعال / غیرفعال کردن کاربر
# =========================================================

@app.route(
    "/admin/user/<int:user_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_user(user_id):
    if user_id == session.get("user_id"):
        flash(
            "نمی‌توانید حساب خودتان را غیرفعال کنید.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    conn = get_db()

    conn.execute(
        """
        UPDATE users
        SET active =
            CASE
                WHEN active = 1 THEN 0
                ELSE 1
            END
        WHERE id = ?
        """,
        (user_id,)
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# تغییر رمز
# =========================================================

@app.route(
    "/admin/password",
    methods=["POST"]
)
@login_required
def admin_password():
    password = request.form.get(
        "password",
        ""
    )

    if len(password) < 6:
        flash(
            "رمز عبور باید حداقل ۶ کاراکتر باشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    conn = get_db()

    conn.execute(
        """
        UPDATE users
        SET password = ?
        WHERE id = ?
        """,
        (
            generate_password_hash(
                password
            ),
            session["user_id"],
        )
    )

    conn.commit()
    conn.close()

    flash(
        "رمز عبور با موفقیت تغییر کرد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# ایجاد کد تخفیف
# =========================================================

@app.route(
    "/admin/discount/create",
    methods=["POST"]
)
@login_required
def create_discount():
    code = request.form.get(
        "code",
        ""
    ).strip().upper()

    kind = request.form.get(
        "kind",
        "percent"
    )

    value = to_int(
        request.form.get("value")
    )

    max_uses = to_int(
        request.form.get(
            "max_uses",
            0
        )
    )

    start_date = request.form.get(
        "start_date",
        ""
    ).strip()

    end_date = request.form.get(
        "end_date",
        ""
    ).strip()

    if kind not in (
        "percent",
        "fixed",
    ):
        kind = "percent"

    if not code or value < 0:
        flash(
            "اطلاعات کد تخفیف صحیح نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    if kind == "percent" and value > 100:
        flash(
            "درصد تخفیف نمی‌تواند بیشتر از ۱۰۰ باشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    conn = get_db()

    exists = conn.execute(
        """
        SELECT id
        FROM discounts
        WHERE code = ?
        """,
        (code,)
    ).fetchone()

    if exists:
        conn.close()

        flash(
            "این کد تخفیف قبلاً وجود دارد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    conn.execute(
        """
        INSERT INTO discounts
        (
            code,
            kind,
            value,
            max_uses,
            start_date,
            end_date,
            active
        )
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (
            code,
            kind,
            value,
            max_uses,
            start_date,
            end_date,
        )
    )

    conn.commit()
    conn.close()

    flash(
        "کد تخفیف ایجاد شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# فعال / غیرفعال کردن تخفیف
# =========================================================

@app.route(
    "/admin/discount/<int:discount_id>/toggle",
    methods=["POST"]
)
@login_required
def toggle_discount(discount_id):
    conn = get_db()

    conn.execute(
        """
        UPDATE discounts
        SET active =
            CASE
                WHEN active = 1 THEN 0
                ELSE 1
            END
        WHERE id = ?
        """,
        (discount_id,)
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# حذف تخفیف
# =========================================================

@app.route(
    "/admin/discount/<int:discount_id>/delete",
    methods=["POST"]
)
@login_required
def delete_discount(discount_id):
    conn = get_db()

    conn.execute(
        """
        DELETE FROM discounts
        WHERE id = ?
        """,
        (discount_id,)
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ایجاد درخواست سازگار با نسخه‌های قبلی
# =========================================================

@app.route(
    "/create-request",
    methods=["POST"]
)
def create_request():
    service_id = to_int(
        request.form.get("service_id")
    )

    return redirect(
        url_for(
            "service",
            service_id=service_id
        )
    )


# =========================================================
# خطاها
# =========================================================

@app.errorhandler(404)
def not_found(error):
    return render_template(
        "base.html",
        content="صفحه مورد نظر پیدا نشد."
    ), 404


@app.errorhandler(413)
def too_large(error):
    flash(
        "حجم فایل بیش از حد مجاز است.",
        "error"
    )

    return redirect(
        request.referrer
        or url_for("index")
    )


@app.errorhandler(500)
def internal_error(error):
    app.logger.exception(
        "Internal server error"
    )

    return (
        "خطای داخلی سرور. لطفاً لاگ Render را بررسی کنید.",
        500,
    )


# =========================================================
# شروع
# =========================================================

create_tables()


if __name__ == "__main__":
    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
