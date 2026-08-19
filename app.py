import os
import json
import sqlite3
import secrets
import random
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# =========================================================
# CONFIG
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

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


SITE_NAME = "کافی نت آنلاین نوین"
MANAGER = "احمد محمدی مهر"
PHONE = ""

IRAN_TIMEZONE = ZoneInfo("Asia/Tehran")


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


ALLOWED_FILE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".pdf"
}


# =========================================================
# DATABASE
# =========================================================

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")

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

    return any(row["name"] == column for row in rows)


def add_column_if_missing(
    conn,
    table,
    column,
    definition
):
    if not column_exists(conn, table, column):
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


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

        service_code TEXT DEFAULT '',

        parent_id INTEGER,

        created_at TEXT DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(parent_id)
            REFERENCES services(id)
            ON DELETE SET NULL
    );


    CREATE TABLE IF NOT EXISTS service_experts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_id INTEGER NOT NULL,
        expert_id INTEGER NOT NULL,

        UNIQUE(service_id, expert_id),

        FOREIGN KEY(service_id)
            REFERENCES services(id)
            ON DELETE CASCADE,

        FOREIGN KEY(expert_id)
            REFERENCES users(id)
            ON DELETE CASCADE
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

        correction_count INTEGER DEFAULT 0,

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
            ON DELETE CASCADE
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


    CREATE TABLE IF NOT EXISTS finance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        request_id INTEGER,

        customer_id INTEGER,

        type TEXT NOT NULL,

        amount INTEGER DEFAULT 0,

        description TEXT DEFAULT '',

        created_at TEXT DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(request_id)
            REFERENCES requests(id)
            ON DELETE SET NULL,

        FOREIGN KEY(customer_id)
            REFERENCES customers(id)
            ON DELETE SET NULL
    );


    CREATE TABLE IF NOT EXISTS backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        filename TEXT NOT NULL,

        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    """)


    # -----------------------------------------------------
    # MIGRATIONS
    # -----------------------------------------------------

    add_column_if_missing(
        conn,
        "services",
        "service_code",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "services",
        "parent_id",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "requests",
        "correction_count",
        "INTEGER DEFAULT 0"
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
        "is_paid",
        "INTEGER DEFAULT 0"
    )


    # -----------------------------------------------------
    # DEFAULT SETTINGS
    # -----------------------------------------------------

    defaults = {

        "site_name": SITE_NAME,

        "manager": MANAGER,

        "phone": PHONE,

        "manager_text":
            "ارائه کلیه خدمات کافی‌نت به صورت غیرحضوری",

        "home_text":
            "تمام خدمات کافی‌نت آنلاین نوین را به صورت غیرحضوری دریافت کنید.",

        "footer_text":
            "کافی نت آنلاین نوین - با مدیریت احمد محمدی مهر",

        "logo": "",

        "chat_start":
            "08:00",

        "chat_end":
            "22:00",

        "chat_days":
            "0,1,2,3,4,5,6",

        "sms_enabled":
            "0",

        "sms_api":
            "",

        "sms_sender":
            "",

        "payment_enabled":
            "0",

        "payment_gateway":
            "",

        "payment_api":
            "",

        "payment_callback":
            "",

        "maintenance_mode":
            "0"
    }


    for key, value in defaults.items():

        conn.execute(
            """
            INSERT OR IGNORE INTO settings
            (key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )


    # -----------------------------------------------------
    # ADMIN
    # -----------------------------------------------------

    admin = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        ("admin",)
    ).fetchone()


    if not admin:

        conn.execute(
            """
            INSERT INTO users
            (username, password, role, active)
            VALUES (?, ?, 'admin', 1)
            """,
            (
                "admin",
                generate_password_hash(
                    os.environ.get(
                        "ADMIN_PASSWORD",
                        "ChangeMe123!"
                    )
                )
            )
        )


    conn.commit()


# =========================================================
# HELPERS
# =========================================================

def get_settings():

    conn = get_db()

    rows = conn.execute(
        "SELECT key, value FROM settings"
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

        if user["role"] != "admin":

            flash(
                "این قسمت فقط برای مدیر اصلی است.",
                "error"
            )

            return redirect(
                url_for("admin")
            )

        return f(*args, **kwargs)

    return decorated


def to_int(value, default=0):

    try:

        return int(
            str(value)
            .replace(",", "")
            .strip()
        )

    except Exception:

        return default


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


def generate_tracking_code():

    conn = get_db()

    while True:

        code = str(
            random.randint(1000, 9999)
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


def allowed_file(filename):

    ext = os.path.splitext(
        filename
    )[1].lower()

    return ext in ALLOWED_FILE_EXTENSIONS


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
        INSERT INTO notifications
        (
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


def notify_request(
    request_id,
    title,
    body=""
):

    conn = get_db()

    row = conn.execute(
        """
        SELECT customer_id, expert_id
        FROM requests
        WHERE id = ?
        """,
        (request_id,)
    ).fetchone()

    if not row:
        return

    if row["customer_id"]:

        create_notification(
            "customer",
            row["customer_id"],
            request_id,
            title,
            body
        )

    if row["expert_id"]:

        create_notification(
            "expert",
            row["expert_id"],
            request_id,
            title,
            body
        )

    create_notification(
        "admin",
        None,
        request_id,
        title,
        body
    )


def add_finance(
    request_id,
    customer_id,
    amount,
    description=""
):

    amount = to_int(amount)

    if amount <= 0:
        return

    conn = get_db()

    conn.execute(
        """
        INSERT INTO finance
        (
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
            amount,
            description
        )
    )

    conn.commit()


def expert_has_service(
    expert_id,
    service_id
):

    conn = get_db()

    row = conn.execute(
        """
        SELECT id
        FROM service_experts
        WHERE expert_id = ?
        AND service_id = ?
        """,
        (
            expert_id,
            service_id
        )
    ).fetchone()

    return bool(row)


def expert_can_see_request(
    user,
    row
):

    if user["role"] == "admin":
        return True

    if user["role"] != "expert":
        return False

    if row["expert_id"]:
        return row["expert_id"] == user["id"]

    if row["service_id"]:
        return expert_has_service(
            user["id"],
            row["service_id"]
        )

    return False


def chat_is_open():

    settings = get_settings()

    now = datetime.now(IRAN_TIMEZONE)

    day = str(
        now.weekday()
    )

    allowed_days = [
        x.strip()
        for x in settings.get(
            "chat_days",
            "0,1,2,3,4,5,6"
        ).split(",")
        if x.strip()
    ]

    if day not in allowed_days:
        return False

    start = settings.get(
        "chat_start",
        "08:00"
    )

    end = settings.get(
        "chat_end",
        "22:00"
    )

    current = now.strftime("%H:%M")

    if start <= end:
        return start <= current <= end

    return current >= start or current <= end


def create_backup():

    timestamp = datetime.now(
        IRAN_TIMEZONE
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    filename = (
        f"novin_backup_{timestamp}.db"
    )

    destination = os.path.join(
        BACKUP_FOLDER,
        filename
    )

    source = sqlite3.connect(DATABASE)

    backup = sqlite3.connect(destination)

    try:

        with backup:
            source.backup(backup)

    finally:

        backup.close()
        source.close()


    conn = get_db()

    conn.execute(
        """
        INSERT INTO backups(filename)
        VALUES (?)
        """,
        (filename,)
    )

    conn.commit()

    return filename


def get_request_for_user(
    rid,
    user
):

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
        return None

    if not expert_can_see_request(
        user,
        row
    ):
        return None

    return row


def safe_download_path(base_folder, filename):

    if not filename:
        abort(404)

    base = os.path.realpath(
        base_folder
    )

    target = os.path.realpath(
        os.path.join(
            base_folder,
            filename
        )
    )

    if (
        target != base
        and
        not target.startswith(
            base + os.sep
        )
    ):
        abort(404)

    if not os.path.isfile(target):
        abort(404)

    return target


# =========================================================
# CONTEXT
# =========================================================

@app.context_processor
def inject_globals():

    settings = get_settings()

    return {

        "site_settings": settings,

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

        "chat_open":
            chat_is_open()
    }


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    conn = get_db()

    services = conn.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        AND parent_id IS NULL
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
# SERVICE
# =========================================================

@app.route(
    "/service/<int:service_id>"
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

    subservices = conn.execute(
        """
        SELECT *
        FROM services
        WHERE parent_id = ?
        AND active = 1
        ORDER BY sort_order ASC, id DESC
        """,
        (service_id,)
    ).fetchall()

    return render_template(
        "service.html",
        service=service_row,
        fields=fields,
        documents=documents,
        subservices=subservices,
        settings=get_settings()
    )


# =========================================================
# CREATE REQUEST
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
            INSERT INTO customers
            (
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


    ignored = {
        "name",
        "phone",
        "national_id",
        "customer_note",
        "discount_code",
        "documents"
    }

    form_data = {}

    for key in request.form:

        if key not in ignored:

            form_data[key] = request.form.get(key)


    base_price = max(
        0,
        to_int(
            service_row["price"]
        )
    )

    discount_amount = 0

    is_paid = 0

    discount_id = None


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

            today = datetime.now(
                IRAN_TIMEZONE
            ).strftime(
                "%Y-%m-%d"
            )

            valid = True


            if (
                discount["start_date"]
                and
                today < discount["start_date"]
            ):
                valid = False


            if (
                discount["end_date"]
                and
                today > discount["end_date"]
            ):
                valid = False


            if (
                discount["max_uses"] > 0
                and
                discount["used_count"]
                >= discount["max_uses"]
            ):
                valid = False


            if valid:

                discount_id = discount["id"]


                if discount["kind"] == "percent":

                    discount_amount = int(
                        base_price
                        *
                        discount["value"]
                        /
                        100
                    )

                else:

                    discount_amount = min(
                        base_price,
                        discount["value"]
                    )


                if (
                    discount["kind"] == "percent"
                    and
                    discount["value"] >= 100
                ):

                    is_paid = 1


    final_price = max(
        0,
        base_price - discount_amount
    )


    if final_price == 0:
        is_paid = 1


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
            is_paid
        )
        VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            service_id,
            tracking_code,
            "در انتظار بررسی",
            customer_note,
            final_price,
            0,
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


    if discount_id:

        conn.execute(
            """
            UPDATE discounts
            SET used_count =
                used_count + 1
            WHERE id = ?
            """,
            (discount_id,)
        )


    files = request.files.getlist(
        "documents"
    )

    for file in files:

        if not file or not file.filename:
            continue

        if not allowed_file(
            file.filename
        ):
            continue

        filename = secure_filename(
            file.filename
        )

        if not filename:
            continue

        new_name = (
            f"{secrets.token_hex(8)}_"
            f"{filename}"
        )

        path = os.path.join(
            DOCUMENTS_FOLDER,
            new_name
        )

        file.save(path)

        conn.execute(
            """
            INSERT INTO documents
            (
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


    conn.execute(
        """
        INSERT INTO messages
        (
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


    conn.commit()


    notify_request(
        request_id,
        "درخواست جدید",
        f"کد پیگیری: {tracking_code}"
    )


    return redirect(
        url_for(
            "success",
            code=tracking_code
        )
    )


# =========================================================
# SUCCESS
# =========================================================

@app.route("/success")
def success():

    code = request.args.get(
        "code",
        ""
    )

    return render_template(
        "success.html",
        tracking_code=code
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
        result=result
    )


# =========================================================
# CUSTOMER REQUEST / CHAT
# =========================================================

@app.route(
    "/customer/request/<tracking_code>",
    methods=["GET", "POST"]
)
def customer_request(
    tracking_code
):

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


    if request.method == "POST":

        if not chat_is_open():

            flash(
                "در حال حاضر زمان پاسخگویی کارشناسان نیست.",
                "error"
            )

            return redirect(
                url_for(
                    "customer_request",
                    tracking_code=tracking_code
                )
            )


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

            if allowed_file(
                file.filename
            ):

                filename = secure_filename(
                    file.filename
                )

                if filename:

                    new_name = (
                        f"{secrets.token_hex(8)}_"
                        f"{filename}"
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
                INSERT INTO messages
                (
                    customer_id,
                    request_id,
                    sender,
                    message,
                    file_path,
                    original_name
                )
                VALUES
                (?, ?, 'customer', ?, ?, ?)
                """,
                (
                    req["customer_id"],
                    req["id"],
                    message or "فایل ارسال شد",
                    file_path,
                    original_name
                )
            )

            conn.commit()


            notify_request(
                req["id"],
                "پیام جدید مشتری",
                "مشتری برای پرونده پیام جدید ارسال کرده است."
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
        documents=documents
    )


# =========================================================
# ADMIN LOGIN
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
        "admin_login.html"
    )


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
@login_required
def admin():

    conn = get_db()

    user = get_current_user()


    if user["role"] == "expert":

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
                        AND
                        EXISTS (
                            SELECT 1
                            FROM service_experts se
                            WHERE se.service_id = r.service_id
                            AND se.expert_id = ?
                        )
                    )
                )

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
        FROM finance
        WHERE type = 'income'
        """
    ).fetchone()[0]


    total_debt = conn.execute(
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


    notifications = conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE
            (
                user_type = 'admin'
                OR
                (
                    user_type = 'expert'
                    AND user_id = ?
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

        notifications=notifications,

        total_income=total_income,

        total_debt=total_debt,

        settings=get_settings(),

        current_user=user
    )


# =========================================================
# ADMIN REQUEST
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


    if not expert_can_see_request(
        user,
        row
    ):

        flash(
            "این پرونده در دسترس شما نیست.",
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


        total_price = max(
            0,
            to_int(
                request.form.get(
                    "total_price",
                    row["total_price"]
                )
            )
        )


        paid_price = max(
            0,
            to_int(
                request.form.get(
                    "paid_price",
                    row["paid_price"]
                )
            )
        )


        if status not in ALLOWED_STATUSES:

            status = row["status"]


        expert_id = row["expert_id"]


        if (
            user["role"] == "expert"
            and
            not expert_id
            and
            status == "پذیرش شد"
        ):

            expert_id = user["id"]


        if (
            user["role"] == "expert"
            and
            row["expert_id"]
            and
            row["expert_id"] != user["id"]
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


        if (
            user["role"] == "admin"
            and
            request.form.get("expert_id")
        ):

            expert_id = to_int(
                request.form.get(
                    "expert_id"
                )
            )

            expert_exists = conn.execute(
                """
                SELECT id
                FROM users
                WHERE id = ?
                AND role = 'expert'
                AND active = 1
                """,
                (expert_id,)
            ).fetchone()

            if not expert_exists:
                expert_id = row["expert_id"]


        paid_price = max(
            0,
            min(
                paid_price,
                total_price
            )
        )


        old_status = row["status"]


        is_paid = (
            1
            if paid_price >= total_price
            else 0
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
                is_paid = ?,
                updated_at = CURRENT_TIMESTAMP

            WHERE id = ?
            """,
            (
                status,
                estimated_time,
                admin_note,
                total_price,
                paid_price,
                expert_id,
                is_paid,
                rid
            )
        )


        if (
            paid_price > row["paid_price"]
        ):

            add_finance(
                rid,
                row["customer_id"],
                paid_price - row["paid_price"],
                "پرداخت پرونده"
            )


        conn.commit()


        if status != old_status:

            notify_request(
                rid,
                "تغییر وضعیت پرونده",
                f"وضعیت پرونده به «{status}» تغییر کرد."
            )


        flash(
            "پرونده با موفقیت ذخیره شد.",
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
        """,
        (rid,)
    ).fetchall()


    experts = conn.execute(
        """
        SELECT id, username
        FROM users
        WHERE role = 'expert'
        AND active = 1
        ORDER BY username
        """
    ).fetchall()


    return render_template(
        "admin_request.html",

        req=row,

        messages=messages,

        documents=documents,

        experts=experts
    )


# =========================================================
# STATUS
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


    if not expert_can_see_request(
        user,
        row
    ):

        flash(
            "این پرونده در دسترس شما نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    expert_id = row["expert_id"]


    if (
        user["role"] == "expert"
        and
        not expert_id
        and
        status == "پذیرش شد"
    ):

        expert_id = user["id"]


    if (
        user["role"] == "expert"
        and
        row["expert_id"]
        and
        row["expert_id"] != user["id"]
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


    old_status = row["status"]


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


    conn.commit()


    if status != old_status:

        notify_request(
            rid,
            "تغییر وضعیت پرونده",
            f"وضعیت جدید: {status}"
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
# UPDATE REQUEST
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


    if not expert_can_see_request(
        user,
        row
    ):

        flash(
            "این پرونده در دسترس شما نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    total_price = max(
        0,
        to_int(
            request.form.get(
                "total_price"
            )
        )
    )


    paid_price = max(
        0,
        to_int(
            request.form.get(
                "paid_price"
            )
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


    expert_id = row["expert_id"]


    if user["role"] == "admin":

        requested_expert = request.form.get(
            "expert_id"
        )

        if requested_expert:

            requested_expert_id = to_int(
                requested_expert
            )

            expert_exists = conn.execute(
                """
                SELECT id
                FROM users
                WHERE id = ?
                AND role = 'expert'
                AND active = 1
                """,
                (requested_expert_id,)
            ).fetchone()

            if expert_exists:
                expert_id = requested_expert_id


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
        else 0
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
            updated_at = CURRENT_TIMESTAMP

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


    if paid_price > row["paid_price"]:

        add_finance(
            rid,
            row["customer_id"],
            paid_price - row["paid_price"],
            "پرداخت پرونده"
        )


    conn.commit()


    notify_request(
        rid,
        "اطلاعات پرونده تغییر کرد",
        "اطلاعات مالی یا توضیحات پرونده بروزرسانی شد."
    )


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
# ADMIN MESSAGE
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


    if not expert_can_see_request(
        user,
        row
    ):

        flash(
            "این پرونده در دسترس شما نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    file_path = ""

    original_name = ""


    if file and file.filename:

        if allowed_file(
            file.filename
        ):

            filename = secure_filename(
                file.filename
            )

            if filename:

                new_name = (
                    f"{secrets.token_hex(8)}_"
                    f"{filename}"
                )

                file.save(
                    os.path.join(
                        CHAT_FOLDER,
                        new_name
                    )
                )

                file_path = new_name

                original_name = filename


    if not message and not file_path:

        return redirect(
            url_for(
                "admin_request",
                rid=rid
            )
        )


    sender = (
        "admin"
        if user["role"] == "admin"
        else
        "expert"
    )


    conn.execute(
        """
        INSERT INTO messages
        (
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


    notify_request(
        rid,
        "پیام جدید",
        "پیام جدیدی برای پرونده شما ارسال شده است."
    )


    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# SERVICES FROM ADMIN
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


    price = max(
        0,
        to_int(
            request.form.get("price")
        )
    )


    sort_order = to_int(
        request.form.get("sort_order")
    )


    active = (
        1
        if request.form.get(
            "active",
            "1"
        ) == "1"
        else 0
    )


    service_code = request.form.get(
        "service_code",
        ""
    ).strip()


    fields_json = request.form.get(
        "fields_json",
        "[]"
    )


    documents_json = request.form.get(
        "documents_json",
        "[]"
    )


    parent_id = request.form.get(
        "parent_id"
    )


    if parent_id:
        parent_id = to_int(
            parent_id
        )
    else:
        parent_id = None


    try:

        parsed_fields = json.loads(
            fields_json
        )

        if not isinstance(
            parsed_fields,
            list
        ):
            fields_json = "[]"

    except Exception:

        fields_json = "[]"


    try:

        parsed_documents = json.loads(
            documents_json
        )

        if not isinstance(
            parsed_documents,
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


    if parent_id:

        parent = conn.execute(
            """
            SELECT id
            FROM services
            WHERE id = ?
            """,
            (parent_id,)
        ).fetchone()

        if not parent:
            parent_id = None


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
            documents_json,
            service_code,
            parent_id
        )
        VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            service_code,
            parent_id
        )
    )


    conn.commit()


    flash(
        "خدمت از داخل پنل مدیر اضافه شد.",
        "success"
    )


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

    conn = get_db()

    conn.execute(
        """
        UPDATE services
        SET parent_id = NULL
        WHERE parent_id = ?
        """,
        (service_id,)
    )

    conn.execute(
        """
        DELETE FROM services
        WHERE id = ?
        """,
        (service_id,)
    )

    conn.commit()


    flash(
        "خدمت حذف شد.",
        "success"
    )


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

    return redirect(
        url_for("admin")
    )


# =========================================================
# SERVICE EXPERT ACCESS
# =========================================================

@app.route(
    "/admin/service/experts",
    methods=["POST"]
)
@admin_required
def service_experts():

    service_id = to_int(
        request.form.get(
            "service_id"
        )
    )


    expert_ids = request.form.getlist(
        "expert_ids"
    )


    conn = get_db()


    service = conn.execute(
        """
        SELECT id
        FROM services
        WHERE id = ?
        """,
        (service_id,)
    ).fetchone()


    if not service:

        flash(
            "خدمت پیدا نشد.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    conn.execute(
        """
        DELETE FROM service_experts
        WHERE service_id = ?
        """,
        (service_id,)
    )


    for expert_id in expert_ids:

        expert_id = to_int(
            expert_id
        )

        if expert_id:

            expert = conn.execute(
                """
                SELECT id
                FROM users
                WHERE id = ?
                AND role = 'expert'
                AND active = 1
                """,
                (expert_id,)
            ).fetchone()

            if expert:

                conn.execute(
                    """
                    INSERT OR IGNORE INTO service_experts
                    (
                        service_id,
                        expert_id
                    )
                    VALUES (?, ?)
                    """,
                    (
                        service_id,
                        expert_id
                    )
                )


    conn.commit()


    flash(
        "دسترسی کارشناسان این خدمت ذخیره شد.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


# =========================================================
# USERS
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
        "expert"
    ):

        role = "expert"


    if (
        not username
        or
        len(password) < 6
    ):

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

        flash(
            "این نام کاربری قبلاً وجود دارد.",
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
            generate_password_hash(password),
            role
        )
    )


    conn.commit()


    flash(
        "کاربر ایجاد شد.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/user/<int:user_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_user(user_id):

    if user_id == session.get(
        "user_id"
    ):

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
@login_required
def admin_password():

    password = request.form.get(
        "password",
        ""
    )


    if len(password) < 6:

        flash(
            "رمز عبور حداقل باید ۶ کاراکتر باشد.",
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
            session["user_id"]
        )
    )


    conn.commit()


    flash(
        "رمز عبور تغییر کرد.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


# =========================================================
# DISCOUNTS
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


    value = to_int(
        request.form.get("value")
    )


    max_uses = max(
        0,
        to_int(
            request.form.get(
                "max_uses",
                0
            )
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
        "fixed"
    ):

        kind = "percent"


    if (
        not code
        or
        value < 0
    ):

        flash(
            "اطلاعات کد تخفیف صحیح نیست.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    if (
        kind == "percent"
        and
        value > 100
    ):

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

        flash(
            "این کد تخفیف قبلاً ثبت شده است.",
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
            end_date
        )
    )


    conn.commit()


    flash(
        "کد تخفیف ایجاد شد.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/discount/<int:discount_id>/toggle",
    methods=["POST"]
)
@admin_required
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

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/discount/<int:discount_id>/delete",
    methods=["POST"]
)
@admin_required
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

    return redirect(
        url_for("admin")
    )


# =========================================================
# SETTINGS
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
        "chat_days",
        "sms_enabled",
        "sms_api",
        "sms_sender",
        "payment_enabled",
        "payment_gateway",
        "payment_api",
        "payment_callback"
    ]


    for key in keys:

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

        if allowed_file(
            logo.filename
        ):

            filename = secure_filename(
                logo.filename
            )

            if (
                filename
                and
                os.path.splitext(
                    filename
                )[1].lower()
                in (
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
        "تنظیمات ذخیره شد.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route(
    "/admin/notifications/read",
    methods=["POST"]
)
@login_required
def notifications_read():

    user = get_current_user()

    conn = get_db()


    if user["role"] == "admin":

        conn.execute(
            """
            UPDATE notifications

            SET is_read = 1

            WHERE user_type = 'admin'
            """
        )

    else:

        conn.execute(
            """
            UPDATE notifications

            SET is_read = 1

            WHERE user_type = 'expert'
            AND user_id = ?
            """,
            (user["id"],)
        )


    conn.commit()


    return redirect(
        url_for("admin")
    )


# =========================================================
# DOWNLOAD DOCUMENT
# =========================================================

@app.route(
    "/download/document/<int:document_id>"
)
@login_required
def download_document(
    document_id
):

    conn = get_db()

    user = get_current_user()


    doc = conn.execute(
        """
        SELECT
            d.*,
            r.expert_id,
            r.service_id

        FROM documents d

        INNER JOIN requests r
            ON r.id = d.request_id

        WHERE d.id = ?
        """,
        (document_id,)
    ).fetchone()


    if not doc:
        abort(404)


    if not expert_can_see_request(
        user,
        doc
    ):
        abort(403)


    safe_download_path(
        DOCUMENTS_FOLDER,
        doc["file_path"]
    )


    return send_from_directory(
        DOCUMENTS_FOLDER,
        doc["file_path"],
        as_attachment=True,
        download_name=doc["original_name"]
    )


# =========================================================
# DOWNLOAD CHAT FILE
# =========================================================

@app.route(
    "/download/chat/<path:filename>"
)
@login_required
def download_chat_file(filename):

    conn = get_db()

    user = get_current_user()


    message = conn.execute(
        """
        SELECT
            m.*,
            r.expert_id,
            r.service_id

        FROM messages m

        INNER JOIN requests r
            ON r.id = m.request_id

        WHERE m.file_path = ?
        """,
        (filename,)
    ).fetchone()


    if not message:
        abort(404)


    if not expert_can_see_request(
        user,
        message
    ):
        abort(403)


    safe_download_path(
        CHAT_FOLDER,
        filename
    )


    return send_from_directory(
        CHAT_FOLDER,
        filename,
        as_attachment=True,
        download_name=(
            message["original_name"]
            or
            filename
        )
    )


# =========================================================
# BACKUP
# =========================================================

@app.route(
    "/admin/backup",
    methods=["POST"]
)
@admin_required
def admin_backup():

    filename = create_backup()


    flash(
        f"پشتیبان دیتابیس ساخته شد: {filename}",
        "success"
    )


    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/backup/<path:filename>"
)
@admin_required
def download_backup(filename):

    safe_download_path(
        BACKUP_FOLDER,
        filename
    )

    return send_from_directory(
        BACKUP_FOLDER,
        filename,
        as_attachment=True
    )


# =========================================================
# ERRORS
# =========================================================

@app.errorhandler(404)
def not_found(error):

    return render_template(
        "base.html",
        content="صفحه مورد نظر پیدا نشد."
    ), 404


@app.errorhandler(403)
def forbidden(error):

    return render_template(
        "base.html",
        content="شما اجازه دسترسی به این بخش را ندارید."
    ), 403


@app.errorhandler(413)
def too_large(error):

    flash(
        "حجم فایل بیش از حد مجاز است.",
        "error"
    )

    return redirect(
        request.referrer
        or
        url_for("home")
    )


@app.errorhandler(500)
def internal_error(error):

    return (
        "خطای داخلی سرور. "
        "لطفاً لاگ سرور را بررسی کنید."
    ), 500


# =========================================================
# START
# =========================================================

with app.app_context():
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
