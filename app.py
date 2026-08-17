import os
import json
import uuid
import random
import sqlite3

from functools import wraps
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
    jsonify
)

from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# =========================================================
# APP CONFIG
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "novin-secret-key-change-this"
)

SITE_NAME = os.environ.get(
    "SITE_NAME",
    "کافی نت آنلاین نوین"
)

MANAGER = os.environ.get(
    "MANAGER",
    "احمد محمدی مهر"
)

PHONE = os.environ.get(
    "PHONE",
    ""
)

DATABASE = os.environ.get(
    "DATABASE_PATH",
    "novin.db"
)

UPLOAD_FOLDER = os.environ.get(
    "UPLOAD_FOLDER",
    "uploads"
)

MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "pdf"
}

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# =========================================================
# CONSTANTS
# =========================================================

STATUSES = [
    "جدید",
    "پذیرش شد",
    "در حال بررسی",
    "نقص مدارک",
    "قطعی سامانه",
    "رد شد",
    "انصراف مشتری",
    "انجام شد"
]

NOTIFICATION_TYPES = {
    "new_request": "درخواست جدید",
    "status_change": "تغییر وضعیت",
    "assignment": "اختصاص پرونده",
    "message": "پیام جدید",
    "payment": "پرداخت",
    "system": "سیستم"
}


# =========================================================
# DATABASE
# =========================================================

def get_db():
    db = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    db.row_factory = sqlite3.Row

    db.execute(
        "PRAGMA foreign_keys = ON"
    )

    return db


def table_columns(db, table_name):
    rows = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        row["name"]
        for row in rows
    }


def add_column_if_missing(
    db,
    table_name,
    column_name,
    column_definition
):
    columns = table_columns(
        db,
        table_name
    )

    if column_name not in columns:
        db.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {column_definition}
            """
        )


def create_tables():

    db = get_db()

    # USERS
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'expert',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # CUSTOMERS
    db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            national_id TEXT,
            phone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # SERVICES
    db.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            price INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            fields_json TEXT DEFAULT '[]',
            documents_json TEXT DEFAULT '[]',
            code TEXT,
            parent_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(parent_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # REQUESTS
    db.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            tracking_code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'جدید',
            customer_note TEXT,
            admin_note TEXT,
            description TEXT,
            estimated_time TEXT,
            total_price INTEGER DEFAULT 0,
            paid_price INTEGER DEFAULT 0,
            discount_amount INTEGER DEFAULT 0,
            payment_status TEXT DEFAULT 'unpaid',
            payment_reference TEXT,
            expert_id INTEGER,
            assigned_at TEXT,
            accepted_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE CASCADE,
            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE,
            FOREIGN KEY(expert_id)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # DOCUMENTS
    db.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            uploaded_by TEXT DEFAULT 'customer',
            uploaded_by_id INTEGER,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE
        )
    """)

    # MESSAGES
    db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL,
            sender_id INTEGER,
            message TEXT,
            attachment_name TEXT,
            attachment_stored_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE
        )
    """)

    # DISCOUNTS
    db.execute("""
        CREATE TABLE IF NOT EXISTS discounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL,
            value INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            start_date TEXT,
            end_date TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # DISCOUNT SERVICES
    db.execute("""
        CREATE TABLE IF NOT EXISTS discount_services (
            discount_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            PRIMARY KEY(discount_id, service_id),
            FOREIGN KEY(discount_id)
                REFERENCES discounts(id)
                ON DELETE CASCADE,
            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # SETTINGS
    db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # EXPERT SERVICES
    db.execute("""
        CREATE TABLE IF NOT EXISTS expert_services (
            user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            PRIMARY KEY(user_id, service_id),
            FOREIGN KEY(user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # NOTIFICATIONS
    db.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_type TEXT NOT NULL,
            recipient_id INTEGER,
            request_id INTEGER,
            type TEXT DEFAULT 'system',
            title TEXT NOT NULL,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE
        )
    """)

    # FINANCIAL TRANSACTIONS
    db.execute("""
        CREATE TABLE IF NOT EXISTS financial_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            customer_id INTEGER,
            type TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            description TEXT,
            reference TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE SET NULL,
            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE SET NULL
        )
    """)

    # SAFE MIGRATION
    add_column_if_missing(
        db,
        "services",
        "code",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "services",
        "parent_id",
        "INTEGER"
    )

    add_column_if_missing(
        db,
        "services",
        "updated_at",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "requests",
        "description",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "requests",
        "estimated_time",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "requests",
        "discount_amount",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        db,
        "requests",
        "payment_status",
        "TEXT DEFAULT 'unpaid'"
    )

    add_column_if_missing(
        db,
        "requests",
        "payment_reference",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "requests",
        "assigned_at",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "requests",
        "accepted_at",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "documents",
        "uploaded_by",
        "TEXT DEFAULT 'customer'"
    )

    add_column_if_missing(
        db,
        "documents",
        "uploaded_by_id",
        "INTEGER"
    )

    # DEFAULT SETTINGS
    defaults = {
        "site_name": SITE_NAME,
        "manager_name": MANAGER,
        "phone": PHONE,
        "logo": "",
        "site_description": "",
        "home_title": "خدمات غیرحضوری کافی نت آنلاین نوین",
        "home_text": "تمام خدمات شما به صورت غیرحضوری ارائه می‌شود.",
        "card_color": "#ffffff",
        "primary_color": "#2563eb"
    }

    for key, value in defaults.items():
        db.execute(
            """
            INSERT OR IGNORE INTO settings
            (key, value)
            VALUES (?, ?)
            """,
            (
                key,
                value
            )
        )

    # DEFAULT ADMIN
    admin = db.execute(
        """
        SELECT id
        FROM users
        WHERE username = ?
        """,
        ("admin",)
    ).fetchone()

    if not admin:

        password = os.environ.get(
            "ADMIN_PASSWORD",
            "ChangeMe123!"
        )

        db.execute(
            """
            INSERT INTO users
            (
                username,
                password_hash,
                role,
                active
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "admin",
                generate_password_hash(password),
                "admin",
                1
            )
        )

    db.commit()
    db.close()


create_tables()


# =========================================================
# SETTINGS
# =========================================================

def get_settings():

    db = get_db()

    rows = db.execute(
        """
        SELECT key, value
        FROM settings
        """
    ).fetchall()

    db.close()

    return {
        row["key"]: row["value"]
        for row in rows
    }


def get_setting(key, default=""):

    db = get_db()

    row = db.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        (key,)
    ).fetchone()

    db.close()

    if row:
        return row["value"]

    return default


@app.context_processor
def inject_global_settings():

    settings = get_settings()

    return {
        "settings": settings,
        "site_name": settings.get(
            "site_name",
            SITE_NAME
        ),
        "manager": settings.get(
            "manager_name",
            MANAGER
        ),
        "phone": settings.get(
            "phone",
            PHONE
        )
    }


# =========================================================
# HELPERS
# =========================================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


def generate_tracking_code():

    db = get_db()

    try:

        for _ in range(100):

            code = str(
                random.randint(
                    1000,
                    9999
                )
            )

            exists = db.execute(
                """
                SELECT id
                FROM requests
                WHERE tracking_code = ?
                """,
                (code,)
            ).fetchone()

            if not exists:
                return code

        raise RuntimeError(
            "امکان ساخت کد پیگیری وجود ندارد."
        )

    finally:
        db.close()


def current_user():

    user_id = session.get(
        "admin_id"
    )

    if not user_id:
        return None

    db = get_db()

    user = db.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND active = 1
        """,
        (user_id,)
    ).fetchone()

    db.close()

    return user


def is_admin():

    user = current_user()

    return bool(
        user
        and user["role"] == "admin"
    )


def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if not session.get("admin_id"):
            return redirect(
                url_for("admin_login")
            )

        if not current_user():
            session.clear()

            return redirect(
                url_for("admin_login")
            )

        return func(
            *args,
            **kwargs
        )

    return wrapper


def get_request(rid):

    db = get_db()

    result = db.execute(
        """
        SELECT
            r.*,
            c.name AS customer_name,
            c.national_id AS national_id,
            c.phone AS customer_phone,
            s.name AS service_name,
            s.description AS service_description,
            s.category AS service_category,
            u.username AS expert_username
        FROM requests r
        JOIN customers c
            ON c.id = r.customer_id
        JOIN services s
            ON s.id = r.service_id
        LEFT JOIN users u
            ON u.id = r.expert_id
        WHERE r.id = ?
        """,
        (rid,)
    ).fetchone()

    db.close()

    return result


def get_service_fields(service):

    try:
        data = json.loads(
            service["fields_json"] or "[]"
        )

        return data if isinstance(
            data,
            list
        ) else []

    except Exception:
        return []


def get_service_documents(service):

    try:
        data = json.loads(
            service["documents_json"] or "[]"
        )

        return data if isinstance(
            data,
            list
        ) else []

    except Exception:
        return []


def notify(
    recipient_type,
    recipient_id,
    title,
    message,
    request_id=None,
    notification_type="system"
):

    db = get_db()

    db.execute(
        """
        INSERT INTO notifications
        (
            recipient_type,
            recipient_id,
            request_id,
            type,
            title,
            message
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            recipient_type,
            recipient_id,
            request_id,
            notification_type,
            title,
            message
        )
    )

    db.commit()
    db.close()


def notify_admins(
    title,
    message,
    request_id=None,
    notification_type="system"
):

    db = get_db()

    admins = db.execute(
        """
        SELECT id
        FROM users
        WHERE role = 'admin'
        AND active = 1
        """
    ).fetchall()

    for admin in admins:

        db.execute(
            """
            INSERT INTO notifications
            (
                recipient_type,
                recipient_id,
                request_id,
                type,
                title,
                message
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "admin",
                admin["id"],
                request_id,
                notification_type,
                title,
                message
            )
        )

    db.commit()
    db.close()


def notify_expert(
    expert_id,
    title,
    message,
    request_id=None,
    notification_type="system"
):

    if not expert_id:
        return

    notify(
        "expert",
        expert_id,
        title,
        message,
        request_id,
        notification_type
    )


def notify_customer(
    customer_id,
    title,
    message,
    request_id=None,
    notification_type="system"
):

    notify(
        "customer",
        customer_id,
        title,
        message,
        request_id,
        notification_type
    )


def calculate_discount(
    service_id,
    code,
    base_price
):

    if not code:
        return {
            "valid": False,
            "amount": 0,
            "message": ""
        }

    code = code.strip().upper()

    db = get_db()

    discount = db.execute(
        """
        SELECT *
        FROM discounts
        WHERE code = ?
        AND active = 1
        """,
        (code,)
    ).fetchone()

    if not discount:

        db.close()

        return {
            "valid": False,
            "amount": 0,
            "message": "کد تخفیف معتبر نیست."
        }

    now = datetime.utcnow().strftime(
        "%Y-%m-%d"
    )

    if (
        discount["start_date"]
        and now < discount["start_date"]
    ):

        db.close()

        return {
            "valid": False,
            "amount": 0,
            "message": "زمان استفاده از این کد هنوز شروع نشده است."
        }

    if (
        discount["end_date"]
        and now > discount["end_date"]
    ):

        db.close()

        return {
            "valid": False,
            "amount": 0,
            "message": "زمان استفاده از این کد به پایان رسیده است."
        }

    if (
        discount["max_uses"] > 0
        and discount["used_count"]
        >= discount["max_uses"]
    ):

        db.close()

        return {
            "valid": False,
            "amount": 0,
            "message": "ظرفیت استفاده از این کد تکمیل شده است."
        }

    service_link = db.execute(
        """
        SELECT service_id
        FROM discount_services
        WHERE discount_id = ?
        AND service_id = ?
        """,
        (
            discount["id"],
            service_id
        )
    ).fetchone()

    linked_count = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM discount_services
        WHERE discount_id = ?
        """,
        (discount["id"],)
    ).fetchone()["count"]

    db.close()

    if linked_count > 0 and not service_link:

        return {
            "valid": False,
            "amount": 0,
            "message": "این کد برای این خدمت قابل استفاده نیست."
        }

    if discount["kind"] == "percent":

        amount = int(
            base_price
            * discount["value"]
            / 100
        )

    else:

        amount = int(
            discount["value"]
        )

    amount = max(
        0,
        min(
            amount,
            base_price
        )
    )

    return {
        "valid": True,
        "amount": amount,
        "discount_id": discount["id"],
        "message": "کد تخفیف با موفقیت اعمال شد."
    }


def record_payment(
    request_id,
    customer_id,
    amount,
    reference="",
    description="پرداخت"
):

    if amount <= 0:
        return

    db = get_db()

    db.execute(
        """
        INSERT INTO financial_transactions
        (
            request_id,
            customer_id,
            type,
            amount,
            description,
            reference
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            customer_id,
            "income",
            amount,
            description,
            reference
        )
    )

    db.commit()
    db.close()


def save_uploaded_files(
    request_id,
    files,
    uploaded_by="customer",
    uploaded_by_id=None
):

    db = get_db()

    for file in files:

        if not file:
            continue

        if not file.filename:
            continue

        if not allowed_file(
            file.filename
        ):
            continue

        original_name = secure_filename(
            file.filename
        )

        extension = ""

        if "." in original_name:

            extension = (
                "."
                + original_name.rsplit(
                    ".",
                    1
                )[1].lower()
            )

        stored_name = (
            uuid.uuid4().hex
            + extension
        )

        folder = os.path.join(
            app.config["UPLOAD_FOLDER"],
            str(request_id)
        )

        os.makedirs(
            folder,
            exist_ok=True
        )

        file.save(
            os.path.join(
                folder,
                stored_name
            )
        )

        db.execute(
            """
            INSERT INTO documents
            (
                request_id,
                original_name,
                stored_name,
                uploaded_by,
                uploaded_by_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                request_id,
                original_name,
                stored_name,
                uploaded_by,
                uploaded_by_id
            )
        )

    db.commit()
    db.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    db = get_db()

    services = db.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        AND parent_id IS NULL
        ORDER BY sort_order ASC, id DESC
        """
    ).fetchall()

    db.close()

    settings = get_settings()

    return render_template(
        "home.html",
        services=services,
        settings=settings,
        site_name=settings.get(
            "site_name",
            SITE_NAME
        ),
        manager=settings.get(
            "manager_name",
            MANAGER
        ),
        phone=settings.get(
            "phone",
            PHONE
        )
    )


# =========================================================
# SERVICE
# =========================================================

@app.route(
    "/service/<int:service_id>"
)
def service(service_id):

    db = get_db()

    service_row = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    if not service_row:

        db.close()

        return "خدمت پیدا نشد", 404

    subservices = db.execute(
        """
        SELECT *
        FROM services
        WHERE parent_id = ?
        AND active = 1
        ORDER BY sort_order ASC, id DESC
        """,
        (service_id,)
    ).fetchall()

    db.close()

    return render_template(
        "service.html",
        service=service_row,
        fields=get_service_fields(
            service_row
        ),
        documents=get_service_documents(
            service_row
        ),
        subservices=subservices
    )


# =========================================================
# DISCOUNT API
# =========================================================

@app.route(
    "/service/<int:service_id>/discount",
    methods=["POST"]
)
def service_discount(service_id):

    db = get_db()

    service_row = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    db.close()

    if not service_row:

        return jsonify({
            "valid": False,
            "message": "خدمت پیدا نشد."
        }), 404

    code = request.form.get(
        "code",
        ""
    )

    result = calculate_discount(
        service_id,
        code,
        int(service_row["price"] or 0)
    )

    return jsonify(result)


# =========================================================
# CREATE REQUEST
# =========================================================

@app.route(
    "/service/<int:service_id>/request",
    methods=["POST"]
)
def create_request(service_id):

    db = get_db()

    service_row = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    if not service_row:

        db.close()

        return "خدمت پیدا نشد", 404

    selected_service_id = service_id

    subservice_id = request.form.get(
        "subservice_id",
        type=int
    )

    if subservice_id:

        subservice = db.execute(
            """
            SELECT *
            FROM services
            WHERE id = ?
            AND parent_id = ?
            AND active = 1
            """,
            (
                subservice_id,
                service_id
            )
        ).fetchone()

        if subservice:

            selected_service_id = subservice_id
            service_row = subservice

    name = request.form.get(
        "name",
        ""
    ).strip()

    national_id = request.form.get(
        "national_id",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    customer_note = request.form.get(
        "customer_note",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    discount_code = request.form.get(
        "discount_code",
        ""
    ).strip()

    if not name or not phone:

        db.close()

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

    customer = db.execute(
        """
        SELECT *
        FROM customers
        WHERE phone = ?
        """,
        (phone,)
    ).fetchone()

    if customer:

        customer_id = customer["id"]

        db.execute(
            """
            UPDATE customers
            SET
                name = ?,
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

        cursor = db.execute(
            """
            INSERT INTO customers
            (
                name,
                national_id,
                phone
            )
            VALUES (?, ?, ?)
            """,
            (
                name,
                national_id,
                phone
            )
        )

        customer_id = cursor.lastrowid

    base_price = int(
        service_row["price"] or 0
    )

    discount_result = calculate_discount(
        selected_service_id,
        discount_code,
        base_price
    )

    discount_amount = 0
    discount_id = None

    if discount_result["valid"]:

        discount_amount = discount_result["amount"]
        discount_id = discount_result.get(
            "discount_id"
        )

    final_price = max(
        0,
        base_price - discount_amount
    )

    payment_status = (
        "paid"
        if final_price == 0
        else "unpaid"
    )

    tracking_code = generate_tracking_code()

    cursor = db.execute(
        """
        INSERT INTO requests
        (
            customer_id,
            service_id,
            tracking_code,
            status,
            customer_note,
            description,
            total_price,
            paid_price,
            discount_amount,
            payment_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            selected_service_id,
            tracking_code,
            "جدید",
            customer_note,
            description,
            final_price,
            0,
            discount_amount,
            payment_status
        )
    )

    request_id = cursor.lastrowid

    if final_price == 0 and discount_id:

        db.execute(
            """
            UPDATE discounts
            SET used_count = used_count + 1
            WHERE id = ?
            """,
            (discount_id,)
        )

    db.commit()
    db.close()

    files = request.files.getlist(
        "documents"
    )

    save_uploaded_files(
        request_id,
        files,
        "customer",
        customer_id
    )

    notify_customer(
        customer_id,
        "درخواست شما ثبت شد",
        f"کد پیگیری شما: {tracking_code}",
        request_id,
        "new_request"
    )

    notify_admins(
        "درخواست جدید",
        f"درخواست جدید با کد {tracking_code} ثبت شد.",
        request_id,
        "new_request"
    )

    return redirect(
        url_for(
            "request_success",
            tracking_code=tracking_code
        )
    )


# =========================================================
# REQUEST SUCCESS
# =========================================================

@app.route(
    "/request/success/<tracking_code>"
)
def request_success(tracking_code):

    return render_template(
        "request_success.html",
        tracking_code=tracking_code
    )


# =========================================================
# TRACKING
# =========================================================

@app.route(
    "/tracking",
    methods=["GET", "POST"]
)
def tracking():

    result = None

    if request.method == "POST":

        code = request.form.get(
            "tracking_code",
            ""
        ).strip()

        db = get_db()

        result = db.execute(
            """
            SELECT
                r.*,
                c.name AS customer_name,
                c.phone AS customer_phone,
                s.name AS service_name
            FROM requests r
            JOIN customers c
                ON c.id = r.customer_id
            JOIN services s
                ON s.id = r.service_id
            WHERE r.tracking_code = ?
            """,
            (code,)
        ).fetchone()

        db.close()

        if not result:

            flash(
                "کد پیگیری پیدا نشد.",
                "error"
            )

    return render_template(
        "tracking.html",
        result=result,
        statuses=STATUSES
    )


# =========================================================
# CUSTOMER REQUEST
# =========================================================

@app.route(
    "/request/<tracking_code>"
)
def customer_request(tracking_code):

    db = get_db()

    req = db.execute(
        """
        SELECT
            r.*,
            c.name AS customer_name,
            c.national_id,
            c.phone AS customer_phone,
            s.name AS service_name
        FROM requests r
        JOIN customers c
            ON c.id = r.customer_id
        JOIN services s
            ON s.id = r.service_id
        WHERE r.tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()

    if not req:

        db.close()

        return "پرونده پیدا نشد", 404

    documents = db.execute(
        """
        SELECT *
        FROM documents
        WHERE request_id = ?
        ORDER BY id DESC
        """,
        (req["id"],)
    ).fetchall()

    messages = db.execute(
        """
        SELECT *
        FROM messages
        WHERE request_id = ?
        ORDER BY id ASC
        """,
        (req["id"],)
    ).fetchall()

    db.close()

    return render_template(
        "request.html",
        req=req,
        documents=documents,
        messages=messages,
        statuses=STATUSES
    )


# =========================================================
# CUSTOMER UPLOAD
# =========================================================

@app.route(
    "/request/<tracking_code>/upload",
    methods=["POST"]
)
def customer_upload(tracking_code):

    db = get_db()

    req = db.execute(
        """
        SELECT
            id,
            customer_id
        FROM requests
        WHERE tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()

    db.close()

    if not req:
        return "پرونده پیدا نشد", 404

    files = request.files.getlist(
        "documents"
    )

    save_uploaded_files(
        req["id"],
        files,
        "customer",
        req["customer_id"]
    )

    notify_admins(
        "مدرک جدید",
        f"برای پرونده {tracking_code} مدرک جدید ارسال شده است.",
        req["id"],
        "message"
    )

    return redirect(
        url_for(
            "customer_request",
            tracking_code=tracking_code
        )
    )


# =========================================================
# CUSTOMER MESSAGE
# =========================================================

@app.route(
    "/request/<tracking_code>/message",
    methods=["POST"]
)
def customer_message(tracking_code):

    message = request.form.get(
        "message",
        ""
    ).strip()

    file = request.files.get(
        "attachment"
    )

    db = get_db()

    req = db.execute(
        """
        SELECT
            id,
            customer_id,
            expert_id
        FROM requests
        WHERE tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()

    db.close()

    if not req:
        return "پرونده پیدا نشد", 404

    attachment_name = None
    attachment_stored_name = None

    if file and file.filename:

        if allowed_file(
            file.filename
        ):

            attachment_name = secure_filename(
                file.filename
            )

            extension = ""

            if "." in attachment_name:

                extension = (
                    "."
                    + attachment_name.rsplit(
                        ".",
                        1
                    )[1].lower()
                )

            attachment_stored_name = (
                uuid.uuid4().hex
                + extension
            )

            folder = os.path.join(
                app.config["UPLOAD_FOLDER"],
                str(req["id"])
            )

            os.makedirs(
                folder,
                exist_ok=True
            )

            file.save(
                os.path.join(
                    folder,
                    attachment_stored_name
                )
            )

    if not message and not attachment_name:

        return redirect(
            url_for(
                "customer_request",
                tracking_code=tracking_code
            )
        )

    db = get_db()

    db.execute(
        """
        INSERT INTO messages
        (
            request_id,
            sender_type,
            sender_id,
            message,
            attachment_name,
            attachment_stored_name
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            req["id"],
            "customer",
            req["customer_id"],
            message,
            attachment_name,
            attachment_stored_name
        )
    )

    db.commit()
    db.close()

    notify_admins(
        "پیام جدید مشتری",
        f"برای پرونده {tracking_code} پیام جدید ارسال شده است.",
        req["id"],
        "message"
    )

    if req["expert_id"]:

        notify_expert(
            req["expert_id"],
            "پیام جدید مشتری",
            f"برای پرونده {tracking_code} پیام جدید ارسال شده است.",
            req["id"],
            "message"
        )

    return redirect(
        url_for(
            "customer_request",
            tracking_code=tracking_code
        )
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        db = get_db()

        user = db.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            AND active = 1
            """,
            (username,)
        ).fetchone()

        db.close()

        if user:

            try:
                valid = check_password_hash(
                    user["password_hash"],
                    password
                )
            except Exception:
                valid = False

            if valid:

                session.clear()

                session["admin_id"] = user["id"]

                return redirect(
                    url_for("admin")
                )

        flash(
            "نام کاربری یا رمز عبور اشتباه است.",
            "error"
        )

    return render_template(
        "admin_login.html"
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@admin_required
def admin():

    user = current_user()

    db = get_db()

    requests = db.execute(
        """
        SELECT
            r.*,
            c.name AS customer_name,
            c.phone AS customer_phone,
            s.name AS service_name,
            u.username AS expert_username
        FROM requests r
        JOIN customers c
            ON c.id = r.customer_id
        JOIN services s
            ON s.id = r.service_id
        LEFT JOIN users u
            ON u.id = r.expert_id
        ORDER BY r.id DESC
        """
    ).fetchall()

    customers = db.execute(
        """
        SELECT
            c.*,
            COUNT(r.id) AS request_count
        FROM customers c
        LEFT JOIN requests r
            ON r.customer_id = c.id
        GROUP BY c.id
        ORDER BY c.id DESC
        """
    ).fetchall()

    services = db.execute(
        """
        SELECT *
        FROM services
        ORDER BY
            parent_id ASC,
            sort_order ASC,
            id DESC
        """
    ).fetchall()

    experts = db.execute(
        """
        SELECT *
        FROM users
        WHERE role = 'expert'
        ORDER BY id DESC
        """
    ).fetchall()

    discounts = db.execute(
        """
        SELECT *
        FROM discounts
        ORDER BY id DESC
        """
    ).fetchall()

    expert_permissions = db.execute(
        """
        SELECT *
        FROM expert_services
        """
    ).fetchall()

    total_income = db.execute(
        """
        SELECT COALESCE(
            SUM(amount),
            0
        )
        FROM financial_transactions
        WHERE type = 'income'
        """
    ).fetchone()[0]

    total_debt = db.execute(
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

    unread_notifications = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE recipient_type = 'admin'
        AND recipient_id = ?
        AND is_read = 0
        """,
        (user["id"],)
    ).fetchone()["count"]

    notifications = db.execute(
        """
        SELECT *
        FROM notifications
        WHERE recipient_type = 'admin'
        AND recipient_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (user["id"],)
    ).fetchall()

    settings_rows = db.execute(
        """
        SELECT *
        FROM settings
        ORDER BY key
        """
    ).fetchall()

    db.close()

    settings = {
        row["key"]: row["value"]
        for row in settings_rows
    }

    return render_template(
        "admin.html",
        requests=requests,
        customers=customers,
        services=services,
        experts=experts,
        discounts=discounts,
        expert_permissions=expert_permissions,
        notifications=notifications,
        unread_notifications=unread_notifications,
        total_income=total_income,
        total_debt=total_debt,
        current_user=user,
        statuses=STATUSES,
        settings=settings
    )


# =========================================================
# ADMIN REQUEST
# =========================================================

@app.route(
    "/admin/request/<int:rid>"
)
@admin_required
def admin_request(rid):

    req = get_request(rid)

    if not req:
        return "پرونده پیدا نشد", 404

    user = current_user()

    db = get_db()

    documents = db.execute(
        """
        SELECT *
        FROM documents
        WHERE request_id = ?
        ORDER BY id DESC
        """,
        (rid,)
    ).fetchall()

    messages = db.execute(
        """
        SELECT *
        FROM messages
        WHERE request_id = ?
        ORDER BY id ASC
        """,
        (rid,)
    ).fetchall()

    experts = db.execute(
        """
        SELECT *
        FROM users
        WHERE role = 'expert'
        AND active = 1
        """
    ).fetchall()

    services = db.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        ORDER BY parent_id, sort_order, id
        """
    ).fetchall()

    db.close()

    if user["role"] == "admin":
        can_view = True

    elif (
        user["role"] == "expert"
        and req["expert_id"] == user["id"]
    ):
        can_view = True

    elif (
        user["role"] == "expert"
        and not req["expert_id"]
        and req["payment_status"] == "paid"
    ):
        can_view = True

    else:
        can_view = False

    if not can_view:

        return (
            "این پرونده به کارشناس دیگری اختصاص داده شده است.",
            403
        )

    return render_template(
        "admin_request.html",
        req=req,
        documents=documents,
        messages=messages,
        experts=experts,
        services=services,
        statuses=STATUSES
    )


# =========================================================
# EXPERT ACCEPT REQUEST
# =========================================================

@app.route(
    "/admin/request/<int:rid>/accept",
    methods=["POST"]
)
@admin_required
def accept_request(rid):

    user = current_user()

    if user["role"] != "expert":

        return (
            "فقط کارشناس می‌تواند پرونده را پذیرش کند.",
            403
        )

    db = get_db()

    req = db.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if not req:

        db.close()

        return "پرونده پیدا نشد", 404

    if req["payment_status"] != "paid":

        db.close()

        flash(
            "تا زمانی که پرداخت انجام نشده باشد، پرونده قابل پذیرش نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    if req["expert_id"]:

        db.close()

        flash(
            "این پرونده قبلاً توسط کارشناس دیگری پذیرش شده است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    permission = db.execute(
        """
        SELECT 1
        FROM expert_services
        WHERE user_id = ?
        AND service_id = ?
        """,
        (
            user["id"],
            req["service_id"]
        )
    ).fetchone()

    if not permission:

        db.close()

        flash(
            "این خدمت برای شما اختصاص داده نشده است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    now = datetime.utcnow().isoformat()

    db.execute(
        """
        UPDATE requests
        SET
            expert_id = ?,
            assigned_at = ?,
            accepted_at = ?,
            status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        AND expert_id IS NULL
        """,
        (
            user["id"],
            now,
            now,
            "پذیرش شد",
            rid
        )
    )

    db.commit()
    db.close()

    notify_customer(
        req["customer_id"],
        "پرونده شما پذیرش شد",
        "پرونده شما توسط کارشناس پذیرش شد.",
        rid,
        "assignment"
    )

    notify_admins(
        "پذیرش پرونده",
        f"پرونده {req['tracking_code']} توسط {user['username']} پذیرش شد.",
        rid,
        "assignment"
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN STATUS
# =========================================================

@app.route(
    "/admin/request/status",
    methods=["POST"]
)
@admin_required
def admin_request_status():

    rid = request.form.get(
        "id",
        type=int
    )

    status = request.form.get(
        "status",
        "جدید"
    )

    if not rid:
        return redirect(
            url_for("admin")
        )

    if status not in STATUSES:

        flash(
            "وضعیت انتخاب‌شده معتبر نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    db = get_db()

    req = db.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if not req:

        db.close()

        return "پرونده پیدا نشد", 404

    user = current_user()

    if (
        user["role"] == "expert"
        and req["expert_id"] != user["id"]
    ):

        db.close()

        return "دسترسی غیرمجاز", 403

    db.execute(
        """
        UPDATE requests
        SET
            status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            status,
            rid
        )
    )

    db.commit()
    db.close()

    notify_customer(
        req["customer_id"],
        "تغییر وضعیت پرونده",
        f"وضعیت پرونده شما به «{status}» تغییر کرد.",
        rid,
        "status_change"
    )

    if req["expert_id"]:

        notify_expert(
            req["expert_id"],
            "تغییر وضعیت پرونده",
            f"وضعیت پرونده {req['tracking_code']} تغییر کرد.",
            rid,
            "status_change"
        )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN REQUEST UPDATE
# =========================================================

@app.route(
    "/admin/request/update",
    methods=["POST"]
)
@admin_required
def admin_request_update():

    rid = request.form.get(
        "id",
        type=int
    )

    if not rid:
        return redirect(
            url_for("admin")
        )

    total_price = request.form.get(
        "total_price",
        type=int
    )

    paid_price = request.form.get(
        "paid_price",
        type=int
    )

    total_price = total_price or 0
    paid_price = paid_price or 0

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    estimated_time = request.form.get(
        "estimated_time",
        ""
    ).strip()

    expert_id = request.form.get(
        "expert_id",
        type=int
    )

    db = get_db()

    req = db.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if not req:

        db.close()

        return "پرونده پیدا نشد", 404

    user = current_user()

    if user["role"] == "expert":

        if (
            req["expert_id"]
            and req["expert_id"] != user["id"]
        ):

            db.close()

            return "دسترسی غیرمجاز", 403

        expert_id = user["id"]

    total_price = max(
        0,
        total_price
    )

    paid_price = max(
        0,
        paid_price
    )

    paid_price = min(
        paid_price,
        total_price
    )

    if total_price == 0:
        payment_status = "paid"

    elif paid_price >= total_price:
        payment_status = "paid"

    elif paid_price > 0:
        payment_status = "partial"

    else:
        payment_status = "unpaid"

    db.execute(
        """
        UPDATE requests
        SET
            total_price = ?,
            paid_price = ?,
            admin_note = ?,
            description = ?,
            estimated_time = ?,
            expert_id = ?,
            payment_status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            total_price,
            paid_price,
            admin_note,
            description,
            estimated_time,
            expert_id,
            payment_status,
            rid
        )
    )

    db.commit()
    db.close()

    old_paid = req["paid_price"] or 0

    if paid_price > old_paid:

        difference = (
            paid_price
            - old_paid
        )

        record_payment(
            rid,
            req["customer_id"],
            difference,
            "",
            "ثبت پرداخت پرونده"
        )

    if (
        req["payment_status"] != "paid"
        and payment_status == "paid"
    ):

        notify_customer(
            req["customer_id"],
            "پرداخت تایید شد",
            "پرداخت پرونده شما با موفقیت ثبت شد.",
            rid,
            "payment"
        )

        notify_admins(
            "پرداخت تکمیل شد",
            f"پرداخت پرونده {req['tracking_code']} تکمیل شد.",
            rid,
            "payment"
        )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN MESSAGE
# =========================================================

@app.route(
    "/admin/request/message",
    methods=["POST"]
)
@admin_required
def admin_message():

    rid = request.form.get(
        "id",
        type=int
    )

    message = request.form.get(
        "message",
        ""
    ).strip()

    file = request.files.get(
        "attachment"
    )

    user = current_user()

    db = get_db()

    req = db.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if not req:

        db.close()

        return "پرونده پیدا نشد", 404

    if (
        user["role"] == "expert"
        and req["expert_id"] != user["id"]
    ):

        db.close()

        return "دسترسی غیرمجاز", 403

    attachment_name = None
    attachment_stored_name = None

    if file and file.filename:

        if allowed_file(
            file.filename
        ):

            attachment_name = secure_filename(
                file.filename
            )

            extension = ""

            if "." in attachment_name:

                extension = (
                    "."
                    + attachment_name.rsplit(
                        ".",
                        1
                    )[1].lower()
                )

            attachment_stored_name = (
                uuid.uuid4().hex
                + extension
            )

            folder = os.path.join(
                app.config["UPLOAD_FOLDER"],
                str(rid)
            )

            os.makedirs(
                folder,
                exist_ok=True
            )

            file.save(
                os.path.join(
                    folder,
                    attachment_stored_name
                )
            )

    if not message and not attachment_name:

        db.close()

        return redirect(
            url_for(
                "admin_request",
                rid=rid
            )
        )

    db.execute(
        """
        INSERT INTO messages
        (
            request_id,
            sender_type,
            sender_id,
            message,
            attachment_name,
            attachment_stored_name
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            user["role"],
            user["id"],
            message,
            attachment_name,
            attachment_stored_name
        )
    )

    db.commit()
    db.close()

    notify_customer(
        req["customer_id"],
        "پیام جدید",
        "برای پرونده شما پیام جدید ارسال شده است.",
        rid,
        "message"
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# DOCUMENT DOWNLOAD
# =========================================================

@app.route(
    "/document/<int:document_id>"
)
@admin_required
def download_document(document_id):

    db = get_db()

    document = db.execute(
        """
        SELECT *
        FROM documents
        WHERE id = ?
        """,
        (document_id,)
    ).fetchone()

    db.close()

    if not document:
        return "فایل پیدا نشد", 404

    directory = os.path.join(
        app.config["UPLOAD_FOLDER"],
        str(document["request_id"])
    )

    return send_from_directory(
        directory,
        document["stored_name"],
        as_attachment=True,
        download_name=document["original_name"]
    )


# =========================================================
# MESSAGE FILE
# =========================================================

@app.route(
    "/message/file/<int:message_id>"
)
def message_file(message_id):

    db = get_db()

    message = db.execute(
        """
        SELECT *
        FROM messages
        WHERE id = ?
        """,
        (message_id,)
    ).fetchone()

    db.close()

    if not message:
        return "فایل پیدا نشد", 404

    stored_name = message[
        "attachment_stored_name"
    ]

    if not stored_name:
        return "فایل وجود ندارد", 404

    folder = os.path.join(
        app.config["UPLOAD_FOLDER"],
        str(message["request_id"])
    )

    return send_from_directory(
        folder,
        stored_name,
        as_attachment=False,
        download_name=message["attachment_name"]
    )


# =========================================================
# SERVICE SAVE
# =========================================================

@app.route(
    "/admin/service/save",
    methods=["POST"]
)
@admin_required
def admin_service_save():

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    name = request.form.get(
        "name",
        ""
    ).strip()

    if not name:

        flash(
            "نام خدمت الزامی است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    category = request.form.get(
        "category",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    price = request.form.get(
        "price",
        type=int
    ) or 0

    sort_order = request.form.get(
        "sort_order",
        type=int
    ) or 0

    active = request.form.get(
        "active",
        "1"
    )

    fields_json = request.form.get(
        "fields_json",
        "[]"
    )

    documents_json = request.form.get(
        "documents_json",
        "[]"
    )

    code = request.form.get(
        "code",
        ""
    ).strip()

    parent_id = request.form.get(
        "parent_id",
        type=int
    )

    try:

        data = json.loads(
            fields_json
        )

        if not isinstance(
            data,
            list
        ):
            fields_json = "[]"

    except Exception:

        fields_json = "[]"

    try:

        data = json.loads(
            documents_json
        )

        if not isinstance(
            data,
            list
        ):
            documents_json = "[]"

    except Exception:

        documents_json = "[]"

    if price < 0:
        price = 0

    if sort_order < 0:
        sort_order = 0

    db = get_db()

    if parent_id:

        parent = db.execute(
            """
            SELECT id
            FROM services
            WHERE id = ?
            """,
            (parent_id,)
        ).fetchone()

        if not parent:
            parent_id = None

    db.execute(
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
            documents_json,
            code,
            parent_id,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            name,
            category,
            description,
            price,
            sort_order,
            1 if active == "1" else 0,
            fields_json,
            documents_json,
            code,
            parent_id
        )
    )

    db.commit()
    db.close()

    flash(
        "خدمت با موفقیت اضافه شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# SERVICE UPDATE
# =========================================================

@app.route(
    "/admin/service/<int:service_id>/update",
    methods=["POST"]
)
@admin_required
def update_service(service_id):

    if not is_admin():
        return "دسترسی غیرمجاز", 403

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

    price = request.form.get(
        "price",
        type=int
    ) or 0

    sort_order = request.form.get(
        "sort_order",
        type=int
    ) or 0

    active = request.form.get(
        "active",
        "0"
    )

    fields_json = request.form.get(
        "fields_json",
        "[]"
    )

    documents_json = request.form.get(
        "documents_json",
        "[]"
    )

    code = request.form.get(
        "code",
        ""
    ).strip()

    parent_id = request.form.get(
        "parent_id",
        type=int
    )

    if not name:

        flash(
            "نام خدمت الزامی است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    price = max(
        0,
        price
    )

    sort_order = max(
        0,
        sort_order
    )

    try:

        data = json.loads(
            fields_json
        )

        if not isinstance(
            data,
            list
        ):
            fields_json = "[]"

    except Exception:

        fields_json = "[]"

    try:

        data = json.loads(
            documents_json
        )

        if not isinstance(
            data,
            list
        ):
            documents_json = "[]"

    except Exception:

        documents_json = "[]"

    db = get_db()

    service_row = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        """,
        (service_id,)
    ).fetchone()

    if not service_row:

        db.close()

        flash(
            "خدمت پیدا نشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    if parent_id == service_id:
        parent_id = None

    if parent_id:

        parent = db.execute(
            """
            SELECT id
            FROM services
            WHERE id = ?
            """,
            (parent_id,)
        ).fetchone()

        if not parent:
            parent_id = None

    db.execute(
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
            code = ?,
            parent_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            name,
            category,
            description,
            price,
            sort_order,
            1 if active == "1" else 0,
            fields_json,
            documents_json,
            code,
            parent_id,
            service_id
        )
    )

    db.commit()
    db.close()

    flash(
        "خدمت با موفقیت ویرایش شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# SERVICE DELETE
# =========================================================

@app.route(
    "/admin/service/<int:service_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_service(service_id):

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    db = get_db()

    service_row = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        """,
        (service_id,)
    ).fetchone()

    if not service_row:

        db.close()

        flash(
            "خدمت پیدا نشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    request_count = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM requests
        WHERE service_id = ?
        """,
        (service_id,)
    ).fetchone()["count"]

    if request_count > 0:

        db.execute(
            """
            UPDATE services
            SET
                active = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (service_id,)
        )

        message = (
            "این خدمت دارای پرونده است و "
            "برای حفظ سوابق غیرفعال شد."
        )

    else:

        db.execute(
            """
            DELETE FROM services
            WHERE id = ?
            """,
            (service_id,)
        )

        message = "خدمت حذف شد."

    db.commit()
    db.close()

    flash(
        message,
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# SERVICE TOGGLE
# =========================================================

@app.route(
    "/admin/service/<int:service_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_service(service_id):

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    db = get_db()

    service_row = db.execute(
        """
        SELECT active
        FROM services
        WHERE id = ?
        """,
        (service_id,)
    ).fetchone()

    if not service_row:

        db.close()

        flash(
            "خدمت پیدا نشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    new_status = (
        0
        if service_row["active"]
        else 1
    )

    db.execute(
        """
        UPDATE services
        SET
            active = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            new_status,
            service_id
        )
    )

    db.commit()
    db.close()

    flash(
        "وضعیت خدمت تغییر کرد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# EXPERT SAVE
# =========================================================

@app.route(
    "/admin/expert/save",
    methods=["POST"]
)
@admin_required
def admin_expert_save():

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    if not username or not password:

        flash(
            "نام کاربری و رمز عبور الزامی است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    db = get_db()

    existing = db.execute(
        """
        SELECT id
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    if existing:

        db.close()

        flash(
            "این نام کاربری قبلاً وجود دارد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    db.execute(
        """
        INSERT INTO users
        (
            username,
            password_hash,
            role,
            active
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            username,
            generate_password_hash(password),
            "expert",
            1
        )
    )

    db.commit()
    db.close()

    flash(
        "کارشناس با موفقیت اضافه شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# EXPERT TOGGLE
# =========================================================

@app.route(
    "/admin/expert/<int:user_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_expert(user_id):

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    db = get_db()

    user = db.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND role = 'expert'
        """,
        (user_id,)
    ).fetchone()

    if not user:

        db.close()

        flash(
            "کارشناس پیدا نشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    new_status = (
        0
        if user["active"]
        else 1
    )

    db.execute(
        """
        UPDATE users
        SET active = ?
        WHERE id = ?
        """,
        (
            new_status,
            user_id
        )
    )

    db.commit()
    db.close()

    flash(
        "وضعیت کارشناس تغییر کرد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# EXPERT SERVICE PERMISSIONS
# =========================================================

@app.route(
    "/admin/expert/<int:user_id>/services",
    methods=["POST"]
)
@admin_required
def update_expert_services(user_id):

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    db = get_db()

    expert = db.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND role = 'expert'
        """,
        (user_id,)
    ).fetchone()

    if not expert:

        db.close()

        flash(
            "کارشناس پیدا نشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    service_ids = request.form.getlist(
        "service_ids"
    )

    db.execute(
        """
        DELETE FROM expert_services
        WHERE user_id = ?
        """,
        (user_id,)
    )

    for service_id in service_ids:

        try:
            service_id = int(
                service_id
            )
        except (
            TypeError,
            ValueError
        ):
            continue

        exists = db.execute(
            """
            SELECT id
            FROM services
            WHERE id = ?
            """,
            (service_id,)
        ).fetchone()

        if exists:

            db.execute(
                """
                INSERT OR IGNORE INTO expert_services
                (
                    user_id,
                    service_id
                )
                VALUES (?, ?)
                """,
                (
                    user_id,
                    service_id
                )
            )

    db.commit()
    db.close()

    flash(
        "خدمات کارشناس به‌روزرسانی شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# DISCOUNT SAVE
# =========================================================

@app.route(
    "/admin/discount/save",
    methods=["POST"]
)
@admin_required
def admin_discount_save():

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    code = request.form.get(
        "code",
        ""
    ).strip().upper()

    kind = request.form.get(
        "kind",
        "percent"
    ).strip()

    value = request.form.get(
        "value",
        type=int
    ) or 0

    max_uses = request.form.get(
        "max_uses",
        type=int
    ) or 0

    start_date = request.form.get(
        "start_date",
        ""
    ).strip()

    end_date = request.form.get(
        "end_date",
        ""
    ).strip()

    service_ids = request.form.getlist(
        "service_ids"
    )

    if not code:

        flash(
            "کد تخفیف الزامی است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    if kind not in (
        "percent",
        "fixed"
    ):
        kind = "percent"

    value = max(
        0,
        value
    )

    if kind == "percent":
        value = min(
            100,
            value
        )

    max_uses = max(
        0,
        max_uses
    )

    db = get_db()

    existing = db.execute(
        """
        SELECT id
        FROM discounts
        WHERE code = ?
        """,
        (code,)
    ).fetchone()

    if existing:

        db.close()

        flash(
            "این کد تخفیف قبلاً ثبت شده است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    cursor = db.execute(
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
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            code,
            kind,
            value,
            max_uses,
            start_date or None,
            end_date or None,
            1
        )
    )

    discount_id = cursor.lastrowid

    for service_id in service_ids:

        try:
            service_id = int(
                service_id
            )
        except (
            TypeError,
            ValueError
        ):
            continue

        db.execute(
            """
            INSERT OR IGNORE INTO discount_services
            (
                discount_id,
                service_id
            )
            VALUES (?, ?)
            """,
            (
                discount_id,
                service_id
            )
        )

    db.commit()
    db.close()

    flash(
        "کد تخفیف ایجاد شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# DISCOUNT TOGGLE
# =========================================================

@app.route(
    "/admin/discount/<int:discount_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_discount(discount_id):

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    db = get_db()

    discount = db.execute(
        """
        SELECT active
        FROM discounts
        WHERE id = ?
        """,
        (discount_id,)
    ).fetchone()

    if not discount:

        db.close()

        flash(
            "کد تخفیف پیدا نشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    db.execute(
        """
        UPDATE discounts
        SET active = ?
        WHERE id = ?
        """,
        (
            0
            if discount["active"]
            else 1,
            discount_id
        )
    )

    db.commit()
    db.close()

    flash(
        "وضعیت کد تخفیف تغییر کرد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# SETTINGS SAVE
# =========================================================

@app.route(
    "/admin/settings/save",
    methods=["POST"]
)
@admin_required
def admin_settings_save():

    if not is_admin():
        return "دسترسی غیرمجاز", 403

    keys = [
        "site_name",
        "manager_name",
        "phone",
        "logo",
        "site_description",
        "home_title",
        "home_text",
        "card_color",
        "primary_color"
    ]

    db = get_db()

    for key in keys:

        value = request.form.get(
            key,
            ""
        ).strip()

        db.execute(
            """
            INSERT INTO settings
            (
                key,
                value
            )
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET
                value = excluded.value
            """,
            (
                key,
                value
            )
        )

    db.commit()
    db.close()

    flash(
        "تنظیمات سایت ذخیره شد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# NOTIFICATION READ
# =========================================================

@app.route(
    "/admin/notification/<int:notification_id>/read",
    methods=["POST"]
)
@admin_required
def notification_read(notification_id):

    user = current_user()

    db = get_db()

    db.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        AND recipient_id = ?
        """,
        (
            notification_id,
            user["id"]
        )
    )

    db.commit()
    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# CUSTOMER NOTIFICATIONS API
# =========================================================

@app.route(
    "/api/request/<tracking_code>/notifications"
)
def customer_notifications(tracking_code):

    db = get_db()

    req = db.execute(
        """
        SELECT id, customer_id
        FROM requests
        WHERE tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()

    if not req:

        db.close()

        return jsonify({
            "success": False,
            "message": "پرونده پیدا نشد."
        }), 404

    rows = db.execute(
        """
        SELECT
            id,
            type,
            title,
            message,
            is_read,
            created_at
        FROM notifications
        WHERE recipient_type = 'customer'
        AND recipient_id = ?
        AND (
            request_id = ?
            OR request_id IS NULL
        )
        ORDER BY id DESC
        LIMIT 50
        """,
        (
            req["customer_id"],
            req["id"]
        )
    ).fetchall()

    db.close()

    return jsonify({
        "success": True,
        "notifications": [
            dict(row)
            for row in rows
        ]
    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    try:

        db = get_db()

        db.execute(
            "SELECT 1"
        ).fetchone()

        db.close()

        return jsonify({
            "status": "ok",
            "database": "ok",
            "site": SITE_NAME
        })

    except Exception as error:

        return jsonify({
            "status": "error",
            "database": "error",
            "message": str(error)
        }), 500


# =========================================================
# API STATUS
# =========================================================

@app.route("/api/status")
def api_status():

    db = get_db()

    services_count = db.execute(
        """
        SELECT COUNT(*)
        FROM services
        WHERE active = 1
        """
    ).fetchone()[0]

    requests_count = db.execute(
        """
        SELECT COUNT(*)
        FROM requests
        """
    ).fetchone()[0]

    customers_count = db.execute(
        """
        SELECT COUNT(*)
        FROM customers
        """
    ).fetchone()[0]

    db.close()

    return jsonify({
        "success": True,
        "site": SITE_NAME,
        "services": services_count,
        "requests": requests_count,
        "customers": customers_count
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return (
        "حجم فایل بیشتر از حد مجاز است.",
        413
    )


@app.errorhandler(404)
def page_not_found(error):

    return (
        "صفحه مورد نظر پیدا نشد.",
        404
    )


@app.errorhandler(500)
def internal_error(error):

    return (
        "خطای داخلی سرور.",
        500
    )


# =========================================================
# RUN
# =========================================================

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
