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
    get_setting,
    set_setting,
    get_financial_summary,
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


os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


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


create_tables()



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

    ext = filename.rsplit(
        ".",
        1
    )[1].lower()

    return ext in ALLOWED_EXTENSIONS



def admin_logged_in():

    return bool(
        session.get("admin_id")
        and session.get("admin_username")
    )



def require_admin():

    if not admin_logged_in():

        return redirect(
            url_for("admin_login")
        )

    return None



def generate_tracking_code():

    while True:

        code = str(
            secrets.randbelow(9000) + 1000
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
        ORDER BY sort_order ASC,id ASC
        """
    ).fetchall()

    con.close()

    return rows



def get_service(service_id):

    con = get_connection()

    row = con.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        """,
        (service_id,)
    ).fetchone()

    con.close()

    return row



@app.route("/")
def home():

    services = get_services()

    return render_template(
        "home.html",
        site=site_settings(),
        services=services
    )



@app.route("/service/<int:service_id>")
@app.route("/service/<int:sid>")
def service(service_id=None, sid=None):

    service_id = service_id or sid

    service = get_service(service_id)

    if not service:

        return "خدمت پیدا نشد",404


    con = get_connection()

    subservices = con.execute(
        """
        SELECT *
        FROM services
        WHERE parent_id = ?
        AND active = 1
        ORDER BY sort_order ASC,id ASC
        """,
        (service_id,)
    ).fetchall()

    con.close()


    return render_template(
        "service.html",
        site=site_settings(),
        service=service,
        subservices=subservices,
        fields=get_fields(service),
        documents=get_documents(service)
    )# =============================================================
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
        return "خدمت پیدا نشد",404


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


    files = request.files.getlist(
        "documents"
    )


    for file in files:

        if not file or not file.filename:

            continue


        if not allowed_file(file.filename):

            continue


        ext = file.filename.rsplit(
            ".",
            1
        )[1].lower()


        stored_name = (
            secrets.token_hex(16)
            + "."
            + ext
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
            file_type=ext,
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

@app.route(
    "/tracking",
    methods=["GET","POST"]
)
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



@app.route(
    "/tracking/<tracking_code>"
)
def tracking_result(tracking_code):

    con = get_connection()


    item = con.execute(
        """
        SELECT
            requests.*,
            customers.name AS customer_name,
            customers.phone AS customer_phone,
            services.name AS service_name
        FROM requests
        LEFT JOIN customers
        ON customers.id=requests.customer_id
        LEFT JOIN services
        ON services.id=requests.service_id
        WHERE requests.tracking_code=?
        """,
        (tracking_code,)
    ).fetchone()


    history = []

    messages = []


    if item:

        history = con.execute(
            """
            SELECT *
            FROM request_history
            WHERE request_id=?
            ORDER BY id ASC
            """,
            (item["id"],)
        ).fetchall()


        messages = con.execute(
            """
            SELECT *
            FROM messages
            WHERE request_id=?
            ORDER BY id ASC
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

@app.route(
    "/support",
    methods=["GET","POST"]
)
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


        row = con.execute(
            """
            SELECT id
            FROM requests
            WHERE customer_id=?
            AND service_id IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (customer_id,)
        ).fetchone()


        if row:

            request_id = row["id"]

        else:

            cur = con.cursor()


            tracking_code = (
                "SUP-"
                +
                secrets.token_hex(5).upper()
            )


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
                VALUES
                (
                ?,
                NULL,
                '{}',
                'پشتیبانی',
                ?,
                0,
                0,
                'full',
                datetime('now'),
                datetime('now')
                )
                """,
                (
                    customer_id,
                    tracking_code
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
            url_for("support")
        )


    messages = []


    if customer_id:

        con = get_connection()

        messages = con.execute(
            """
            SELECT *
            FROM messages
            WHERE customer_id=?
            ORDER BY id ASC
            """,
            (customer_id,)
        ).fetchall()

        con.close()


    return render_template(
        "support.html",
        site=site_settings(),
        messages=messages
    )# =============================================================
# ورود مدیر
# =============================================================

@app.route(
    "/admin/login",
    methods=["GET","POST"]
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
            WHERE username=?
            AND active=1
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


    requests_rows = con.execute(
        """
        SELECT
            requests.*,
            customers.name AS customer_name,
            services.name AS service_name
        FROM requests
        LEFT JOIN customers
        ON customers.id=requests.customer_id
        LEFT JOIN services
        ON services.id=requests.service_id
        ORDER BY requests.id DESC
        """
    ).fetchall()



    customers = con.execute(
        """
        SELECT *
        FROM customers
        ORDER BY id DESC
        """
    ).fetchall()



    services = con.execute(
        """
        SELECT *
        FROM services
        ORDER BY id DESC
        """
    ).fetchall()



    messages = con.execute(
        """
        SELECT *
        FROM messages
        ORDER BY id DESC
        """
    ).fetchall()


    con.close()



    return render_template(
        "admin.html",
        site=site_settings(),
        requests=requests_rows,
        customers=customers,
        services=services,
        messages=messages,
        statuses=STATUSES,
        financial_summary=get_financial_summary()
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


    if not name:

        return redirect(
            url_for("admin")
        )


    try:

        price = int(price or 0)

    except Exception:

        price = 0



    con = get_connection()



    if service_id:


        con.execute(
            """
            UPDATE services
            SET
            name=?,
            description=?,
            category=?,
            price=?
            WHERE id=?
            """,
            (
                name,
                description,
                category,
                price,
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
            VALUES
            (
            ?,
            ?,
            ?,
            '',
            ?,
            1,
            0,
            '[]',
            '[]',
            datetime('now')
            )
            """,
            (
                name,
                description,
                category,
                price
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


    con = get_connection()


    con.execute(
        """
        DELETE FROM services
        WHERE id=?
        """,
        (sid,)
    )


    con.commit()

    con.close()


    return redirect(
        url_for("admin")
    )



# =============================================================
# تغییر وضعیت درخواست
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



    if status not in STATUSES:

        status = "جدید"



    update_request_status(
        request_id=request_id,
        admin_id=session["admin_id"],
        status=status,
        description=description,
        estimated_time="",
        expert_name=""
    )


    return redirect(
        url_for("admin")
    )# =============================================================
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
            WHERE id=?
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
# مدیریت کاربران مدیر
# =============================================================

@app.route(
    "/admin/user/save",
    methods=["POST"]
)
def admin_user_save():

    guard = require_admin()

    if guard:
        return guard

    # فقط مدیر ارشد اجازه مدیریت کاربران را دارد
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

    if not username:
        flash(
            "نام کاربری الزامی است.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    if role not in (
        "admin",
        "operator",
        "superadmin"
    ):
        role = "admin"

    if active not in ("0", "1"):
        active = "1"

    con = get_connection()

    try:

        if admin_id:

            # ویرایش کاربر موجود
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

                # اگر رمز خالی باشد، رمز قبلی حفظ می‌شود
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

            # ایجاد کاربر جدید
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
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    1,
                    datetime('now')
                )
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

    except Exception as e:

        con.rollback()

        flash(
            "خطا در ذخیره کاربر: " + str(e),
            "error"
        )

    finally:

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



    for key,value in values.items():

        set_setting(
            key,
            value
        )


    return redirect(
        url_for("admin")
    )



# =============================================================
# تغییر رمز مدیر
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
        SET password=?
        WHERE id=?
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
# اعلان‌ها
# =============================================================

@app.route(
    "/admin/notifications"
)
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
# خروج مدیر
# =============================================================

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.clear()


    return redirect(
        url_for("admin_login")
    )



# =============================================================
# خطای حجم فایل
# =============================================================

@app.errorhandler(413)
def file_too_large(error):

    return """
    حجم فایل بیشتر از حد مجاز است.
    حداکثر حجم مجاز 25 مگابایت می‌باشد.
    """,413



# =============================================================
# اجرا
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
