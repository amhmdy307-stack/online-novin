from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
import json
import os
import secrets

from database import (
    create_tables,
    get_connection,
    create_customer,
    add_request,
    add_message,
    add_file,
    accept_request,
    update_request_status,
    add_admin,
    get_setting,
    set_setting,
    get_financial_summary,
    unread_admin_notifications,
    get_admin_notifications,
    mark_all_admin_notifications_read
)


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "novin-secret-key-change-this"
)

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(
    app.root_path,
    "static",
    "uploads"
)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "pdf"
}

STATUSES = [
    "جدید",
    "پذیرش شد",
    "در حال بررسی",
    "در حال انجام",
    "تکمیل شد",
    "آماده تحویل",
    "بسته شد",
    "لغو شد"
]


# =============================================================
# آماده‌سازی
# =============================================================

create_tables()


# =============================================================
# ابزارها
# =============================================================

def site_settings():

    return {
        "site_name": get_setting(
            "site_name",
            "کافی‌نت آنلاین نوین"
        ),
        "manager": get_setting(
            "manager",
            "احمد محمدی مهر"
        ),
        "phone": get_setting(
            "phone",
            "09920345139"
        ),
        "logo": get_setting(
            "logo",
            ""
        ),
        "warning_text": get_setting(
            "warning_text",
            ""
        )
    }


def allowed_file(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS


def admin_logged_in():

    return bool(
        session.get("admin_id")
        and session.get("admin_username")
    )


def require_admin():

    if not admin_logged_in():
        return redirect(url_for("admin_login"))

    return None


def generate_tracking_code():

    while True:

        code = str(
            secrets.randbelow(900) + 100
        )

        con = get_connection()

        row = con.execute(
            """
            SELECT id
            FROM requests
            WHERE tracking_code = ?
            """,
            (code,)
        ).fetchone()

        con.close()

        if not row:
            return code


def get_fields(service):

    try:
        value = service["fields_json"] or "[]"

        if isinstance(value, list):
            return value

        return json.loads(value)

    except Exception:
        return []


def get_documents(service):

    try:
        value = service["documents_json"] or "[]"

        if isinstance(value, list):
            return value

        return json.loads(value)

    except Exception:
        return []


def get_services():

    con = get_connection()

    rows = con.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        AND parent_id IS NULL
        ORDER BY sort_order ASC, id ASC
        """
    ).fetchall()

    con.close()

    return rows


def get_service(service_id):

    con = get_connection()

    service = con.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        """,
        (service_id,)
    ).fetchone()

    con.close()

    return service


# =============================================================
# صفحه اصلی
# =============================================================

@app.route("/")
def home():

    services = get_services()

    return render_template(
        "home.html",
        site=site_settings(),
        services=services
    )


# =============================================================
# صفحه خدمت
# =============================================================

@app.route("/service/<int:service_id>")
@app.route("/service/<int:sid>")
def service(service_id=None, sid=None):

    service_id = service_id or sid

    service = get_service(service_id)

    if not service:
        return "خدمت پیدا نشد", 404

    con = get_connection()

    subservices = con.execute(
        """
        SELECT *
        FROM services
        WHERE parent_id = ?
        AND active = 1
        ORDER BY sort_order ASC, id ASC
        """,
        (service_id,)
    ).fetchall()

    con.close()

    fields = get_fields(service)
    documents = get_documents(service)

    return render_template(
        "service.html",
        site=site_settings(),
        service=service,
        subservices=subservices,
        fields=fields,
        documents=documents
    )


# =============================================================
# ثبت درخواست
# =============================================================

@app.route(
    "/service/<int:service_id>/request",
    methods=["POST"]
)
@app.route(
    "/create-request/<int:service_id>",
    methods=["POST"]
)
def create_request(service_id):

    service = get_service(service_id)

    if not service:
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

    customer_id = create_customer(
        name=name,
        national_id=national_id,
        phone=phone
    )

    data = {}

    for key in request.form:

        if key.startswith("field_"):

            data[key] = request.form.get(
                key,
                ""
            )

    data["customer_note"] = customer_note

    discount_code = request.form.get(
        "discount_code",
        ""
    ).strip()

    if discount_code:

        data["discount_code"] = discount_code

    tracking_code = generate_tracking_code()

    total_price = int(
        service["price"] or 0
    )

    request_id = add_request(
        customer_id=customer_id,
        service_id=service_id,
        data_json=json.dumps(
            data,
            ensure_ascii=False
        ),
        total_price=total_price,
        tracking_code=tracking_code
    )

    # ---------------------------------------------------------
    # ذخیره فایل‌های مدارک
    # ---------------------------------------------------------

    uploaded_files = request.files.getlist(
        "documents"
    )

    for file in uploaded_files:

        if not file or not file.filename:
            continue

        if not allowed_file(file.filename):
            continue

        extension = file.filename.rsplit(
            ".",
            1
        )[1].lower()

        stored_name = (
            secrets.token_hex(16)
            + "."
            + extension
        )

        path = os.path.join(
            UPLOAD_FOLDER,
            stored_name
        )

        file.save(path)

        add_file(
            request_id=request_id,
            customer_id=customer_id,
            field_name="documents",
            original_name=file.filename,
            stored_name=stored_name,
            file_type=extension,
            downloadable=1
        )

    session["customer_id"] = customer_id

    return redirect(
        url_for(
            "tracking_result",
            tracking_code=tracking_code
        )
    )


# =============================================================
# پیگیری
# =============================================================

@app.route("/tracking", methods=["GET", "POST"])
def tracking():

    if request.method == "POST":

        tracking_code = request.form.get(
            "tracking_code",
            ""
        ).strip()

        if tracking_code:

            return redirect(
                url_for(
                    "tracking_result",
                    tracking_code=tracking_code
                )
            )

    return render_template(
        "tracking.html",
        site=site_settings()
    )


@app.route("/tracking/<tracking_code>")
def tracking_result(tracking_code):

    con = get_connection()

    item = con.execute(
        """
        SELECT
            requests.*,
            customers.name AS customer_name,
            customers.phone AS customer_phone,
            services.name AS service_name,
            admins.name AS admin_name
        FROM requests
        LEFT JOIN customers
            ON customers.id = requests.customer_id
        LEFT JOIN services
            ON services.id = requests.service_id
        LEFT JOIN admins
            ON admins.id = requests.assigned_admin_id
        WHERE requests.tracking_code = ?
        """,
        (tracking_code,)
    ).fetchone()

    history = []

    messages = []

    if item:

        history = con.execute(
            """
            SELECT
                request_history.*,
                admins.name AS admin_name
            FROM request_history
            LEFT JOIN admins
                ON admins.id = request_history.admin_id
            WHERE request_history.request_id = ?
            ORDER BY request_history.id ASC
            """,
            (item["id"],)
        ).fetchall()

        messages = con.execute(
            """
            SELECT
                messages.*,
                admins.name AS admin_name
            FROM messages
            LEFT JOIN admins
                ON admins.id = messages.sender_admin_id
            WHERE messages.request_id = ?
            ORDER BY messages.id ASC
            """,
            (item["id"],)
        ).fetchall()

    con.close()

    if not item:

        return render_template(
            "tracking.html",
            site=site_settings(),
            error="درخواستی با این کد پیگیری پیدا نشد."
        )

    return render_template(
        "tracking_result.html",
        site=site_settings(),
        item=item,
        history=history,
        messages=messages
    )


# =============================================================
# پشتیبانی
# =============================================================

@app.route("/support", methods=["GET", "POST"])
def support():

    customer_id = session.get(
        "customer_id"
    )

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        message = request.form.get(
            "message",
            ""
        ).strip()

        if not message:

            flash(
                "متن پیام را وارد کنید.",
                "error"
            )

            return redirect(
                url_for("support")
            )

        if not customer_id:

            if not name or not phone:

                flash(
                    "نام و شماره موبایل را وارد کنید.",
                    "error"
                )

                return redirect(
                    url_for("support")
                )

            customer_id = create_customer(
                name=name,
                phone=phone
            )

            session["customer_id"] = customer_id

        con = get_connection()

        existing = con.execute(
            """
            SELECT id
            FROM requests
            WHERE customer_id = ?
            AND service_id IS NULL
            AND status NOT IN ('بسته شد','لغو شد')
            ORDER BY id DESC
            LIMIT 1
            """,
            (customer_id,)
        ).fetchone()

        if existing:

            request_id = existing["id"]

        else:

            tracking_code = (
                "SUP-"
                + secrets.token_hex(5).upper()
            )

            cur = con.cursor()

            cur.execute(
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
                    created_at,
                    updated_at
                )
                VALUES (?, NULL, '{}', 'پشتیبانی', ?, 0, 0, 'full', ?, ?)
                """,
                (
                    customer_id,
                    tracking_code,
                    __import__(
                        "datetime"
                    ).datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    __import__(
                        "datetime"
                    ).datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )

            request_id = cur.lastrowid

            con.commit()

        con.close()

        add_message(
            request_id=request_id,
            customer_id=customer_id,
            sender="customer",
            message=message
        )

        return redirect(
            url_for(
                "support"
            )
        )

    messages = []

    if customer_id:

        con = get_connection()

        messages = con.execute(
            """
            SELECT
                messages.*,
                admins.name AS admin_name,
                requests.tracking_code
            FROM messages
            INNER JOIN requests
                ON requests.id = messages.request_id
            LEFT JOIN admins
                ON admins.id = messages.sender_admin_id
            WHERE requests.customer_id = ?
            AND requests.service_id IS NULL
            ORDER BY messages.id ASC
            """,
            (customer_id,)
        ).fetchall()

        con.close()

    return render_template(
        "support.html",
        site=site_settings(),
        messages=messages
    )


# =============================================================
# ورود مدیر
# =============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if admin_logged_in():

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

        con = get_connection()

        admin = con.execute(
            """
            SELECT *
            FROM admins
            WHERE username = ?
            AND active = 1
            LIMIT 1
            """,
            (username,)
        ).fetchone()

        con.close()

        if admin and admin["password"] == password:

            session.clear()

            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            session["admin_role"] = admin["role"]
            session["admin_name"] = admin["name"]

            return redirect(
                url_for("admin")
            )

        flash(
            "نام کاربری یا رمز عبور اشتباه است.",
            "error"
        )

    return render_template(
        "admin_login.html",
        site=site_settings()
    )


# =============================================================
# پنل مدیریت
# =============================================================

@app.route("/admin")
def admin():

    guard = require_admin()

    if guard:
        return guard

    con = get_connection()

    services = con.execute(
        """
        SELECT *
        FROM services
        ORDER BY sort_order ASC, id ASC
        """
    ).fetchall()

    customers = con.execute(
        """
        SELECT
            customers.*,
            COUNT(requests.id) AS request_count
        FROM customers
        LEFT JOIN requests
            ON requests.customer_id = customers.id
        GROUP BY customers.id
        ORDER BY customers.id DESC
        """
    ).fetchall()

    requests_rows = con.execute(
        """
        SELECT
            requests.*,
            customers.name AS customer_name,
            services.name AS service_name,
            admins.name AS admin_name
        FROM requests
        LEFT JOIN customers
            ON customers.id = requests.customer_id
        LEFT JOIN services
            ON services.id = requests.service_id
        LEFT JOIN admins
            ON admins.id = requests.assigned_admin_id
        ORDER BY requests.id DESC
        """
    ).fetchall()

    messages = con.execute(
        """
        SELECT
            messages.*,
            customers.name AS customer_name,
            requests.tracking_code
        FROM messages
        LEFT JOIN customers
            ON customers.id = messages.customer_id
        LEFT JOIN requests
            ON requests.id = messages.request_id
        ORDER BY messages.id DESC
        """
    ).fetchall()

    payments = con.execute(
        """
        SELECT
            payments.*,
            customers.name AS customer_name,
            services.name AS service_name
        FROM payments
        LEFT JOIN customers
            ON customers.id = payments.customer_id
        LEFT JOIN requests
            ON requests.id = payments.request_id
        LEFT JOIN services
            ON services.id = requests.service_id
        ORDER BY payments.id DESC
        """
    ).fetchall()

    admins = con.execute(
        """
        SELECT *
        FROM admins
        ORDER BY id ASC
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
        (session["admin_id"],)
    ).fetchall()

    con.close()

    return render_template(
        "admin.html",
        site=site_settings(),
        site_settings=site_settings(),
        services=services,
        customers=customers,
        requests=requests_rows,
        messages=messages,
        payments=payments,
        admins=admins,
        statuses=STATUSES,
        financial_summary=get_financial_summary(),
        notifications=notifications,
        unread_notifications=[
            x for x in notifications
            if not x["is_read"]
        ]
    )


# =============================================================
# ذخیره خدمت
# =============================================================

@app.route(
    "/admin/service/save",
    methods=["POST"]
)
def admin_service_save():

    guard = require_admin()

    if guard:
        return guard

    service_id = request.form.get(
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

    price = request.form.get(
        "price",
        "0"
    ).strip()

    sort_order = request.form.get(
        "sort_order",
        "0"
    ).strip()

    active = request.form.get(
        "active",
        "1"
    ).strip()

    fields_json = request.form.get(
        "fields_json",
        "[]"
    ).strip()

    if not name:
        return redirect(
            url_for("admin")
        )

    try:
        price = int(price or 0)
    except Exception:
        price = 0

    try:
        sort_order = int(sort_order or 0)
    except Exception:
        sort_order = 0

    if active not in ("0", "1"):
        active = "1"

    try:
        json.loads(fields_json or "[]")
    except Exception:
        fields_json = "[]"

    con = get_connection()

    if service_id:

        con.execute(
            """
            UPDATE services
            SET
                name = ?,
                description = ?,
                category = ?,
                price = ?,
                active = ?,
                sort_order = ?,
                fields_json = ?
            WHERE id = ?
            """,
            (
                name,
                description,
                category,
                price,
                int(active),
                sort_order,
                fields_json,
                int(service_id)
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
            VALUES (?, ?, ?, '', ?, ?, ?, ?, '[]', datetime('now'))
            """,
            (
                name,
                description,
                category,
                price,
                int(active),
                sort_order,
                fields_json
            )
        )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =============================================================
# حذف خدمت
# =============================================================

@app.route(
    "/admin/service/delete/<int:sid>",
    methods=["POST"]
)
def admin_service_delete(sid):

    guard = require_admin()

    if guard:
        return guard

    if session.get("admin_role") != "superadmin":

        return "دسترسی غیرمجاز", 403

    con = get_connection()

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
        url_for("admin")
    )


# =============================================================
# پذیرش پرونده
# =============================================================

@app.route(
    "/admin/request/accept",
    methods=["POST"]
)
def admin_request_accept():

    guard = require_admin()

    if guard:
        return guard

    request_id = request.form.get(
        "request_id",
        ""
    )

    expert_name = request.form.get(
        "expert_name",
        ""
    ).strip()

    estimated_time = request.form.get(
        "estimated_time",
        ""
    ).strip()

    try:
        request_id = int(request_id)
    except Exception:
        return redirect(
            url_for("admin")
        )

    accept_request(
        request_id=request_id,
        admin_id=session["admin_id"],
        estimated_time=estimated_time,
        expert_name=expert_name
    )

    return redirect(
        url_for("admin")
    )


# =============================================================
# تغییر وضعیت پرونده
# =============================================================

@app.route(
    "/admin/request/status",
    methods=["POST"]
)
def admin_request_status():

    guard = require_admin()

    if guard:
        return guard

    try:
        request_id = int(
            request.form.get(
                "request_id",
                "0"
            )
        )
    except Exception:
        return redirect(
            url_for("admin")
        )

    status = request.form.get(
        "status",
        "جدید"
    )

    description = request.form.get(
        "description",
        ""
    ).strip()

    estimated_time = request.form.get(
        "estimated_time",
        ""
    ).strip()

    expert_name = request.form.get(
        "expert_name",
        ""
    ).strip()

    if status not in STATUSES:
        status = "جدید"

    update_request_status(
        request_id=request_id,
        admin_id=session["admin_id"],
        status=status,
        description=description,
        estimated_time=estimated_time,
        expert_name=expert_name
    )

    return redirect(
        url_for("admin")
    )


# =============================================================
# پاسخ مدیر
# =============================================================

@app.route(
    "/admin/reply",
    methods=["POST"]
)
def admin_reply():

    guard = require_admin()

    if guard:
        return guard

    try:
        request_id = int(
            request.form.get(
                "request_id",
                "0"
            )
        )
    except Exception:
        return redirect(
            url_for("admin")
        )

    message = request.form.get(
        "message",
        ""
    ).strip()

    if message:

        con = get_connection()

        row = con.execute(
            """
            SELECT customer_id
            FROM requests
            WHERE id = ?
            """,
            (request_id,)
        ).fetchone()

        con.close()

        if row:

            add_message(
                request_id=request_id,
                customer_id=row["customer_id"],
                sender="admin",
                message=message,
                sender_admin_id=session["admin_id"]
            )

    return redirect(
        url_for("admin")
    )


# =============================================================
# مدیریت کاربران
# =============================================================

@app.route(
    "/admin/user/save",
    methods=["POST"]
)
def admin_user_save():

    guard = require_admin()

    if guard:
        return guard

    if session.get("admin_role") != "superadmin":

        return "دسترسی غیرمجاز", 403

    admin_id = request.form.get(
        "id",
        ""
    ).strip()

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    name = request.form.get(
        "name",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    role = request.form.get(
        "role",
        "admin"
    )

    active = request.form.get(
        "active",
        "1"
    )

    if role not in (
        "admin",
        "operator",
        "superadmin"
    ):
        role = "admin"

    if active not in ("0", "1"):
        active = "1"

    if not username:

        return redirect(
            url_for("admin")
        )

    con = get_connection()

    if admin_id:

        if password:

            con.execute(
                """
                UPDATE admins
                SET
                    username = ?,
                    password = ?,
                    name = ?,
                    phone = ?,
                    role = ?,
                    active = ?
                WHERE id = ?
                """,
                (
                    username,
                    password,
                    name,
                    phone,
                    role,
                    int(active),
                    int(admin_id)
                )
            )

        else:

            con.execute(
                """
                UPDATE admins
                SET
                    username = ?,
                    name = ?,
                    phone = ?,
                    role = ?,
                    active = ?
                WHERE id = ?
                """,
                (
                    username,
                    name,
                    phone,
                    role,
                    int(active),
                    int(admin_id)
                )
            )

    else:

        if not password:
            password = "123456"

        con.execute(
            """
            INSERT INTO admins
            (
                username,
                password,
                name,
                phone,
                role,
                active,
                notifications_enabled,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'))
            """,
            (
                username,
                password,
                name,
                phone,
                role,
                int(active)
            )
        )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =============================================================
# تنظیمات سایت
# =============================================================

@app.route(
    "/admin/settings/save",
    methods=["POST"]
)
def admin_settings_save():

    guard = require_admin()

    if guard:
        return guard

    values = {
        "site_name": request.form.get(
            "site_name",
            ""
        ).strip(),

        "manager": request.form.get(
            "manager",
            ""
        ).strip(),

        "phone": request.form.get(
            "phone",
            ""
        ).strip(),

        "logo": request.form.get(
            "logo",
            ""
        ).strip(),

        "warning_text": request.form.get(
            "warning_text",
            ""
        ).strip()
    }

    for key, value in values.items():

        set_setting(
            key,
            value
        )

    return redirect(
        url_for("admin")
    )


# =============================================================
# تغییر رمز مدیر فعلی
# =============================================================

@app.route(
    "/admin/password",
    methods=["POST"]
)
def admin_password():

    guard = require_admin()

    if guard:
        return guard

    password = request.form.get(
        "password",
        ""
    )

    if not password:

        return redirect(
            url_for("admin")
        )

    con = get_connection()

    con.execute(
        """
        UPDATE admins
        SET password = ?
        WHERE id = ?
        """,
        (
            password,
            session["admin_id"]
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# =============================================================
# اعلان‌های مدیر
# =============================================================

@app.route("/admin/notifications")
def admin_notifications():

    guard = require_admin()

    if guard:
        return guard

    notifications = get_admin_notifications(
        session["admin_id"]
    )

    return render_template(
        "admin_notifications.html",
        site=site_settings(),
        notifications=notifications
    )


@app.route(
    "/admin/notifications/read-all",
    methods=["POST"]
)
def admin_notifications_read_all():

    guard = require_admin()

    if guard:
        return guard

    mark_all_admin_notifications_read(
        session["admin_id"]
    )

    return redirect(
        url_for("admin")
    )


# =============================================================
# خروج
# =============================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin_id", None)
    session.pop("admin_username", None)
    session.pop("admin_role", None)
    session.pop("admin_name", None)

    return redirect(
        url_for("admin_login")
    )


# =============================================================
# اجرای برنامه
# =============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
