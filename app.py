import os
import json
import secrets
import sqlite3
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
# APP
# =========================================================

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "site.db")
UPLOADS = os.path.join(BASE, "uploads")

os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "CHANGE_THIS_SECRET_KEY"
)


# =========================================================
# DATABASE
# =========================================================

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
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

    CREATE TABLE IF NOT EXISTS subservices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        price INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        fields_json TEXT DEFAULT '[]',
        documents_json TEXT DEFAULT '[]',
        created_at TEXT,
        FOREIGN KEY(service_id) REFERENCES services(id)
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
        paid_price INTEGER DEFAULT 0,
        discount_amount INTEGER DEFAULT 0,
        discount_code TEXT DEFAULT '',
        payment_status TEXT DEFAULT 'unpaid',
        payment_mode TEXT DEFAULT 'full',
        estimated_time TEXT DEFAULT '',
        assigned_admin_id INTEGER,
        assigned_at TEXT,
        finished_at TEXT,
        customer_note TEXT DEFAULT '',
        admin_note TEXT DEFAULT '',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS request_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        admin_id INTEGER NOT NULL,
        accepted INTEGER DEFAULT 0,
        accepted_at TEXT,
        rejected INTEGER DEFAULT 0,
        rejected_at TEXT,
        UNIQUE(request_id, admin_id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        admin_id INTEGER,
        sender TEXT,
        message TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        admin_id INTEGER,
        field_name TEXT,
        original_name TEXT,
        stored_name TEXT,
        file_type TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        admin_id INTEGER,
        title TEXT,
        message TEXT,
        request_id INTEGER,
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS notification_settings (
        id INTEGER PRIMARY KEY CHECK(id = 1),
        browser_enabled INTEGER DEFAULT 1,
        sms_enabled INTEGER DEFAULT 0,
        always_notify INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        role TEXT DEFAULT 'admin',
        active INTEGER DEFAULT 1,
        is_main INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS admin_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        service_id INTEGER NOT NULL,
        can_view INTEGER DEFAULT 1,
        can_accept INTEGER DEFAULT 1,
        can_work INTEGER DEFAULT 1,
        UNIQUE(admin_id, service_id)
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        request_id INTEGER,
        amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        tracking_id TEXT DEFAULT '',
        transaction_id TEXT DEFAULT '',
        gateway TEXT DEFAULT '',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS financial_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        title TEXT,
        description TEXT DEFAULT '',
        amount INTEGER DEFAULT 0,
        request_id INTEGER,
        payment_id INTEGER,
        created_by INTEGER,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS discount_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        kind TEXT DEFAULT 'percent',
        value INTEGER DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        max_uses INTEGER DEFAULT 0,
        used_count INTEGER DEFAULT 0,
        service_id INTEGER,
        subservice_id INTEGER,
        active INTEGER DEFAULT 1,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS sms_settings (
        id INTEGER PRIMARY KEY CHECK(id = 1),
        enabled INTEGER DEFAULT 0,
        provider TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        api_secret TEXT DEFAULT '',
        sender TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS payment_settings (
        id INTEGER PRIMARY KEY CHECK(id = 1),
        enabled INTEGER DEFAULT 0,
        gateway TEXT DEFAULT '',
        merchant_id TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        test_mode INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    );

    """)

    # مدیر اصلی
    admin = con.execute(
        "SELECT id FROM admins WHERE is_main=1 LIMIT 1"
    ).fetchone()

    if not admin:

        con.execute(
            """
            INSERT INTO admins
            (
                username,
                password,
                name,
                role,
                active,
                is_main,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "admin",
                os.environ.get("ADMIN_PASSWORD", "123456"),
                "مدیر اصلی",
                "main_admin",
                1,
                1,
                now()
            )
        )

    defaults = {

        "site_name": "کافی‌نت آنلاین نوین",
        "manager": "احمد محمدی مهر",
        "phone": "09920345139",

        "logo": "",

        "primary_color": "#102a43",
        "secondary_color": "#1479d1",
        "background_color": "#f5f7fb",
        "card_color": "#ffffff",
        "text_color": "#172033",

        "hero_title": "کافی‌نت آنلاین نوین",
        "hero_text": "ثبت و انجام خدمات اینترنتی به صورت غیرحضوری",

        "tracking_digits": "3",

        "show_hero": "1",
        "show_services": "1",

        "payment_enabled": "0",
        "sms_enabled": "0"
    }

    for key, value in defaults.items():

        con.execute(
            """
            INSERT OR IGNORE INTO settings
            (key,value)
            VALUES (?,?)
            """,
            (key, value)
        )

    con.execute(
        """
        INSERT OR IGNORE INTO notification_settings
        (id,browser_enabled,sms_enabled,always_notify)
        VALUES (1,1,0,1)
        """
    )

    con.execute(
        """
        INSERT OR IGNORE INTO sms_settings
        (id,enabled,provider,api_key,api_secret,sender)
        VALUES (1,0,'','','','')
        """
    )

    con.execute(
        """
        INSERT OR IGNORE INTO payment_settings
        (id,enabled,gateway,merchant_id,api_key,test_mode)
        VALUES (1,0,'','','',1)
        """
    )

    con.commit()
    con.close()


def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


init_db()


# =========================================================
# SETTINGS
# =========================================================

def get_settings():

    con = db()

    rows = con.execute(
        "SELECT key,value FROM settings"
    ).fetchall()

    con.close()

    return {
        r["key"]: r["value"]
        for r in rows
    }


# =========================================================
# AUTH
# =========================================================

def is_admin():

    return bool(
        session.get("admin_id")
    )


def is_main_admin():

    return (
        session.get("admin_role")
        == "main_admin"
    )


def current_admin_id():

    return session.get("admin_id")


def require_admin():

    if not is_admin():
        return redirect(
            url_for("admin_login")
        )

    return None


# =========================================================
# TRACKING CODE
# =========================================================

def generate_tracking_code():

    con = db()

    while True:

        code = "".join(
            secrets.choice(
                string.digits
            )
            for _ in range(3)
        )

        exists = con.execute(
            """
            SELECT id
            FROM requests
            WHERE tracking_code=?
            AND status NOT IN ('انجام شد','لغو شد','رد شد')
            LIMIT 1
            """,
            (code,)
        ).fetchone()

        if not exists:
            con.close()
            return code


# =========================================================
# NOTIFICATIONS
# =========================================================

def notify_customer(
    customer_id,
    title,
    message,
    request_id=None
):

    con = db()

    con.execute(
        """
        INSERT INTO notifications
        (
            customer_id,
            title,
            message,
            request_id,
            created_at
        )
        VALUES (?,?,?,?,?)
        """,
        (
            customer_id,
            title,
            message,
            request_id,
            now()
        )
    )

    con.commit()
    con.close()


def notify_admin(
    admin_id,
    title,
    message,
    request_id=None
):

    con = db()

    con.execute(
        """
        INSERT INTO notifications
        (
            admin_id,
            title,
            message,
            request_id,
            created_at
        )
        VALUES (?,?,?,?,?)
        """,
        (
            admin_id,
            title,
            message,
            request_id,
            now()
        )
    )

    con.commit()
    con.close()


def notify_main_admins(
    title,
    message,
    request_id=None
):

    con = db()

    admins = con.execute(
        """
        SELECT id
        FROM admins
        WHERE is_main=1
        AND active=1
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
                request_id,
                created_at
            )
            VALUES (?,?,?,?,?)
            """,
            (
                admin["id"],
                title,
                message,
                request_id,
                now()
            )
        )

    con.commit()
    con.close()


# =========================================================
# FILE UPLOAD
# =========================================================

def save_files(
    request_id,
    customer_id=None,
    admin_id=None
):

    for field_name in request.files:

        files = request.files.getlist(
            field_name
        )

        for uploaded in files:

            if not uploaded:
                continue

            if not uploaded.filename:
                continue

            original = secure_filename(
                uploaded.filename
            )

            if not original:
                continue

            stored = (
                secrets.token_hex(12)
                + "_"
                + original
            )

            uploaded.save(
                os.path.join(
                    UPLOADS,
                    stored
                )
            )

            con = db()

            con.execute(
                """
                INSERT INTO files
                (
                    request_id,
                    customer_id,
                    admin_id,
                    field_name,
                    original_name,
                    stored_name,
                    file_type,
                    created_at
                )
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    request_id,
                    customer_id,
                    admin_id,
                    field_name,
                    original,
                    stored,
                    uploaded.content_type or "",
                    now()
                )
            )

            con.commit()
            con.close()


# =========================================================
# DISCOUNT
# =========================================================

def calculate_discount(
    code,
    price,
    service_id=None,
    subservice_id=None
):

    if not code:
        return 0

    con = db()

    row = con.execute(
        """
        SELECT *
        FROM discount_codes
        WHERE code=?
        AND active=1
        """,
        (code,)
    ).fetchone()

    if not row:
        con.close()
        return 0

    if row["max_uses"] > 0:

        if row["used_count"] >= row["max_uses"]:
            con.close()
            return 0

    if row["service_id"]:

        if row["service_id"] != service_id:
            con.close()
            return 0

    if row["subservice_id"]:

        if row["subservice_id"] != subservice_id:
            con.close()
            return 0

    if row["kind"] == "percent":

        amount = int(
            price * row["value"] / 100
        )

    else:

        amount = row["value"]

    amount = min(
        amount,
        price
    )

    con.close()

    return amount


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
        WHERE active=1
        ORDER BY sort_order ASC,id DESC
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
    methods=["GET","POST"]
)
def service(sid):

    con = db()

    service_item = con.execute(
        """
        SELECT *
        FROM services
        WHERE id=?
        AND active=1
        """,
        (sid,)
    ).fetchone()

    subservices = con.execute(
        """
        SELECT *
        FROM subservices
        WHERE service_id=?
        AND active=1
        ORDER BY id ASC
        """,
        (sid,)
    ).fetchall()

    con.close()

    if not service_item:
        return "سامانه پیدا نشد.",404

    if request.method == "POST":

        name = request.form.get(
            "name",""
        ).strip()

        national_id = request.form.get(
            "national_id",""
        ).strip()

        phone = request.form.get(
            "phone",""
        ).strip()

        subservice_id = request.form.get(
            "subservice_id",
            ""
        ).strip()

        if not name:
            flash(
                "نام و نام خانوادگی الزامی است."
            )
            return redirect(request.url)

        if not national_id:
            flash(
                "کد ملی الزامی است."
            )
            return redirect(request.url)

        if not phone:
            flash(
                "شماره موبایل الزامی است."
            )
            return redirect(request.url)

        selected_subservice = None

        if subservice_id:

            con = db()

            selected_subservice = con.execute(
                """
                SELECT *
                FROM subservices
                WHERE id=?
                AND service_id=?
                AND active=1
                """,
                (
                    subservice_id,
                    sid
                )
            ).fetchone()

            con.close()

        price = (
            selected_subservice["price"]
            if selected_subservice
            else service_item["price"]
        )

        discount_code = request.form.get(
            "discount_code",
            ""
        ).strip()

        discount = calculate_discount(
            discount_code,
            price,
            sid,
            selected_subservice["id"]
            if selected_subservice
            else None
        )

        final_price = max(
            price - discount,
            0
        )

        con = db()

        customer = con.execute(
            """
            SELECT *
            FROM customers
            WHERE phone=?
            OR national_id=?
            LIMIT 1
            """,
            (
                phone,
                national_id
            )
        ).fetchone()

        if customer:

            customer_id = customer["id"]

            con.execute(
                """
                UPDATE customers
                SET name=?,
                    phone=?,
                    national_id=?
                WHERE id=?
                """,
                (
                    name,
                    phone,
                    national_id,
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
                VALUES (?,?,?,?)
                """,
                (
                    name,
                    national_id,
                    phone,
                    now()
                )
            )

            customer_id = cursor.lastrowid

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

        tracking = generate_tracking_code()

        payment_status = (
            "paid"
            if final_price == 0
            else "unpaid"
        )

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
                paid_price,
                discount_amount,
                discount_code,
                payment_status,
                created_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                customer_id,
                sid,
                selected_subservice["id"]
                if selected_subservice
                else None,
                json.dumps(
                    data,
                    ensure_ascii=False
                ),
                "جدید",
                tracking,
                final_price,
                0,
                discount,
                discount_code,
                payment_status,
                now()
            )
        )

        request_id = cursor.lastrowid

        if discount_code and discount:

            con.execute(
                """
                UPDATE discount_codes
                SET used_count=used_count+1
                WHERE code=?
                """,
                (discount_code,)
            )

        con.commit()
        con.close()

        save_files(
            request_id,
            customer_id
        )

        notify_main_admins(
            "درخواست جدید",
            f"درخواست جدید با کد {tracking} ثبت شد.",
            request_id
        )

        if final_price == 0:

            flash(
                "درخواست شما بدون نیاز به پرداخت ثبت شد."
            )

            return render_template(
                "success.html",
                code=tracking,
                price=0,
                settings=get_settings()
            )

        return redirect(
            url_for(
                "payment",
                rid=request_id
            )
        )

    return render_template(
        "service.html",
        service=service_item,
        subservices=subservices,
        settings=get_settings()
    )


# =========================================================
# PAYMENT
# =========================================================

@app.route(
    "/payment/<int:rid>"
)
def payment(rid):

    customer_id = session.get(
        "customer_id"
    )

    con = db()

    item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id=?
        """,
        (rid,)
    ).fetchone()

    con.close()

    if not item:
        return "درخواست پیدا نشد.",404

    return render_template(
        "payment.html",
        request_item=item,
        settings=get_settings()
    )


@app.post(
    "/payment/<int:rid>/pay"
)
def payment_pay(rid):

    con = db()

    item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id=?
        """,
        (rid,)
    ).fetchone()

    if not item:
        con.close()
        return "درخواست پیدا نشد.",404

    amount = item["total_price"]

    con.execute(
        """
        INSERT INTO payments
        (
            customer_id,
            request_id,
            amount,
            status,
            gateway,
            created_at
        )
        VALUES (?,?,?,?,?,?)
        """,
        (
            item["customer_id"],
            rid,
            amount,
            "paid",
            "configured_gateway",
            now()
        )
    )

    payment_id = con.execute(
        "SELECT last_insert_rowid()"
    ).fetchone()[0]

    con.execute(
        """
        UPDATE requests
        SET
            paid_price=?,
            payment_status='paid'
        WHERE id=?
        """,
        (
            amount,
            rid
        )
    )

    con.execute(
        """
        INSERT INTO financial_transactions
        (
            type,
            title,
            description,
            amount,
            request_id,
            payment_id,
            created_at
        )
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            "income",
            "دریافت هزینه خدمت",
            "پرداخت مشتری",
            amount,
            rid,
            payment_id,
            now()
        )
    )

    con.commit()
    con.close()

    notify_main_admins(
        "پرداخت جدید",
        f"هزینه درخواست شماره {rid} پرداخت شد.",
        rid
    )

    return redirect(
        url_for(
            "payment_success",
            rid=rid
        )
    )


@app.route(
    "/payment-success/<int:rid>"
)
def payment_success(rid):

    return render_template(
        "success.html",
        code="پرداخت با موفقیت انجام شد",
        settings=get_settings()
    )


# =========================================================
# CUSTOMER LOGIN
# =========================================================

@app.route(
    "/customer/login",
    methods=["GET","POST"]
)
def customer_login():

    if request.method == "POST":

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        if not phone:

            flash(
                "شماره موبایل را وارد کنید."
            )

            return redirect(
                request.url
            )

        con = db()

        customer = con.execute(
            """
            SELECT *
            FROM customers
            WHERE phone=?
            LIMIT 1
            """,
            (phone,)
        ).fetchone()

        if not customer:

            cursor = con.execute(
                """
                INSERT INTO customers
                (
                    name,
                    phone,
                    created_at
                )
                VALUES (?,?,?)
                """,
                (
                    "مشتری",
                    phone,
                    now()
                )
            )

            customer_id = cursor.lastrowid

        else:

            customer_id = customer["id"]

        con.commit()
        con.close()

        session["customer_id"] = customer_id

        return redirect(
            url_for(
                "customer_dashboard"
            )
        )

    return render_template(
        "customer_login.html",
        settings=get_settings()
    )


@app.route(
    "/customer/logout"
)
def customer_logout():

    session.pop(
        "customer_id",
        None
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# CUSTOMER PANEL
# =========================================================

@app.route("/customer")
def customer_dashboard():

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        return redirect(
            url_for(
                "customer_login"
            )
        )

    con = db()

    customer = con.execute(
        """
        SELECT *
        FROM customers
        WHERE id=?
        """,
        (customer_id,)
    ).fetchone()

    requests_list = con.execute(
        """
        SELECT
            r.*,
            s.name service_name,
            ss.name subservice_name,
            a.name expert_name
        FROM requests r

        LEFT JOIN services s
        ON s.id=r.service_id

        LEFT JOIN subservices ss
        ON ss.id=r.subservice_id

        LEFT JOIN admins a
        ON a.id=r.assigned_admin_id

        WHERE r.customer_id=?

        ORDER BY r.id DESC
        """,
        (customer_id,)
    ).fetchall()

    notifications = con.execute(
        """
        SELECT *
        FROM notifications
        WHERE customer_id=?
        ORDER BY id DESC
        LIMIT 50
        """,
        (customer_id,)
    ).fetchall()

    con.close()

    return render_template(
        "customer.html",
        customer=customer,
        requests=requests_list,
        notifications=notifications,
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
            url_for(
                "customer_login"
            )
        )

    con = db()

    item = con.execute(
        """
        SELECT
            r.*,
            s.name service_name,
            ss.name subservice_name,
            a.name expert_name
        FROM requests r

        LEFT JOIN services s
        ON s.id=r.service_id

        LEFT JOIN subservices ss
        ON ss.id=r.subservice_id

        LEFT JOIN admins a
        ON a.id=r.assigned_admin_id

        WHERE r.id=?
        AND r.customer_id=?
        """,
        (
            rid,
            customer_id
        )
    ).fetchone()

    messages = con.execute(
        """
        SELECT
            m.*,
            a.name admin_name
        FROM messages m
        LEFT JOIN admins a
        ON a.id=m.admin_id
        WHERE m.request_id=?
        ORDER BY m.id ASC
        """,
        (rid,)
    ).fetchall()

    files = con.execute(
        """
        SELECT *
        FROM files
        WHERE request_id=?
        ORDER BY id DESC
        """,
        (rid,)
    ).fetchall()

    con.close()

    if not item:
        return "درخواست پیدا نشد.",404

    return render_template(
        "customer_request.html",
        request_item=item,
        messages=messages,
        files=files,
        settings=get_settings()
    )


# =========================================================
# CUSTOMER CHAT
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
            url_for(
                "customer_login"
            )
        )

    message = request.form.get(
        "message",
        ""
    ).strip()

    con = db()

    valid = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id=?
        AND customer_id=?
        """,
        (
            rid,
            customer_id
        )
    ).fetchone()

    if not valid:

        con.close()

        return "دسترسی غیرمجاز.",403

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
        VALUES (?,?,?,?,?)
        """,
        (
            rid,
            customer_id,
            "customer",
            message,
            now()
        )
    )

    con.commit()
    con.close()

    if valid["assigned_admin_id"]:

        notify_admin(
            valid["assigned_admin_id"],
            "پیام جدید مشتری",
            "برای یکی از پرونده‌های شما پیام جدید ارسال شده است.",
            rid
        )

    notify_main_admins(
        "پیام جدید مشتری",
        f"برای پرونده {rid} پیام جدید ثبت شد.",
        rid
    )

    return redirect(
        url_for(
            "customer_request",
            rid=rid
        )
    )


@app.post(
    "/customer/request/<int:rid>/upload"
)
def customer_upload(rid):

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:
        return redirect(
            url_for(
                "customer_login"
            )
        )

    con = db()

    valid = con.execute(
        """
        SELECT id
        FROM requests
        WHERE id=?
        AND customer_id=?
        """,
        (
            rid,
            customer_id
        )
    ).fetchone()

    con.close()

    if not valid:
        return "دسترسی غیرمجاز.",403

    save_files(
        rid,
        customer_id=customer_id
    )

    notify_main_admins(
        "مدرک جدید مشتری",
        f"برای پرونده {rid} فایل جدید ارسال شد.",
        rid
    )

    return redirect(
        url_for(
            "customer_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET","POST"]
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
            WHERE username=?
            AND password=?
            AND active=1
            """,
            (
                username,
                password
            )
        ).fetchone()

        con.close()

        if admin:

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


@app.route(
    "/admin/logout"
)
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

    check = require_admin()

    if check:
        return check

    con = db()

    admin_id = current_admin_id()

    admin_item = con.execute(
        """
        SELECT *
        FROM admins
        WHERE id=?
        """,
        (admin_id,)
    ).fetchone()

    services = con.execute(
        """
        SELECT *
        FROM services
        ORDER BY sort_order ASC,id DESC
        """
    ).fetchall()

    subservices = con.execute(
        """
        SELECT
            ss.*,
            s.name service_name
        FROM subservices ss
        JOIN services s
        ON s.id=ss.service_id
        ORDER BY ss.id DESC
        """
    ).fetchall()

    if is_main_admin():

        requests_list = con.execute(
            """
            SELECT
                r.*,
                s.name service_name,
                ss.name subservice_name,
                c.name customer_name,
                c.phone customer_phone,
                a.name expert_name
            FROM requests r
            LEFT JOIN services s
            ON s.id=r.service_id
            LEFT JOIN subservices ss
            ON ss.id=r.subservice_id
            LEFT JOIN customers c
            ON c.id=r.customer_id
            LEFT JOIN admins a
            ON a.id=r.assigned_admin_id
            ORDER BY r.id DESC
            """
        ).fetchall()

    else:

        requests_list = con.execute(
            """
            SELECT
                r.*,
                s.name service_name,
                ss.name subservice_name,
                c.name customer_name,
                c.phone customer_phone,
                a.name expert_name
            FROM requests r
            LEFT JOIN services s
            ON s.id=r.service_id
            LEFT JOIN subservices ss
            ON ss.id=r.subservice_id
            LEFT JOIN customers c
            ON c.id=r.customer_id
            LEFT JOIN admins a
            ON a.id=r.assigned_admin_id

            JOIN admin_permissions p
            ON p.service_id=r.service_id

            WHERE p.admin_id=?
            AND p.can_view=1

            ORDER BY r.id DESC
            """,
            (admin_id,)
        ).fetchall()

    customers = con.execute(
        """
        SELECT
            c.*,
            COUNT(r.id) request_count
        FROM customers c
        LEFT JOIN requests r
        ON r.customer_id=c.id
        GROUP BY c.id
        ORDER BY c.id DESC
        """
    ).fetchall()

    notifications = con.execute(
        """
        SELECT *
        FROM notifications
        WHERE admin_id=?
        ORDER BY id DESC
        LIMIT 50
        """,
        (admin_id,)
    ).fetchall()

    con.close()

    return render_template(
        "admin.html",
        admin=admin_item,
        services=services,
        subservices=subservices,
        requests=requests_list,
        customers=customers,
        notifications=notifications,
        settings=get_settings()
    )


# =========================================================
# SERVICE SAVE
# =========================================================

@app.post(
    "/admin/service/save"
)
def admin_service_save():

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "فقط مدیر اصلی اجازه دارد سامانه ایجاد کند.",403

    name = request.form.get(
        "name",""
    ).strip()

    description = request.form.get(
        "description",""
    ).strip()

    category = request.form.get(
        "category",""
    ).strip()

    price = int(
        request.form.get(
            "price",
            0
        ) or 0
    )

    active = (
        1
        if request.form.get("active")
        == "1"
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
        json.loads(documents_json)
    except Exception:
        return "فرمت فرم یا مدارک اشتباه است.",400

    con = db()

    con.execute(
        """
        INSERT INTO services
        (
            name,
            description,
            category,
            price,
            active,
            fields_json,
            documents_json,
            created_at
        )
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            name,
            description,
            category,
            price,
            active,
            fields_json,
            documents_json,
            now()
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# SUBSERVICE
# =========================================================

@app.post(
    "/admin/subservice/save"
)
def admin_subservice_save():

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "دسترسی غیرمجاز.",403

    service_id = request.form.get(
        "service_id"
    )

    name = request.form.get(
        "name",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    price = int(
        request.form.get(
            "price",
            0
        ) or 0
    )

    fields_json = request.form.get(
        "fields_json",
        "[]"
    )

    documents_json = request.form.get(
        "documents_json",
        "[]"
    )

    con = db()

    con.execute(
        """
        INSERT INTO subservices
        (
            service_id,
            name,
            description,
            price,
            fields_json,
            documents_json,
            created_at
        )
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            service_id,
            name,
            description,
            price,
            fields_json,
            documents_json,
            now()
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN CREATE
# =========================================================

@app.post(
    "/admin/create"
)
def admin_create():

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "فقط مدیر اصلی.",403

    username = request.form.get(
        "username"
    ).strip()

    password = request.form.get(
        "password"
    )

    name = request.form.get(
        "name",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    con = db()

    try:

        cursor = con.execute(
            """
            INSERT INTO admins
            (
                username,
                password,
                name,
                phone,
                role,
                active,
                is_main,
                created_at
            )
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                username,
                password,
                name,
                phone,
                "admin",
                1,
                0,
                now()
            )
        )

        admin_id = cursor.lastrowid

        service_ids = request.form.getlist(
            "service_ids"
        )

        for service_id in service_ids:

            con.execute(
                """
                INSERT OR REPLACE INTO admin_permissions
                (
                    admin_id,
                    service_id,
                    can_view,
                    can_accept,
                    can_work
                )
                VALUES (?,?,?,?,?)
                """,
                (
                    admin_id,
                    service_id,
                    1,
                    1,
                    1
                )
            )

        con.commit()

    except sqlite3.IntegrityError:

        con.rollback()
        con.close()

        flash(
            "نام کاربری تکراری است."
        )

        return redirect(
            url_for("admin")
        )

    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ACCEPT REQUEST
# =========================================================

@app.post(
    "/admin/request/<int:rid>/accept"
)
def admin_accept_request(rid):

    check = require_admin()

    if check:
        return check

    admin_id = current_admin_id()

    con = db()

    request_item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id=?
        """,
        (rid,)
    ).fetchone()

    if not request_item:

        con.close()
        return "پرونده پیدا نشد.",404

    # اگر قبلاً پذیرش شده
    if request_item["assigned_admin_id"]:

        con.close()

        flash(
            "این پرونده قبلاً توسط کارشناس دیگری پذیرفته شده است."
        )

        return redirect(
            url_for("admin")
        )

    permission = con.execute(
        """
        SELECT *
        FROM admin_permissions
        WHERE admin_id=?
        AND service_id=?
        AND can_accept=1
        """,
        (
            admin_id,
            request_item["service_id"]
        )
    ).fetchone()

    if not permission and not is_main_admin():

        con.close()
        return "شما اجازه پذیرش این سامانه را ندارید.",403

    # قفل پذیرش
    cursor = con.execute(
        """
        UPDATE requests
        SET
            assigned_admin_id=?,
            assigned_at=?,
            status='پذیرش شد'
        WHERE id=?
        AND assigned_admin_id IS NULL
        """,
        (
            admin_id,
            now(),
            rid
        )
    )

    if cursor.rowcount == 0:

        con.close()

        flash(
            "این پرونده قبلاً توسط شخص دیگری پذیرش شده است."
        )

        return redirect(
            url_for("admin")
        )

    con.execute(
        """
        INSERT OR REPLACE INTO request_assignments
        (
            request_id,
            admin_id,
            accepted,
            accepted_at
        )
        VALUES (?,?,1,?)
        """,
        (
            rid,
            admin_id,
            now()
        )
    )

    con.commit()
    con.close()

    notify_customer(
        request_item["customer_id"],
        "پذیرش درخواست",
        "درخواست شما توسط کارشناس پذیرش شد.",
        rid
    )

    notify_main_admins(
        "پذیرش پرونده",
        f"پرونده {rid} توسط یک کارشناس پذیرفته شد.",
        rid
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN REQUEST
# =========================================================

@app.route(
    "/admin/request/<int:rid>"
)
def admin_request(rid):

    check = require_admin()

    if check:
        return check

    admin_id = current_admin_id()

    con = db()

    item = con.execute(
        """
        SELECT
            r.*,
            s.name service_name,
            ss.name subservice_name,
            c.name customer_name,
            c.phone customer_phone,
            c.national_id,
            a.name expert_name
        FROM requests r
        LEFT JOIN services s
        ON s.id=r.service_id
        LEFT JOIN subservices ss
        ON ss.id=r.subservice_id
        LEFT JOIN customers c
        ON c.id=r.customer_id
        LEFT JOIN admins a
        ON a.id=r.assigned_admin_id
        WHERE r.id=?
        """,
        (rid,)
    ).fetchone()

    messages = con.execute(
        """
        SELECT
            m.*,
            a.name admin_name
        FROM messages m
        LEFT JOIN admins a
        ON a.id=m.admin_id
        WHERE m.request_id=?
        ORDER BY m.id ASC
        """,
        (rid,)
    ).fetchall()

    files = con.execute(
        """
        SELECT *
        FROM files
        WHERE request_id=?
        ORDER BY id DESC
        """
    ).fetchall()

    admins = con.execute(
        """
        SELECT *
        FROM admins
        WHERE active=1
        ORDER BY is_main DESC,id ASC
        """
    ).fetchall()

    con.close()

    if not item:
        return "پرونده پیدا نشد.",404

    if (
        not is_main_admin()
        and item["assigned_admin_id"]
        != admin_id
    ):

        return "این پرونده در اختیار شما نیست.",403

    return render_template(
        "admin_request.html",
        request_item=item,
        messages=messages,
        files=files,
        admins=admins,
        settings=get_settings()
    )


# =========================================================
# ADMIN UPDATE REQUEST
# =========================================================

@app.post(
    "/admin/request/<int:rid>/update"
)
def admin_update_request(rid):

    check = require_admin()

    if check:
        return check

    admin_id = current_admin_id()

    con = db()

    item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id=?
        """,
        (rid,)
    ).fetchone()

    if not item:

        con.close()
        return "پرونده پیدا نشد.",404

    if (
        not is_main_admin()
        and item["assigned_admin_id"]
        != admin_id
    ):

        con.close()

        return "دسترسی غیرمجاز.",403

    status = request.form.get(
        "status",
        "در حال بررسی"
    )

    estimated_time = request.form.get(
        "estimated_time",
        ""
    ).strip()

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    con.execute(
        """
        UPDATE requests
        SET
            status=?,
            estimated_time=?,
            admin_note=?
        WHERE id=?
        """,
        (
            status,
            estimated_time,
            admin_note,
            rid
        )
    )

    if status == "انجام شد":

        con.execute(
            """
            UPDATE requests
            SET finished_at=?
            WHERE id=?
            """,
            (
                now(),
                rid
            )
        )

    con.commit()
    con.close()

    notify_customer(
        item["customer_id"],
        "تغییر وضعیت پرونده",
        f"وضعیت پرونده شما به «{status}» تغییر کرد.",
        rid
    )

    if item["assigned_admin_id"]:

        notify_admin(
            item["assigned_admin_id"],
            "تغییر وضعیت پرونده",
            f"وضعیت پرونده {rid} تغییر کرد.",
            rid
        )

    notify_main_admins(
        "تغییر وضعیت پرونده",
        f"وضعیت پرونده {rid} تغییر کرد.",
        rid
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


# =========================================================
# ADMIN CHAT
# =========================================================

@app.post(
    "/admin/request/<int:rid>/message"
)
def admin_message(rid):

    check = require_admin()

    if check:
        return check

    admin_id = current_admin_id()

    message = request.form.get(
        "message",
        ""
    ).strip()

    con = db()

    item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id=?
        """,
        (rid,)
    ).fetchone()

    if not item:

        con.close()
        return "پرونده پیدا نشد.",404

    if (
        not is_main_admin()
        and item["assigned_admin_id"]
        != admin_id
    ):

        con.close()
        return "دسترسی غیرمجاز.",403

    con.execute(
        """
        INSERT INTO messages
        (
            request_id,
            customer_id,
            admin_id,
            sender,
            message,
            created_at
        )
        VALUES (?,?,?,?,?,?)
        """,
        (
            rid,
            item["customer_id"],
            admin_id,
            "admin",
            message,
            now()
        )
    )

    con.commit()
    con.close()

    notify_customer(
        item["customer_id"],
        "پیام کارشناس",
        message,
        rid
    )

    notify_main_admins(
        "پیام کارشناس",
        f"برای پرونده {rid} پیام جدید ثبت شد.",
        rid
    )

    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
    )


@app.post(
    "/admin/request/<int:rid>/upload"
)
def admin_upload(rid):

    check = require_admin()

    if check:
        return check

    admin_id = current_admin_id()

    con = db()

    item = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id=?
        """,
        (rid,)
    ).fetchone()

    con.close()

    if not item:
        return "پرونده پیدا نشد.",404

    if (
        not is_main_admin()
        and item["assigned_admin_id"]
        != admin_id
    ):
        return "دسترسی غیرمجاز.",403

    save_files(
        rid,
        admin_id=admin_id
    )

    notify_customer(
        item["customer_id"],
        "فایل جدید",
        "کارشناس برای پرونده شما فایل جدید ارسال کرد.",
        rid
    )

    notify_main_admins(
        "فایل جدید پرونده",
        f"برای پرونده {rid} فایل جدید ارسال شد.",
        rid
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

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "دسترسی غیرمجاز.",403

    code = request.form.get(
        "code",
        ""
    ).strip().upper()

    kind = request.form.get(
        "kind",
        "percent"
    )

    value = int(
        request.form.get(
            "value",
            0
        ) or 0
    )

    max_uses = int(
        request.form.get(
            "max_uses",
            0
        ) or 0
    )

    service_id = request.form.get(
        "service_id"
    ) or None

    subservice_id = request.form.get(
        "subservice_id"
    ) or None

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
                active,
                created_at
            )
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                code,
                kind,
                value,
                max_uses,
                service_id,
                subservice_id,
                1,
                now()
            )
        )

        con.commit()

    except sqlite3.IntegrityError:

        con.rollback()

        flash(
            "این کد تخفیف قبلاً وجود دارد."
        )

    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# FINANCE
# =========================================================

@app.route(
    "/admin/finance"
)
def admin_finance():

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "دسترسی غیرمجاز.",403

    con = db()

    income = con.execute(
        """
        SELECT COALESCE(SUM(amount),0) total
        FROM financial_transactions
        WHERE type='income'
        """
    ).fetchone()["total"]

    expense = con.execute(
        """
        SELECT COALESCE(SUM(amount),0) total
        FROM financial_transactions
        WHERE type='expense'
        """
    ).fetchone()["total"]

    transactions = con.execute(
        """
        SELECT *
        FROM financial_transactions
        ORDER BY id DESC
        """
    ).fetchall()

    payments = con.execute(
        """
        SELECT
            p.*,
            c.name customer_name
        FROM payments p
        LEFT JOIN customers c
        ON c.id=p.customer_id
        ORDER BY p.id DESC
        """
    ).fetchall()

    con.close()

    balance = income - expense

    return render_template(
        "finance.html",
        income=income,
        expense=expense,
        balance=balance,
        transactions=transactions,
        payments=payments,
        settings=get_settings()
    )


@app.post(
    "/admin/finance/add"
)
def admin_finance_add():

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "دسترسی غیرمجاز.",403

    kind = request.form.get(
        "type",
        "expense"
    )

    title = request.form.get(
        "title",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    amount = int(
        request.form.get(
            "amount",
            0
        ) or 0
    )

    con = db()

    con.execute(
        """
        INSERT INTO financial_transactions
        (
            type,
            title,
            description,
            amount,
            created_by,
            created_at
        )
        VALUES (?,?,?,?,?,?)
        """,
        (
            kind,
            title,
            description,
            amount,
            current_admin_id(),
            now()
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for(
            "admin_finance"
        )
    )


# =========================================================
# PAYMENT SETTINGS
# =========================================================

@app.post(
    "/admin/payment/settings"
)
def admin_payment_settings():

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "دسترسی غیرمجاز.",403

    con = db()

    con.execute(
        """
        UPDATE payment_settings
        SET
            enabled=?,
            gateway=?,
            merchant_id=?,
            api_key=?,
            test_mode=?
        WHERE id=1
        """,
        (
            1 if request.form.get("enabled")
            else 0,
            request.form.get(
                "gateway",
                ""
            ),
            request.form.get(
                "merchant_id",
                ""
            ),
            request.form.get(
                "api_key",
                ""
            ),
            1 if request.form.get(
                "test_mode"
            ) else 0
        )
    )

    con.commit()
    con.close()

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

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "دسترسی غیرمجاز.",403

    con = db()

    con.execute(
        """
        UPDATE sms_settings
        SET
            enabled=?,
            provider=?,
            api_key=?,
            api_secret=?,
            sender=?
        WHERE id=1
        """,
        (
            1 if request.form.get("enabled")
            else 0,
            request.form.get(
                "provider",
                ""
            ),
            request.form.get(
                "api_key",
                ""
            ),
            request.form.get(
                "api_secret",
                ""
            ),
            request.form.get(
                "sender",
                ""
            )
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# NOTIFICATION SETTINGS
# =========================================================

@app.post(
    "/admin/notifications/settings"
)
def admin_notification_settings():

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "دسترسی غیرمجاز.",403

    con = db()

    con.execute(
        """
        UPDATE notification_settings
        SET
            browser_enabled=?,
            sms_enabled=?,
            always_notify=?
        WHERE id=1
        """,
        (
            1 if request.form.get(
                "browser_enabled"
            ) else 0,
            1 if request.form.get(
                "sms_enabled"
            ) else 0,
            1 if request.form.get(
                "always_notify"
            ) else 0
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# SITE APPEARANCE
# =========================================================

@app.post(
    "/admin/settings"
)
def admin_settings():

    check = require_admin()

    if check:
        return check

    if not is_main_admin():
        return "دسترسی غیرمجاز.",403

    keys = [
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
        "tracking_digits",
        "show_hero",
        "show_services"
    ]

    con = db()

    for key in keys:

        value = request.form.get(
            key,
            ""
        ).strip()

        con.execute(
            """
            INSERT OR REPLACE INTO settings
            (key,value)
            VALUES (?,?)
            """,
            (
                key,
                value
            )
        )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# FILE DOWNLOAD
# =========================================================

@app.route(
    "/uploads/<path:filename>"
)
def uploaded_file(filename):

    return send_from_directory(
        UPLOADS,
        filename,
        as_attachment=False
    )


@app.route(
    "/uploads/download/<path:filename>"
)
def download_file(filename):

    if not is_admin():
        return "دسترسی غیرمجاز.",403

    return send_from_directory(
        UPLOADS,
        filename,
        as_attachment=True
    )


# =========================================================
# TRACKING
# =========================================================

@app.route(
    "/tracking",
    methods=["GET","POST"]
)
def tracking():

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
                s.name service_name,
                ss.name subservice_name,
                a.name expert_name
            FROM requests r
            LEFT JOIN services s
            ON s.id=r.service_id
            LEFT JOIN subservices ss
            ON ss.id=r.subservice_id
            LEFT JOIN admins a
            ON a.id=r.assigned_admin_id
            WHERE r.tracking_code=?
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
