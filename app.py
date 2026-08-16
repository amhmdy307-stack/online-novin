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
# تنظیمات اصلی
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        service_id INTEGER,
        data_json TEXT DEFAULT '{}',
        status TEXT DEFAULT 'جدید',
        tracking_code TEXT UNIQUE,
        total_price INTEGER DEFAULT 0,
        paid_price INTEGER DEFAULT 0,
        payment_mode TEXT DEFAULT 'full',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        sender TEXT,
        message TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
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

    CREATE TABLE IF NOT EXISTS installments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        installment_number INTEGER,
        amount INTEGER DEFAULT 0,
        due_date TEXT,
        status TEXT DEFAULT 'pending',
        paid_at TEXT
    );

    CREATE TABLE IF NOT EXISTS discount_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        kind TEXT DEFAULT 'percent',
        value INTEGER DEFAULT 0,
        start_date TEXT,
        end_date TEXT,
        max_uses INTEGER DEFAULT 0,
        used_count INTEGER DEFAULT 0,
        service_id INTEGER,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS payment_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        prepayment_percent INTEGER DEFAULT 0,
        installment_count INTEGER DEFAULT 0,
        installment_percent INTEGER DEFAULT 0,
        valid_until TEXT,
        service_id INTEGER,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS free_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        valid_until TEXT,
        max_uses INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0,
        service_id INTEGER,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'admin',
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admin_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        permission TEXT
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

    """)


    # =====================================================
    # مدیر اولیه
    # =====================================================

    if not con.execute(
        "SELECT id FROM admins LIMIT 1"
    ).fetchone():

        con.execute(
            """
            INSERT INTO admins
            (username, password, role, active)
            VALUES (?, ?, ?, ?)
            """,
            (
                "admin",
                ADMIN_PASSWORD,
                "admin",
                1
            )
        )


    # =====================================================
    # تنظیمات سایت
    # =====================================================

    defaults = {

        "site_name":
            "کافی‌نت آنلاین نوین",

        "manager":
            "احمد محمدی مهر",

        "phone":
            "09920345139",

        "logo":
            "",

        "tracking_prefix":
            "NV-",

        "tracking_digits":
            "8",

        "tracking_separator":
            "",

        "warning_text":
            "توجه: پرداخت هزینه خدمات فقط از طریق درگاه رسمی همین سایت.",


        # ==============================
        # ظاهر سایت
        # ==============================

        "theme_primary":
            "#102a43",

        "theme_secondary":
            "#1479d1",

        "theme_background":
            "#f5f7fb",

        "theme_card":
            "#ffffff",

        "theme_text":
            "#172033",

        "theme_button":
            "#1479d1",

        "theme_button_text":
            "#ffffff",


        # ==============================
        # نوشته‌های سایت
        # ==============================

        "site_header_text":
            "خدمات آنلاین",

        "site_subtitle":
            "تمام خدمات کافی‌نت آنلاین نوین به صورت غیرحضوری",


        # ==============================
        # نمایش لینک‌ها
        # ==============================

        "show_warning":
            "1",

        "show_customer_link":
            "1",

        "show_admin_link":
            "1",

        "show_tracking_link":
            "1"

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


    # =====================================================
    # تنظیمات پیامک
    # =====================================================

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


    # =====================================================
    # تنظیمات پرداخت
    # =====================================================

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
        (
            1,
            0,
            '',
            '',
            1
        )
        """
    )


    # =====================================================
    # خدمات اولیه
    # =====================================================

    if not con.execute(
        "SELECT id FROM services LIMIT 1"
    ).fetchone():

        services = [

            (
                "مسکن ملی",
                "ثبت درخواست مسکن ملی و بارگذاری مدارک",
                "مسکن"
            ),

            (
                "ثبت‌نام سهام نوزاد",
                "ثبت اطلاعات پدر و فرزند",
                "سهام نوزاد"
            ),

            (
                "ثبت‌نام خودرو",
                "ایران‌خودرو، سایپا و بهمن موتور",
                "خودرو"
            ),

            (
                "چک صیادی",
                "ثبت، تأیید یا رد چک صیادی",
                "چک صیادی"
            ),

            (
                "ثبت قرارداد",
                "اجاره‌نامه و قولنامه",
                "قرارداد"
            ),

            (
                "جواز کسب",
                "ثبت درخواست جواز کسب",
                "جواز کسب"
            )

        ]


        for name, description, category in services:

            con.execute(
                """
                INSERT INTO services
                (
                    name,
                    description,
                    category,
                    price,
                    active,
                    sort_order,
                    fields_json,
                    documents_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    description,
                    category,
                    0,
                    1,
                    0,
                    "[]",
                    "[]",
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )


    con.commit()

    con.close()


init_db()


# =========================================================
# HELPERS
# =========================================================

def admin_required():

    return session.get("admin") is True


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


def generate_tracking_code():

    settings = get_settings()

    prefix = settings.get(
        "tracking_prefix",
        "NV-"
    )

    try:

        digits = int(
            settings.get(
                "tracking_digits",
                "8"
            )
        )

    except ValueError:

        digits = 8


    digits = max(
        4,
        min(digits, 20)
    )


    separator = settings.get(
        "tracking_separator",
        ""
    )


    while True:

        number = "".join(
            secrets.choice(
                string.digits
            )
            for _ in range(digits)
        )


        code = (
            prefix
            +
            separator
            +
            number
        )


        con = db()

        exists = con.execute(
            """
            SELECT id
            FROM requests
            WHERE tracking_code = ?
            """,
            (code,)
        ).fetchone()

        con.close()


        if not exists:

            return code


def save_uploaded_files(
    request_id,
    customer_id
):

    for field_name in request.files:

        uploaded = request.files.getlist(
            field_name
        )


        for file in uploaded:

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
                +
                "_"
                +
                original_name
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
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )


            con.commit()

            con.close()


def add_notification(
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
        """,
        (sid,)
    ).fetchone()


    con.close()


    if not service_item:

        return (
            "خدمت موردنظر پیدا نشد.",
            404
        )


    if not service_item["active"]:

        return (
            "این خدمت فعال نیست.",
            404
        )


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


        con = db()


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


        data = {}


        for key in request.form.keys():

            if key in (
                "name",
                "national_id",
                "phone"
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


        tracking_code = generate_tracking_code()


        total_price = (
            service_item["price"]
            or 0
        )


        cursor = con.execute(
            """
            INSERT INTO requests
            (
                customer_id,
                service_id,
                data_json,
                status,
                tracking_code,
                total_price,
                paid_price,
                payment_mode,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                sid,
                json.dumps(
                    data,
                    ensure_ascii=False
                ),
                "جدید",
                tracking_code,
                total_price,
                0,
                "full",
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )


        request_id = cursor.lastrowid


        con.commit()

        con.close()


        save_uploaded_files(
            request_id,
            customer_id
        )


        add_notification(
            customer_id,
            "ثبت درخواست",
            f"درخواست شما با کد {tracking_code} ثبت شد."
        )


        return render_template(
            "success.html",
            code=tracking_code
        )


    return render_template(
        "service.html",
        service=service_item,
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
            WHERE phone = ?
            """,
            (phone,)
        ).fetchone()


        if customer:

            customer_id = customer["id"]


        else:

            cursor = con.execute(
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
                    "مشتری جدید",
                    "",
                    phone
                )
            )


            customer_id = cursor.lastrowid


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


# =========================================================
# CUSTOMER LOGOUT
# =========================================================

@app.route(
    "/customer/logout"
)
def customer_logout():

    session.pop(
        "customer_id",
        None
    )


    return redirect(
        url_for(
            "customer_login"
        )
    )


# =========================================================
# CUSTOMER DASHBOARD
# =========================================================

@app.route(
    "/customer"
)
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
        WHERE id = ?
        """,
        (customer_id,)
    ).fetchone()


    requests_list = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name
        FROM requests r
        JOIN services s
        ON s.id = r.service_id
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
        LIMIT 20
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


    result = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name
        FROM requests r
        JOIN services s
        ON s.id = r.service_id
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

        return (
            "درخواست پیدا نشد.",
            404
        )


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
            url_for(
                "customer_login"
            )
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
                c.name AS customer_name
            FROM requests r
            JOIN services s
            ON s.id = r.service_id
            JOIN customers c
            ON c.id = r.customer_id
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
                url_for(
                    "admin"
                )
            )


        flash(
            "نام کاربری یا رمز عبور اشتباه است."
        )


    return render_template(
        "admin_login.html",
        settings=get_settings()
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
        url_for(
            "admin_login"
        )
    )


# =========================================================
# ADMIN PANEL
# =========================================================

@app.route(
    "/admin"
)
def admin():

    if not admin_required():

        return redirect(
            url_for(
                "admin_login"
            )
        )


    con = db()


    services = con.execute(
        """
        SELECT *
        FROM services
        ORDER BY sort_order ASC, id DESC
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


    requests_list = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name,
            c.name AS customer_name,
            c.phone AS customer_phone
        FROM requests r
        JOIN services s
        ON s.id = r.service_id
        JOIN customers c
        ON c.id = r.customer_id
        ORDER BY r.id DESC
        """
    ).fetchall()


    settings = get_settings()


    con.close()


    return render_template(
        "admin.html",
        services=services,
        customers=customers,
        requests=requests_list,
        settings=settings
    )


# =========================================================
# ADMIN SERVICE SAVE
# =========================================================

@app.post(
    "/admin/service/save"
)
def admin_service_save():

    if not admin_required():

        return redirect(
            url_for(
                "admin_login"
            )
        )


    sid = request.form.get(
        "id",
        ""
    ).strip()


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
            )
            or 0
        )

    except ValueError:

        price = 0


    try:

        sort_order = int(
            request.form.get(
                "sort_order",
                "0"
            )
            or 0
        )

    except ValueError:

        sort_order = 0


    active = (
        1
        if request.form.get(
            "active"
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

        json.loads(
            fields_json
        )

    except Exception:

        fields_json = "[]"


    try:

        json.loads(
            documents_json
        )

    except Exception:

        documents_json = "[]"


    con = db()


    if sid:

        con.execute(
            """
            UPDATE services

            SET
                name = ?,
                description = ?,
                category = ?,
                image = ?,
                price = ?,
                active = ?,
                sort_order = ?,
                fields_json = ?,
                documents_json = ?

            WHERE id = ?
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
                sid
            )
        )


    else:

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


    return redirect(
        url_for(
            "admin"
        )
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
            url_for(
                "admin_login"
            )
        )


    request_id = request.form.get(
        "id"
    )


    status = request.form.get(
        "status",
        "جدید"
    )


    con = db()


    row = con.execute(
        """
        SELECT customer_id
        FROM requests
        WHERE id = ?
        """,
        (request_id,)
    ).fetchone()


    con.execute(
        """
        UPDATE requests
        SET status = ?
        WHERE id = ?
        """,
        (
            status,
            request_id
        )
    )


    con.commit()

    con.close()


    if row:

        add_notification(
            row["customer_id"],
            "تغییر وضعیت درخواست",
            f"وضعیت درخواست شما به «{status}» تغییر کرد."
        )


    return redirect(
        url_for(
            "admin"
        )
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
            url_for(
                "admin_login"
            )
        )


    con = db()


    result = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name,
            c.name AS customer_name,
            c.national_id,
            c.phone

        FROM requests r

        JOIN services s
        ON s.id = r.service_id

        JOIN customers c
        ON c.id = r.customer_id

        WHERE r.id = ?
        """,
        (rid,)
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

        return (
            "درخواست پیدا نشد.",
            404
        )


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
            url_for(
                "admin_login"
            )
        )


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


    request_item = con.execute(
        """
        SELECT customer_id
        FROM requests
        WHERE id = ?
        """,
        (rid,)
    ).fetchone()


    if request_item:

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
                request_item["customer_id"],
                "admin",
                message,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )


        con.commit()


    con.close()


    if request_item:

        add_notification(
            request_item["customer_id"],
            "پیام پشتیبانی",
            message
        )


    return redirect(
        url_for(
            "admin_request",
            rid=rid
        )
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
            url_for(
                "admin_login"
            )
        )


    keys = (

        "site_name",
        "manager",
        "phone",
        "logo",

        "warning_text",

        "tracking_prefix",
        "tracking_digits",
        "tracking_separator",

        # ظاهر
        "theme_primary",
        "theme_secondary",
        "theme_background",
        "theme_card",
        "theme_text",
        "theme_button",
        "theme_button_text",

        # نوشته‌ها
        "site_header_text",
        "site_subtitle",

        # نمایش
        "show_warning",
        "show_customer_link",
        "show_admin_link",
        "show_tracking_link"

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


    return redirect(
        url_for(
            "admin"
        )
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
            url_for(
                "admin_login"
            )
        )


    new_password = request.form.get(
        "password",
        ""
    )


    if len(new_password) >= 6:

        con = db()


        con.execute(
            """
            UPDATE admins
            SET password = ?
            WHERE id = ?
            """,
            (
                new_password,
                session["admin_id"]
            )
        )


        con.commit()

        con.close()


    return redirect(
        url_for(
            "admin"
        )
    )


# =========================================================
# ADMIN DELETE SERVICE
# =========================================================

@app.post(
    "/admin/service/delete/<int:sid>"
)
def admin_service_delete(sid):

    if not admin_required():

        return redirect(
            url_for(
                "admin_login"
            )
        )


    con = db()


    con.execute(
        """
        UPDATE services
        SET active = 0
        WHERE id = ?
        """,
        (sid,)
    )


    con.commit()

    con.close()


    return redirect(
        url_for(
            "admin"
        )
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

@app.route(
    "/health"
)
def health():

    return jsonify(
        ok=True,
        service="online-novin"
    )


# =========================================================
# LOCAL
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
