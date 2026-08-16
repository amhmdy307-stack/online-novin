import os
import json
import sqlite3
import secrets
import string
from datetime import datetime

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
    return con


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
        price INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        fields_json TEXT DEFAULT '[]',
        documents_json TEXT DEFAULT '[]',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS service_subservices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        price INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        fields_json TEXT DEFAULT '[]',
        documents_json TEXT DEFAULT '[]',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        service_id INTEGER,
        subservice_id INTEGER,
        data_json TEXT DEFAULT '{}',
        status TEXT DEFAULT 'جدید',
        tracking_code TEXT UNIQUE,
        total_price INTEGER DEFAULT 0,
        discount_amount INTEGER DEFAULT 0,
        final_price INTEGER DEFAULT 0,
        paid_price INTEGER DEFAULT 0,
        payment_mode TEXT DEFAULT 'full',
        assigned_admin_id INTEGER,
        estimated_time TEXT DEFAULT '',
        admin_note TEXT DEFAULT '',
        customer_note TEXT DEFAULT '',
        created_at TEXT,
        accepted_at TEXT,
        completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        sender TEXT,
        sender_admin_id INTEGER,
        message TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        field_name TEXT,
        original_name TEXT,
        stored_name TEXT,
        file_type TEXT,
        sender TEXT DEFAULT 'customer',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        admin_id INTEGER,
        title TEXT,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        request_id INTEGER,
        amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        tracking_id TEXT,
        transaction_id TEXT,
        gateway TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS financial_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        type TEXT DEFAULT 'income',
        amount INTEGER DEFAULT 0,
        description TEXT DEFAULT '',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS discount_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        kind TEXT DEFAULT 'percent',
        value INTEGER DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        max_uses INTEGER DEFAULT 0,
        used_count INTEGER DEFAULT 0,
        service_id INTEGER,
        subservice_id INTEGER,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'staff',
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admin_service_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        service_id INTEGER NOT NULL,
        UNIQUE(admin_id, service_id)
    );

    CREATE TABLE IF NOT EXISTS admin_subservice_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        subservice_id INTEGER NOT NULL,
        UNIQUE(admin_id, subservice_id)
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS sms_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        enabled INTEGER DEFAULT 0,
        provider TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        api_secret TEXT DEFAULT '',
        sender TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS payment_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        enabled INTEGER DEFAULT 0,
        gateway TEXT DEFAULT '',
        merchant_id TEXT DEFAULT '',
        test_mode INTEGER DEFAULT 1
    );

    """)

    # -----------------------------------------------------
    # ADMIN اصلی
    # -----------------------------------------------------

    admin = con.execute(
        "SELECT id FROM admins WHERE username = 'admin'"
    ).fetchone()

    if not admin:

        con.execute(
            """
            INSERT INTO admins
            (username, password, role, active)
            VALUES (?, ?, ?, 1)
            """,
            (
                "admin",
                ADMIN_PASSWORD,
                "admin"
            )
        )

    # -----------------------------------------------------
    # تنظیمات پیش فرض
    # -----------------------------------------------------

    defaults = {

        "site_name": "کافی‌نت آنلاین نوین",
        "manager": "احمد محمدی مهر",
        "phone": "09920345139",

        "logo": "",

        "primary_color": "#1479d1",
        "secondary_color": "#102a43",
        "background_color": "#f5f7fb",
        "card_color": "#ffffff",
        "text_color": "#172033",

        "hero_title": "خدمات آنلاین کافی‌نت نوین",
        "hero_text": "تمام خدمات کافی‌نت را به‌صورت غیرحضوری دریافت کنید.",

        "warning_text":
            "⚠️ پرداخت خدمات فقط از طریق درگاه رسمی سایت انجام می‌شود.",

        "show_hero": "1",
        "show_services": "1",
        "show_tracking": "1",
        "show_customer_login": "1",

        "tracking_digits": "3",

        "sms_enabled": "0",
        "payment_enabled": "0",

        "notification_permission": "0"
    }

    for key, value in defaults.items():

        con.execute(
            """
            INSERT OR IGNORE INTO settings
            (key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )

    # -----------------------------------------------------
    # SMS
    # -----------------------------------------------------

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
        (1, 0, '', '', '', '')
        """
    )

    # -----------------------------------------------------
    # PAYMENT
    # -----------------------------------------------------

    con.execute(
        """
        INSERT OR IGNORE INTO payment_settings
        (
            id,
            enabled,
            gateway,
            merchant_id,
            test_mode
        )
        VALUES
        (1, 0, '', '', 1)
        """
    )

    # -----------------------------------------------------
    # مهم:
    # هیچ خدمت نمونه‌ای ایجاد نمی‌کنیم.
    # تمام خدمات فقط از پنل مدیریت اضافه می‌شوند.
    # -----------------------------------------------------

    con.commit()
    con.close()


init_db()


# =========================================================
# HELPERS
# =========================================================

def admin_required():

    return session.get("admin") is True


def current_admin_id():

    return session.get("admin_id")


def current_admin_role():

    return session.get(
        "admin_role",
        "staff"
    )


def is_main_admin():

    return (
        admin_required()
        and current_admin_role() == "admin"
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


# =========================================================
# TRACKING CODE
# =========================================================

def generate_tracking_code():

    digits = 3

    while True:

        number = "".join(
            secrets.choice(string.digits)
            for _ in range(digits)
        )

        con = db()

        exists = con.execute(
            """
            SELECT id
            FROM requests
            WHERE tracking_code = ?
            AND status != 'انجام شده'
            """,
            (number,)
        ).fetchone()

        con.close()

        if not exists:
            return number


# =========================================================
# FILE UPLOAD
# =========================================================

def save_uploaded_files(
    request_id,
    customer_id,
    sender="customer"
):

    for field_name in request.files:

        uploaded = request.files.getlist(
            field_name
        )

        for file in uploaded:

            if not file:
                continue

            if not file.filename:
                continue

            original_name = secure_filename(
                file.filename
            )

            if not original_name:
                continue

            stored_name = (
                secrets.token_hex(12)
                + "_"
                + original_name
            )

            path = os.path.join(
                UPLOADS,
                stored_name
            )

            file.save(path)

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
                    sender,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    customer_id,
                    field_name,
                    original_name,
                    stored_name,
                    file.content_type or "",
                    sender,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )

            con.commit()
            con.close()


# =========================================================
# NOTIFICATION
# =========================================================

def add_customer_notification(
    customer_id,
    title,
    message
):

    con = db()

    con.execute(
        """
        INSERT INTO notifications
        (
            customer_id,
            title,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            customer_id,
            title,
            message,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    con.commit()
    con.close()


def add_admin_notification(
    admin_id,
    title,
    message
):

    con = db()

    con.execute(
        """
        INSERT INTO notifications
        (
            admin_id,
            title,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            admin_id,
            title,
            message,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    con.commit()
    con.close()


def notify_all_main_admins(
    title,
    message
):

    con = db()

    admins = con.execute(
        """
        SELECT id
        FROM admins
        WHERE role = 'admin'
        AND active = 1
        """
    ).fetchall()

    for admin in admins:

        con.execute(
            """
            INSERT INTO notifications
            (
                admin_id,
                title,
                message,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                admin["id"],
                title,
                message,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

    con.commit()
    con.close()


def notify_request_parties(
    request_id,
    title,
    message
):

    con = db()

    row = con.execute(
        """
        SELECT
            customer_id,
            assigned_admin_id
        FROM requests
        WHERE id = ?
        """,
        (request_id,)
    ).fetchone()

    con.close()

    if not row:
        return

    if row["customer_id"]:

        add_customer_notification(
            row["customer_id"],
            title,
            message
        )

    if row["assigned_admin_id"]:

        add_admin_notification(
            row["assigned_admin_id"],
            title,
            message
        )

    # مدیر اصلی همیشه مطلع باشد
    notify_all_main_admins(
        title,
        message
    )


# =========================================================
# ADMIN SERVICE ACCESS
# =========================================================

def admin_can_access_service(
    admin_id,
    service_id
):

    con = db()

    admin = con.execute(
        """
        SELECT role
        FROM admins
        WHERE id = ?
        """,
        (admin_id,)
    ).fetchone()

    if not admin:
        con.close()
        return False

    if admin["role"] == "admin":
        con.close()
        return True

    row = con.execute(
        """
        SELECT id
        FROM admin_service_permissions
        WHERE admin_id = ?
        AND service_id = ?
        """,
        (
            admin_id,
            service_id
        )
    ).fetchone()

    con.close()

    return bool(row)


def admin_can_access_subservice(
    admin_id,
    subservice_id
):

    con = db()

    admin = con.execute(
        """
        SELECT role
        FROM admins
        WHERE id = ?
        """,
        (admin_id,)
    ).fetchone()

    if not admin:
        con.close()
        return False

    if admin["role"] == "admin":
        con.close()
        return True

    row = con.execute(
        """
        SELECT id
        FROM admin_subservice_permissions
        WHERE admin_id = ?
        AND subservice_id = ?
        """,
        (
            admin_id,
            subservice_id
        )
    ).fetchone()

    con.close()

    return bool(row)


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

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
# SERVICE
# =========================================================

@app.route(
    "/service/<int:sid>",
    methods=["GET", "POST"]
)
def service(sid):

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

    if not service_item:

        con.close()

        return "خدمت موردنظر پیدا نشد.", 404

    subservices = con.execute(
        """
        SELECT *
        FROM service_subservices
        WHERE service_id = ?
        AND active = 1
        ORDER BY sort_order ASC, id DESC
        """,
        (sid,)
    ).fetchall()

    con.close()

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

    if request.method == "POST":

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

        if not name:

            flash(
                "نام و نام خانوادگی الزامی است."
            )

            return redirect(
                request.url
            )

        if not national_id:

            flash(
                "کد ملی الزامی است."
            )

            return redirect(
                request.url
            )

        if not phone:

            flash(
                "شماره تلفن الزامی است."
            )

            return redirect(
                request.url
            )

        try:

            subservice_id = int(
                request.form.get(
                    "subservice_id",
                    "0"
                ) or 0
            )

        except ValueError:

            subservice_id = 0

        con = db()

        # -------------------------------------------------
        # Customer
        # -------------------------------------------------

        customer = con.execute(
            """
            SELECT *
            FROM customers
            WHERE national_id = ?
            OR phone = ?
            LIMIT 1
            """,
            (
                national_id,
                phone
            )
        ).fetchone()

        if customer:

            customer_id = customer["id"]

            con.execute(
                """
                UPDATE customers
                SET
                    name = ?,
                    national_id = ?,
                    phone = ?
                WHERE id = ?
                """,
                (
                    name,
                    national_id,
                    phone,
                    customer_id
                )
            )

        else:

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
                    name,
                    national_id,
                    phone,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )

            customer_id = cursor.lastrowid

        # -------------------------------------------------
        # Price
        # -------------------------------------------------

        total_price = service_item["price"] or 0

        if subservice_id:

            selected_subservice = con.execute(
                """
                SELECT *
                FROM service_subservices
                WHERE id = ?
                AND service_id = ?
                AND active = 1
                """,
                (
                    subservice_id,
                    sid
                )
            ).fetchone()

            if selected_subservice:

                total_price = (
                    selected_subservice["price"]
                    or total_price
                )

        # -------------------------------------------------
        # Data
        # -------------------------------------------------

        data = {}

        for key in request.form.keys():

            if key in (
                "name",
                "national_id",
                "phone",
                "subservice_id",
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

        # -------------------------------------------------
        # Discount
        # -------------------------------------------------

        discount_code = request.form.get(
            "discount_code",
            ""
        ).strip()

        discount_amount = 0

        if discount_code:

            discount = con.execute(
                """
                SELECT *
                FROM discount_codes
                WHERE code = ?
                AND active = 1
                """,
                (discount_code,)
            ).fetchone()

            if discount:

                valid_service = (
                    not discount["service_id"]
                    or discount["service_id"] == sid
                )

                valid_subservice = (
                    not discount["subservice_id"]
                    or discount["subservice_id"] == subservice_id
                )

                valid_usage = (
                    not discount["max_uses"]
                    or discount["used_count"] < discount["max_uses"]
                )

                if (
                    valid_service
                    and valid_subservice
                    and valid_usage
                ):

                    if discount["kind"] == "percent":

                        percent = max(
                            0,
                            min(
                                100,
                                discount["value"]
                            )
                        )

                        discount_amount = int(
                            total_price
                            * percent
                            / 100
                        )

                    else:

                        discount_amount = min(
                            total_price,
                            max(
                                0,
                                discount["value"]
                            )
                        )

        final_price = max(
            0,
            total_price - discount_amount
        )

        tracking_code = generate_tracking_code()

        # -------------------------------------------------
        # وضعیت پرداخت
        # -------------------------------------------------

        if final_price == 0:

            initial_status = "جدید"
            paid_price = 0

        else:

            initial_status = "منتظر پرداخت"
            paid_price = 0

        # -------------------------------------------------
        # Request
        # -------------------------------------------------

        cursor = con.execute(
            """
            INSERT INTO requests
            (
                customer_id,
                service_id,
                subservice_id,
                data_json,
                status,
                tracking_code,
                total_price,
                discount_amount,
                final_price,
                paid_price,
                payment_mode,
                assigned_admin_id,
                estimated_time,
                admin_note,
                customer_note,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                sid,
                subservice_id or None,
                json.dumps(
                    data,
                    ensure_ascii=False
                ),
                initial_status,
                tracking_code,
                total_price,
                discount_amount,
                final_price,
                paid_price,
                "full",
                None,
                "",
                "",
                "",
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        request_id = cursor.lastrowid

        # استفاده از کد تخفیف
        if discount_code and discount_amount > 0:

            con.execute(
                """
                UPDATE discount_codes
                SET used_count = used_count + 1
                WHERE code = ?
                """,
                (discount_code,)
            )

        con.commit()
        con.close()

        save_uploaded_files(
            request_id,
            customer_id,
            "customer"
        )

        # -------------------------------------------------
        # اگر قیمت صفر باشد مستقیم وارد صف کارشناس شود
        # -------------------------------------------------

        if final_price == 0:

            notify_all_main_admins(
                "درخواست جدید",
                f"درخواست {tracking_code} بدون پرداخت ثبت شد."
            )

            add_customer_notification(
                customer_id,
                "ثبت درخواست",
                f"درخواست شما با کد {tracking_code} ثبت شد."
            )

        else:

            add_customer_notification(
                customer_id,
                "در انتظار پرداخت",
                f"درخواست شما با کد {tracking_code} ایجاد شد. مبلغ قابل پرداخت: {final_price:,} ریال"
            )

        return render_template(
            "success.html",
            code=tracking_code,
            price=final_price
        )

    return render_template(
        "service.html",
        service=service_item,
        subservices=subservices,
        fields=fields,
        documents=documents,
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
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
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

    requests_list = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name,
            ss.name AS subservice_name
        FROM requests r
        JOIN services s
        ON s.id = r.service_id
        LEFT JOIN service_subservices ss
        ON ss.id = r.subservice_id
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
        "customer.html",
        customer=customer,
        requests=requests_list,
        notifications=notifications,
        services=services,
        settings=get_settings()
    )


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
            ss.name AS subservice_name
        FROM requests r
        JOIN services s
        ON s.id = r.service_id
        LEFT JOIN service_subservices ss
        ON ss.id = r.subservice_id
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

        return "درخواست پیدا نشد.", 404

    return render_template(
        "customer_request.html",
        request_item=result,
        messages=messages,
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
                sender,
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
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        con.commit()

    con.close()

    notify_request_parties(
        rid,
        "پیام جدید مشتری",
        message
    )

    return redirect(
        url_for(
            "customer_request",
            rid=rid
        )
    )


# =========================================================
# CUSTOMER FILE
# =========================================================

@app.post(
    "/customer/request/<int:rid>/file"
)
def customer_file(rid):

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        return redirect(
            url_for("customer_login")
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

    con.close()

    if not valid:

        return "دسترسی غیرمجاز.", 403

    save_uploaded_files(
        rid,
        customer_id,
        "customer"
    )

    notify_request_parties(
        rid,
        "مدرک جدید",
        "مشتری برای پرونده مدرک جدید ارسال کرد."
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

    result = None

    code = request.values.get(
        "code",
        ""
    ).strip()

    if code:

        con = db()

        result = con.execute(
            """
            SELECT
                r.*,
                s.name AS service_name,
                ss.name AS subservice_name,
                c.name AS customer_name,
                a.username AS assigned_admin
            FROM requests r
            JOIN services s
            ON s.id = r.service_id
            LEFT JOIN service_subservices ss
            ON ss.id = r.subservice_id
            JOIN customers c
            ON c.id = r.customer_id
            LEFT JOIN admins a
            ON a.id = r.assigned_admin_id
            WHERE r.tracking_code = ?
            """,
            (code,)
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

            session["admin"] = True
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

    session.clear()

    return redirect(
        url_for("home")
    )


# =========================================================
# ADMIN PANEL
# =========================================================

@app.route("/admin")
def admin():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    admin_id = current_admin_id()

    con = db()

    if is_main_admin():

        services = con.execute(
            """
            SELECT *
            FROM services
            ORDER BY sort_order ASC, id DESC
            """
        ).fetchall()

        requests_list = con.execute(
            """
            SELECT
                r.*,
                s.name AS service_name,
                ss.name AS subservice_name,
                c.name AS customer_name,
                c.phone AS customer_phone,
                a.username AS assigned_admin
            FROM requests r
            JOIN services s
            ON s.id = r.service_id
            LEFT JOIN service_subservices ss
            ON ss.id = r.subservice_id
            JOIN customers c
            ON c.id = r.customer_id
            LEFT JOIN admins a
            ON a.id = r.assigned_admin_id
            ORDER BY r.id DESC
            """
        ).fetchall()

    else:

        services = con.execute(
            """
            SELECT s.*
            FROM services s
            JOIN admin_service_permissions p
            ON p.service_id = s.id
            WHERE p.admin_id = ?
            ORDER BY s.sort_order ASC, s.id DESC
            """,
            (admin_id,)
        ).fetchall()

        requests_list = con.execute(
            """
            SELECT
                r.*,
                s.name AS service_name,
                ss.name AS subservice_name,
                c.name AS customer_name,
                c.phone AS customer_phone,
                a.username AS assigned_admin
            FROM requests r
            JOIN services s
            ON s.id = r.service_id
            LEFT JOIN service_subservices ss
            ON ss.id = r.subservice_id
            JOIN customers c
            ON c.id = r.customer_id
            LEFT JOIN admins a
            ON a.id = r.assigned_admin_id
            JOIN admin_service_permissions p
            ON p.service_id = r.service_id
            WHERE p.admin_id = ?
            ORDER BY r.id DESC
            """,
            (admin_id,)
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

    admins = con.execute(
        """
        SELECT id, username, role, active
        FROM admins
        ORDER BY id DESC
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

    discount_codes = con.execute(
        """
        SELECT *
        FROM discount_codes
        ORDER BY id DESC
        """
    ).fetchall()

    financial = con.execute(
        """
        SELECT *
        FROM financial_transactions
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()

    con.close()

    return render_template(
        "admin.html",
        services=services,
        customers=customers,
        requests=requests_list,
        admins=admins,
        notifications=notifications,
        discount_codes=discount_codes,
        financial=financial,
        settings=get_settings()
    )


# =========================================================
# ADD SERVICE
# =========================================================

@app.post(
    "/admin/service/save"
)
def admin_service_save():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

    name = request.form.get(
        "name",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    category = request.form.get(
        "category",
        ""
    ).strip()

    image = request.form.get(
        "image",
        ""
    ).strip()

    try:

        price = int(
            request.form.get(
                "price",
                "0"
            ) or 0
        )

    except ValueError:

        price = 0

    try:

        sort_order = int(
            request.form.get(
                "sort_order",
                "0"
            ) or 0
        )

    except ValueError:

        sort_order = 0

    active = (
        1
        if request.form.get("active") == "1"
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

    con = db()

    con.execute(
        """
        INSERT INTO services
        (
            name,
            description,
            category,
            image,
            price,
            active,
            sort_order,
            fields_json,
            documents_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            description,
            category,
            image,
            price,
            active,
            sort_order,
            fields_json,
            documents_json,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    con.commit()
    con.close()

    flash(
        "سامانه با موفقیت اضافه شد."
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADD SUBSERVICE
# =========================================================

@app.post(
    "/admin/subservice/save"
)
def admin_subservice_save():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

    try:

        service_id = int(
            request.form.get(
                "service_id"
            )
        )

    except Exception:

        return redirect(
            url_for("admin")
        )

    name = request.form.get(
        "name",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    try:

        price = int(
            request.form.get(
                "price",
                "0"
            ) or 0
        )

    except ValueError:

        price = 0

    try:

        sort_order = int(
            request.form.get(
                "sort_order",
                "0"
            ) or 0
        )

    except ValueError:

        sort_order = 0

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

    con = db()

    con.execute(
        """
        INSERT INTO service_subservices
        (
            service_id,
            name,
            description,
            price,
            active,
            sort_order,
            fields_json,
            documents_json,
            created_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
        """,
        (
            service_id,
            name,
            description,
            price,
            sort_order,
            fields_json,
            documents_json,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    con.commit()
    con.close()

    flash(
        "زیرسامانه اضافه شد."
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN USERS
# =========================================================

@app.route(
    "/admin/users"
)
def admin_users():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

    con = db()

    admins = con.execute(
        """
        SELECT id, username, role, active
        FROM admins
        ORDER BY id DESC
        """
    ).fetchall()

    services = con.execute(
        """
        SELECT *
        FROM services
        ORDER BY sort_order ASC, id DESC
        """
    ).fetchall()

    subservices = con.execute(
        """
        SELECT *
        FROM service_subservices
        ORDER BY service_id, sort_order, id
        """
    ).fetchall()

    permissions = con.execute(
        """
        SELECT admin_id, service_id
        FROM admin_service_permissions
        """
    ).fetchall()

    sub_permissions = con.execute(
        """
        SELECT admin_id, subservice_id
        FROM admin_subservice_permissions
        """
    ).fetchall()

    con.close()

    permission_map = {}

    for item in permissions:

        permission_map.setdefault(
            item["admin_id"],
            []
        ).append(
            item["service_id"]
        )

    sub_permission_map = {}

    for item in sub_permissions:

        sub_permission_map.setdefault(
            item["admin_id"],
            []
        ).append(
            item["subservice_id"]
        )

    return render_template(
        "admin_users.html",
        admins=admins,
        services=services,
        subservices=subservices,
        permission_map=permission_map,
        sub_permission_map=sub_permission_map,
        settings=get_settings()
    )


# =========================================================
# CREATE ADMIN
# =========================================================

@app.post(
    "/admin/users/save"
)
def admin_users_save():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

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
        "staff"
    )

    service_ids = request.form.getlist(
        "service_ids"
    )

    subservice_ids = request.form.getlist(
        "subservice_ids"
    )

    if not username or not password:

        flash(
            "نام کاربری و رمز عبور الزامی است."
        )

        return redirect(
            url_for("admin_users")
        )

    if len(password) < 6:

        flash(
            "رمز عبور باید حداقل ۶ کاراکتر باشد."
        )

        return redirect(
            url_for("admin_users")
        )

    con = db()

    exists = con.execute(
        """
        SELECT id
        FROM admins
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    if exists:

        con.close()

        flash(
            "این نام کاربری قبلاً وجود دارد."
        )

        return redirect(
            url_for("admin_users")
        )

    cursor = con.execute(
        """
        INSERT INTO admins
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
            password,
            role
        )
    )

    admin_id = cursor.lastrowid

    for service_id in service_ids:

        try:
            service_id = int(service_id)
        except ValueError:
            continue

        con.execute(
            """
            INSERT OR IGNORE INTO
            admin_service_permissions
            (
                admin_id,
                service_id
            )
            VALUES (?, ?)
            """,
            (
                admin_id,
                service_id
            )
        )

    for subservice_id in subservice_ids:

        try:
            subservice_id = int(
                subservice_id
            )
        except ValueError:
            continue

        con.execute(
            """
            INSERT OR IGNORE INTO
            admin_subservice_permissions
            (
                admin_id,
                subservice_id
            )
            VALUES (?, ?)
            """,
            (
                admin_id,
                subservice_id
            )
        )

    con.commit()
    con.close()

    flash(
        "ادمین جدید ایجاد شد."
    )

    return redirect(
        url_for("admin_users")
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

    row = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    if not row:

        con.close()

        return "پرونده پیدا نشد.", 404

    # اگر قبلاً توسط فرد دیگری پذیرفته شده
    if row["assigned_admin_id"]:

        con.close()

        flash(
            "این پرونده قبلاً توسط کارشناس دیگری پذیرفته شده است."
        )

        return redirect(
            url_for("admin")
        )

    if not is_main_admin():

        allowed = admin_can_access_service(
            admin_id,
            row["service_id"]
        )

        if not allowed:

            con.close()

            return "شما به این سامانه دسترسی ندارید.", 403

    # پذیرش اتمیک
    cursor = con.execute(
        """
        UPDATE requests
        SET
            assigned_admin_id = ?,
            status = ?,
            accepted_at = ?
        WHERE id = ?
        AND assigned_admin_id IS NULL
        """,
        (
            admin_id,
            "پذیرش شد",
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            rid
        )
    )

    con.commit()

    accepted = cursor.rowcount

    con.close()

    if accepted:

        notify_request_parties(
            rid,
            "پذیرش پرونده",
            "پرونده توسط کارشناس پذیرش شد."
        )

        flash(
            "پرونده با موفقیت به نام شما ثبت شد."
        )

    else:

        flash(
            "پرونده قبلاً توسط کارشناس دیگری پذیرفته شده است."
        )

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN REQUEST STATUS
# =========================================================

@app.post(
    "/admin/request/status"
)
def admin_request_status():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    request_id = request.form.get(
        "id"
    )

    status = request.form.get(
        "status",
        "جدید"
    )

    estimated_time = request.form.get(
        "estimated_time",
        ""
    ).strip()

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    admin_id = current_admin_id()

    con = db()

    row = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (request_id,)
    ).fetchone()

    if not row:

        con.close()

        return "پرونده پیدا نشد.", 404

    # کارشناس فقط پرونده خودش
    if (
        not is_main_admin()
        and row["assigned_admin_id"] != admin_id
    ):

        con.close()

        return "شما مسئول این پرونده نیستید.", 403

    completed_at = None

    if status == "انجام شده":

        completed_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    con.execute(
        """
        UPDATE requests
        SET
            status = ?,
            estimated_time = ?,
            admin_note = ?,
            completed_at = ?
        WHERE id = ?
        """,
        (
            status,
            estimated_time,
            admin_note,
            completed_at,
            request_id
        )
    )

    con.commit()
    con.close()

    notify_request_parties(
        int(request_id),
        "تغییر وضعیت پرونده",
        f"وضعیت پرونده به «{status}» تغییر کرد."
    )

    if completed_at:

        notify_all_main_admins(
            "پرونده انجام شد",
            f"پرونده {row['tracking_code']} انجام شد."
        )

    return redirect(
        url_for("admin")
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
            ss.name AS subservice_name,
            c.name AS customer_name,
            c.national_id,
            c.phone,
            a.username AS assigned_admin
        FROM requests r
        JOIN services s
        ON s.id = r.service_id
        LEFT JOIN service_subservices ss
        ON ss.id = r.subservice_id
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

    if not is_main_admin():

        if result["assigned_admin_id"]:

            if result["assigned_admin_id"] != admin_id:

                con.close()

                return "این پرونده به کارشناس دیگری اختصاص دارد.", 403

        else:

            if not admin_can_access_service(
                admin_id,
                result["service_id"]
            ):

                con.close()

                return "شما به این سامانه دسترسی ندارید.", 403

    messages = con.execute(
        """
        SELECT *
        FROM messages
        WHERE request_id = ?
        ORDER BY id ASC
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
        files=files,
        settings=get_settings()
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

    message = request.form.get(
        "message",
        ""
    ).strip()

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

    if (
        not is_main_admin()
        and request_item["assigned_admin_id"] != admin_id
    ):

        con.close()

        return "دسترسی غیرمجاز.", 403

    if message:

        con.execute(
            """
            INSERT INTO messages
            (
                request_id,
                customer_id,
                sender,
                sender_admin_id,
                message,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                request_item["customer_id"],
                "admin",
                admin_id,
                message,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        con.commit()

    con.close()

    notify_request_parties(
        rid,
        "پیام کارشناس",
        message
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN FILE
# =========================================================

@app.post(
    "/admin/request/<int:rid>/file"
)
def admin_file(rid):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    admin_id = current_admin_id()

    con = db()

    row = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()

    con.close()

    if not row:

        return "پرونده پیدا نشد.", 404

    if (
        not is_main_admin()
        and row["assigned_admin_id"] != admin_id
    ):

        return "دسترسی غیرمجاز.", 403

    save_uploaded_files(
        rid,
        row["customer_id"],
        "admin"
    )

    notify_request_parties(
        rid,
        "فایل جدید",
        "کارشناس برای پرونده فایل جدید ارسال کرد."
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# DISCOUNT CODE
# =========================================================

@app.post(
    "/admin/discount/save"
)
def admin_discount_save():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

    code = request.form.get(
        "code",
        ""
    ).strip().upper()

    kind = request.form.get(
        "kind",
        "percent"
    )

    try:

        value = int(
            request.form.get(
                "value",
                "0"
            ) or 0
        )

    except ValueError:

        value = 0

    try:

        max_uses = int(
            request.form.get(
                "max_uses",
                "0"
            ) or 0
        )

    except ValueError:

        max_uses = 0

    try:

        service_id = int(
            request.form.get(
                "service_id",
                "0"
            ) or 0
        )

    except ValueError:

        service_id = 0

    try:

        subservice_id = int(
            request.form.get(
                "subservice_id",
                "0"
            ) or 0
        )

    except ValueError:

        subservice_id = 0

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
            min(
                100,
                value
            )
        )

    else:

        value = max(
            0,
            value
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
                max_uses,
                service_id,
                subservice_id,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                code,
                kind,
                value,
                max_uses,
                service_id or None,
                subservice_id or None
            )
        )

        con.commit()

    except sqlite3.IntegrityError:

        con.close()

        flash(
            "این کد تخفیف قبلاً وجود دارد."
        )

        return redirect(
            url_for("admin")
        )

    con.close()

    flash(
        "کد تخفیف ایجاد شد."
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# FINANCIAL TRANSACTION
# =========================================================

@app.post(
    "/admin/finance/save"
)
def admin_finance_save():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

    try:

        amount = int(
            request.form.get(
                "amount",
                "0"
            ) or 0
        )

    except ValueError:

        amount = 0

    transaction_type = request.form.get(
        "type",
        "income"
    )

    description = request.form.get(
        "description",
        ""
    ).strip()

    con = db()

    con.execute(
        """
        INSERT INTO financial_transactions
        (
            type,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            transaction_type,
            amount,
            description,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ONLINE PAYMENT CALLBACK
# =========================================================

@app.route(
    "/payment/callback",
    methods=["GET", "POST"]
)
def payment_callback():

    request_id = request.values.get(
        "request_id",
        ""
    )

    transaction_id = request.values.get(
        "transaction_id",
        ""
    )

    if not request_id:

        return "شناسه درخواست نامعتبر است.", 400

    con = db()

    row = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        """,
        (request_id,)
    ).fetchone()

    if not row:

        con.close()

        return "درخواست پیدا نشد.", 404

    # این بخش محل اتصال درگاه واقعی است.
    # درگاه بعداً از پنل تنظیم می‌شود.

    con.execute(
        """
        UPDATE requests
        SET
            paid_price = final_price,
            status = 'جدید'
        WHERE id = ?
        """,
        (request_id,)
    )

    con.execute(
        """
        INSERT INTO payments
        (
            customer_id,
            request_id,
            amount,
            status,
            transaction_id,
            gateway,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["customer_id"],
            request_id,
            row["final_price"],
            "paid",
            transaction_id,
            "configured_gateway",
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    con.execute(
        """
        INSERT INTO financial_transactions
        (
            request_id,
            customer_id,
            type,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            row["customer_id"],
            "income",
            row["final_price"],
            "پرداخت درخواست خدمات",
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    con.commit()
    con.close()

    notify_all_main_admins(
        "پرداخت موفق",
        f"پرداخت درخواست {row['tracking_code']} انجام شد."
    )

    add_customer_notification(
        row["customer_id"],
        "پرداخت موفق",
        "پرداخت شما با موفقیت ثبت شد."
    )

    return render_template(
        "success.html",
        code=row["tracking_code"],
        price=row["final_price"]
    )


# =========================================================
# ADMIN SETTINGS
# =========================================================

@app.post(
    "/admin/settings"
)
def admin_settings():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

    keys = (

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

        "show_hero",
        "show_services",
        "show_tracking",
        "show_customer_login",

        "tracking_digits",

        "sms_enabled",
        "payment_enabled",

        "notification_permission"
    )

    con = db()

    for key in keys:

        value = request.form.get(
            key,
            ""
        ).strip()

        con.execute(
            """
            INSERT OR REPLACE INTO settings
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
# SMS SETTINGS
# =========================================================

@app.post(
    "/admin/sms/settings"
)
def admin_sms_settings():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

    enabled = (
        1
        if request.form.get("enabled") == "1"
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

    return redirect(
        url_for("admin")
    )


# =========================================================
# PAYMENT SETTINGS
# =========================================================

@app.post(
    "/admin/payment/settings"
)
def admin_payment_settings():

    if not is_main_admin():

        return redirect(
            url_for("admin_login")
        )

    enabled = (
        1
        if request.form.get("enabled") == "1"
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

    test_mode = (
        1
        if request.form.get("test_mode") == "1"
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
            test_mode = ?
        WHERE id = 1
        """,
        (
            enabled,
            gateway,
            merchant_id,
            test_mode
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN PASSWORD
# =========================================================

@app.post(
    "/admin/password"
)
def admin_password():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    new_password = request.form.get(
        "password",
        ""
    )

    if len(new_password) < 6:

        flash(
            "رمز باید حداقل ۶ کاراکتر باشد."
        )

        return redirect(
            url_for("admin")
        )

    con = db()

    con.execute(
        """
        UPDATE admins
        SET password = ?
        WHERE id = ?
        """,
        (
            new_password,
            current_admin_id()
        )
    )

    con.commit()
    con.close()

    flash(
        "رمز مدیریت تغییر کرد."
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route(
    "/admin/notifications/read/<int:nid>"
)
def admin_notification_read(nid):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    con = db()

    con.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        AND admin_id = ?
        """,
        (
            nid,
            current_admin_id()
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


@app.route(
    "/customer/notifications/read/<int:nid>"
)
def customer_notification_read(nid):

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        return redirect(
            url_for("customer_login")
        )

    con = db()

    con.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        AND customer_id = ?
        """,
        (
            nid,
            customer_id
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("customer_dashboard")
    )


# =========================================================
# FILES
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
# RUN
# =========================================================

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
