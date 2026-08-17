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
    send_from_directory
)

from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


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

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def column_exists(db, table_name, column_name):
    rows = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row["name"] == column_name
        for row in rows
    )


def add_column_if_missing(
    db,
    table_name,
    column_name,
    column_definition
):
    if not column_exists(
        db,
        table_name,
        column_name
    ):
        db.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name}
            {column_definition}
            """
        )


def create_tables():

    db = get_db()

    # -----------------------------------------------------
    # customers
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
    # services
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------
    # requests
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            tracking_code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'جدید',
            customer_note TEXT,
            admin_note TEXT,
            total_price INTEGER DEFAULT 0,
            paid_price INTEGER DEFAULT 0,
            discount_code TEXT,
            discount_amount INTEGER DEFAULT 0,
            payment_status TEXT DEFAULT 'در انتظار پرداخت',
            payment_reference TEXT,
            expert_id INTEGER,
            estimated_time TEXT,
            accepted_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE CASCADE,

            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # documents
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # messages
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL,
            sender_id INTEGER,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # users
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
    # discounts
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # notifications
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_type TEXT NOT NULL,
            user_id INTEGER,
            request_id INTEGER,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------
    # service_subservices
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS service_subservices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # expert_services
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS expert_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expert_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(expert_id, service_id),

            FOREIGN KEY(expert_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY(service_id)
                REFERENCES services(id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # financial_transactions
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS financial_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            type TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            description TEXT,
            reference TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(request_id)
                REFERENCES requests(id)
                ON DELETE SET NULL
        )
    """)

    # -----------------------------------------------------
    # settings
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # -----------------------------------------------------
    # MIGRATION FOR OLD DATABASE
    # -----------------------------------------------------

    add_column_if_missing(
        db,
        "requests",
        "discount_code",
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
        "TEXT DEFAULT 'در انتظار پرداخت'"
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
        "estimated_time",
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
        "services",
        "fields_json",
        "TEXT DEFAULT '[]'"
    )

    add_column_if_missing(
        db,
        "services",
        "documents_json",
        "TEXT DEFAULT '[]'"
    )

    # -----------------------------------------------------
    # ADMIN
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

    db.commit()
    db.close()


create_tables()


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

        while True:

            code = str(
                __import__("random").randint(
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
        user and
        user["role"] == "admin"
    )


def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if not session.get("admin_id"):
            return redirect(
                url_for("admin_login")
            )

        user = current_user()

        if not user:
            session.clear()

            return redirect(
                url_for("admin_login")
            )

        return func(*args, **kwargs)

    return wrapper


def admin_only(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if not session.get("admin_id"):
            return redirect(
                url_for("admin_login")
            )

        if not is_admin():
            return "دسترسی غیرمجاز", 403

        return func(*args, **kwargs)

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


def add_notification(
    user_type,
    title,
    message,
    request_id=None,
    user_id=None
):

    db = get_db()

    db.execute(
        """
        INSERT INTO notifications
        (
            user_type,
            user_id,
            request_id,
            title,
            message
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_type,
            user_id,
            request_id,
            title,
            message
        )
    )

    db.commit()
    db.close()


def notify_request_change(
    request_id,
    title,
    message
):

    add_notification(
        "customer",
        title,
        message,
        request_id=request_id
    )

    add_notification(
        "admin",
        title,
        message,
        request_id=request_id
    )


def create_financial_transaction(
    request_id,
    transaction_type,
    amount,
    description="",
    reference=""
):

    db = get_db()

    db.execute(
        """
        INSERT INTO financial_transactions
        (
            request_id,
            type,
            amount,
            description,
            reference
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            request_id,
            transaction_type,
            amount,
            description,
            reference
        )
    )

    db.commit()
    db.close()


# =========================================================
# CONTEXT
# =========================================================

@app.context_processor
def inject_global_values():

    settings = {}

    try:

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

    except Exception:

        settings = {}

    return {
        "site_name": SITE_NAME,
        "manager": MANAGER,
        "phone": PHONE,
        "settings": settings,
        "current_user": current_user()
    }


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
        ORDER BY sort_order ASC, id DESC
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

    service_item = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    if not service_item:

        db.close()

        return "خدمت پیدا نشد", 404

    subservices = db.execute(
        """
        SELECT *
        FROM service_subservices
        WHERE service_id = ?
        AND active = 1
        ORDER BY id ASC
        """,
        (service_id,)
    ).fetchall()

    db.close()

    try:
        fields = json.loads(
            service_item["fields_json"] or "[]"
        )
    except Exception:
        fields = []

    try:
        documents = json.loads(
            service_item["documents_json"] or "[]"
        )
    except Exception:
        documents = []

    return render_template(
        "service.html",
        service=service_item,
        fields=fields,
        documents=documents,
        subservices=subservices
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

    service_item = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    if not service_item:

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

    subservice_id = request.form.get(
        "subservice_id",
        type=int
    )

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

    total_price = int(
        service_item["price"] or 0
    )

    selected_subservice = None

    if subservice_id:

        selected_subservice = db.execute(
            """
            SELECT *
            FROM service_subservices
            WHERE id = ?
            AND service_id = ?
            AND active = 1
            """,
            (
                subservice_id,
                service_id
            )
        ).fetchone()

        if selected_subservice:
            total_price = int(
                selected_subservice["price"] or 0
            )

    # -----------------------------------------------------
    # DISCOUNT
    # -----------------------------------------------------

    discount_amount = 0
    payment_status = "در انتظار پرداخت"

    if discount_code:

        discount = db.execute(
            """
            SELECT *
            FROM discounts
            WHERE code = ?
            AND active = 1
            """,
            (discount_code,)
        ).fetchone()

        if discount:

            valid = True

            if (
                discount["max_uses"] > 0
                and
                discount["used_count"]
                >= discount["max_uses"]
            ):
                valid = False

            if valid:

                if discount["kind"] == "percent":

                    discount_amount = int(
                        total_price
                        *
                        discount["value"]
                        / 100
                    )

                else:

                    discount_amount = int(
                        discount["value"]
                    )

                if discount_amount > total_price:
                    discount_amount = total_price

                total_price -= discount_amount

                # 100% تخفیف
                if total_price <= 0:

                    total_price = 0

                    payment_status = "پرداخت کامل با تخفیف"

                    db.execute(
                        """
                        UPDATE discounts
                        SET used_count =
                            used_count + 1
                        WHERE id = ?
                        """,
                        (discount["id"],)
                    )

    tracking_code = generate_tracking_code()

    # -----------------------------------------------------
    # REQUEST
    # -----------------------------------------------------

    cursor = db.execute(
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
            payment_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            service_id,
            tracking_code,
            "جدید",
            customer_note,
            total_price,
            0,
            discount_code or None,
            discount_amount,
            payment_status
        )
    )

    request_id = cursor.lastrowid

    # 100% تخفیف
    if total_price == 0:

        db.execute(
            """
            UPDATE requests
            SET
                paid_price = 0,
                payment_status = ?
            WHERE id = ?
            """,
            (
                "پرداخت کامل با تخفیف",
                request_id
            )
        )

    db.commit()
    db.close()

    # -----------------------------------------------------
    # UPLOAD
    # -----------------------------------------------------

    files = request.files.getlist(
        "documents"
    )

    save_uploaded_files(
        request_id,
        files
    )

    # -----------------------------------------------------
    # NOTIFICATION
    # -----------------------------------------------------

    notify_request_change(
        request_id,
        "درخواست جدید",
        f"درخواست جدید با کد پیگیری {tracking_code} ثبت شد."
    )

    # -----------------------------------------------------
    # FINANCIAL
    # -----------------------------------------------------

    if discount_amount > 0:

        create_financial_transaction(
            request_id,
            "discount",
            discount_amount,
            "تخفیف درخواست"
        )

    return redirect(
        url_for(
            "request_success",
            tracking_code=tracking_code
        )
    )


# =========================================================
# UPLOAD
# =========================================================

def save_uploaded_files(
    request_id,
    files
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
                stored_name
            )
            VALUES (?, ?, ?)
            """,
            (
                request_id,
                original_name,
                stored_name
            )
        )

    db.commit()
    db.close()


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
        SELECT id
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
        files
    )

    notify_request_change(
        req["id"],
        "مدرک جدید",
        "مشتری برای پرونده مدرک جدید ارسال کرد."
    )

    return redirect(
        url_for(
            "customer_request",
            tracking_code=tracking_code
        )
    )


# =========================================================
# DOWNLOAD DOCUMENT
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

    if not message:

        return redirect(
            url_for(
                "customer_request",
                tracking_code=tracking_code
            )
        )

    db = get_db()

    req = db.execute(
        """
        SELECT id
        FROM requests
        WHERE tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()

    if req:

        db.execute(
            """
            INSERT INTO messages
            (
                request_id,
                sender_type,
                message
            )
            VALUES (?, ?, ?)
            """,
            (
                req["id"],
                "customer",
                message
            )
        )

        db.commit()

        request_id = req["id"]

    else:

        request_id = None

    db.close()

    if request_id:

        notify_request_change(
            request_id,
            "پیام جدید مشتری",
            "مشتری برای پرونده پیام جدید ارسال کرد."
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

        if (
            user
            and
            check_password_hash(
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

    db = get_db()

    requests_list = db.execute(
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
        ORDER BY sort_order ASC, id DESC
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

    total_income = db.execute(
        """
        SELECT COALESCE(
            SUM(paid_price),
            0
        )
        FROM requests
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

    db.close()

    return render_template(
        "admin.html",
        requests=requests_list,
        customers=customers,
        services=services,
        experts=experts,
        total_income=total_income,
        total_debt=total_debt,
        current_user=current_user()
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
# ADMIN REQUEST STATUS
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

    allowed_statuses = {
        "پذیرش شد",
        "در حال بررسی",
        "نقص مدارک",
        "قطعی سامانه",
        "رد شد",
        "انصراف مشتری",
        "انجام شد",
        "جدید"
    }

    if status not in allowed_statuses:
        status = "جدید"

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

    notify_request_change(
        rid,
        "تغییر وضعیت پرونده",
        f"وضعیت پرونده به «{status}» تغییر کرد."
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

    total_price = request.form.get(
        "total_price",
        type=int
    ) or 0

    paid_price = request.form.get(
        "paid_price",
        type=int
    ) or 0

    admin_note = request.form.get(
        "admin_note",
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

    # -----------------------------------------------------
    # پذیرش انحصاری
    # -----------------------------------------------------

    existing = db.execute(
        """
        SELECT expert_id
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if existing and existing["expert_id"]:

        if (
            expert_id
            and
            expert_id != existing["expert_id"]
            and
            not is_admin()
        ):

            db.close()

            return (
                "این پرونده قبلاً توسط کارشناس دیگری "
                "پذیرش شده است.",
                403
            )

    db.execute(
        """
        UPDATE requests
        SET
            total_price = ?,
            paid_price = ?,
            admin_note = ?,
            estimated_time = ?,
            expert_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            total_price,
            paid_price,
            admin_note,
            estimated_time,
            expert_id,
            rid
        )
    )

    if paid_price > 0:

        db.execute(
            """
            UPDATE requests
            SET payment_status = ?
            WHERE id = ?
            """,
            (
                "پرداخت شده",
                rid
            )
        )

    db.commit()
    db.close()

    notify_request_change(
        rid,
        "تغییر اطلاعات پرونده",
        "اطلاعات پرونده توسط مدیریت به‌روزرسانی شد."
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

    if message:

        db = get_db()

        db.execute(
            """
            INSERT INTO messages
            (
                request_id,
                sender_type,
                sender_id,
                message
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                rid,
                "admin",
                session.get("admin_id"),
                message
            )
        )

        db.commit()
        db.close()

        notify_request_change(
            rid,
            "پاسخ کارشناس",
            "برای پرونده شما پیام جدیدی ثبت شد."
        )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADD SERVICE
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

    try:
        json.loads(fields_json)
    except Exception:
        fields_json = "[]"

    try:
        json.loads(documents_json)
    except Exception:
        documents_json = "[]"

    if not name:
        return "نام خدمت الزامی است.", 400

    db = get_db()

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
            1 if active == "1" else 0,
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
@admin_only
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

    if role not in {
        "admin",
        "expert"
    }:
        role = "expert"

    if not username or len(password) < 6:

        flash(
            "رمز عبور باید حداقل ۶ کاراکتر باشد.",
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
                generate_password_hash(password),
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
# PASSWORD
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
            generate_password_hash(password),
            session.get("admin_id")
        )
    )

    db.commit()
    db.close()

    flash(
        "رمز مدیریت با موفقیت تغییر کرد.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# DISCOUNT
# =========================================================

@app.route(
    "/admin/discount/create",
    methods=["POST"]
)
@admin_only
def create_discount():

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

    max_uses = request.form.get(
        "max_uses",
        type=int
    )

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
        kind = "percent"

    if kind == "percent" and value > 100:
        value = 100

    db = get_db()

    try:

        db.execute(
            """
            INSERT INTO discounts
            (
                code,
                kind,
                value,
                max_uses,
                start_date,
                end_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                kind,
                value,
                max_uses or 0,
                start_date,
                end_date
            )
        )

        db.commit()

    except sqlite3.IntegrityError:

        flash(
            "کد تخفیف قبلاً ثبت شده است.",
            "error"
        )

    db.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# SUBSERVICE
# =========================================================

@app.route(
    "/admin/subservice/save",
    methods=["POST"]
)
@admin_only
def save_subservice():

    service_id = request.form.get(
        "service_id",
        type=int
    )

    name = request.form.get(
        "name",
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

    if not service_id or not name:
        return "اطلاعات ناقص است.", 400

    db = get_db()

    db.execute(
        """
        INSERT INTO service_subservices
        (
            service_id,
            name,
            description,
            price
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            service_id,
            name,
            description,
            price
        )
    )

    db.commit()
    db.close()

    return redirect(
        url_for("admin")
    )


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

        return {
            "status": "ok",
            "site": SITE_NAME,
            "database": "ok"
        }

    except Exception as error:

        return {
            "status": "error",
            "database": str(error)
        }, 500


# =========================================================
# ERROR 413
# =========================================================

@app.errorhandler(413)
def too_large(error):

    return (
        "حجم فایل بیش از حد مجاز است. "
        "حداکثر حجم فایل ۱۰ مگابایت است.",
        413
    )


# =========================================================
# ERROR 500
# =========================================================

@app.errorhandler(500)
def internal_error(error):

    return (
        "خطای داخلی سرور رخ داده است. "
        "لطفاً دوباره تلاش کنید.",
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
