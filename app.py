import os
import json
import uuid
import sqlite3
from functools import wraps
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_from_directory
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

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# =========================================================
# FOLDER
# =========================================================

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():

    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            national_id TEXT,
            phone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            price INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            fields_json TEXT,
            documents_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

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
            expert_id INTEGER,
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

    db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # ادمین اولیه
    admin = db.execute(
        "SELECT id FROM users WHERE username = ?",
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
            (username, password_hash, role)
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
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def generate_tracking_code():

    while True:

        code = str(uuid.uuid4()).replace("-", "")[:10].upper()

        db = get_db()

        exists = db.execute(
            """
            SELECT id
            FROM requests
            WHERE tracking_code = ?
            """,
            (code,)
        ).fetchone()

        db.close()

        if not exists:
            return code


def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if not session.get("admin_id"):
            return redirect(
                url_for("admin_login")
            )

        return func(*args, **kwargs)

    return wrapper


def current_user():

    user_id = session.get("admin_id")

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

    return user and user["role"] == "admin"


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

@app.route("/service/<int:service_id>")
def service(service_id):

    db = get_db()

    service = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    db.close()

    if not service:
        return "سامانه پیدا نشد", 404

    fields = []

    documents = []

    try:
        fields = json.loads(
            service["fields_json"] or "[]"
        )
    except Exception:
        fields = []

    try:
        documents = json.loads(
            service["documents_json"] or "[]"
        )
    except Exception:
        documents = []

    return render_template(
        "service.html",
        service=service,
        fields=fields,
        documents=documents
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

    service = db.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    if not service:

        db.close()

        return "سامانه پیدا نشد", 404

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
            total_price
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            service_id,
            tracking_code,
            "جدید",
            customer_note,
            service["price"] or 0
        )
    )

    request_id = cursor.lastrowid

    db.commit()
    db.close()

    # آپلود مدارک
    files = request.files.getlist("documents")

    save_uploaded_files(
        request_id,
        files
    )

    return redirect(
        url_for(
            "request_success",
            tracking_code=tracking_code
        )
    )


# =========================================================
# SAVE UPLOADS
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

        if not allowed_file(file.filename):
            continue

        original_name = secure_filename(
            file.filename
        )

        extension = ""

        if "." in original_name:
            extension = "." + original_name.rsplit(
                ".",
                1
            )[1].lower()

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
        ).strip().upper()

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
# CUSTOMER UPLOAD MORE DOCUMENTS
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

    db.close()

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

        if user and check_password_hash(
            user["password_hash"],
            password
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
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
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
        SELECT COALESCE(SUM(paid_price), 0)
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
        requests=requests,
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

    expert_id = request.form.get(
        "expert_id",
        type=int
    )

    db = get_db()

    db.execute(
        """
        UPDATE requests
        SET
            total_price = ?,
            paid_price = ?,
            admin_note = ?,
            expert_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            total_price,
            paid_price,
            admin_note,
            expert_id,
            rid
        )
    )

    db.commit()
    db.close()

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

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN ADD SERVICE
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
# ADMIN DELETE SERVICE
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
# ADMIN TOGGLE SERVICE
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
# ADMIN CREATE USER
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
# ADMIN PASSWORD
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
@admin_required
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
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "site": SITE_NAME
    }


# =========================================================
# ERROR
# =========================================================

@app.errorhandler(413)
def too_large(error):

    return (
        "حجم فایل بیش از حد مجاز است. "
        "حداکثر حجم هر فایل ۱۰ مگابایت است.",
        413
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
