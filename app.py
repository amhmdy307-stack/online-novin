import os
import json
import uuid
import sqlite3
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
    jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# =========================================================
# APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "CHANGE_THIS_SECRET_KEY"
)

SITE_NAME = "کافی نت آنلاین نوین"
MANAGER = "احمد محمدی مهر"

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

STATUSES = [
    "پذیرش شد",
    "در حال بررسی",
    "نقص مدارک",
    "قطعی سامانه",
    "رد شد",
    "انصراف مشتری",
    "انجام شد"
]

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    return conn


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
    table,
    column,
    definition
):

    columns = table_columns(
        db,
        table
    )

    if column not in columns:

        db.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )


def create_tables():

    db = get_db()

    # -----------------------------------------------------
    # CUSTOMERS
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            national_id TEXT,
            phone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------
    # SERVICES
    # -----------------------------------------------------

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
            parent_id INTEGER,
            service_code TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(parent_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # DISCOUNTS
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS discounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL,
            value INTEGER NOT NULL,
            service_id INTEGER,
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            start_date TEXT,
            end_date TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # REQUESTS
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            tracking_code TEXT UNIQUE NOT NULL,

            status TEXT DEFAULT 'پذیرش شد',

            estimated_time TEXT,

            customer_note TEXT,
            admin_note TEXT,

            total_price INTEGER DEFAULT 0,
            paid_price INTEGER DEFAULT 0,

            discount_id INTEGER,
            discount_amount INTEGER DEFAULT 0,

            payment_status TEXT DEFAULT 'unpaid',
            payment_ref TEXT,

            expert_id INTEGER,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE CASCADE,

            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE,

            FOREIGN KEY(discount_id)
                REFERENCES discounts(id)
                ON DELETE SET NULL,

            FOREIGN KEY(expert_id)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # -----------------------------------------------------
    # EXPERT SERVICES
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS expert_services (
            expert_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,

            PRIMARY KEY (
                expert_id,
                service_id
            ),

            FOREIGN KEY(expert_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # DOCUMENTS
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            request_id INTEGER NOT NULL,

            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,

            uploader_type TEXT DEFAULT 'customer',
            uploader_id INTEGER,

            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # MESSAGES
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # NOTIFICATIONS
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            recipient_type TEXT NOT NULL,
            recipient_id INTEGER,

            request_id INTEGER,

            title TEXT NOT NULL,
            message TEXT NOT NULL,

            is_read INTEGER DEFAULT 0,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # SETTINGS
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # -----------------------------------------------------
    # MIGRATION
    # -----------------------------------------------------

    add_column_if_missing(
        db,
        "services",
        "parent_id",
        "INTEGER"
    )

    add_column_if_missing(
        db,
        "services",
        "service_code",
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
        "discount_id",
        "INTEGER"
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
        "payment_ref",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "requests",
        "expert_id",
        "INTEGER"
    )

    add_column_if_missing(
        db,
        "documents",
        "uploader_type",
        "TEXT DEFAULT 'customer'"
    )

    add_column_if_missing(
        db,
        "documents",
        "uploader_id",
        "INTEGER"
    )

    add_column_if_missing(
        db,
        "messages",
        "attachment_name",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "messages",
        "attachment_stored_name",
        "TEXT"
    )

    # -----------------------------------------------------
    # DEFAULT ADMIN
    # -----------------------------------------------------

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
                role
            )
            VALUES (?, ?, ?)
            """,
            (
                "admin",
                generate_password_hash(password),
                "admin"
            )
        )

    # -----------------------------------------------------
    # DEFAULT SETTINGS
    # -----------------------------------------------------

    default_settings = {
        "card_color": "#ffffff",
        "primary_color": "#2563eb",
        "site_title": SITE_NAME,
        "manager": MANAGER
    }

    for key, value in default_settings.items():

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

    db.commit()
    db.close()


create_tables()


# =========================================================
# TEMPLATE SETTINGS
# =========================================================

@app.context_processor
def inject_global_data():

    db = get_db()

    rows = db.execute(
        """
        SELECT key, value
        FROM settings
        """
    ).fetchall()

    db.close()

    settings = {
        row["key"]: row["value"]
        for row in rows
    }

    return {
        "settings": settings,
        "site_name": SITE_NAME,
        "manager": MANAGER,
        "phone": PHONE,
        "statuses": STATUSES
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
        )[1].lower() in ALLOWED_EXTENSIONS
    )


def generate_tracking_code():

    db = get_db()

    try:

        while True:

            code = str(
                uuid.uuid4().int
            )[-4:]

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

        if not session.get(
            "admin_id"
        ):

            return redirect(
                url_for(
                    "admin_login"
                )
            )

        user = current_user()

        if not user or not user["active"]:

            session.clear()

            return redirect(
                url_for(
                    "admin_login"
                )
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


def create_notification(
    recipient_type,
    recipient_id,
    title,
    message,
    request_id=None
):

    db = get_db()

    db.execute(
        """
        INSERT INTO notifications
        (
            recipient_type,
            recipient_id,
            request_id,
            title,
            message
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            recipient_type,
            recipient_id,
            request_id,
            title,
            message
        )
    )

    db.commit()
    db.close()


def notify_admins(
    title,
    message,
    request_id=None
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
                title,
                message
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "admin",
                admin["id"],
                request_id,
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
    request_id=None
):

    if not expert_id:
        return

    create_notification(
        "expert",
        expert_id,
        title,
        message,
        request_id
    )


def notify_customer(
    customer_id,
    title,
    message,
    request_id=None
):

    create_notification(
        "customer",
        customer_id,
        title,
        message,
        request_id
    )


def get_discount(
    code,
    service_id
):

    if not code:
        return None

    db = get_db()

    discount = db.execute(
        """
        SELECT *
        FROM discounts
        WHERE code = ?
        AND active = 1
        AND (
            service_id IS NULL
            OR service_id = ?
        )
        """,
        (
            code.upper(),
            service_id
        )
    ).fetchone()

    db.close()

    if not discount:
        return None

    # max_uses = 0 یعنی نامحدود
    if (
        discount["max_uses"]
        and
        discount["used_count"]
        >= discount["max_uses"]
    ):
        return None

    return discount


def calculate_discount(
    price,
    discount
):

    if not discount:
        return 0

    if discount["kind"] == "percent":

        amount = int(
            price
            * discount["value"]
            / 100
        )

    else:

        amount = int(
            discount["value"]
        )

    if amount > price:
        amount = price

    if amount < 0:
        amount = 0

    return amount


def save_uploaded_files(
    request_id,
    files,
    uploader_type="customer",
    uploader_id=None
):

    db = get_db()

    folder = os.path.join(
        app.config["UPLOAD_FOLDER"],
        str(request_id)
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

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
                +
                original_name.rsplit(
                    ".",
                    1
                )[1].lower()
            )

        stored_name = (
            uuid.uuid4().hex
            +
            extension
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
                uploader_type,
                uploader_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                request_id,
                original_name,
                stored_name,
                uploader_type,
                uploader_id
            )
        )

    db.commit()
    db.close()


def can_expert_access(
    user_id,
    request_id
):

    db = get_db()

    req = db.execute(
        """
        SELECT
            r.*,
            es.expert_id AS allowed_expert

        FROM requests r

        LEFT JOIN expert_services es
            ON es.service_id = r.service_id
            AND es.expert_id = ?

        WHERE r.id = ?
        """,
        (
            user_id,
            request_id
        )
    ).fetchone()

    db.close()

    if not req:
        return False

    # پرونده‌ای که قبلاً پذیرش شده فقط برای همان کارشناس
    if req["expert_id"]:

        return (
            req["expert_id"]
            == user_id
        )

    return bool(
        req["allowed_expert"]
    )


def expert_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        user = current_user()

        if not user:
            return redirect(
                url_for("admin_login")
            )

        if user["role"] == "admin":
            return func(*args, **kwargs)

        if user["role"] != "expert":
            return "دسترسی غیرمجاز", 403

        rid = kwargs.get(
            "rid"
        )

        if rid is not None:

            if not can_expert_access(
                user["id"],
                rid
            ):
                return "این پرونده در دسترس شما نیست.", 403

        return func(
            *args,
            **kwargs
        )

    return wrapper


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
        ORDER BY
            sort_order ASC,
            id DESC
        """
    ).fetchall()

    db.close()

    return render_template(
        "home.html",
        services=services,
        site_name=SITE_NAME,
        manager=MANAGER,
        phone=PHONE
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

    children = db.execute(
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

    if not service_row:

        return "خدمت پیدا نشد", 404

    try:

        fields = json.loads(
            service_row["fields_json"]
            or "[]"
        )

    except Exception:

        fields = []

    try:

        documents = json.loads(
            service_row["documents_json"]
            or "[]"
        )

    except Exception:

        documents = []

    return render_template(
        "service.html",
        service=service_row,
        fields=fields,
        documents=documents,
        children=children
    )


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

    discount_code = request.form.get(
        "discount_code",
        ""
    ).strip().upper()

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

    # -----------------------------------------------------
    # CUSTOMER
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # PRICE
    # -----------------------------------------------------

    base_price = int(
        service_row["price"]
        or 0
    )

    discount = get_discount(
        discount_code,
        service_id
    )

    discount_amount = calculate_discount(
        base_price,
        discount
    )

    final_price = (
        base_price
        - discount_amount
    )

    if final_price < 0:
        final_price = 0

    if final_price == 0:

        payment_status = "paid"

    else:

        payment_status = "unpaid"

    tracking_code = generate_tracking_code()

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    status = "پذیرش شد"

    # -----------------------------------------------------
    # IMPORTANT
    #
    # درخواست قبل از پرداخت برای کارشناس ارسال نمی‌شود.
    # expert_id خالی می‌ماند تا پرداخت انجام شود.
    # -----------------------------------------------------

    cursor = db.execute(
        """
        INSERT INTO requests
        (
            customer_id,
            service_id,
            tracking_code,
            status,
            estimated_time,
            customer_note,
            total_price,
            paid_price,
            discount_id,
            discount_amount,
            payment_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            service_id,
            tracking_code,
            status,
            "",
            customer_note,
            final_price,
            0,
            discount["id"]
            if discount else None,
            discount_amount,
            payment_status
        )
    )

    request_id = cursor.lastrowid

    # -----------------------------------------------------
    # 100% DISCOUNT
    # -----------------------------------------------------

    if (
        discount
        and final_price == 0
    ):

        db.execute(
            """
            UPDATE requests
            SET
                paid_price = 0,
                payment_status = 'paid',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (request_id,)
        )

        db.execute(
            """
            UPDATE discounts
            SET used_count = used_count + 1
            WHERE id = ?
            """,
            (discount["id"],)
        )

    db.commit()
    db.close()

    # -----------------------------------------------------
    # FILES
    # -----------------------------------------------------

    files = request.files.getlist(
        "documents"
    )

    save_uploaded_files(
        request_id,
        files,
        "customer",
        customer_id
    )

    # -----------------------------------------------------
    # NOTIFICATIONS
    # -----------------------------------------------------

    notify_customer(
        customer_id,
        "ثبت درخواست",
        f"درخواست شما با کد پیگیری {tracking_code} ثبت شد.",
        request_id
    )

    notify_admins(
        "درخواست جدید",
        f"درخواست جدید با کد پیگیری {tracking_code} ثبت شد.",
        request_id
    )

    # فقط درخواست پرداخت‌شده یا ۱۰۰٪ تخفیف
    # برای کارشناسان مجاز قابل مشاهده خواهد بود.

    if payment_status == "paid":

        notify_admins(
            "درخواست آماده پذیرش",
            f"درخواست {tracking_code} آماده پذیرش کارشناس است.",
            request_id
        )

    return redirect(
        url_for(
            "request_success",
            tracking_code=tracking_code
        )
    )


# =========================================================
# SUCCESS
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
        result=result
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
        messages=messages
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
        SELECT *
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
        f"مشتری برای پرونده {tracking_code} مدرک جدید ارسال کرد.",
        req["id"]
    )

    if req["expert_id"]:

        notify_expert(
            req["expert_id"],
            "مدرک جدید",
            f"برای پرونده {tracking_code} مدرک جدید ارسال شده است.",
            req["id"]
        )

    return redirect(
        url_for(
            "customer_request",
            tracking_code=tracking_code
        )
    )


# =========================================================
# CUSTOMER CHAT
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

    db = get_db()

    req = db.execute(
        """
        SELECT *
        FROM requests
        WHERE tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()

    if not req:

        db.close()

        return "پرونده پیدا نشد", 404

    file = request.files.get(
        "attachment"
    )

    attachment_name = None
    attachment_stored_name = None

    if file and file.filename:

        if not allowed_file(
            file.filename
        ):

            db.close()

            flash(
                "فرمت فایل مجاز نیست.",
                "error"
            )

            return redirect(
                url_for(
                    "customer_request",
                    tracking_code=tracking_code
                )
            )

        attachment_name = secure_filename(
            file.filename
        )

        extension = ""

        if "." in attachment_name:

            extension = (
                "."
                +
                attachment_name.rsplit(
                    ".",
                    1
                )[1].lower()
            )

        attachment_stored_name = (
            uuid.uuid4().hex
            + extension
        )

        folder = os.path.join(
            UPLOAD_FOLDER,
            str(req["id"]),
            "chat"
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

    if message or attachment_name:

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

    if req["expert_id"]:

        notify_expert(
            req["expert_id"],
            "پیام جدید مشتری",
            f"برای پرونده {tracking_code} پیام جدید دریافت شد.",
            req["id"]
        )

    notify_admins(
        "پیام جدید مشتری",
        f"برای پرونده {tracking_code} پیام جدید دریافت شد.",
        req["id"]
    )

    return redirect(
        url_for(
            "customer_request",
            tracking_code=tracking_code
        )
    )


# =========================================================
# CHAT FILE
# =========================================================

@app.route(
    "/request/<tracking_code>/chat-file/<int:message_id>"
)
def customer_chat_file(
    tracking_code,
    message_id
):

    db = get_db()

    message = db.execute(
        """
        SELECT
            m.*,
            r.tracking_code
        FROM messages m
        JOIN requests r
            ON r.id = m.request_id
        WHERE m.id = ?
        AND r.tracking_code = ?
        """,
        (
            message_id,
            tracking_code
        )
    ).fetchone()

    db.close()

    if not message:
        return "فایل پیدا نشد", 404

    if not message["attachment_stored_name"]:
        return "فایل وجود ندارد", 404

    directory = os.path.join(
        UPLOAD_FOLDER,
        str(message["request_id"]),
        "chat"
    )

    return send_from_directory(
        directory,
        message["attachment_stored_name"],
        as_attachment=False,
        download_name=message["attachment_name"]
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

        if (
            user
            and check_password_hash(
                user["password_hash"],
                password
            )
        ):

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
# LOGOUT
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

    if user["role"] == "admin":

        requests = db.execute(
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
            ORDER BY r.id DESC
            """
        ).fetchall()

    else:

        requests = db.execute(
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

            JOIN expert_services es
                ON es.service_id = r.service_id
                AND es.expert_id = ?

            WHERE
                r.payment_status = 'paid'
                AND (
                    r.expert_id IS NULL
                    OR r.expert_id = ?
                )

            ORDER BY r.id DESC
            """,
            (
                user["id"],
                user["id"]
            )
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
        SELECT
            s.*,
            p.name AS parent_name
        FROM services s
        LEFT JOIN services p
            ON p.id = s.parent_id
        ORDER BY
            s.sort_order ASC,
            s.id DESC
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

    admins = db.execute(
        """
        SELECT *
        FROM users
        WHERE role = 'admin'
        ORDER BY id DESC
        """
    ).fetchall()

    total_income = db.execute(
        """
        SELECT
            COALESCE(
                SUM(paid_price),
                0
            )
        FROM requests
        """
    ).fetchone()[0]

    total_debt = db.execute(
        """
        SELECT
            COALESCE(
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

    total_requests = db.execute(
        """
        SELECT COUNT(*)
        FROM requests
        """
    ).fetchone()[0]

    unread_notifications = db.execute(
        """
        SELECT COUNT(*)
        FROM notifications
        WHERE
            recipient_type = ?
            AND recipient_id = ?
            AND is_read = 0
        """,
        (
            user["role"],
            user["id"]
        )
    ).fetchone()[0]

    db.close()

    return render_template(
        "admin.html",

        requests=requests,

        customers=customers,

        services=services,

        experts=experts,

        admins=admins,

        total_income=total_income,

        total_debt=total_debt,

        total_requests=total_requests,

        unread_notifications=unread_notifications,

        current_user=user
    )


# =========================================================
# ADMIN / EXPERT REQUEST
# =========================================================

@app.route(
    "/admin/request/<int:rid>"
)
@admin_required
def admin_request(rid):

    user = current_user()

    req = get_request(rid)

    if not req:

        return "پرونده پیدا نشد", 404

    # کارشناسی که پرونده برای او قفل نشده باشد
    if user["role"] == "expert":

        if not can_expert_access(
            user["id"],
            rid
        ):
            return "این پرونده در دسترس شما نیست.", 403

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

    db.close()

    return render_template(
        "admin_request.html",
        req=req,
        documents=documents,
        messages=messages,
        experts=experts
    )


# =========================================================
# ACCEPT REQUEST
# =========================================================

@app.route(
    "/admin/request/accept",
    methods=["POST"]
)
@admin_required
def accept_request():

    rid = request.form.get(
        "id",
        type=int
    )

    user = current_user()

    if not rid:
        return "شناسه پرونده نامعتبر است.", 400

    db = get_db()

    # قفل اتمیک:
    # فقط اولین کارشناس می‌تواند expert_id را تعیین کند.
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

        return "این پرونده هنوز پرداخت نشده است.", 403

    if req["expert_id"]:

        db.close()

        return "این پرونده قبلاً توسط کارشناس دیگری پذیرش شده است.", 409

    if user["role"] == "expert":

        allowed = db.execute(
            """
            SELECT id
            FROM expert_services
            WHERE expert_id = ?
            AND service_id = ?
            """,
            (
                user["id"],
                req["service_id"]
            )
        ).fetchone()

        if not allowed:

            db.close()

            return "این خدمت در دسترسی شما نیست.", 403

        expert_id = user["id"]

    else:

        expert_id = request.form.get(
            "expert_id",
            type=int
        )

        if not expert_id:

            db.close()

            return "کارشناس مشخص نشده است.", 400

    cursor = db.execute(
        """
        UPDATE requests
        SET
            expert_id = ?,
            status = 'پذیرش شد',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        AND expert_id IS NULL
        AND payment_status = 'paid'
        """,
        (
            expert_id,
            rid
        )
    )

    if cursor.rowcount != 1:

        db.rollback()
        db.close()

        return (
            "پرونده قبلاً توسط شخص دیگری پذیرش شده است.",
            409
        )

    db.commit()
    db.close()

    req = get_request(rid)

    notify_expert(
        expert_id,
        "پرونده به شما اختصاص یافت",
        f"پرونده {req['tracking_code']} به شما اختصاص یافت.",
        rid
    )

    notify_customer(
        req["customer_id"],
        "پذیرش درخواست",
        f"درخواست شما با کد {req['tracking_code']} توسط کارشناس پذیرش شد.",
        rid
    )

    notify_admins(
        "پذیرش پرونده",
        f"پرونده {req['tracking_code']} توسط کارشناس پذیرش شد.",
        rid
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# STATUS
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
        ""
    ).strip()

    if status not in STATUSES:

        return "وضعیت نامعتبر است.", 400

    user = current_user()

    req = get_request(rid)

    if not req:
        return "پرونده پیدا نشد", 404

    if user["role"] == "expert":

        if req["expert_id"] != user["id"]:

            return "این پرونده در اختیار شما نیست.", 403

    db = get_db()

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

    req = get_request(rid)

    notify_customer(
        req["customer_id"],
        "تغییر وضعیت پرونده",
        f"وضعیت پرونده {req['tracking_code']} به «{status}» تغییر کرد.",
        rid
    )

    if req["expert_id"]:

        notify_expert(
            req["expert_id"],
            "تغییر وضعیت پرونده",
            f"وضعیت پرونده {req['tracking_code']} به «{status}» تغییر کرد.",
            rid
        )

    notify_admins(
        "تغییر وضعیت پرونده",
        f"وضعیت پرونده {req['tracking_code']} به «{status}» تغییر کرد.",
        rid
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# REQUEST UPDATE
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

    req = get_request(rid)

    if not req:

        return "پرونده پیدا نشد", 404

    user = current_user()

    if (
        user["role"] == "expert"
        and req["expert_id"] != user["id"]
    ):

        return "این پرونده در اختیار شما نیست.", 403

    total_price = request.form.get(
        "total_price",
        type=int
    ) or 0

    paid_price = request.form.get(
        "paid_price",
        type=int
    ) or 0

    estimated_time = request.form.get(
        "estimated_time",
        ""
    ).strip()

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    db = get_db()

    db.execute(
        """
        UPDATE requests
        SET
            total_price = ?,
            paid_price = ?,
            estimated_time = ?,
            admin_note = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            total_price,
            paid_price,
            estimated_time,
            admin_note,
            rid
        )
    )

    db.commit()
    db.close()

    req = get_request(rid)

    notify_customer(
        req["customer_id"],
        "به‌روزرسانی پرونده",
        f"اطلاعات پرونده {req['tracking_code']} به‌روزرسانی شد.",
        rid
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

    user = current_user()

    req = get_request(rid)

    if not req:
        return "پرونده پیدا نشد", 404

    if (
        user["role"] == "expert"
        and req["expert_id"] != user["id"]
    ):

        return "این پرونده در اختیار شما نیست.", 403

    db = get_db()

    file = request.files.get(
        "attachment"
    )

    attachment_name = None
    attachment_stored_name = None

    if file and file.filename:

        if not allowed_file(
            file.filename
        ):

            db.close()

            return "فرمت فایل مجاز نیست.", 400

        attachment_name = secure_filename(
            file.filename
        )

        extension = ""

        if "." in attachment_name:

            extension = (
                "."
                +
                attachment_name.rsplit(
                    ".",
                    1
                )[1].lower()
            )

        attachment_stored_name = (
            uuid.uuid4().hex
            +
            extension
        )

        folder = os.path.join(
            UPLOAD_FOLDER,
            str(rid),
            "chat"
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

    if message or attachment_name:

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
        f"برای پرونده {req['tracking_code']} پیام جدید دریافت شد.",
        rid
    )

    notify_admins(
        "پیام جدید پرونده",
        f"برای پرونده {req['tracking_code']} پیام جدید دریافت شد.",
        rid
    )

    if req["expert_id"]:

        notify_expert(
            req["expert_id"],
            "پیام جدید پرونده",
            f"برای پرونده {req['tracking_code']} پیام جدید دریافت شد.",
            rid
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
        UPLOAD_FOLDER,
        str(document["request_id"])
    )

    return send_from_directory(
        directory,
        document["stored_name"],
        as_attachment=True,
        download_name=document["original_name"]
    )


# =========================================================
# ADMIN SAVE SERVICE
# =========================================================

@app.route(
    "/admin/service/save",
    methods=["POST"]
)
@admin_required
def admin_service_save():

    if not is_admin():

        return "دسترسی غیرمجاز", 403

    service_id = request.form.get(
        "id",
        type=int
    )

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

    service_code = request.form.get(
        "service_code",
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

    parent_id = request.form.get(
        "parent_id",
        type=int
    )

    active = (
        1
        if request.form.get(
            "active",
            "1"
        ) == "1"
        else 0
    )

    fields_json = request.form.get(
        "fields_json",
        "[]"
    )

    documents_json = request.form.get(
        "documents_json",
        "[]"
    )

    try:
        json.loads(fields_json)
    except Exception:
        fields_json = "[]"

    try:
        json.loads(documents_json)
    except Exception:
        documents_json = "[]"

    db = get_db()

    if service_id:

        db.execute(
            """
            UPDATE services
            SET
                name = ?,
                category = ?,
                description = ?,
                service_code = ?,
                price = ?,
                sort_order = ?,
                parent_id = ?,
                active = ?,
                fields_json = ?,
                documents_json = ?
            WHERE id = ?
            """,
            (
                name,
                category,
                description,
                service_code,
                price,
                sort_order,
                parent_id,
                active,
                fields_json,
                documents_json,
                service_id
            )
        )

    else:

        db.execute(
            """
            INSERT INTO services
            (
                name,
                category,
                description,
                service_code,
                price,
                sort_order,
                parent_id,
                active,
                fields_json,
                documents_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                category,
                description,
                service_code,
                price,
                sort_order,
                parent_id,
                active,
                fields_json,
                documents_json
            )
        )

    db.commit()
    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# DELETE SERVICE
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

    db.execute(
        """
        DELETE FROM services
        WHERE id = ?
        """,
        (service_id,)
    )

    db.commit()
    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# TOGGLE SERVICE
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

    db.execute(
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

    db.commit()
    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# CREATE USER
# =========================================================

@app.route(
    "/admin/users/create",
    methods=["POST"]
)
@admin_required
def create_user():

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

    role = request.form.get(
        "role",
        "expert"
    )

    if role not in {
        "admin",
        "expert"
    }:

        role = "expert"

    if (
        not username
        or len(password) < 6
    ):

        flash(
            "نام کاربری و رمز معتبر وارد کنید.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    db = get_db()

    try:

        db.execute(
            """
            INSERT INTO users
            (
                username,
                password_hash,
                role
            )
            VALUES (?, ?, ?)
            """,
            (
                username,
                generate_password_hash(
                    password
                ),
                role
            )
        )

        db.commit()

    except sqlite3.IntegrityError:

        flash(
            "این نام کاربری قبلاً ثبت شده است.",
            "error"
        )

    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ASSIGN EXPERT SERVICE
# =========================================================

@app.route(
    "/admin/expert/service",
    methods=["POST"]
)
@admin_required
def assign_expert_service():

    if not is_admin():

        return "دسترسی غیرمجاز", 403

    expert_id = request.form.get(
        "expert_id",
        type=int
    )

    service_id = request.form.get(
        "service_id",
        type=int
    )

    if not expert_id or not service_id:

        return "اطلاعات ناقص است.", 400

    db = get_db()

    db.execute(
        """
        INSERT OR IGNORE INTO expert_services
        (
            expert_id,
            service_id
        )
        VALUES (?, ?)
        """,
        (
            expert_id,
            service_id
        )
    )

    db.commit()
    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# REMOVE EXPERT SERVICE
# =========================================================

@app.route(
    "/admin/expert/service/remove",
    methods=["POST"]
)
@admin_required
def remove_expert_service():

    if not is_admin():

        return "دسترسی غیرمجاز", 403

    expert_id = request.form.get(
        "expert_id",
        type=int
    )

    service_id = request.form.get(
        "service_id",
        type=int
    )

    db = get_db()

    db.execute(
        """
        DELETE FROM expert_services
        WHERE expert_id = ?
        AND service_id = ?
        """,
        (
            expert_id,
            service_id
        )
    )

    db.commit()
    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# CHANGE ADMIN PASSWORD
# =========================================================

@app.route(
    "/admin/password",
    methods=["POST"]
)
@admin_required
def admin_password():

    password = request.form.get(
        "password",
        ""
    )

    if len(password) < 6:

        flash(
            "رمز باید حداقل ۶ کاراکتر باشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    db = get_db()

    db.execute(
        """
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
        """,
        (
            generate_password_hash(
                password
            ),
            session.get("admin_id")
        )
    )

    db.commit()
    db.close()

    flash(
        "رمز با موفقیت تغییر کرد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# CREATE DISCOUNT
# =========================================================

@app.route(
    "/admin/discount/create",
    methods=["POST"]
)
@admin_required
def create_discount():

    if not is_admin():

        return "دسترسی غیرمجاز", 403

    code = request.form.get(
        "code",
        ""
    ).strip().upper()

    kind = request.form.get(
        "kind",
        "percent"
    )

    value = request.form.get(
        "value",
        type=int
    ) or 0

    service_id = request.form.get(
        "service_id",
        type=int
    )

    max_uses = request.form.get(
        "max_uses",
        type=int
    ) or 0

    start_date = request.form.get(
        "start_date"
    )

    end_date = request.form.get(
        "end_date"
    )

    if not code:

        return "کد تخفیف الزامی است.", 400

    if kind not in {
        "percent",
        "fixed"
    }:

        return "نوع تخفیف نامعتبر است.", 400

    if value < 0:

        return "مقدار تخفیف نامعتبر است.", 400

    if kind == "percent" and value > 100:

        return "درصد تخفیف نمی‌تواند بیشتر از ۱۰۰ باشد.", 400

    db = get_db()

    try:

        db.execute(
            """
            INSERT INTO discounts
            (
                code,
                kind,
                value,
                service_id,
                max_uses,
                start_date,
                end_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                kind,
                value,
                service_id,
                max_uses,
                start_date,
                end_date
            )
        )

        db.commit()

    except sqlite3.IntegrityError:

        flash(
            "این کد تخفیف قبلاً ثبت شده است.",
            "error"
        )

    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# DELETE DISCOUNT
# =========================================================

@app.route(
    "/admin/discount/<int:discount_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_discount(discount_id):

    if not is_admin():

        return "دسترسی غیرمجاز", 403

    db = get_db()

    db.execute(
        """
        DELETE FROM discounts
        WHERE id = ?
        """,
        (discount_id,)
    )

    db.commit()
    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route(
    "/admin/notifications"
)
@admin_required
def notifications():

    user = current_user()

    db = get_db()

    rows = db.execute(
        """
        SELECT *
        FROM notifications
        WHERE
            recipient_type = ?
            AND recipient_id = ?
        ORDER BY id DESC
        LIMIT 100
        """,
        (
            user["role"],
            user["id"]
        )
    ).fetchall()

    db.close()

    return render_template(
        "notifications.html",
        notifications=rows
    )


@app.route(
    "/admin/notifications/read",
    methods=["POST"]
)
@admin_required
def notifications_read():

    user = current_user()

    db = get_db()

    db.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE
            recipient_type = ?
            AND recipient_id = ?
        """,
        (
            user["role"],
            user["id"]
        )
    )

    db.commit()
    db.close()

    return redirect(
        url_for(
            "notifications"
        )
    )


# =========================================================
# FINANCIAL MANAGEMENT
# =========================================================

@app.route(
    "/admin/finance"
)
@admin_required
def finance():

    if not is_admin():

        return "دسترسی غیرمجاز", 403

    db = get_db()

    transactions = db.execute(
        """
        SELECT
            r.id,
            r.tracking_code,
            r.total_price,
            r.paid_price,
            r.discount_amount,
            r.payment_status,
            r.payment_ref,
            r.created_at,

            c.name AS customer_name,
            s.name AS service_name

        FROM requests r

        JOIN customers c
            ON c.id = r.customer_id

        JOIN services s
            ON s.id = r.service_id

        ORDER BY r.id DESC
        """
    ).fetchall()

    income = db.execute(
        """
        SELECT
            COALESCE(
                SUM(paid_price),
                0
            )
        FROM requests
        WHERE payment_status = 'paid'
        """
    ).fetchone()[0]

    debt = db.execute(
        """
        SELECT
            COALESCE(
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

    total_discount = db.execute(
        """
        SELECT
            COALESCE(
                SUM(discount_amount),
                0
            )
        FROM requests
        """
    ).fetchone()[0]

    db.close()

    return render_template(
        "finance.html",
        transactions=transactions,
        income=income,
        debt=debt,
        total_discount=total_discount
    )


# =========================================================
# HEALTH
# =========================================================

@app.route(
    "/health"
)
def health():

    return {
        "status": "ok",
        "site": SITE_NAME
    }


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def not_found(error):

    return (
        "صفحه مورد نظر پیدا نشد.",
        404
    )


# =========================================================
# 413
# =========================================================

@app.errorhandler(413)
def too_large(error):

    return (
        "حجم فایل بیش از حد مجاز است. "
        "حداکثر حجم فایل ۱۰ مگابایت است.",
        413
    )


# =========================================================
# 500
# =========================================================

@app.errorhandler(500)
def internal_error(error):

    app.logger.exception(
        "Internal Server Error"
    )

    return (
        "خطای داخلی سرور. "
        "لطفاً لاگ Render را بررسی کنید.",
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
