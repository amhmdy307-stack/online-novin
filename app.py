import os
import json
import sqlite3
import secrets
import string
from datetime import datetime, timedelta

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_from_directory
)

from werkzeug.utils import secure_filename


# =========================================================
# SETTINGS
# =========================================================

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "site.db")
UPLOADS = os.path.join(BASE, "uploads")

os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "123456"
)


# =========================================================
# DATABASE
# =========================================================

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def column_exists(con, table, column):
    rows = con.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(
        row["name"] == column
        for row in rows
    )


def add_column_if_missing(
    con,
    table,
    column,
    definition
):
    if not column_exists(
        con,
        table,
        column
    ):
        con.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )


def init_db():

    con = db()

    con.executescript("""

    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL DEFAULT 'مشتری',
        national_id TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        category TEXT DEFAULT '',
        image TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        code_json TEXT DEFAULT '{}',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS service_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        price INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        fields_json TEXT DEFAULT '[]',
        documents_json TEXT DEFAULT '[]',
        FOREIGN KEY(service_id)
            REFERENCES services(id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        service_id INTEGER NOT NULL,
        service_item_id INTEGER,
        data_json TEXT DEFAULT '{}',
        status TEXT DEFAULT 'در انتظار پذیرش',
        tracking_code TEXT UNIQUE,
        total_price INTEGER DEFAULT 0,
        discount_amount INTEGER DEFAULT 0,
        final_price INTEGER DEFAULT 0,
        paid_price INTEGER DEFAULT 0,
        payment_status TEXT DEFAULT 'unpaid',
        payment_mode TEXT DEFAULT 'online',
        assigned_admin_id INTEGER,
        accepted_at TEXT,
        estimated_value INTEGER DEFAULT 0,
        estimated_unit TEXT DEFAULT 'روز کاری',
        admin_note TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS request_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        note TEXT DEFAULT '',
        admin_id INTEGER,
        created_at TEXT,
        FOREIGN KEY(request_id)
            REFERENCES requests(id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        customer_id INTEGER NOT NULL,
        sender_type TEXT NOT NULL,
        sender_admin_id INTEGER,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(request_id)
            REFERENCES requests(id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        admin_id INTEGER,
        request_id INTEGER,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        notification_type TEXT DEFAULT 'general',
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        request_id INTEGER,
        amount INTEGER DEFAULT 0,
        discount_amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        tracking_id TEXT,
        transaction_id TEXT,
        gateway TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS discount_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        kind TEXT DEFAULT 'percent',
        value INTEGER DEFAULT 0,
        start_date TEXT,
        end_date TEXT,
        max_uses INTEGER DEFAULT 0,
        used_count INTEGER DEFAULT 0,
        service_id INTEGER,
        service_item_id INTEGER,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT DEFAULT '',
        role TEXT DEFAULT 'operator',
        active INTEGER DEFAULT 1,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS admin_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        permission TEXT NOT NULL,
        UNIQUE(admin_id, permission)
    );

    CREATE TABLE IF NOT EXISTS admin_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        service_id INTEGER NOT NULL,
        service_item_id INTEGER,
        UNIQUE(
            admin_id,
            service_id,
            service_item_id
        )
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS payment_settings (
        id INTEGER PRIMARY KEY CHECK(id = 1),
        enabled INTEGER DEFAULT 0,
        gateway TEXT DEFAULT '',
        merchant_id TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        api_secret TEXT DEFAULT '',
        test_mode INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS sms_settings (
        id INTEGER PRIMARY KEY CHECK(id = 1),
        enabled INTEGER DEFAULT 0,
        provider TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        api_secret TEXT DEFAULT '',
        sender TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        field_name TEXT,
        original_name TEXT,
        stored_name TEXT,
        file_type TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS notification_devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        admin_id INTEGER,
        endpoint TEXT,
        created_at TEXT,
        UNIQUE(
            customer_id,
            admin_id,
            endpoint
        )
    );

    """)

    # -----------------------------------------------------
    # Compatibility with old database
    # -----------------------------------------------------

    add_column_if_missing(
        con,
        "services",
        "code_json",
        "TEXT DEFAULT '{}'"
    )

    add_column_if_missing(
        con,
        "requests",
        "service_item_id",
        "INTEGER"
    )

    add_column_if_missing(
        con,
        "requests",
        "discount_amount",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        con,
        "requests",
        "final_price",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        con,
        "requests",
        "payment_status",
        "TEXT DEFAULT 'unpaid'"
    )

    add_column_if_missing(
        con,
        "requests",
        "assigned_admin_id",
        "INTEGER"
    )

    add_column_if_missing(
        con,
        "requests",
        "accepted_at",
        "TEXT"
    )

    add_column_if_missing(
        con,
        "requests",
        "estimated_value",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        con,
        "requests",
        "estimated_unit",
        "TEXT DEFAULT 'روز کاری'"
    )

    add_column_if_missing(
        con,
        "requests",
        "admin_note",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        con,
        "requests",
        "updated_at",
        "TEXT"
    )

    add_column_if_missing(
        con,
        "admins",
        "full_name",
        "TEXT DEFAULT ''"
    )

    # -----------------------------------------------------
    # Default admin
    # -----------------------------------------------------

    admin = con.execute(
        """
        SELECT id
        FROM admins
        WHERE username = 'admin'
        LIMIT 1
        """
    ).fetchone()

    if not admin:

        cur = con.execute(
            """
            INSERT INTO admins
            (
                username,
                password,
                full_name,
                role,
                active,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "admin",
                ADMIN_PASSWORD,
                "مدیر اصلی",
                "superadmin",
                1,
                now()
            )
        )

        admin_id = cur.lastrowid

        permissions = [
            "all",
            "services",
            "requests",
            "customers",
            "finance",
            "payments",
            "sms",
            "settings",
            "admins"
        ]

        for permission in permissions:

            con.execute(
                """
                INSERT OR IGNORE INTO admin_permissions
                (admin_id, permission)
                VALUES (?, ?)
                """,
                (
                    admin_id,
                    permission
                )
            )

    # -----------------------------------------------------
    # Default settings
    # -----------------------------------------------------

    defaults = {

        "site_name":
            "کافی‌نت آنلاین نوین",

        "manager":
            "احمد محمدی مهر",

        "phone":
            "09920345139",

        "logo":
            "",

        "primary_color":
            "#1479d1",

        "secondary_color":
            "#102a43",

        "background_color":
            "#f5f7fb",

        "card_color":
            "#ffffff",

        "text_color":
            "#172033",

        "hero_title":
            "کافی‌نت آنلاین نوین",

        "hero_text":
            "ثبت‌نام و دریافت خدمات به صورت غیرحضوری",

        "warning_text":
            "پرداخت خدمات فقط از طریق درگاه رسمی سایت انجام می‌شود.",

        "payment_required":
            "1",

        "notification_enabled":
            "1",

        "sms_enabled":
            "0"
    }

    for key, value in defaults.items():

        con.execute(
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

    con.execute(
        """
        INSERT OR IGNORE INTO payment_settings
        (
            id,
            enabled,
            gateway,
            merchant_id,
            api_key,
            api_secret,
            test_mode
        )
        VALUES
        (
            1,
            0,
            '',
            '',
            '',
            '',
            1
        )
        """
    )

    con.execute(
        """
        INSERT OR IGNORE INTO sms_settings
        (
            id,
            enabled,
            provider,
            api_key,
            api_secret,
            sender
        )
        VALUES
        (
            1,
            0,
            '',
            '',
            '',
            ''
        )
        """
    )

    con.commit()
    con.close()


# =========================================================
# HELPERS
# =========================================================

def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def get_settings():

    con = db()

    rows = con.execute(
        """
        SELECT key, value
        FROM settings
        """
    ).fetchall()

    con.close()

    return {
        row["key"]: row["value"]
        for row in rows
    }


def admin_required():

    return session.get("admin_id") is not None


def current_admin_id():

    return session.get("admin_id")


def is_superadmin():

    return (
        session.get("admin_role")
        == "superadmin"
    )


def has_permission(permission):

    if not admin_required():
        return False

    if is_superadmin():
        return True

    admin_id = current_admin_id()

    con = db()

    row = con.execute(
        """
        SELECT 1
        FROM admin_permissions
        WHERE admin_id = ?
        AND permission = ?
        LIMIT 1
        """,
        (
            admin_id,
            permission
        )
    ).fetchone()

    all_permission = con.execute(
        """
        SELECT 1
        FROM admin_permissions
        WHERE admin_id = ?
        AND permission = 'all'
        LIMIT 1
        """,
        (admin_id,)
    ).fetchone()

    con.close()

    return bool(
        row or all_permission
    )


def admin_can_access_service(
    admin_id,
    service_id,
    service_item_id=None
):

    con = db()

    if is_superadmin():
        con.close()
        return True

    row = con.execute(
        """
        SELECT id
        FROM admin_services
        WHERE admin_id = ?
        AND service_id = ?
        AND (
            service_item_id IS NULL
            OR service_item_id = ?
        )
        LIMIT 1
        """,
        (
            admin_id,
            service_id,
            service_item_id
        )
    ).fetchone()

    con.close()

    return bool(row)


def generate_tracking_code():

    con = db()

    for _ in range(100):

        code = str(
            secrets.randbelow(900) + 100
        )

        used = con.execute(
            """
            SELECT id
            FROM requests
            WHERE tracking_code = ?
            AND status NOT IN
            (
                'انجام شد',
                'مختومه',
                'لغو توسط مشتری'
            )
            LIMIT 1
            """,
            (code,)
        ).fetchone()

        if not used:

            con.close()

            return code

    con.close()

    raise RuntimeError(
        "امکان ساخت کد پرونده وجود ندارد."
    )


def add_notification(
    title,
    message,
    customer_id=None,
    admin_id=None,
    request_id=None,
    notification_type="general"
):

    con = db()

    con.execute(
        """
        INSERT INTO notifications
        (
            customer_id,
            admin_id,
            request_id,
            title,
            message,
            notification_type,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            admin_id,
            request_id,
            title,
            message,
            notification_type,
            now()
        )
    )

    con.commit()
    con.close()


def notify_admins_for_request(
    request_id,
    service_id,
    service_item_id
):

    con = db()

    admins = con.execute(
        """
        SELECT DISTINCT
            a.id
        FROM admins a
        LEFT JOIN admin_services x
            ON x.admin_id = a.id
        WHERE a.active = 1
        AND
        (
            a.role = 'superadmin'
            OR
            (
                x.service_id = ?
                AND
                (
                    x.service_item_id IS NULL
                    OR x.service_item_id = ?
                )
            )
        )
        """,
        (
            service_id,
            service_item_id
        )
    ).fetchall()

    request_item = con.execute(
        """
        SELECT
            r.tracking_code,
            s.name AS service_name,
            si.name AS item_name
        FROM requests r
        JOIN services s
            ON s.id = r.service_id
        LEFT JOIN service_items si
            ON si.id = r.service_item_id
        WHERE r.id = ?
        """,
        (request_id,)
    ).fetchone()

    con.close()

    if not request_item:
        return

    for admin in admins:

        add_notification(
            "درخواست جدید",
            (
                f"درخواست جدید برای "
                f"{request_item['service_name']}"
                f" - "
                f"{request_item['item_name'] or ''}"
                f" با کد "
                f"{request_item['tracking_code']}"
                f" ثبت شد."
            ),
            admin_id=admin["id"],
            request_id=request_id,
            notification_type="new_request"
        )


def add_status_history(
    request_id,
    status,
    note="",
    admin_id=None
):

    con = db()

    con.execute(
        """
        INSERT INTO request_status_history
        (
            request_id,
            status,
            note,
            admin_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            request_id,
            status,
            note,
            admin_id,
            now()
        )
    )

    con.commit()
    con.close()


def notify_customer_status(
    request_id,
    customer_id,
    status
):

    add_notification(
        "تغییر وضعیت پرونده",
        f"وضعیت پرونده شما به «{status}» تغییر کرد.",
        customer_id=customer_id,
        request_id=request_id,
        notification_type="status"
    )


def calculate_discount(
    code,
    total,
    service_id,
    service_item_id
):

    if not code:
        return 0

    con = db()

    row = con.execute(
        """
        SELECT *
        FROM discount_codes
        WHERE code = ?
        AND active = 1
        LIMIT 1
        """,
        (code.upper(),)
    ).fetchone()

    con.close()

    if not row:
        return 0

    today = datetime.now().date()

    if row["start_date"]:

        try:
            start = datetime.strptime(
                row["start_date"],
                "%Y-%m-%d"
            ).date()

            if today < start:
                return 0

        except Exception:
            pass

    if row["end_date"]:

        try:
            end = datetime.strptime(
                row["end_date"],
                "%Y-%m-%d"
            ).date()

            if today > end:
                return 0

        except Exception:
            pass

    if (
        row["max_uses"] > 0
        and row["used_count"] >= row["max_uses"]
    ):
        return 0

    if (
        row["service_id"]
        and row["service_id"] != service_id
    ):
        return 0

    if (
        row["service_item_id"]
        and row["service_item_id"]
        != service_item_id
    ):
        return 0

    if row["kind"] == "percent":

        percent = max(
            0,
            min(
                100,
                row["value"]
            )
        )

        return int(
            total * percent / 100
        )

    return min(
        total,
        max(0, row["value"])
    )


def use_discount(code):

    if not code:
        return

    con = db()

    con.execute(
        """
        UPDATE discount_codes
        SET used_count = used_count + 1
        WHERE code = ?
        AND active = 1
        """,
        (code.upper(),)
    )

    con.commit()
    con.close()


def save_uploaded_files(
    request_id,
    customer_id
):

    for field_name in request.files:

        for file in request.files.getlist(
            field_name
        ):

            if (
                not file
                or not file.filename
            ):
                continue

            original_name = secure_filename(
                file.filename
            )

            if not original_name:
                continue

            stored_name = (
                secrets.token_hex(8)
                + "_"
                + original_name
            )

            file.save(
                os.path.join(
                    UPLOADS,
                    stored_name
                )
            )

            con = db()

            con.execute(
                """
                INSERT INTO files
                (
                    request_id,
                    customer_id,
                    field_name,
                    original_name,
                    stored_name,
                    file_type,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    customer_id,
                    field_name,
                    original_name,
                    stored_name,
                    file.content_type or "",
                    now()
                )
            )

            con.commit()
            con.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    if session.get("customer_id"):

        return redirect(
            url_for("customer_dashboard")
        )

    con = db()

    services = con.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        ORDER BY sort_order ASC, id DESC
        """
    ).fetchall()

    con.close()

    return render_template(
        "home.html",
        services=services,
        settings=get_settings()
    )


# =========================================================
# CUSTOMER LOGIN
# =========================================================

@app.route(
    "/customer/login",
    methods=["GET", "POST"]
)
def customer_login():

    if session.get("customer_id"):

        return redirect(
            url_for("customer_dashboard")
        )

    con = db()

    cursor = con.execute(
        """
        INSERT INTO customers
        (
            name,
            national_id,
            phone,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            "مشتری",
            "",
            "",
            now()
        )
    )

    customer_id = cursor.lastrowid

    con.commit()
    con.close()

    session["customer_id"] = customer_id

    return redirect(
        url_for("customer_dashboard")
    )


@app.route("/customer/logout")
def customer_logout():

    session.pop(
        "customer_id",
        None
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# CUSTOMER DASHBOARD
# =========================================================

@app.route("/customer")
def customer_dashboard():

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        return redirect(
            url_for("customer_login")
        )

    con = db()

    customer = con.execute(
        """
        SELECT *
        FROM customers
        WHERE id = ?
        """,
        (customer_id,)
    ).fetchone()

    services = con.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        ORDER BY sort_order ASC, id DESC
        """
    ).fetchall()

    requests_list = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name,
            si.name AS item_name
        FROM requests r
        JOIN services s
            ON s.id = r.service_id
        LEFT JOIN service_items si
            ON si.id = r.service_item_id
        WHERE r.customer_id = ?
        ORDER BY r.id DESC
        """,
        (customer_id,)
    ).fetchall()

    notifications = con.execute(
        """
        SELECT *
        FROM notifications
        WHERE customer_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (customer_id,)
    ).fetchall()

    unread_notifications = con.execute(
        """
        SELECT COUNT(*) AS total
        FROM notifications
        WHERE customer_id = ?
        AND is_read = 0
        """,
        (customer_id,)
    ).fetchone()["total"]

    con.close()

    return render_template(
        "customer.html",
        customer=customer,
        services=services,
        requests=requests_list,
        notifications=notifications,
        unread_notifications=unread_notifications,
        settings=get_settings()
    )


# =========================================================
# SERVICE PAGE
# =========================================================

@app.route(
    "/service/<int:sid>",
    methods=["GET", "POST"]
)
def service(sid):

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        return redirect(
            url_for("customer_login")
        )

    con = db()

    service_item = con.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (sid,)
    ).fetchone()

    sub_services = con.execute(
        """
        SELECT *
        FROM service_items
        WHERE service_id = ?
        AND active = 1
        ORDER BY sort_order ASC, id ASC
        """,
        (sid,)
    ).fetchall()

    con.close()

    if not service_item:

        return "سامانه پیدا نشد.", 404

    return render_template(
        "service.html",
        service=service_item,
        sub_services=sub_services,
        settings=get_settings()
    )


# =========================================================
# CREATE REQUEST
# =========================================================

@app.post(
    "/request/create"
)
def create_request():

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        return redirect(
            url_for("customer_login")
        )

    service_id = request.form.get(
        "service_id",
        type=int
    )

    service_item_id = request.form.get(
        "service_item_id",
        type=int
    )

    discount_code = request.form.get(
        "discount_code",
        ""
    ).strip().upper()

    if not service_id:

        flash(
            "سامانه انتخاب نشده است."
        )

        return redirect(
            url_for("customer_dashboard")
        )

    con = db()

    service_row = con.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    item_row = None

    if service_item_id:

        item_row = con.execute(
            """
            SELECT *
            FROM service_items
            WHERE id = ?
            AND service_id = ?
            AND active = 1
            """,
            (
                service_item_id,
                service_id
            )
        ).fetchone()

    con.close()

    if not service_row:

        return "سامانه پیدا نشد.", 404

    total_price = 0

    if item_row:

        total_price = (
            item_row["price"] or 0
        )

    discount = calculate_discount(
        discount_code,
        total_price,
        service_id,
        service_item_id
    )

    final_price = max(
        0,
        total_price - discount
    )

    payment_settings = get_payment_settings()

    payment_required = (
        get_settings().get(
            "payment_required",
            "1"
        ) == "1"
    )

    if final_price == 0:

        payment_status = "paid"

        payment_mode = "discount_100"

    elif (
        payment_required
        and payment_settings["enabled"]
    ):

        payment_status = "unpaid"

        payment_mode = "online"

    else:

        payment_status = "paid"

        payment_mode = "free_mode"

    data = {}

    for key in request.form.keys():

        if key in (
            "service_id",
            "service_item_id",
            "discount_code"
        ):
            continue

        values = request.form.getlist(
            key
        )

        data[key] = (
            values
            if len(values) > 1
            else values[0]
        )

    # -----------------------------------------------------
    # پرداخت اجباری:
    # فقط پرونده‌ای که پرداخت شده یا 100٪ تخفیف دارد
    # نهایی می‌شود.
    # -----------------------------------------------------

    if (
        payment_status != "paid"
        and payment_mode == "online"
    ):

        session["pending_request"] = {
            "customer_id": customer_id,
            "service_id": service_id,
            "service_item_id": service_item_id,
            "data": data,
            "discount_code": discount_code,
            "total_price": total_price,
            "discount": discount,
            "final_price": final_price
        }

        return render_template(
            "payment_required.html",
            total_price=total_price,
            discount=discount,
            final_price=final_price,
            settings=get_settings()
        )

    tracking_code = generate_tracking_code()

    con = db()

    cursor = con.execute(
        """
        INSERT INTO requests
        (
            customer_id,
            service_id,
            service_item_id,
            data_json,
            status,
            tracking_code,
            total_price,
            discount_amount,
            final_price,
            paid_price,
            payment_status,
            payment_mode,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            service_id,
            service_item_id,
            json.dumps(
                data,
                ensure_ascii=False
            ),
            "در انتظار پذیرش",
            tracking_code,
            total_price,
            discount,
            final_price,
            final_price,
            payment_status,
            payment_mode,
            now(),
            now()
        )
    )

    request_id = cursor.lastrowid

    con.commit()
    con.close()

    if discount_code:

        use_discount(
            discount_code
        )

    save_uploaded_files(
        request_id,
        customer_id
    )

    add_status_history(
        request_id,
        "در انتظار پذیرش",
        "پرونده ثبت و آماده بررسی شد."
    )

    notify_admins_for_request(
        request_id,
        service_id,
        service_item_id
    )

    add_notification(
        "ثبت پرونده",
        f"پرونده شما با کد {tracking_code} ثبت شد.",
        customer_id=customer_id,
        request_id=request_id,
        notification_type="request"
    )

    return redirect(
        url_for(
            "customer_request",
            rid=request_id
        )
    )


# =========================================================
# PAYMENT SETTINGS
# =========================================================

def get_payment_settings():

    con = db()

    row = con.execute(
        """
        SELECT *
        FROM payment_settings
        WHERE id = 1
        """
    ).fetchone()

    con.close()

    if not row:

        return {
            "enabled": 0,
            "gateway": "",
            "merchant_id": "",
            "api_key": "",
            "api_secret": "",
            "test_mode": 1
        }

    return dict(row)


# =========================================================
# PAYMENT CALLBACK PLACEHOLDER
# =========================================================

@app.route(
    "/payment/start",
    methods=["POST"]
)
def payment_start():

    pending = session.get(
        "pending_request"
    )

    if not pending:

        return redirect(
            url_for("customer_dashboard")
        )

    settings = get_payment_settings()

    if not settings["enabled"]:

        flash(
            "درگاه پرداخت هنوز فعال نشده است."
        )

        return redirect(
            url_for("customer_dashboard")
        )

    # درگاه واقعی در مرحله اتصال درگاه
    # این بخش بدون تغییر معماری تکمیل می‌شود.

    return render_template(
        "payment_start.html",
        pending=pending,
        settings=get_settings()
    )


@app.route(
    "/payment/callback",
    methods=["GET", "POST"]
)
def payment_callback():

    # نقطه ورود بازگشت تمام درگاه‌ها
    # اتصال درگاه واقعی در این endpoint
    # انجام خواهد شد.

    return "درگاه پرداخت هنوز به حساب بانکی متصل نشده است."


# =========================================================
# CUSTOMER REQUEST
# =========================================================

@app.route(
    "/customer/request/<int:rid>"
)
def customer_request(rid):

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        return redirect(
            url_for("customer_login")
        )

    con = db()

    result = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name,
            si.name AS item_name,
            a.full_name AS admin_name
        FROM requests r
        JOIN services s
            ON s.id = r.service_id
        LEFT JOIN service_items si
            ON si.id = r.service_item_id
        LEFT JOIN admins a
            ON a.id = r.assigned_admin_id
        WHERE r.id = ?
        AND r.customer_id = ?
        """,
        (
            rid,
            customer_id
        )
    ).fetchone()

    messages = con.execute(
        """
        SELECT *
        FROM messages
        WHERE request_id = ?
        ORDER BY id ASC
        """,
        (rid,)
    ).fetchall()

    history = con.execute(
        """
        SELECT
            h.*,
            a.full_name AS admin_name
        FROM request_status_history h
        LEFT JOIN admins a
            ON a.id = h.admin_id
        WHERE h.request_id = ?
        ORDER BY h.id ASC
        """,
        (rid,)
    ).fetchall()

    files = con.execute(
        """
        SELECT *
        FROM files
        WHERE request_id = ?
        ORDER BY id DESC
        """,
        (rid,)
    ).fetchall()

    con.close()

    if not result:

        return "پرونده پیدا نشد.", 404

    return render_template(
        "customer_request.html",
        request_item=result,
        messages=messages,
        history=history,
        files=files,
        settings=get_settings()
    )


# =========================================================
# CUSTOMER MESSAGE
# =========================================================

@app.post(
    "/customer/request/<int:rid>/message"
)
def customer_message(rid):

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        return redirect(
            url_for("customer_login")
        )

    message = request.form.get(
        "message",
        ""
    ).strip()

    if not message:

        return redirect(
            url_for(
                "customer_request",
                rid=rid
            )
        )

    con = db()

    valid = con.execute(
        """
        SELECT id
        FROM requests
        WHERE id = ?
        AND customer_id = ?
        """,
        (
            rid,
            customer_id
        )
    ).fetchone()

    if valid:

        con.execute(
            """
            INSERT INTO messages
            (
                request_id,
                customer_id,
                sender_type,
                message,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                rid,
                customer_id,
                "customer",
                message,
                now()
            )
        )

        assigned = con.execute(
            """
            SELECT assigned_admin_id
            FROM requests
            WHERE id = ?
            """,
            (rid,)
        ).fetchone()

        con.commit()

    else:

        assigned = None

    con.close()

    if valid:

        add_notification(
            "پیام جدید مشتری",
            message,
            admin_id=(
                assigned["assigned_admin_id"]
                if assigned
                and assigned["assigned_admin_id"]
                else None
            ),
            request_id=rid,
            notification_type="message"
        )

        # اعلان برای مدیر اصلی
        con = db()

        superadmins = con.execute(
            """
            SELECT id
            FROM admins
            WHERE role = 'superadmin'
            AND active = 1
            """
        ).fetchall()

        con.close()

        for admin in superadmins:

            add_notification(
                "پیام جدید مشتری",
                message,
                admin_id=admin["id"],
                request_id=rid,
                notification_type="message"
            )

    return redirect(
        url_for(
            "customer_request",
            rid=rid
        )
    )


# =========================================================
# TRACKING
# =========================================================

@app.route(
    "/tracking",
    methods=["GET", "POST"]
)
def tracking():

    customer_id = session.get(
        "customer_id"
    )

    code = request.values.get(
        "code",
        ""
    ).strip()

    result = None

    if code:

        con = db()

        result = con.execute(
            """
            SELECT
                r.*,
                s.name AS service_name,
                si.name AS item_name,
                a.full_name AS admin_name
            FROM requests r
            JOIN services s
                ON s.id = r.service_id
            LEFT JOIN service_items si
                ON si.id = r.service_item_id
            LEFT JOIN admins a
                ON a.id = r.assigned_admin_id
            WHERE r.tracking_code = ?
            AND
            (
                ? IS NULL
                OR r.customer_id = ?
            )
            """,
            (
                code,
                customer_id,
                customer_id
            )
        ).fetchone()

        con.close()

    return render_template(
        "tracking.html",
        result=result,
        settings=get_settings()
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

        con = db()

        admin = con.execute(
            """
            SELECT *
            FROM admins
            WHERE username = ?
            AND active = 1
            """,
            (username,)
        ).fetchone()

        con.close()

        if (
            admin
            and secrets.compare_digest(
                password,
                admin["password"]
            )
        ):

            session["admin_id"] = admin["id"]
            session["admin_role"] = admin["role"]

            return redirect(
                url_for("admin")
            )

        flash(
            "نام کاربری یا رمز عبور اشتباه است."
        )

    return render_template(
        "admin_login.html",
        settings=get_settings()
    )


@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin_id",
        None
    )

    session.pop(
        "admin_role",
        None
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    admin_id = current_admin_id()

    con = db()

    if is_superadmin():

        requests_list = con.execute(
            """
            SELECT
                r.*,
                s.name AS service_name,
                si.name AS item_name,
                c.name AS customer_name,
                c.phone AS customer_phone,
                a.full_name AS admin_name
            FROM requests r
            JOIN services s
                ON s.id = r.service_id
            LEFT JOIN service_items si
                ON si.id = r.service_item_id
            JOIN customers c
                ON c.id = r.customer_id
            LEFT JOIN admins a
                ON a.id = r.assigned_admin_id
            ORDER BY r.id DESC
            """
        ).fetchall()

    else:

        requests_list = con.execute(
            """
            SELECT
                r.*,
                s.name AS service_name,
                si.name AS item_name,
                c.name AS customer_name,
                c.phone AS customer_phone,
                a.full_name AS admin_name
            FROM requests r
            JOIN services s
                ON s.id = r.service_id
            LEFT JOIN service_items si
                ON si.id = r.service_item_id
            JOIN customers c
                ON c.id = r.customer_id
            LEFT JOIN admins a
                ON a.id = r.assigned_admin_id
            JOIN admin_services x
                ON x.service_id = r.service_id
                AND
                (
                    x.service_item_id IS NULL
                    OR x.service_item_id =
                        r.service_item_id
                )
            WHERE
                x.admin_id = ?
                OR r.assigned_admin_id = ?
            ORDER BY r.id DESC
            """,
            (
                admin_id,
                admin_id
            )
        ).fetchall()

    services = con.execute(
        """
        SELECT *
        FROM services
        ORDER BY sort_order ASC, id DESC
        """
    ).fetchall()

    admins = con.execute(
        """
        SELECT *
        FROM admins
        ORDER BY id DESC
        """
    ).fetchall()

    customers = con.execute(
        """
        SELECT
            c.*,
            (
                SELECT COUNT(*)
                FROM requests r
                WHERE r.customer_id = c.id
            ) AS request_count
        FROM customers c
        ORDER BY c.id DESC
        """
    ).fetchall()

    notifications = con.execute(
        """
        SELECT *
        FROM notifications
        WHERE admin_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (admin_id,)
    ).fetchall()

    unread_notifications = con.execute(
        """
        SELECT COUNT(*) AS total
        FROM notifications
        WHERE admin_id = ?
        AND is_read = 0
        """,
        (admin_id,)
    ).fetchone()["total"]

    con.close()

    return render_template(
        "admin.html",
        requests=requests_list,
        services=services,
        admins=admins,
        customers=customers,
        notifications=notifications,
        unread_notifications=unread_notifications,
        settings=get_settings()
    )


# =========================================================
# ADMIN ACCEPT REQUEST
# =========================================================

@app.post(
    "/admin/request/<int:rid>/accept"
)
def admin_accept_request(rid):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    admin_id = current_admin_id()

    con = db()

    request_item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if not request_item:

        con.close()

        return "پرونده پیدا نشد.", 404

    # مدیر اصلی همیشه مجاز است
    # سایر ادمین‌ها باید دسترسی سامانه داشته باشند.

    allowed = (
        is_superadmin()
        or admin_can_access_service(
            admin_id,
            request_item["service_id"],
            request_item["service_item_id"]
        )
    )

    if not allowed:

        con.close()

        flash(
            "شما به این سامانه دسترسی ندارید."
        )

        return redirect(
            url_for("admin")
        )

    # قفل اتمیک پرونده
    cur = con.execute(
        """
        UPDATE requests
        SET
            assigned_admin_id = ?,
            accepted_at = ?,
            status = ?,
            updated_at = ?
        WHERE id = ?
        AND assigned_admin_id IS NULL
        AND status = 'در انتظار پذیرش'
        """,
        (
            admin_id,
            now(),
            "پرونده پذیرش شد",
            now(),
            rid
        )
    )

    con.commit()

    accepted = (
        cur.rowcount == 1
    )

    if accepted:

        con.execute(
            """
            INSERT INTO request_status_history
            (
                request_id,
                status,
                note,
                admin_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                rid,
                "پرونده پذیرش شد",
                "پرونده توسط کارشناس پذیرش شد.",
                admin_id,
                now()
            )
        )

        customer_id = request_item[
            "customer_id"
        ]

        con.commit()

    else:

        customer_id = None

    con.close()

    if accepted:

        add_notification(
            "پذیرش پرونده",
            "پرونده شما توسط کارشناس پذیرش شد.",
            customer_id=customer_id,
            request_id=rid,
            notification_type="accepted"
        )

    else:

        flash(
            "این پرونده قبلاً توسط کارشناس دیگری پذیرش شده است."
        )

    return redirect(
        url_for("admin_request", rid=rid)
    )


# =========================================================
# ADMIN REQUEST VIEW
# =========================================================

@app.route(
    "/admin/request/<int:rid>"
)
def admin_request(rid):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    admin_id = current_admin_id()

    con = db()

    result = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name,
            si.name AS item_name,
            c.name AS customer_name,
            c.national_id,
            c.phone,
            a.full_name AS admin_name
        FROM requests r
        JOIN services s
            ON s.id = r.service_id
        LEFT JOIN service_items si
            ON si.id = r.service_item_id
        JOIN customers c
            ON c.id = r.customer_id
        LEFT JOIN admins a
            ON a.id = r.assigned_admin_id
        WHERE r.id = ?
        """,
        (rid,)
    ).fetchone()

    if not result:

        con.close()

        return "پرونده پیدا نشد.", 404

    allowed = (
        is_superadmin()
        or result["assigned_admin_id"]
        == admin_id
        or con.execute(
            """
            SELECT 1
            FROM admin_services
            WHERE admin_id = ?
            AND service_id = ?
            AND
            (
                service_item_id IS NULL
                OR service_item_id = ?
            )
            LIMIT 1
            """,
            (
                admin_id,
                result["service_id"],
                result["service_item_id"]
            )
        ).fetchone()
    )

    if not allowed:

        con.close()

        return "دسترسی ندارید.", 403

    messages = con.execute(
        """
        SELECT *
        FROM messages
        WHERE request_id = ?
        ORDER BY id ASC
        """,
        (rid,)
    ).fetchall()

    history = con.execute(
        """
        SELECT
            h.*,
            a.full_name AS admin_name
        FROM request_status_history h
        LEFT JOIN admins a
            ON a.id = h.admin_id
        WHERE h.request_id = ?
        ORDER BY h.id ASC
        """,
        (rid,)
    ).fetchall()

    files = con.execute(
        """
        SELECT *
        FROM files
        WHERE request_id = ?
        ORDER BY id DESC
        """,
        (rid,)
    ).fetchall()

    con.close()

    return render_template(
        "admin_request.html",
        request_item=result,
        messages=messages,
        history=history,
        files=files,
        settings=get_settings()
    )


# =========================================================
# ADMIN UPDATE REQUEST
# =========================================================

@app.post(
    "/admin/request/<int:rid>/update"
)
def admin_update_request(rid):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    admin_id = current_admin_id()

    status = request.form.get(
        "status",
        ""
    ).strip()

    estimated_value = request.form.get(
        "estimated_value",
        type=int
    ) or 0

    estimated_unit = request.form.get(
        "estimated_unit",
        "روز کاری"
    ).strip()

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    con = db()

    item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if not item:

        con.close()

        return "پرونده پیدا نشد.", 404

    if (
        not is_superadmin()
        and item["assigned_admin_id"]
        != admin_id
    ):

        con.close()

        return "فقط کارشناس مسئول پرونده می‌تواند آن را تغییر دهد.", 403

    old_status = item["status"]

    con.execute(
        """
        UPDATE requests
        SET
            status = ?,
            estimated_value = ?,
            estimated_unit = ?,
            admin_note = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            estimated_value,
            estimated_unit,
            admin_note,
            now(),
            rid
        )
    )

    if status != old_status:

        con.execute(
            """
            INSERT INTO request_status_history
            (
                request_id,
                status,
                note,
                admin_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                rid,
                status,
                admin_note,
                admin_id,
                now()
            )
        )

    con.commit()
    con.close()

    if status != old_status:

        notify_customer_status(
            rid,
            item["customer_id"],
            status
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

@app.post(
    "/admin/request/<int:rid>/message"
)
def admin_message(rid):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    admin_id = current_admin_id()

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

    con = db()

    item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if not item:

        con.close()

        return "پرونده پیدا نشد.", 404

    if (
        not is_superadmin()
        and item["assigned_admin_id"]
        != admin_id
    ):

        con.close()

        return "دسترسی ندارید.", 403

    con.execute(
        """
        INSERT INTO messages
        (
            request_id,
            customer_id,
            sender_type,
            sender_admin_id,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            item["customer_id"],
            "admin",
            admin_id,
            message,
            now()
        )
    )

    con.commit()
    con.close()

    add_notification(
        "پیام جدید کارشناس",
        message,
        customer_id=item["customer_id"],
        request_id=rid,
        notification_type="message"
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN SERVICE CODE
# =========================================================

@app.post(
    "/admin/service/code"
)
def admin_service_code():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if not has_permission("services"):

        return "دسترسی ندارید.", 403

    code = request.form.get(
        "service_code",
        ""
    ).strip()

    if not code:

        flash(
            "کد سامانه وارد نشده است."
        )

        return redirect(
            url_for("admin")
        )

    try:

        config = json.loads(code)

        name = config["name"]

        category = config.get(
            "category",
            ""
        )

        description = config.get(
            "description",
            ""
        )

        items = config.get(
            "items",
            []
        )

        if not isinstance(
            items,
            list
        ):
            raise ValueError()

    except Exception:

        flash(
            "کد سامانه معتبر نیست."
        )

        return redirect(
            url_for("admin")
        )

    con = db()

    cur = con.execute(
        """
        INSERT INTO services
        (
            name,
            description,
            category,
            active,
            sort_order,
            code_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            description,
            category,
            1,
            0,
            code,
            now()
        )
    )

    service_id = cur.lastrowid

    for index, item in enumerate(items):

        item_name = item.get(
            "name",
            f"زیرسامانه {index + 1}"
        )

        fields = item.get(
            "fields",
            []
        )

        documents = item.get(
            "documents",
            []
        )

        con.execute(
            """
            INSERT INTO service_items
            (
                service_id,
                name,
                description,
                price,
                active,
                sort_order,
                fields_json,
                documents_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_id,
                item_name,
                item.get(
                    "description",
                    ""
                ),
                0,
                1,
                index,
                json.dumps(
                    fields,
                    ensure_ascii=False
                ),
                json.dumps(
                    documents,
                    ensure_ascii=False
                )
            )
        )

    con.commit()
    con.close()

    flash(
        f"سامانه «{name}» با موفقیت اضافه شد."
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN SERVICE PRICE
# =========================================================

@app.post(
    "/admin/service-item/price"
)
def admin_service_item_price():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if not has_permission("services"):

        return "دسترسی ندارید.", 403

    item_id = request.form.get(
        "id",
        type=int
    )

    price = request.form.get(
        "price",
        type=int
    ) or 0

    active = (
        1
        if request.form.get(
            "active"
        ) == "1"
        else 0
    )

    con = db()

    con.execute(
        """
        UPDATE service_items
        SET
            price = ?,
            active = ?
        WHERE id = ?
        """,
        (
            price,
            active,
            item_id
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN ADD ADMIN
# =========================================================

@app.post(
    "/admin/admin/create"
)
def admin_create():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    if not is_superadmin():

        return "فقط مدیر اصلی اجازه دارد.", 403

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    full_name = request.form.get(
        "full_name",
        ""
    ).strip()

    if (
        not username
        or len(password) < 6
    ):

        flash(
            "نام کاربری و رمز معتبر وارد کنید."
        )

        return redirect(
            url_for("admin")
        )

    con = db()

    try:

        cur = con.execute(
            """
            INSERT INTO admins
            (
                username,
                password,
                full_name,
                role,
                active,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                password,
                full_name,
                "operator",
                1,
                now()
            )
        )

        admin_id = cur.lastrowid

        permissions = request.form.getlist(
            "permissions"
        )

        for permission in permissions:

            con.execute(
                """
                INSERT OR IGNORE INTO
                admin_permissions
                (
                    admin_id,
                    permission
                )
                VALUES (?, ?)
                """,
                (
                    admin_id,
                    permission
                )
            )

        service_ids = request.form.getlist(
            "service_ids"
        )

        for service_id in service_ids:

            con.execute(
                """
                INSERT OR IGNORE INTO
                admin_services
                (
                    admin_id,
                    service_id,
                    service_item_id
                )
                VALUES (?, ?, NULL)
                """,
                (
                    admin_id,
                    int(service_id)
                )
            )

        con.commit()

    except sqlite3.IntegrityError:

        con.rollback()

        flash(
            "این نام کاربری قبلاً استفاده شده است."
        )

    finally:

        con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN ASSIGN SERVICE
# =========================================================

@app.post(
    "/admin/admin/service-access"
)
def admin_service_access():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    if not is_superadmin():

        return "فقط مدیر اصلی اجازه دارد.", 403

    admin_id = request.form.get(
        "admin_id",
        type=int
    )

    service_id = request.form.get(
        "service_id",
        type=int
    )

    service_item_id = request.form.get(
        "service_item_id",
        type=int
    )

    con = db()

    con.execute(
        """
        INSERT OR IGNORE INTO
        admin_services
        (
            admin_id,
            service_id,
            service_item_id
        )
        VALUES (?, ?, ?)
        """,
        (
            admin_id,
            service_id,
            service_item_id
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN SETTINGS
# =========================================================

@app.post(
    "/admin/settings"
)
def admin_settings():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if not has_permission("settings"):

        return "دسترسی ندارید.", 403

    allowed = [
        "site_name",
        "manager",
        "phone",
        "logo",
        "primary_color",
        "secondary_color",
        "background_color",
        "card_color",
        "text_color",
        "hero_title",
        "hero_text",
        "warning_text",
        "payment_required",
        "notification_enabled"
    ]

    con = db()

    for key in allowed:

        value = request.form.get(
            key,
            ""
        ).strip()

        con.execute(
            """
            INSERT OR REPLACE INTO
            settings
            (
                key,
                value
            )
            VALUES (?, ?)
            """,
            (
                key,
                value
            )
        )

    con.commit()
    con.close()

    flash(
        "تنظیمات ذخیره شد."
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# PAYMENT SETTINGS ADMIN
# =========================================================

@app.post(
    "/admin/payment-settings"
)
def admin_payment_settings():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if not has_permission("payments"):

        return "دسترسی ندارید.", 403

    enabled = (
        1
        if request.form.get(
            "enabled"
        ) == "1"
        else 0
    )

    gateway = request.form.get(
        "gateway",
        ""
    ).strip()

    merchant_id = request.form.get(
        "merchant_id",
        ""
    ).strip()

    api_key = request.form.get(
        "api_key",
        ""
    ).strip()

    api_secret = request.form.get(
        "api_secret",
        ""
    ).strip()

    test_mode = (
        1
        if request.form.get(
            "test_mode"
        ) == "1"
        else 0
    )

    con = db()

    con.execute(
        """
        UPDATE payment_settings
        SET
            enabled = ?,
            gateway = ?,
            merchant_id = ?,
            api_key = ?,
            api_secret = ?,
            test_mode = ?
        WHERE id = 1
        """,
        (
            enabled,
            gateway,
            merchant_id,
            api_key,
            api_secret,
            test_mode
        )
    )

    con.commit()
    con.close()

    flash(
        "تنظیمات درگاه ذخیره شد."
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# SMS SETTINGS ADMIN
# =========================================================

@app.post(
    "/admin/sms-settings"
)
def admin_sms_settings():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if not has_permission("sms"):

        return "دسترسی ندارید.", 403

    enabled = (
        1
        if request.form.get(
            "enabled"
        ) == "1"
        else 0
    )

    provider = request.form.get(
        "provider",
        ""
    ).strip()

    api_key = request.form.get(
        "api_key",
        ""
    ).strip()

    api_secret = request.form.get(
        "api_secret",
        ""
    ).strip()

    sender = request.form.get(
        "sender",
        ""
    ).strip()

    con = db()

    con.execute(
        """
        UPDATE sms_settings
        SET
            enabled = ?,
            provider = ?,
            api_key = ?,
            api_secret = ?,
            sender = ?
        WHERE id = 1
        """,
        (
            enabled,
            provider,
            api_key,
            api_secret,
            sender
        )
    )

    con.commit()
    con.close()

    flash(
        "تنظیمات پیامک ذخیره شد."
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# DISCOUNT CODE
# =========================================================

@app.post(
    "/admin/discount/create"
)
def admin_discount_create():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if not has_permission("finance"):

        return "دسترسی ندارید.", 403

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

    start_date = request.form.get(
        "start_date",
        ""
    ).strip()

    end_date = request.form.get(
        "end_date",
        ""
    ).strip()

    max_uses = request.form.get(
        "max_uses",
        type=int
    ) or 0

    service_id = request.form.get(
        "service_id",
        type=int
    )

    service_item_id = request.form.get(
        "service_item_id",
        type=int
    )

    if not code:

        flash(
            "کد تخفیف را وارد کنید."
        )

        return redirect(
            url_for("admin")
        )

    if kind == "percent":

        value = max(
            0,
            min(100, value)
        )

    con = db()

    try:

        con.execute(
            """
            INSERT INTO discount_codes
            (
                code,
                kind,
                value,
                start_date,
                end_date,
                max_uses,
                service_id,
                service_item_id,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                code,
                kind,
                value,
                start_date,
                end_date,
                max_uses,
                service_id,
                service_item_id
            )
        )

        con.commit()

    except sqlite3.IntegrityError:

        con.rollback()

        flash(
            "این کد تخفیف قبلاً ثبت شده است."
        )

    finally:

        con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# READ NOTIFICATIONS
# =========================================================

@app.post(
    "/notifications/read"
)
def notifications_read():

    if session.get("customer_id"):

        customer_id = session[
            "customer_id"
        ]

        con = db()

        con.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE customer_id = ?
            """,
            (customer_id,)
        )

        con.commit()
        con.close()

    elif admin_required():

        con = db()

        con.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE admin_id = ?
            """,
            (
                current_admin_id(),
            )
        )

        con.commit()
        con.close()

    return jsonify(
        ok=True
    )


# =========================================================
# NOTIFICATION DEVICE
# =========================================================

@app.post(
    "/notifications/device"
)
def save_notification_device():

    customer_id = session.get(
        "customer_id"
    )

    admin_id = current_admin_id()

    endpoint = request.form.get(
        "endpoint",
        ""
    ).strip()

    if not endpoint:

        return jsonify(
            ok=False
        )

    con = db()

    con.execute(
        """
        INSERT OR IGNORE INTO
        notification_devices
        (
            customer_id,
            admin_id,
            endpoint,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            customer_id,
            admin_id,
            endpoint,
            now()
        )
    )

    con.commit()
    con.close()

    return jsonify(
        ok=True
    )


# =========================================================
# UPLOADS
# =========================================================

@app.route(
    "/uploads/<path:filename>"
)
def uploaded_file(filename):

    return send_from_directory(
        UPLOADS,
        filename
    )


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    return jsonify(
        ok=True,
        service="online-novin"
    )


# =========================================================
# START
# =========================================================

init_db()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
