import os
import json
import sqlite3
import secrets
import random
import shutil
import urllib.request
import urllib.parse
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
    g,
    jsonify
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# =========================================================
# تنظیمات اصلی
# =========================================================

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

app.secret_key = os.environ.get(
    "SECRET_KEY",
    secrets.token_hex(32)
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


SITE_NAME = "کافی نت آنلاین نوین"
MANAGER = "احمد محمدی مهر"
PHONE = ""


# =========================================================
# وضعیت پرونده
# =========================================================

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
# نقش ها
# =========================================================

ROLE_ADMIN = "admin"
ROLE_EXPERT = "expert"


# =========================================================
# فرمت فایل ها
# =========================================================

ALLOWED_DOCUMENT_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".pdf"
}


# =========================================================
# دیتابیس
# =========================================================

def get_db():

    if "db" not in g:

        g.db = sqlite3.connect(DATABASE)

        g.db.row_factory = sqlite3.Row

        g.db.execute(
            "PRAGMA foreign_keys = ON"
        )

    return g.db


@app.teardown_appcontext
def close_db(exception):

    db = g.pop("db", None)

    if db is not None:
        db.close()


def column_exists(conn, table, column):

    rows = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(
        row["name"] == column
        for row in rows
    )


def add_column_if_missing(
    conn,
    table,
    column,
    definition
):

    if not column_exists(
        conn,
        table,
        column
    ):

        conn.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )


# =========================================================
# ساخت جداول
# =========================================================

def create_tables():

    conn = get_db()

    conn.executescript(
        """

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
            password TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
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

            subservices_json TEXT DEFAULT '[]',

            icon TEXT DEFAULT '📋',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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

            payment_reference TEXT DEFAULT '',

            payment_method TEXT DEFAULT '',

            resubmission_count INTEGER DEFAULT 0,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE SET NULL,

            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE SET NULL,

            FOREIGN KEY(expert_id)
                REFERENCES users(id)
                ON DELETE SET NULL
        );


        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            customer_id INTEGER,
            request_id INTEGER,

            sender TEXT NOT NULL,

            message TEXT DEFAULT '',

            file_path TEXT DEFAULT '',
            original_name TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE CASCADE,

            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE
        );


        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            request_id INTEGER NOT NULL,
            customer_id INTEGER,

            file_path TEXT NOT NULL,
            original_name TEXT NOT NULL,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE,

            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE SET NULL
        );


        CREATE TABLE IF NOT EXISTS discounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            code TEXT UNIQUE NOT NULL,

            kind TEXT NOT NULL DEFAULT 'percent',

            value INTEGER NOT NULL DEFAULT 0,

            max_uses INTEGER DEFAULT 0,

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


        CREATE TABLE IF NOT EXISTS expert_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            expert_id INTEGER NOT NULL,

            service_id INTEGER NOT NULL,

            UNIQUE(expert_id, service_id),

            FOREIGN KEY(expert_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        );


        CREATE TABLE IF NOT EXISTS financial_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            request_id INTEGER,

            customer_id INTEGER,

            type TEXT NOT NULL,

            amount INTEGER DEFAULT 0,

            description TEXT DEFAULT '',

            reference TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE SET NULL,

            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE SET NULL
        );


        CREATE TABLE IF NOT EXISTS expert_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            expert_id INTEGER NOT NULL,

            day_of_week INTEGER NOT NULL,

            start_time TEXT DEFAULT '08:00',

            end_time TEXT DEFAULT '20:00',

            enabled INTEGER DEFAULT 1,

            FOREIGN KEY(expert_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );


        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            filename TEXT NOT NULL,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        """
    )


    # =====================================================
    # مهاجرت دیتابیس قدیمی
    # =====================================================

    add_column_if_missing(
        conn,
        "customers",
        "password",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "customers",
        "active",
        "INTEGER DEFAULT 1"
    )

    add_column_if_missing(
        conn,
        "services",
        "form_code",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "services",
        "subservices_json",
        "TEXT DEFAULT '[]'"
    )

    add_column_if_missing(
        conn,
        "services",
        "icon",
        "TEXT DEFAULT '📋'"
    )

    add_column_if_missing(
        conn,
        "requests",
        "expert_id",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "requests",
        "admin_note",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "requests",
        "estimated_time",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "requests",
        "discount_code",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "requests",
        "discount_amount",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        conn,
        "requests",
        "is_paid",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        conn,
        "requests",
        "payment_reference",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "requests",
        "payment_method",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "requests",
        "resubmission_count",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        conn,
        "messages",
        "file_path",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "messages",
        "original_name",
        "TEXT DEFAULT ''"
    )


    # =====================================================
    # تنظیمات پیش فرض
    # =====================================================

    defaults = {

        "site_name":
            SITE_NAME,

        "manager":
            MANAGER,

        "phone":
            PHONE,

        "manager_text":
            "ارائه کلیه خدمات کافی‌نت به صورت غیرحضوری",

        "home_text":
            "تمام خدمات کافی‌نت آنلاین نوین را به صورت غیرحضوری دریافت کنید.",

        "footer_text":
            "کافی نت آنلاین نوین - با مدیریت احمد محمدی مهر",

        "logo":
            "",

        "force_change_password":
            "1",

        "chat_start":
            "08:00",

        "chat_end":
            "20:00",

        "chat_enabled":
            "1",

        "chat_rest_days":
            "5",

        "sms_enabled":
            "0",

        "sms_api_url":
            "",

        "sms_api_token":
            "",

        "sms_sender":
            "",

        "payment_enabled":
            "0",

        "payment_api_url":
            "",

        "payment_api_token":
            "",

        "payment_merchant":
            "",

        "payment_callback_url":
            "",

    }


    for key, value in defaults.items():

        conn.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )


    # =====================================================
    # ساخت مدیر اولیه فقط در اولین اجرا
    # =====================================================

    admin = conn.execute(
        """
        SELECT id
        FROM users
        WHERE username = ?
        """,
        ("admin",)
    ).fetchone()


    if not admin:

        initial_password = os.environ.get(
            "ADMIN_INITIAL_PASSWORD"
        )

        if not initial_password:

            initial_password = secrets.token_urlsafe(12)

            print(
                "\n========================================"
            )

            print(
                "ADMIN USER CREATED"
            )

            print(
                "username: admin"
            )

            print(
                f"temporary password: {initial_password}"
            )

            print(
                "IMPORTANT: change this password immediately."
            )

            print(
                "========================================\n"
            )


        conn.execute(
            """
            INSERT INTO users(
                username,
                password,
                role,
                active
            )
            VALUES (?, ?, 'admin', 1)
            """,
            (
                "admin",
                generate_password_hash(
                    initial_password
                )
            )
        )


    conn.commit()


# =========================================================
# تنظیمات
# =========================================================

def get_settings():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT key, value
        FROM settings
        """
    ).fetchall()

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


# =========================================================
# کاربر فعلی
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

    if not user:
        return None

    if not user["active"]:
        return None

    return user


def login_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        if not get_current_user():

            return redirect(
                url_for("admin_login")
            )

        return f(*args, **kwargs)

    return decorated


def admin_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        user = get_current_user()

        if not user:

            return redirect(
                url_for("admin_login")
            )

        if user["role"] != ROLE_ADMIN:

            flash(
                "دسترسی فقط برای مدیر اصلی امکان‌پذیر است.",
                "error"
            )

            return redirect(
                url_for("admin")
            )

        return f(*args, **kwargs)

    return decorated


# =========================================================
# ابزار JSON
# =========================================================

def parse_json_list(value):

    if not value:
        return []

    try:

        result = json.loads(value)

        if isinstance(result, list):
            return result

    except Exception:
        pass

    return []


def parse_json_dict(value):

    if not value:
        return {}

    try:

        result = json.loads(value)

        if isinstance(result, dict):
            return result

    except Exception:
        pass

    return {}


def clean_json(value, default="[]"):

    try:

        parsed = json.loads(value)

        return json.dumps(
            parsed,
            ensure_ascii=False
        )

    except Exception:

        return default


# =========================================================
# اعداد
# =========================================================

def to_int(value, default=0):

    try:

        return int(
            str(value)
            .replace(",", "")
            .strip()
        )

    except Exception:

        return default


# =========================================================
# کد پیگیری
# =========================================================

def generate_tracking_code():

    conn = get_db()

    while True:

        code = str(
            random.randint(
                1000,
                9999
            )
        )

        exists = conn.execute(
            """
            SELECT id
            FROM requests
            WHERE tracking_code = ?
            """,
            (code,)
        ).fetchone()

        if not exists:

            return code


# =========================================================
# اعلان
# =========================================================

def create_notification(
    user_type,
    user_id,
    request_id,
    title,
    body=""
):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO notifications(
            user_type,
            user_id,
            request_id,
            title,
            body
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_type,
            user_id,
            request_id,
            title,
            body
        )
    )

    conn.commit()


def notify_all_admins(
    request_id,
    title,
    body=""
):

    conn = get_db()

    admins = conn.execute(
        """
        SELECT id
        FROM users
        WHERE role = 'admin'
        AND active = 1
        """
    ).fetchall()

    for admin in admins:

        create_notification(
            "admin",
            admin["id"],
            request_id,
            title,
            body
        )


# =========================================================
# اعلان پیامکی
# =========================================================

def send_sms(phone, text):

    settings = get_settings()

    if settings.get("sms_enabled") != "1":
        return False

    api_url = settings.get(
        "sms_api_url",
        ""
    ).strip()

    token = settings.get(
        "sms_api_token",
        ""
    ).strip()

    if not api_url or not phone:
        return False

    try:

        payload = urllib.parse.urlencode(
            {
                "token": token,
                "to": phone,
                "message": text,
                "sender": settings.get(
                    "sms_sender",
                    ""
                )
            }
        ).encode()

        req = urllib.request.Request(
            api_url,
            data=payload,
            method="POST"
        )

        urllib.request.urlopen(
            req,
            timeout=10
        )

        return True

    except Exception as exc:

        print(
            "SMS ERROR:",
            exc
        )

        return False


def notify_customer(
    customer_id,
    request_id,
    title,
    body,
    sms_text=None
):

    create_notification(
        "customer",
        customer_id,
        request_id,
        title,
        body
    )

    if sms_text:

        conn = get_db()

        customer = conn.execute(
            """
            SELECT phone
            FROM customers
            WHERE id = ?
            """,
            (customer_id,)
        ).fetchone()

        if customer:

            send_sms(
                customer["phone"],
                sms_text
            )


# =========================================================
# سطح دسترسی خدمات کارشناس
# =========================================================

def expert_can_use_service(
    expert_id,
    service_id
):

    conn = get_db()

    row = conn.execute(
        """
        SELECT id
        FROM expert_services
        WHERE expert_id = ?
        AND service_id = ?
        """,
        (
            expert_id,
            service_id
        )
    ).fetchone()

    return bool(row)


def expert_can_access_request(
    user,
    row
):

    if user["role"] == ROLE_ADMIN:
        return True

    if user["role"] != ROLE_EXPERT:
        return False

    # پرونده اختصاص داده شده به کارشناس دیگر
    if row["expert_id"]:

        return row["expert_id"] == user["id"]

    # پرونده بدون کارشناس
    return expert_can_use_service(
        user["id"],
        row["service_id"]
    )


# =========================================================
# Context Processor
# =========================================================

@app.context_processor
def inject_globals():

    settings = get_settings()

    return {

        "site_settings":
            settings,

        "site_name":
            settings.get(
                "site_name",
                SITE_NAME
            ),

        "manager":
            settings.get(
                "manager",
                MANAGER
            ),

        "phone":
            settings.get(
                "phone",
                PHONE
            ),

        "current_user":
            get_current_user(),

        "allowed_statuses":
            ALLOWED_STATUSES

    }


# =========================================================
# صفحه اصلی
# =========================================================

@app.route("/")
def home():

    conn = get_db()

    services = conn.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        ORDER BY sort_order ASC, id DESC
        """
    ).fetchall()

    return render_template(
        "index.html",
        services=services,
        settings=get_settings()
    )


@app.route("/index")
def index():

    return redirect(
        url_for("home")
    )


# =========================================================
# صفحه خدمت
# =========================================================

@app.route(
    "/service/<int:service_id>",
    methods=["GET", "POST"]
)
def service(service_id):

    conn = get_db()

    service_row = conn.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    if not service_row:
        abort(404)

    fields = parse_json_list(
        service_row["fields_json"]
    )

    documents = parse_json_list(
        service_row["documents_json"]
    )

    subservices = parse_json_list(
        service_row["subservices_json"]
    )

    return render_template(
        "service.html",

        service=service_row,

        fields=fields,

        documents=documents,

        subservices=subservices,

        settings=get_settings()
    )


# =========================================================
# اعتبارسنجی کد تخفیف
# =========================================================

def calculate_discount(
    code,
    base_price
):

    if not code:

        return 0, None

    conn = get_db()

    discount = conn.execute(
        """
        SELECT *
        FROM discounts
        WHERE code = ?
        AND active = 1
        """,
        (
            code.strip().upper(),
        )
    ).fetchone()

    if not discount:

        return 0, None

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    if (
        discount["start_date"]
        and today < discount["start_date"]
    ):
        return 0, None

    if (
        discount["end_date"]
        and today > discount["end_date"]
    ):
        return 0, None

    if (
        discount["max_uses"] > 0
        and discount["used_count"]
        >= discount["max_uses"]
    ):
        return 0, None

    if discount["kind"] == "percent":

        amount = int(
            base_price
            * discount["value"]
            / 100
        )

    else:

        amount = discount["value"]

    amount = min(
        base_price,
        max(0, amount)
    )

    return amount, discount


# =========================================================
# ثبت درخواست
# =========================================================

@app.route(
    "/create-request/<int:service_id>",
    methods=["POST"]
)
def create_request(service_id):

    conn = get_db()

    service_row = conn.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    if not service_row:
        abort(404)

    name = request.form.get(
        "name",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    national_id = request.form.get(
        "national_id",
        ""
    ).strip()

    customer_note = request.form.get(
        "customer_note",
        ""
    ).strip()

    discount_code = request.form.get(
        "discount_code",
        ""
    ).strip().upper()

    subservice_id = request.form.get(
        "subservice_id",
        ""
    ).strip()


    if not name or not phone:

        flash(
            "نام و شماره موبایل الزامی است.",
            "error"
        )

        return redirect(
            url_for(
                "service",
                service_id=service_id
            )
        )


    # =====================================================
    # مشتری
    # =====================================================

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
            SET name = ?,
                national_id = ?
            WHERE id = ?
            """,
            (
                name,
                national_id,
                customer_id
            )
        )

    else:

        cursor = conn.execute(
            """
            INSERT INTO customers(
                name,
                phone,
                national_id
            )
            VALUES (?, ?, ?)
            """,
            (
                name,
                phone,
                national_id
            )
        )

        customer_id = cursor.lastrowid


    # =====================================================
    # اطلاعات فرم
    # =====================================================

    form_data = {}

    excluded = {
        "name",
        "phone",
        "national_id",
        "customer_note",
        "discount_code",
        "subservice_id",
        "documents"
    }


    for key in request.form:

        if key not in excluded:

            form_data[key] = request.form.get(
                key
            )


    # =====================================================
    # قیمت
    # =====================================================

    base_price = to_int(
        service_row["price"]
    )

    subservices = parse_json_list(
        service_row["subservices_json"]
    )


    if subservice_id:

        for sub in subservices:

            if str(
                sub.get("id", "")
            ) == subservice_id:

                base_price = to_int(
                    sub.get(
                        "price",
                        base_price
                    )
                )

                break


    discount_amount, discount = calculate_discount(
        discount_code,
        base_price
    )


    final_price = max(
        0,
        base_price - discount_amount
    )


    # 100 درصد یا قیمت صفر
    is_paid = 1 if final_price == 0 else 0


    if discount:

        conn.execute(
            """
            UPDATE discounts
            SET used_count = used_count + 1
            WHERE id = ?
            """,
            (
                discount["id"],
            )
        )


    tracking_code = generate_tracking_code()


    cursor = conn.execute(
        """
        INSERT INTO requests(

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

            is_paid

        )

        VALUES (

            ?,
            ?,
            ?,
            ?,

            ?,

            ?,
            0,

            ?,
            ?,

            ?,

            ?

        )
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

            is_paid
        )
    )


    request_id = cursor.lastrowid


    # =====================================================
    # مدارک
    # =====================================================

    files = request.files.getlist(
        "documents"
    )


    for file in files:

        if not file:
            continue

        if not file.filename:
            continue

        filename = secure_filename(
            file.filename
        )

        ext = os.path.splitext(
            filename
        )[1].lower()


        if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
            continue


        new_name = (
            secrets.token_hex(8)
            + "_"
            + filename
        )


        path = os.path.join(
            DOCUMENTS_FOLDER,
            new_name
        )


        file.save(path)


        conn.execute(
            """
            INSERT INTO documents(
                request_id,
                customer_id,
                file_path,
                original_name
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                request_id,
                customer_id,
                new_name,
                filename
            )
        )


    # =====================================================
    # پیام سیستم
    # =====================================================

    conn.execute(
        """
        INSERT INTO messages(
            customer_id,
            request_id,
            sender,
            message
        )
        VALUES (?, ?, 'system', ?)
        """,
        (
            customer_id,
            request_id,
            "درخواست شما با موفقیت ثبت شد."
        )
    )


    # =====================================================
    # تراکنش مالی
    # =====================================================

    if is_paid:

        conn.execute(
            """
            INSERT INTO financial_transactions(
                request_id,
                customer_id,
                type,
                amount,
                description
            )
            VALUES (?, ?, 'income', ?, ?)
            """,
            (
                request_id,
                customer_id,
                final_price,
                "ثبت درخواست با تخفیف کامل"
            )
        )


    conn.commit()


    # =====================================================
    # اعلان مدیر
    # =====================================================

    notify_all_admins(
        request_id,
        "درخواست جدید",
        f"کد پیگیری: {tracking_code}"
    )


    # =====================================================
    # اگر رایگان است → قابل پذیرش
    # اگر پولی است → ابتدا پرداخت
    # =====================================================

    if is_paid:

        notify_customer(
            customer_id,
            request_id,
            "درخواست ثبت شد",
            "درخواست شما ثبت شد و آماده پذیرش کارشناس است.",
            f"کافی نت آنلاین نوین: درخواست شما با کد {tracking_code} ثبت شد."
        )

    else:

        notify_customer(
            customer_id,
            request_id,
            "پرداخت مورد نیاز است",
            f"مبلغ قابل پرداخت: {final_price:,} تومان",
            f"کافی نت آنلاین نوین: مبلغ درخواست {final_price:,} تومان است."
        )


    return redirect(
        url_for(
            "tracking",
            code=tracking_code
        )
    )


# =========================================================
# پیگیری
# =========================================================

@app.route(
    "/tracking",
    methods=["GET", "POST"]
)
def tracking():

    result = None

    code = (
        request.args.get("code")
        or
        request.form.get(
            "tracking_code",
            ""
        ).strip()
    )


    if code:

        conn = get_db()

        result = conn.execute(
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
            (code,)
        ).fetchone()


        if not result:

            flash(
                "کد پیگیری پیدا نشد.",
                "error"
            )


    return render_template(
        "tracking.html",
        result=result,
        settings=get_settings()
    )


# =========================================================
# مشتری / چت / پرونده
# =========================================================

@app.route(
    "/customer/request/<tracking_code>",
    methods=["GET", "POST"]
)
def customer_request(tracking_code):

    conn = get_db()

    req = conn.execute(
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


    if not req:
        abort(404)


    # =====================================================
    # رفع نقص مدارک / ثبت مجدد
    # =====================================================

    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()

        file = request.files.get(
            "file"
        )


        file_path = ""
        original_name = ""


        if file and file.filename:

            filename = secure_filename(
                file.filename
            )

            ext = os.path.splitext(
                filename
            )[1].lower()


            if ext in ALLOWED_DOCUMENT_EXTENSIONS:

                new_name = (
                    secrets.token_hex(8)
                    + "_"
                    + filename
                )

                path = os.path.join(
                    CHAT_FOLDER,
                    new_name
                )

                file.save(path)

                file_path = new_name
                original_name = filename


        if message or file_path:

            conn.execute(
                """
                INSERT INTO messages(

                    customer_id,
                    request_id,
                    sender,
                    message,
                    file_path,
                    original_name

                )

                VALUES (?, ?, 'customer', ?, ?, ?)
                """,
                (
                    req["customer_id"],
                    req["id"],
                    message
                    or
                    "فایل ارسال شد",
                    file_path,
                    original_name
                )
            )


            # اعلان کارشناس
            if req["expert_id"]:

                create_notification(
                    "expert",
                    req["expert_id"],
                    req["id"],
                    "پیام جدید مشتری",
                    f"کد پیگیری: {tracking_code}"
                )


            notify_all_admins(
                req["id"],
                "پیام جدید مشتری",
                f"کد پیگیری: {tracking_code}"
            )


            conn.commit()


            flash(
                "پیام شما ارسال شد.",
                "success"
            )


        return redirect(
            url_for(
                "customer_request",
                tracking_code=tracking_code
            )
        )


    messages = conn.execute(
        """
        SELECT *
        FROM messages
        WHERE request_id = ?
        ORDER BY id ASC
        """,
        (req["id"],)
    ).fetchall()


    documents = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE request_id = ?
        ORDER BY id DESC
        """,
        (req["id"],)
    ).fetchall()


    return render_template(
        "chat.html",

        request_row=req,

        messages=messages,

        documents=documents,

        settings=get_settings()
    )


# =========================================================
# پرداخت آماده اتصال
# =========================================================

@app.route(
    "/payment/<int:rid>",
    methods=["GET"]
)
def payment(rid):

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()


    if not row:
        abort(404)


    if row["is_paid"]:

        return redirect(
            url_for(
                "tracking",
                code=row["tracking_code"]
            )
        )


    amount = max(
        0,
        row["total_price"]
        -
        row["paid_price"]
    )


    if amount <= 0:

        conn.execute(
            """
            UPDATE requests
            SET is_paid = 1
            WHERE id = ?
            """,
            (rid,)
        )

        conn.commit()

        return redirect(
            url_for(
                "tracking",
                code=row["tracking_code"]
            )
        )


    settings = get_settings()


    if settings.get(
        "payment_enabled"
    ) != "1":

        flash(
            "درگاه پرداخت هنوز در تنظیمات فعال نشده است.",
            "error"
        )

        return redirect(
            url_for(
                "tracking",
                code=row["tracking_code"]
            )
        )


    # این قسمت عمداً به API عمومی متصل نمی‌شود.
    # بعداً مشخصات درگاه واقعی از داخل پنل وارد می‌شود.


    flash(
        "تنظیمات درگاه انجام شده ولی اتصال API درگاه هنوز فعال نشده است.",
        "error"
    )


    return redirect(
        url_for(
            "tracking",
            code=row["tracking_code"]
        )
    )


# =========================================================
# callback پرداخت
# =========================================================

@app.route(
    "/payment/callback",
    methods=["GET", "POST"]
)
def payment_callback():

    tracking_code = (
        request.values.get(
            "tracking_code",
            ""
        ).strip()
    )

    reference = (
        request.values.get(
            "reference",
            ""
        ).strip()
    )


    if not tracking_code:

        return "invalid request", 400


    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM requests
        WHERE tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()


    if not row:

        return "request not found", 404


    # فقط بعد از تأیید واقعی درگاه
    # این route باید فراخوانی شود.

    amount = row["total_price"]


    conn.execute(
        """
        UPDATE requests

        SET
            paid_price = ?,
            is_paid = 1,
            payment_reference = ?,
            payment_method = 'gateway',
            updated_at = CURRENT_TIMESTAMP

        WHERE id = ?
        """,
        (
            amount,
            reference,
            row["id"]
        )
    )


    conn.execute(
        """
        INSERT INTO financial_transactions(

            request_id,
            customer_id,
            type,
            amount,
            description,
            reference

        )

        VALUES (?, ?, 'income', ?, ?, ?)
        """,
        (
            row["id"],
            row["customer_id"],
            amount,
            "پرداخت آنلاین",
            reference
        )
    )


    conn.commit()


    notify_all_admins(
        row["id"],
        "پرداخت موفق",
        f"کد پیگیری: {tracking_code}"
    )


    return redirect(
        url_for(
            "tracking",
            code=tracking_code
        )
    )


# =========================================================
# ورود مدیر / کارشناس
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if get_current_user():

        return redirect(
            url_for("admin")
        )


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


        if (
            user
            and
            check_password_hash(
                user["password"],
                password
            )
        ):

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
        settings=get_settings()
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

    user = get_current_user()


    if user["role"] == ROLE_EXPERT:

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

            WHERE

                (

                    r.expert_id = ?

                    OR

                    (

                        r.expert_id IS NULL

                        AND EXISTS (

                            SELECT 1

                            FROM expert_services es

                            WHERE es.expert_id = ?
                            AND es.service_id = r.service_id

                        )

                    )

                )

                AND r.is_paid = 1

            ORDER BY r.id DESC

            """,
            (
                user["id"],
                user["id"]
            )
        ).fetchall()


    else:

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


    discounts = conn.execute(
        """
        SELECT *
        FROM discounts
        ORDER BY id DESC
        """
    ).fetchall()


    users = conn.execute(
        """
        SELECT
            id,
            username,
            role,
            active,
            created_at
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()


    total_income = conn.execute(
        """
        SELECT
            COALESCE(
                SUM(amount),
                0
            )

        FROM financial_transactions

        WHERE type = 'income'

        """
    ).fetchone()[0]


    total_expense = conn.execute(
        """
        SELECT
            COALESCE(
                SUM(amount),
                0
            )

        FROM financial_transactions

        WHERE type = 'expense'

        """
    ).fetchone()[0]


    total_debt = conn.execute(
        """
        SELECT
            COALESCE(
                SUM(
                    CASE

                        WHEN
                            total_price
                            >
                            paid_price

                        THEN
                            total_price
                            -
                            paid_price

                        ELSE 0

                    END
                ),
                0
            )

        FROM requests

        """
    ).fetchone()[0]


    notifications = conn.execute(
        """
        SELECT *
        FROM notifications

        WHERE

            (

                user_type = 'admin'
                AND
                (
                    user_id = ?
                    OR
                    user_id IS NULL
                )

            )

        ORDER BY id DESC

        LIMIT 30

        """,
        (user["id"],)
    ).fetchall()


    return render_template(
        "admin.html",

        requests=requests_rows,

        customers=customers,

        services=services,

        discounts=discounts,

        users=users,

        total_income=total_income,

        total_expense=total_expense,

        total_debt=total_debt,

        notifications=notifications,

        settings=get_settings(),

        current_user=user
    )


# =========================================================
# تنظیمات سایت
# =========================================================

@app.route(
    "/admin/settings/save",
    methods=["POST"]
)
@admin_required
def admin_settings_save():

    keys = [

        "site_name",
        "manager",
        "phone",
        "manager_text",
        "home_text",
        "footer_text",

        "chat_start",
        "chat_end",
        "chat_enabled",
        "chat_rest_days",

        "sms_enabled",
        "sms_api_url",
        "sms_api_token",
        "sms_sender",

        "payment_enabled",
        "payment_api_url",
        "payment_api_token",
        "payment_merchant",
        "payment_callback_url"

    ]


    for key in keys:

        if key in request.form:

            set_setting(
                key,
                request.form.get(
                    key,
                    ""
                ).strip()
            )


    logo = request.files.get(
        "logo"
    )


    if logo and logo.filename:

        filename = secure_filename(
            logo.filename
        )

        if filename.lower().endswith(
            (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp"
            )
        ):

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
# مدیریت پرونده
# =========================================================

@app.route(
    "/admin/request/<int:rid>",
    methods=["GET", "POST"]
)
@login_required
def admin_request(rid):

    conn = get_db()

    user = get_current_user()


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
        abort(404)


    if not expert_can_access_request(
        user,
        row
    ):

        flash(
            "دسترسی به این پرونده برای شما مجاز نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    if request.method == "POST":

        status = request.form.get(
            "status",
            row["status"]
        ).strip()

        estimated_time = request.form.get(
            "estimated_time",
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

        expert_id = request.form.get(
            "expert_id"
        ) or None


        if status not in ALLOWED_STATUSES:

            status = row["status"]


        if expert_id:

            expert_id = to_int(
                expert_id
            )


        # اولین کارشناس پذیرنده
        if (
            user["role"] == ROLE_EXPERT
            and not row["expert_id"]
            and status == "پذیرش شد"
        ):

            expert_id = user["id"]


        # کارشناس نمی‌تواند پرونده اختصاص یافته
        # به فرد دیگر را جابه‌جا کند
        if (
            user["role"] == ROLE_EXPERT
            and row["expert_id"]
            and row["expert_id"] != user["id"]
        ):

            flash(
                "این پرونده قبلاً توسط کارشناس دیگری پذیرش شده است.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_request",
                    rid=rid
                )
            )


        paid_price = max(
            0,
            min(
                paid_price,
                total_price
            )
        )


        conn.execute(
            """
            UPDATE requests

            SET

                status = ?,

                estimated_time = ?,

                admin_note = ?,

                total_price = ?,

                paid_price = ?,

                expert_id = ?,

                is_paid =
                    CASE

                        WHEN
                            paid_price >= total_price
                        THEN 1

                        ELSE is_paid

                    END,

                updated_at =
                    CURRENT_TIMESTAMP

            WHERE id = ?

            """,
            (
                status,
                estimated_time,
                admin_note,
                total_price,
                paid_price,
                expert_id,
                rid
            )
        )


        conn.commit()


        # اعلان مشتری
        notify_customer(
            row["customer_id"],
            rid,
            "تغییر وضعیت پرونده",
            f"وضعیت جدید: {status}",
            f"کافی نت آنلاین نوین: وضعیت پرونده {row['tracking_code']} به «{status}» تغییر کرد."
        )


        # اعلان کارشناس
        if expert_id:

            create_notification(
                "expert",
                expert_id,
                rid,
                "پرونده جدید",
                f"کد پیگیری: {row['tracking_code']}"
            )


        # اعلان مدیر
        notify_all_admins(
            rid,
            "تغییر پرونده",
            f"کد پیگیری: {row['tracking_code']} - {status}"
        )


        flash(
            "پرونده به‌روزرسانی شد.",
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


    documents = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE request_id = ?
        ORDER BY id DESC
        """
    ).fetchall()


    experts = conn.execute(
        """
        SELECT
            id,
            username
        FROM users

        WHERE
            role = 'expert'
            AND active = 1

        ORDER BY username
        """
    ).fetchall()


    assigned_services = conn.execute(
        """
        SELECT
            es.expert_id,
            es.service_id

        FROM expert_services es

        """
    ).fetchall()


    return render_template(
        "admin_request.html",

        req=row,

        messages=messages,

        documents=documents,

        experts=experts,

        assigned_services=assigned_services,

        settings=get_settings()
    )


# =========================================================
# تغییر وضعیت
# =========================================================

@app.route(
    "/admin/request/status",
    methods=["POST"]
)
@login_required
def admin_request_status():

    rid = to_int(
        request.form.get("id")
    )

    status = request.form.get(
        "status",
        ""
    ).strip()


    if status not in ALLOWED_STATUSES:

        flash(
            "وضعیت نامعتبر است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    conn = get_db()

    user = get_current_user()


    row = conn.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()


    if not row:
        abort(404)


    if not expert_can_access_request(
        user,
        row
    ):

        flash(
            "دسترسی به این پرونده مجاز نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    expert_id = row["expert_id"]


    # اولین پذیرش
    if (
        user["role"] == ROLE_EXPERT
        and not expert_id
        and status == "پذیرش شد"
    ):

        expert_id = user["id"]


    conn.execute(
        """
        UPDATE requests

        SET
            status = ?,
            expert_id = ?,
            updated_at = CURRENT_TIMESTAMP

        WHERE id = ?

        """,
        (
            status,
            expert_id,
            rid
        )
    )


    # اگر نقص مدارک شد
    if status == "نقص مدارک":

        # اجازه ارسال مجدد رایگان
        conn.execute(
            """
            UPDATE requests

            SET
                paid_price = paid_price

            WHERE id = ?

            """,
            (rid,)
        )


    conn.commit()


    notify_customer(
        row["customer_id"],
        rid,
        "تغییر وضعیت پرونده",
        f"وضعیت جدید: {status}",
        f"کافی نت آنلاین نوین: وضعیت پرونده {row['tracking_code']} به «{status}» تغییر کرد."
    )


    notify_all_admins(
        rid,
        "تغییر وضعیت پرونده",
        f"{row['tracking_code']} - {status}"
    )


    flash(
        "وضعیت پرونده تغییر کرد.",
        "success"
    )


    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# به روز رسانی پرونده
# =========================================================

@app.route(
    "/admin/request/update",
    methods=["POST"]
)
@login_required
def admin_request_update():

    rid = to_int(
        request.form.get("id")
    )

    conn = get_db()

    user = get_current_user()


    row = conn.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()


    if not row:
        abort(404)


    if not expert_can_access_request(
        user,
        row
    ):

        flash(
            "دسترسی غیرمجاز.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    total_price = to_int(
        request.form.get(
            "total_price"
        )
    )

    paid_price = to_int(
        request.form.get(
            "paid_price"
        )
    )

    estimated_time = request.form.get(
        "estimated_time",
        ""
    ).strip()

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()


    expert_id = request.form.get(
        "expert_id"
    ) or row["expert_id"]


    if expert_id:

        expert_id = to_int(
            expert_id
        )


    paid_price = max(
        0,
        min(
            paid_price,
            total_price
        )
    )


    is_paid = (
        1
        if paid_price >= total_price
        else row["is_paid"]
    )


    conn.execute(
        """
        UPDATE requests

        SET

            total_price = ?,

            paid_price = ?,

            estimated_time = ?,

            admin_note = ?,

            expert_id = ?,

            is_paid = ?,

            updated_at =
                CURRENT_TIMESTAMP

        WHERE id = ?

        """,
        (
            total_price,
            paid_price,
            estimated_time,
            admin_note,
            expert_id,
            is_paid,
            rid
        )
    )


    conn.commit()


    flash(
        "اطلاعات پرونده ذخیره شد.",
        "success"
    )


    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# پیام مدیر / کارشناس + فایل
# =========================================================

@app.route(
    "/admin/message",
    methods=["POST"]
)
@login_required
def admin_message():

    rid = to_int(
        request.form.get("id")
    )

    message = request.form.get(
        "message",
        ""
    ).strip()

    file = request.files.get(
        "file"
    )


    conn = get_db()

    user = get_current_user()


    row = conn.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()


    if not row:
        abort(404)


    if not expert_can_access_request(
        user,
        row
    ):

        flash(
            "دسترسی غیرمجاز.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    file_path = ""
    original_name = ""


    if file and file.filename:

        filename = secure_filename(
            file.filename
        )

        ext = os.path.splitext(
            filename
        )[1].lower()


        if ext in ALLOWED_DOCUMENT_EXTENSIONS:

            new_name = (
                secrets.token_hex(8)
                + "_"
                + filename
            )


            path = os.path.join(
                CHAT_FOLDER,
                new_name
            )


            file.save(path)

            file_path = new_name
            original_name = filename


    if message or file_path:

        sender = (
            "admin"
            if user["role"] == ROLE_ADMIN
            else "expert"
        )


        conn.execute(
            """
            INSERT INTO messages(

                customer_id,
                request_id,
                sender,
                message,
                file_path,
                original_name

            )

            VALUES (?, ?, ?, ?, ?, ?)

            """,
            (
                row["customer_id"],
                rid,
                sender,
                message,
                file_path,
                original_name
            )
        )


        conn.commit()


        notify_customer(
            row["customer_id"],
            rid,
            "پیام جدید",
            "برای پرونده شما پیام جدید ارسال شده است.",
            f"کافی نت آنلاین نوین: برای پرونده {row['tracking_code']} پیام جدید دارید."
        )


        flash(
            "پیام ارسال شد.",
            "success"
        )


    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# افزودن خدمت از داخل پنل
# =========================================================

@app.route(
    "/admin/service/save",
    methods=["POST"]
)
@admin_required
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
        request.form.get(
            "sort_order"
        )
    )

    active = (
        1
        if request.form.get(
            "active",
            "1"
        ) == "1"
        else 0
    )

    icon = request.form.get(
        "icon",
        "📋"
    ).strip()


    fields_json = clean_json(
        request.form.get(
            "fields_json",
            "[]"
        )
    )


    documents_json = clean_json(
        request.form.get(
            "documents_json",
            "[]"
        )
    )


    subservices_json = clean_json(
        request.form.get(
            "subservices_json",
            "[]"
        )
    )


    form_code = request.form.get(
        "form_code",
        ""
    )


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
        INSERT INTO services(

            name,
            category,
            description,
            price,
            sort_order,
            active,

            fields_json,
            documents_json,

            form_code,
            subservices_json,

            icon

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

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

            form_code,
            subservices_json,

            icon or "📋"
        )
    )


    conn.commit()


    flash(
        "خدمت جدید از داخل پنل مدیر ایجاد شد.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


# =========================================================
# ویرایش خدمت
# =========================================================

@app.route(
    "/admin/service/<int:service_id>/update",
    methods=["POST"]
)
@admin_required
def update_service(service_id):

    conn = get_db()


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
        request.form.get(
            "price"
        )
    )

    sort_order = to_int(
        request.form.get(
            "sort_order"
        )
    )

    active = (
        1
        if request.form.get(
            "active"
        ) == "1"
        else 0
    )

    icon = request.form.get(
        "icon",
        "📋"
    ).strip()


    fields_json = clean_json(
        request.form.get(
            "fields_json",
            "[]"
        )
    )


    documents_json = clean_json(
        request.form.get(
            "documents_json",
            "[]"
        )
    )


    subservices_json = clean_json(
        request.form.get(
            "subservices_json",
            "[]"
        )
    )


    form_code = request.form.get(
        "form_code",
        ""
    )


    conn.execute(
        """
        UPDATE services

        SET

            name = ?,

            category = ?,

            description = ?,

            price = ?,

            sort_order = ?,

            active = ?,

            fields_json = ?,

            documents_json = ?,

            form_code = ?,

            subservices_json = ?,

            icon = ?,

            updated_at =
                CURRENT_TIMESTAMP

        WHERE id = ?

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
            form_code,
            subservices_json,
            icon,
            service_id
        )
    )


    conn.commit()


    flash(
        "خدمت ویرایش شد.",
        "success"
    )


    return redirect(
        url_for("admin
