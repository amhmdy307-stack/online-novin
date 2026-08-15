import os
import json
import sqlite3
import secrets

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify
)

from werkzeug.utils import secure_filename


# =========================
# تنظیمات اصلی
# =========================

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


# =========================
# اتصال به دیتابیس
# =========================

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


# =========================
# ساخت دیتابیس و جدول‌ها
# =========================

def init_db():

    con = db()

    con.executescript("""

    CREATE TABLE IF NOT EXISTS customers(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        name TEXT NOT NULL DEFAULT 'مشتری',

        national_id TEXT NOT NULL DEFAULT '',

        phone TEXT NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    );


    CREATE TABLE IF NOT EXISTS services(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        name TEXT NOT NULL,

        description TEXT DEFAULT '',

        price INTEGER DEFAULT 0,

        active INTEGER DEFAULT 1,

        image TEXT DEFAULT '',

        fields_json TEXT DEFAULT '[]'

    );


    CREATE TABLE IF NOT EXISTS requests(

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


    CREATE TABLE IF NOT EXISTS admins(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE,

        password TEXT NOT NULL,

        active INTEGER DEFAULT 1

    );


    CREATE TABLE IF NOT EXISTS settings(

        key TEXT PRIMARY KEY,

        value TEXT DEFAULT ''

    );


    CREATE TABLE IF NOT EXISTS discount_codes(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        code TEXT UNIQUE,

        kind TEXT,

        value INTEGER DEFAULT 0,

        active INTEGER DEFAULT 1

    );

    """)

    # =========================
    # مدیر پیش‌فرض
    # =========================

    admin_exists = con.execute(
        "SELECT 1 FROM admins LIMIT 1"
    ).fetchone()

    if not admin_exists:

        con.execute(
            """
            INSERT INTO admins(username, password)
            VALUES(?, ?)
            """,
            (
                "admin",
                ADMIN_PASSWORD
            )
        )


    # =========================
    # تنظیمات پیش‌فرض
    # =========================

    defaults = {

        "site_name": "کافی‌نت آنلاین نوین",

        "manager": "احمد محمدی مهر",

        "phone": "09920345139",

        "sms_enabled": "0",

        "payment_enabled": "0",

        "customer_login_mode": "phone",

        "customer_otp_enabled": "0"

    }


    for key, value in defaults.items():

        con.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES(?, ?)
            """,
            (
                key,
                value
            )
        )


    # =========================
    # خدمات اولیه
    # =========================

    service_exists = con.execute(
        "SELECT 1 FROM services LIMIT 1"
    ).fetchone()


    if not service_exists:

        seed_services = [

            (
                "مسکن ملی",
                "ثبت درخواست و بارگذاری مدارک",
                0
            ),

            (
                "ثبت‌نام سهام نوزاد",
                "ثبت اطلاعات پدر و فرزند",
                0
            ),

            (
                "ثبت‌نام خودرو",
                "ایران‌خودرو، سایپا، بهمن موتور",
                0
            ),

            (
                "چک صیادی",
                "ثبت، تأیید یا رد چک",
                0
            ),

            (
                "ثبت قرارداد",
                "ثبت قرارداد اجاره و قولنامه",
                0
            ),

            (
                "جواز کسب",
                "ثبت درخواست جواز کسب",
                0
            )

        ]


        for name, description, price in seed_services:

            con.execute(
                """
                INSERT INTO services(
                    name,
                    description,
                    price
                )
                VALUES(?, ?, ?)
                """,
                (
                    name,
                    description,
                    price
                )
            )


    con.commit()

    con.close()


# ==========================================================
# بسیار مهم:
# این خط خارج از if __name__ است تا Gunicorn روی Render هم
# دیتابیس و جدول‌ها را بسازد.
# ==========================================================

init_db()


# =========================
# بررسی ورود مدیر
# =========================

def admin_required():

    return session.get("admin") is True


# =========================
# صفحه اصلی
# =========================

@app.route("/")
def home():

    con = db()

    services = con.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        ORDER BY id DESC
        """
    ).fetchall()


    settings_rows = con.execute(
        """
        SELECT key, value
        FROM settings
        """
    ).fetchall()


    settings = {
        row["key"]: row["value"]
        for row in settings_rows
    }


    con.close()


    return render_template(
        "home.html",
        services=services,
        settings=settings
    )


# =========================
# صفحه یک خدمت
# =========================

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

        return "خدمت موردنظر پیدا نشد.", 404


    if not service_item["active"]:

        return "این خدمت در حال حاضر فعال نیست.", 404


    try:

        fields = json.loads(
            service_item["fields_json"] or "[]"
        )

    except Exception:

        fields = []


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

            flash("نام و نام خانوادگی الزامی است.")

            return redirect(request.url)


        if not phone:

            flash("شماره تلفن الزامی است.")

            return redirect(request.url)


        con = db()


        customer = con.execute(
            """
            SELECT id
            FROM customers
            WHERE phone = ?
            """,
            (phone,)
        ).fetchone()


        if customer:

            customer_id = customer["id"]


            con.execute(
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

            cursor = con.execute(
                """
                INSERT INTO customers(
                    name,
                    national_id,
                    phone
                )
                VALUES(?, ?, ?)
                """,
                (
                    name,
                    national_id,
                    phone
                )
            )


            customer_id = cursor.lastrowid


        # اطلاعات اختصاصی خدمت

        data = {}

        for key in request.form.keys():

            if key not in (
                "name",
                "national_id",
                "phone"
            ):

                data[key] = request.form.get(
                    key,
                    ""
                )


        tracking_code = (
            "NV-"
            +
            secrets.token_hex(4).upper()
        )


        total_price = (
            service_item["price"]
            or 0
        )


        con.execute(
            """
            INSERT INTO requests(

                customer_id,
                service_id,
                data_json,
                tracking_code,
                total_price

            )
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                sid,
                json.dumps(
                    data,
                    ensure_ascii=False
                ),
                tracking_code,
                total_price
            )
        )


        con.commit()

        con.close()


        return render_template(
            "success.html",
            code=tracking_code
        )


    return render_template(
        "service.html",
        service=service_item,
        fields=fields
    )


# =========================
# ورود مشتری
# =========================

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

            return redirect(request.url)


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
                INSERT INTO customers(
                    name,
                    national_id,
                    phone
                )
                VALUES(?, ?, ?)
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
        "customer_login.html"
    )


# =========================
# خروج مشتری
# =========================

@app.route("/customer/logout")
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


# =========================
# پنل مشتری
# =========================

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
        WHERE id = ?
        """,
        (customer_id,)
    ).fetchone()


    if not customer:

        con.close()

        session.pop(
            "customer_id",
            None
        )

        return redirect(
            url_for(
                "customer_login"
            )
        )


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


    con.close()


    return render_template(
        "customer.html",
        customer=customer,
        requests=requests_list
    )


# =========================
# رهگیری درخواست
# =========================

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
        result=result
    )


# =========================
# ورود مدیر
# =========================

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


            return redirect(
                url_for(
                    "admin"
                )
            )


        flash(
            "نام کاربری یا رمز عبور اشتباه است."
        )


    return render_template(
        "admin_login.html"
    )


# =========================
# خروج مدیر
# =========================

@app.route("/admin/logout")
def admin_logout():

    session.clear()


    return redirect(
        url_for(
            "admin_login"
        )
    )


# =========================
# پنل مدیریت
# =========================

@app.route("/admin")
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
        ORDER BY id DESC
        """
    ).fetchall()


    customers = con.execute(
        """
        SELECT *
        FROM customers
        ORDER BY id DESC
        """
    ).fetchall()


    settings_rows = con.execute(
        """
        SELECT key, value
        FROM settings
        """
    ).fetchall()


    settings = {
        row["key"]: row["value"]
        for row in settings_rows
    }


    requests_list = con.execute(
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

        ORDER BY r.id DESC
        """
    ).fetchall()


    con.close()


    return render_template(
        "admin.html",

        services=services,

        customers=customers,

        requests=requests_list,

        settings=settings
    )


# =========================
# افزودن / ویرایش خدمت
# =========================

@app.post("/admin/service/save")
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


    active = (
        1
        if request.form.get("active") == "1"
        else 0
    )


    fields_raw = request.form.get(
        "fields_json",
        "[]"
    )


    try:

        json.loads(fields_raw)

    except Exception:

        fields_raw = "[]"


    con = db()


    if sid:

        con.execute(
            """
            UPDATE services

            SET
                name = ?,
                description = ?,
                price = ?,
                active = ?,
                fields_json = ?

            WHERE id = ?

            """,
            (
                name,
                description,
                price,
                active,
                fields_raw,
                sid
            )
        )


    else:

        con.execute(
            """
            INSERT INTO services(

                name,
                description,
                price,
                active,
                fields_json

            )
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                price,
                active,
                fields_raw
            )
        )


    con.commit()

    con.close()


    return redirect(
        url_for(
            "admin"
        )
    )


# =========================
# تغییر وضعیت درخواست
# =========================

@app.post("/admin/request/status")
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


    return redirect(
        url_for(
            "admin"
        )
    )


# =========================
# تنظیمات پنل مدیریت
# =========================

@app.post("/admin/settings")
def admin_settings():

    if not admin_required():

        return redirect(
            url_for(
                "admin_login"
            )
        )


    con = db()


    keys = (

        "site_name",

        "manager",

        "phone",

        "sms_enabled",

        "payment_enabled",

        "customer_login_mode",

        "customer_otp_enabled"

    )


    for key in keys:

        value = request.form.get(
            key,
            ""
        )


        con.execute(
            """
            INSERT OR REPLACE INTO settings(
                key,
                value
            )
            VALUES(?, ?)
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


# =========================
# تغییر رمز مدیر
# =========================

@app.post("/admin/password")
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


# =========================
# حذف خدمت
# =========================

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
        DELETE FROM services
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


# =========================
# سلامت سرویس
# =========================

@app.route("/health")
def health():

    return jsonify(
        ok=True
    )


# =========================
# اجرای محلی
# =========================

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
