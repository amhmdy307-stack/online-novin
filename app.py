import os
import json
import secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory

from database import (
    create_tables,
    get_connection,
    get_setting,
    set_setting,
    add_request,
    add_message,
    add_file,
    add_financial_transaction,
    add_payment,
    mark_payment_paid,
    add_discount_code,
    get_financial_transactions,
    get_financial_summary,
    unread_admin_notifications,
    unread_customer_notifications,
    mark_all_admin_notifications_read,
    mark_all_customer_notifications_read,
    get_request_history,
    get_request_messages,
    get_customer_requests,
    get_support_messages,
    create_support_request,
    add_support_message,
    add_admin,
    set_admin_permission,
    remove_admin_permission,
    has_permission,
    set_admin_notification_permission,
    accept_request,
    update_request_status,
    now,
)

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "static", "uploads")

os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "novin-online-secret-key-change-this"
)

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

create_tables()


STATUSES = [
    "جدید",
    "پذیرش شد",
    "در حال بررسی",
    "منتظر مدارک",
    "منتظر پرداخت",
    "در حال انجام",
    "منتظر پاسخ سامانه",
    "انجام شده",
    "رد شده",
    "لغو شد",
    "نیاز به پیگیری",
    "بسته شد",
]


FIELD_TYPES = [
    "text",
    "number",
    "phone",
    "national_id",
    "national_identifier",
    "date",
    "select",
    "person_type",
    "province",
    "city",
    "image",
    "pdf",
    "multi_file",
    "checkbox",
    "textarea",
]


DEFAULT_SERVICES = [
    {
        "name": "ثبت‌نام خودرو",
        "description": "ایران‌خودرو، سایپا و بهمن موتور",
        "category": "خودرو",
        "price": 300000,
        "fields": [
            {
                "name": "company",
                "label": "شرکت ثبت‌نام",
                "type": "select",
                "required": 1,
                "options": ["ایران‌خودرو", "سایپا", "بهمن موتور"],
            },
            {
                "name": "previous_registration",
                "label": "سابقه ثبت‌نام",
                "type": "select",
                "required": 1,
                "options": [
                    "اولین بار ثبت‌نام می‌کنم",
                    "قبلاً ثبت‌نام کرده‌ام",
                ],
            },
            {
                "name": "father_name",
                "label": "نام پدر",
                "type": "text",
                "required": 0,
            },
            {
                "name": "birth_cert_no",
                "label": "شماره شناسنامه",
                "type": "text",
                "required": 0,
            },
            {
                "name": "birth_cert_series",
                "label": "سری شناسنامه",
                "type": "text",
                "required": 0,
            },
            {
                "name": "birth_cert_letter",
                "label": "حرف",
                "type": "text",
                "required": 0,
            },
            {
                "name": "birth_cert_serial",
                "label": "سریال",
                "type": "text",
                "required": 0,
            },
            {
                "name": "gender",
                "label": "جنسیت",
                "type": "select",
                "required": 0,
                "options": ["مرد", "زن"],
            },
            {
                "name": "birth_date",
                "label": "تاریخ تولد",
                "type": "date",
                "required": 0,
            },
            {
                "name": "issue_date",
                "label": "تاریخ صدور",
                "type": "date",
                "required": 0,
            },
            {
                "name": "postal_code",
                "label": "کد پستی",
                "type": "text",
                "required": 0,
            },
            {
                "name": "sheba",
                "label": "شماره شبا",
                "type": "text",
                "required": 0,
            },
            {
                "name": "previous_registration_phone",
                "label": "تلفن ثبت‌شده در سامانه",
                "type": "phone",
                "required": 0,
            },
            {
                "name": "bank_card",
                "label": "عکس کارت بانکی",
                "type": "image",
                "required": 0,
            },
        ],
    },
    {
        "name": "مسکن ملی",
        "description": "ثبت درخواست و بارگذاری مدارک",
        "category": "مسکن",
        "price": 0,
        "fields": [
            {
                "name": "postal_code",
                "label": "کد پستی",
                "type": "text",
                "required": 1,
            },
            {
                "name": "province_residence",
                "label": "استان محل سکونت",
                "type": "province",
                "required": 1,
            },
            {
                "name": "city_residence",
                "label": "شهر محل سکونت",
                "type": "city",
                "required": 1,
            },
            {
                "name": "applicant_documents",
                "label": "مدارک متقاضی",
                "type": "multi_file",
                "required": 0,
            },
            {
                "name": "spouse_documents",
                "label": "مدارک همسر",
                "type": "multi_file",
                "required": 0,
            },
            {
                "name": "children_documents",
                "label": "مدارک فرزندان",
                "type": "multi_file",
                "required": 0,
            },
        ],
    },
    {
        "name": "ثبت‌نام سهام نوزاد",
        "description": "ثبت اطلاعات پدر و فرزند",
        "category": "خانواده",
        "price": 0,
        "fields": [
            {
                "name": "father_phone",
                "label": "تلفن به نام پدر",
                "type": "phone",
                "required": 1,
            },
            {
                "name": "child_national_id",
                "label": "کد ملی فرزند",
                "type": "national_id",
                "required": 1,
            },
            {
                "name": "child_birth_date",
                "label": "تاریخ تولد فرزند",
                "type": "date",
                "required": 1,
            },
            {
                "name": "father_national_id",
                "label": "کد ملی پدر",
                "type": "national_id",
                "required": 1,
            },
            {
                "name": "father_birth_date",
                "label": "تاریخ تولد پدر",
                "type": "date",
                "required": 1,
            },
            {
                "name": "postal_code",
                "label": "کد پستی",
                "type": "text",
                "required": 1,
            },
        ],
    },
    {
        "name": "چک صیادی",
        "description": "ثبت، تأیید یا رد چک صیادی",
        "category": "بانکی",
        "price": 0,
        "fields": [
            {
                "name": "action",
                "label": "نوع خدمت",
                "type": "select",
                "required": 1,
                "options": ["ثبت چک", "تأیید چک", "رد چک"],
            },
            {
                "name": "receiver_type",
                "label": "نوع شخص گیرنده",
                "type": "person_type",
                "required": 1,
            },
            {
                "name": "receiver_id",
                "label": "کد ملی / شناسه ملی گیرنده",
                "type": "national_identifier",
                "required": 1,
            },
            {
                "name": "issuer_type",
                "label": "نوع شخص صادرکننده",
                "type": "person_type",
                "required": 1,
            },
            {
                "name": "issuer_id",
                "label": "کد ملی / شناسه ملی صادرکننده",
                "type": "national_identifier",
                "required": 1,
            },
            {
                "name": "sayad_id",
                "label": "شناسه صیادی",
                "type": "text",
                "required": 1,
            },
            {
                "name": "check_series",
                "label": "سری چک",
                "type": "text",
                "required": 0,
            },
            {
                "name": "check_serial",
                "label": "سریال چک",
                "type": "text",
                "required": 0,
            },
            {
                "name": "amount",
                "label": "مبلغ",
                "type": "number",
                "required": 0,
            },
        ],
    },
    {
        "name": "ثبت قرارداد",
        "description": "اجاره‌نامه / قولنامه",
        "category": "قرارداد",
        "price": 0,
        "fields": [
            {
                "name": "contract_type",
                "label": "نوع قرارداد",
                "type": "select",
                "required": 1,
                "options": ["اجاره‌نامه", "قولنامه"],
            },
            {
                "name": "property_type",
                "label": "نوع ملک / زمین",
                "type": "select",
                "required": 1,
                "options": ["ملک", "زمین"],
            },
            {
                "name": "role",
                "label": "نقش مشتری",
                "type": "select",
                "required": 1,
                "options": ["موجر", "مستأجر"],
            },
            {
                "name": "other_national_id",
                "label": "کد ملی طرف مقابل",
                "type": "national_id",
                "required": 1,
            },
            {
                "name": "other_phone",
                "label": "تلفن طرف مقابل",
                "type": "phone",
                "required": 1,
            },
            {
                "name": "other_postal_code",
                "label": "کد پستی طرف مقابل",
                "type": "text",
                "required": 1,
            },
            {
                "name": "property_postal_code",
                "label": "کد پستی ملک",
                "type": "text",
                "required": 1,
            },
            {
                "name": "usage",
                "label": "نوع کاربری",
                "type": "select",
                "required": 1,
                "options": [
                    "مسکونی",
                    "تجاری",
                    "ورزشی",
                    "مرغداری",
                    "گلخانه",
                ],
            },
            {
                "name": "building_type",
                "label": "نوع ملک",
                "type": "select",
                "required": 1,
                "options": ["آپارتمان", "ویلایی"],
            },
            {
                "name": "shares",
                "label": "میزان دانگ",
                "type": "select",
                "required": 1,
                "options": ["۱", "۲", "۳", "۴", "۵", "۶"],
            },
            {
                "name": "deposit",
                "label": "مبلغ رهن",
                "type": "number",
                "required": 0,
            },
            {
                "name": "monthly_rent",
                "label": "مبلغ اجاره ماهانه",
                "type": "number",
                "required": 0,
            },
        ],
    },
    {
        "name": "جواز کسب",
        "description": "ثبت درخواست جواز کسب و بارگذاری مدارک",
        "category": "اداری",
        "price": 0,
        "fields": [
            {
                "name": "license_type",
                "label": "نوع جواز",
                "type": "text",
                "required": 1,
            },
            {
                "name": "postal_code",
                "label": "کد پستی",
                "type": "text",
                "required": 1,
            },
            {
                "name": "tax_id",
                "label": "کد مالیاتی",
                "type": "text",
                "required": 1,
            },
            {
                "name": "bank_card",
                "label": "تصویر کارت بانکی",
                "type": "image",
                "required": 0,
            },
        ],
    },
]


def ensure_default_services():
    con = get_connection()

    count = con.execute(
        "SELECT COUNT(*) AS c FROM services"
    ).fetchone()["c"]

    if count == 0:
        for order, item in enumerate(DEFAULT_SERVICES):
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
                VALUES (?, ?, ?, '', ?, 1, ?, ?, '[]', ?)
                """,
                (
                    item["name"],
                    item["description"],
                    item["category"],
                    item["price"],
                    order,
                    json.dumps(item["fields"], ensure_ascii=False),
                    now(),
                ),
            )

    con.commit()
    con.close()


ensure_default_services()


def settings():
    con = get_connection()
    rows = con.execute(
        "SELECT key,value FROM settings"
    ).fetchall()
    con.close()
    return dict(rows)


def make_tracking_code():
    while True:
        code = (
            "NV-"
            + __import__("datetime").datetime.now().strftime("%Y%m%d")
            + "-"
            + secrets.token_hex(3).upper()
        )

        con = get_connection()

        exists = con.execute(
            """
            SELECT 1
            FROM requests
            WHERE tracking_code=?
            """,
            (code,),
        ).fetchone()

        con.close()

        if not exists:
            return code


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


def superadmin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))

        if session.get("admin_role") != "superadmin":
            flash("دسترسی غیرمجاز.")
            return redirect(url_for("admin"))

        return view(*args, **kwargs)

    return wrapped


def save_upload(file_obj):
    if not file_obj or not file_obj.filename:
        return None

    ext = os.path.splitext(file_obj.filename)[1].lower()

    allowed = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".pdf",
    }

    if ext not in allowed:
        return None

    filename = secrets.token_hex(16) + ext

    file_obj.save(
        os.path.join(UPLOADS, filename)
    )

    return filename


@app.context_processor
def inject_globals():
    return {
        "site": settings(),
        "statuses": STATUSES,
    }


@app.route("/")
def home():
    con = get_connection()

    services = con.execute(
        """
        SELECT *
        FROM services
        WHERE active=1
        ORDER BY sort_order,id
        """
    ).fetchall()

    con.close()

    return render_template(
        "home.html",
        services=services,
    )


@app.route(
    "/service/<int:sid>",
    methods=["GET", "POST"]
)
def service(sid):

    con = get_connection()

    service_row = con.execute(
        """
        SELECT *
        FROM services
        WHERE id=?
        """,
        (sid,),
    ).fetchone()

    con.close()

    if not service_row or not service_row["active"]:
        return "این خدمت فعال نیست.", 404

    try:
        fields = json.loads(
            service_row["fields_json"] or "[]"
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

        if not name or not national_id or not phone:
            flash(
                "نام، کد ملی و شماره موبایل الزامی است."
            )

            return redirect(request.url)

        con = get_connection()

        customer = con.execute(
            """
            SELECT id
            FROM customers
            WHERE national_id=?
            AND phone=?
            LIMIT 1
            """,
            (
                national_id,
                phone,
            ),
        ).fetchone()

        if customer:

            customer_id = customer["id"]

            con.execute(
                """
                UPDATE customers
                SET name=?
                WHERE id=?
                """,
                (
                    name,
                    customer_id,
                ),
            )

        else:

            cur = con.execute(
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
                    now(),
                ),
            )

            customer_id = cur.lastrowid

        data = {}
        uploaded_files = []

        for field in fields:

            key = field.get("name")

            if not key:
                continue

            field_type = field.get("type")

            if field_type in (
                "image",
                "pdf",
                "multi_file",
            ):

                if field_type == "multi_file":

                    objects = request.files.getlist(
                        key
                    )

                    for obj in objects:

                        stored = save_upload(obj)

                        if stored:

                            uploaded_files.append(
                                {
                                    "field_name": key,
                                    "original_name": obj.filename,
                                    "stored_name": stored,
                                }
                            )

                else:

                    obj = request.files.get(key)

                    stored = save_upload(obj)

                    if stored:

                        uploaded_files.append(
                            {
                                "field_name": key,
                                "original_name": obj.filename,
                                "stored_name": stored,
                            }
                        )

            else:

                value = request.form.get(
                    key,
                    "",
                )

                if field_type == "checkbox":
                    value = (
                        request.form.get(key)
                        == "on"
                    )

                data[key] = value

        discount_code = (
            request.form.get(
                "discount_code",
                "",
            )
            .strip()
            .upper()
        )

        base_price = int(
            service_row["price"] or 0
        )

        final_price = base_price
        valid_discount = None

        if discount_code:

            discount = con.execute(
                """
                SELECT *
                FROM discount_codes
                WHERE code=?
                AND active=1
                """,
                (discount_code,),
            ).fetchone()

            if discount:

                today = (
                    __import__("datetime")
                    .datetime.now()
                    .strftime("%Y-%m-%d")
                )

                valid_date = True

                if (
                    discount["start_date"]
                    and today < discount["start_date"]
                ):
                    valid_date = False

                if (
                    discount["end_date"]
                    and today > discount["end_date"]
                ):
                    valid_date = False

                if (
                    discount["max_uses"]
                    and discount["used_count"]
                    >= discount["max_uses"]
                ):
                    valid_date = False

                if (
                    discount["service_id"]
                    and discount["service_id"]
                    != sid
                ):
                    valid_date = False

                if valid_date:

                    if discount["kind"] == "amount":
                        reduction = min(
                            final_price,
                            discount["value"],
                        )
                    else:
                        reduction = min(
                            final_price,
                            round(
                                final_price
                                * discount["value"]
                                / 100
                            ),
                        )

                    final_price = max(
                        0,
                        final_price - reduction,
                    )

                    valid_discount = discount

        free = None

        free_code = (
            request.form.get(
                "free_code",
                "",
            )
            .strip()
            .upper()
        )

        if free_code:

            free = con.execute(
                """
                SELECT *
                FROM free_codes
                WHERE code=?
                AND active=1
                """,
                (free_code,),
            ).fetchone()

            if free:

                today = (
                    __import__("datetime")
                    .datetime.now()
                    .strftime("%Y-%m-%d")
                )

                if (
                    free["service_id"]
                    and free["service_id"] != sid
                ):
                    free = None

                elif (
                    free["valid_until"]
                    and today > free["valid_until"]
                ):
                    free = None

                elif (
                    free["max_uses"]
                    and free["used_count"]
                    >= free["max_uses"]
                ):
                    free = None

                else:
                    final_price = 0

        tracking_code = make_tracking_code()

        status = (
            "منتظر پرداخت"
            if final_price > 0
            else "جدید"
        )

        cur = con.execute(
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
            VALUES (?, ?, ?, ?, ?, ?, 0, 'full', ?, ?)
            """,
            (
                customer_id,
                sid,
                json.dumps(
                    data,
                    ensure_ascii=False,
                ),
                status,
                tracking_code,
                final_price,
                now(),
                now(),
            ),
        )

        request_id = cur.lastrowid

        if valid_discount:

            con.execute(
                """
                UPDATE discount_codes
                SET used_count=used_count+1
                WHERE id=?
                """,
                (
                    valid_discount["id"],
                ),
            )

        if free:

            con.execute(
                """
                UPDATE free_codes
                SET used_count=used_count+1
                WHERE id=?
                """,
                (
                    free["id"],
                ),
            )

        for item in uploaded_files:

            cur_file = con.execute(
                """
                INSERT INTO files
                (
                    request_id,
                    customer_id,
                    field_name,
                    original_name,
                    stored_name,
                    file_type,
                    downloadable,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    request_id,
                    customer_id,
                    item["field_name"],
                    item["original_name"],
                    item["stored_name"],
                    os.path.splitext(
                        item["original_name"]
                    )[1].lower(),
                    now(),
                ),
            )

        con.commit()
        con.close()

        # اعلان ثبت درخواست برای مدیران
        # از تابع اصلی database.py استفاده می‌شود.
        try:
            add_request(
                customer_id=customer_id,
                service_id=sid,
                data_json=json.dumps(
                    data,
                    ensure_ascii=False,
                ),
                total_price=final_price,
                tracking_code=tracking_code,
            )
        except Exception:
            pass

        return render_template(
            "success.html",
            code=tracking_code,
            price=final_price,
            payment_needed=final_price > 0,
        )

    return render_template(
        "service.html",
        service=service_row,
        fields=fields,
    )


@app.route(
    "/tracking",
    methods=["GET", "POST"]
)
def tracking():

    code = request.values.get(
        "code",
        "",
    ).strip()

    result = None
    messages = []

    if code:

        con = get_connection()

        result = con.execute(
            """
            SELECT
                r.*,
                s.name AS service_name,
                c.name AS customer_name,
                c.phone AS customer_phone
            FROM requests r
            LEFT JOIN services s
                ON s.id=r.service_id
            LEFT JOIN customers c
                ON c.id=r.customer_id
            WHERE r.tracking_code=?
            """,
            (code,),
        ).fetchone()

        if result:

            messages = con.execute(
                """
                SELECT
                    m.*,
                    a.name AS admin_name
                FROM messages m
                LEFT JOIN admins a
                    ON a.id=m.sender_admin_id
                WHERE m.request_id=?
                ORDER BY m.id ASC
                """,
                (
                    result["id"],
                ),
            ).fetchall()

        con.close()

    return render_template(
        "tracking.html",
        result=result,
        messages=messages,
    )


@app.route("/customer")
def customer_panel():

    code = request.args.get(
        "code",
        "",
    ).strip()

    if not code:
        return redirect(
            url_for("tracking")
        )

    con = get_connection()

    requests_rows = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name
        FROM requests r
        LEFT JOIN services s
            ON s.id=r.service_id
        WHERE r.tracking_code=?
        """,
        (code,),
    ).fetchall()

    customer = None
    messages = []

    if requests_rows:

        customer = con.execute(
            """
            SELECT *
            FROM customers
            WHERE id=?
            """,
            (
                requests_rows[0]["customer_id"],
            ),
        ).fetchone()

        messages = con.execute(
            """
            SELECT
                m.*,
                a.name AS admin_name
            FROM messages m
            LEFT JOIN admins a
                ON a.id=m.sender_admin_id
            WHERE m.request_id=?
            ORDER BY m.id ASC
            """,
            (
                requests_rows[0]["id"],
            ),
        ).fetchall()

    con.close()

    return render_template(
        "customer.html",
        requests=requests_rows,
        customer=customer,
        code=code,
        messages=messages,
    )


@app.post("/customer/message")
def customer_message():

    code = request.form.get(
        "code",
        "",
    ).strip()

    message = request.form.get(
        "message",
        "",
    ).strip()

    if not code or not message:
        return redirect(
            url_for(
                "customer_panel",
                code=code,
            )
        )

    con = get_connection()

    r = con.execute(
        """
        SELECT *
        FROM requests
        WHERE tracking_code=?
        """,
        (code,),
    ).fetchone()

    if r:

        cur = con.execute(
            """
            INSERT INTO messages
            (
                request_id,
                customer_id,
                sender,
                message,
                created_at
            )
            VALUES (?, ?, 'customer', ?, ?)
            """,
            (
                r["id"],
                r["customer_id"],
                message,
                now(),
            ),
        )

        con.commit()

        # اعلان پیام مشتری برای مدیران
        admins = con.execute(
            """
            SELECT id
            FROM admins
            WHERE active=1
            AND notifications_enabled=1
            """
        ).fetchall()

        for admin in admins:

            con.execute(
                """
                INSERT INTO notifications
                (
                    admin_id,
                    request_id,
                    title,
                    message,
                    is_read,
                    created_at
                )
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    admin["id"],
                    r["id"],
                    "پیام جدید مشتری",
                    "مشتری برای پرونده شما پیام جدید ارسال کرده است.",
                    0,
                    now(),
                ),
            )

        con.commit()

    con.close()

    return redirect(
        url_for(
            "customer_panel",
            code=code,
        )
    )


@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        con = get_connection()

        admin = con.execute(
            """
            SELECT *
            FROM admins
            WHERE username=?
            AND active=1
            """,
            (
                username,
            ),
        ).fetchone()

        con.close()

        if (
            admin
            and secrets.compare_digest(
                password,
                admin["password"],
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
        "admin_login.html"
    )


@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


@app.route("/admin")
@admin_required
def admin():

    con = get_connection()

    services = con.execute(
        """
        SELECT *
        FROM services
        ORDER BY sort_order,id
        """
    ).fetchall()

    customers = con.execute(
        """
        SELECT
            c.*,
            COUNT(r.id) AS request_count
        FROM customers c
        LEFT JOIN requests r
            ON r.customer_id=c.id
        GROUP BY c.id
        ORDER BY c.id DESC
        """
    ).fetchall()

    requests_rows = con.execute(
        """
        SELECT
            r.*,
            s.name AS service_name,
            c.name AS customer_name,
            c.phone,
            a.name AS admin_name
        FROM requests r
        LEFT JOIN services s
            ON s.id=r.service_id
        LEFT JOIN customers c
            ON c.id=r.customer_id
        LEFT JOIN admins a
            ON a.id=r.assigned_admin_id
        ORDER BY r.id DESC
        """
    ).fetchall()

    messages = con.execute(
        """
        SELECT
            m.*,
            c.name AS customer_name,
            r.tracking_code,
            a.name AS admin_name
        FROM messages m
        LEFT JOIN customers c
            ON c.id=m.customer_id
        LEFT JOIN requests r
            ON r.id=m.request_id
        LEFT JOIN admins a
            ON a.id=m.sender_admin_id
        ORDER BY m.id DESC
        LIMIT 100
        """
    ).fetchall()

    admins = con.execute(
        """
        SELECT *
        FROM admins
        ORDER BY id
        """
    ).fetchall()

    discounts = con.execute(
        """
        SELECT *
        FROM discount_codes
        ORDER BY id DESC
        """
    ).fetchall()

    payment_codes = con.execute(
        """
        SELECT *
        FROM payment_codes
        ORDER BY id DESC
        """
    ).fetchall()

    free_codes = con.execute(
        """
        SELECT *
        FROM free_codes
        ORDER BY id DESC
        """
    ).fetchall()

    payments = con.execute(
        """
        SELECT
            p.*,
            r.tracking_code,
            c.name AS customer_name,
            s.name AS service_name
        FROM payments p
        LEFT JOIN requests r
            ON r.id=p.request_id
        LEFT JOIN customers c
            ON c.id=p.customer_id
        LEFT JOIN services s
            ON s.id=r.service_id
        ORDER BY p.id DESC
        """
    ).fetchall()

    site_settings = dict(
        con.execute(
            "SELECT key,value FROM settings"
        ).fetchall()
    )

    unread_notifications = unread_admin_notifications(
        session["admin_id"]
    )

    financial_summary = get_financial_summary()

    con.close()

    return render_template(
        "admin.html",
        services=services,
        customers=customers,
        requests=requests_rows,
        messages=messages,
        admins=admins,
        discounts=discounts,
        payment_codes=payment_codes,
        free_codes=free_codes,
        payments=payments,
        site_settings=site_settings,
        unread_notifications=unread_notifications,
        financial_summary=financial_summary,
    )


@app.post("/admin/request/accept")
@admin_required
def admin_request_accept():

    request_id = int(
        request.form.get(
            "request_id"
        )
    )

    estimated_time = request.form.get(
        "estimated_time",
        "",
    ).strip()

    expert_name = request.form.get(
        "expert_name",
        "",
    ).strip()

    success = accept_request(
        request_id=request_id,
        admin_id=session["admin_id"],
        estimated_time=estimated_time,
        expert_name=expert_name,
    )

    if not success:
        flash(
            "این پرونده قبلاً توسط کارشناس دیگری پذیرفته شده یا وجود ندارد."
        )

    return redirect(
        url_for("admin")
    )


@app.post("/admin/request/status")
@admin_required
def admin_request_status():

    request_id = int(
        request.form.get(
            "request_id"
        )
    )

    status = request.form.get(
        "status",
        "جدید",
    )

    description = request.form.get(
        "description",
        "",
    ).strip()

    estimated_time = request.form.get(
        "estimated_time",
        "",
    ).strip()

    expert_name = request.form.get(
        "expert_name",
        "",
    ).strip()

    update_request_status(
        request_id=request_id,
        admin_id=session["admin_id"],
        status=status,
        description=description,
        estimated_time=estimated_time,
        expert_name=expert_name,
    )

    return redirect(
        url_for("admin")
    )


@app.post("/admin/request/payment")
@admin_required
def admin_request_payment():

    request_id = int(
        request.form.get(
            "request_id"
        )
    )

    paid_price = int(
        request.form.get(
            "paid_price"
        )
        or 0
    )

    con = get_connection()

    con.execute(
        """
        UPDATE requests
        SET paid_price=?,
            updated_at=?
        WHERE id=?
        """,
        (
            paid_price,
            now(),
            request_id,
        ),
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


@app.post("/admin/reply")
@admin_required
def admin_reply():

    request_id = int(
        request.form.get(
            "request_id"
        )
    )

    message = request.form.get(
        "message",
        "",
    ).strip()

    if not message:
        return redirect(
            url_for("admin")
        )

    con = get_connection()

    req = con.execute(
        """
        SELECT *
        FROM requests
        WHERE id=?
        """,
        (
            request_id,
        ),
    ).fetchone()

    if req:

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
            VALUES (?, ?, 'admin', ?, ?, ?)
            """,
            (
                request_id,
                req["customer_id"],
                session["admin_id"],
                message,
                now(),
            ),
        )

        # اعلان پاسخ مدیر/کارشناس برای مشتری
        con.execute(
            """
            INSERT INTO notifications
            (
                customer_id,
                request_id,
                title,
                message,
                is_read,
                created_at
            )
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                req["customer_id"],
                request_id,
                "پاسخ جدید پشتیبانی",
                "مدیر یا کارشناس برای پرونده شما پاسخ جدیدی ارسال کرده است.",
                0,
                now(),
            ),
        )

        con.commit()

    con.close()

    return redirect(
        url_for("admin")
    )


@app.post("/admin/service/save")
@admin_required
def admin_service_save():

    service_id = request.form.get(
        "id",
        "",
    ).strip()

    name = request.form.get(
        "name",
        "",
    ).strip()

    description = request.form.get(
        "description",
        "",
    ).strip()

    category = request.form.get(
        "category",
        "",
    ).strip()

    price = int(
        request.form.get(
            "price"
        )
        or 0
    )

    sort_order = int(
        request.form.get(
            "sort_order"
        )
        or 0
    )

    active = (
        1
        if request.form.get("active")
        == "1"
        else 0
    )

    fields_json = request.form.get(
        "fields_json",
        "[]",
    )

    try:
        fields = json.loads(
            fields_json
        )

        if not isinstance(fields, list):
            fields = []

    except Exception:
        fields = []

    con = get_connection()

    if service_id:

        con.execute(
            """
            UPDATE services
            SET
                name=?,
                description=?,
                category=?,
                price=?,
                active=?,
                sort_order=?,
                fields_json=?
            WHERE id=?
            """,
            (
                name,
                description,
                category,
                price,
                active,
                sort_order,
                json.dumps(
                    fields,
                    ensure_ascii=False,
                ),
                service_id,
            ),
        )

    else:

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
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                category,
                price,
                active,
                sort_order,
                json.dumps(
                    fields,
                    ensure_ascii=False,
                ),
                now(),
            ),
        )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


@app.post(
    "/admin/service/delete/<int:sid>"
)
@superadmin_required
def admin_service_delete(sid):

    con = get_connection()

    con.execute(
        """
        DELETE FROM services
        WHERE id=?
        """,
        (
            sid,
        ),
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


@app.post("/admin/password")
@admin_required
def admin_password():

    password = request.form.get(
        "password",
        "",
    )

    if len(password) >= 6:

        con = get_connection()

        con.execute(
            """
            UPDATE admins
            SET password=?
            WHERE id=?
            """,
            (
                password,
                session["admin_id"],
            ),
        )

        con.commit()
        con.close()

    return redirect(
        url_for("admin")
    )


@app.post("/admin/user/save")
@superadmin_required
def admin_user_save():

    admin_id = request.form.get(
        "id",
        "",
    ).strip()

    username = request.form.get(
        "username",
        "",
    ).strip()

    password = request.form.get(
        "password",
        "",
    )

    name = request.form.get(
        "name",
        "",
    ).strip()

    phone = request.form.get(
        "phone",
        "",
    ).strip()

    role = request.form.get(
        "role",
        "admin",
    )

    active = (
        1
        if request.form.get("active")
        == "1"
        else 0
    )

    con = get_connection()

    if admin_id:

        if password:

            con.execute(
                """
                UPDATE admins
                SET
                    username=?,
                    password=?,
                    name=?,
                    phone=?,
                    role=?,
                    active=?
                WHERE id=?
                """,
                (
                    username,
                    password,
                    name,
                    phone,
                    role,
                    active,
                    admin_id,
                ),
            )

        else:

            con.execute(
                """
                UPDATE admins
                SET
                    username=?,
                    name=?,
                    phone=?,
                    role=?,
                    active=?
                WHERE id=?
                """,
                (
                    username,
                    name,
                    phone,
                    role,
                    active,
                    admin_id,
                ),
            )

    else:

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
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                username,
                password or "123456",
                name,
                phone,
                role,
                active,
                now(),
            ),
        )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


@app.post("/admin/discount/save")
@admin_required
def admin_discount_save():

    code = request.form.get(
        "code",
        "",
    ).strip().upper()

    kind = request.form.get(
        "kind",
        "percent",
    )

    value = int(
        request.form.get(
            "value"
        )
        or 0
    )

    start_date = request.form.get(
        "start_date",
        "",
    )

    end_date = request.form.get(
        "end_date",
        "",
    )

    max_uses = int(
        request.form.get(
            "max_uses"
        )
        or 0
    )

    service_id = (
        int(
            request.form.get(
                "service_id"
            )
            or 0
        )
        or None
    )

    add_discount_code(
        code=code,
        kind=kind,
        value=value,
        start_date=start_date,
        end_date=end_date,
        max_uses=max_uses,
        service_id=service_id,
    )

    return redirect(
        url_for("admin")
    )


@app.post("/admin/payment-code/save")
@admin_required
def admin_payment_code_save():

    con = get_connection()

    con.execute(
        """
        INSERT INTO payment_codes
        (
            code,
            prepayment_percent,
            installment_count,
            installment_percent,
            valid_until,
            service_id,
            active
        )
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (
            request.form.get(
                "code",
                "",
            ).strip().upper(),
            int(
                request.form.get(
                    "prepayment_percent"
                )
                or 0
            ),
            int(
                request.form.get(
                    "installment_count"
                )
                or 0
            ),
            int(
                request.form.get(
                    "installment_percent"
                )
                or 0
            ),
            request.form.get(
                "valid_until",
                "",
            ),
            int(
                request.form.get(
                    "service_id"
                )
                or 0
            )
            or None,
        ),
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


@app.post("/admin/free/save")
@admin_required
def admin_free_save():

    con = get_connection()

    con.execute(
        """
        INSERT INTO free_codes
        (
            code,
            valid_until,
            max_uses,
            used_count,
            service_id,
            active
        )
        VALUES (?, ?, ?, 0, ?, 1)
        """,
        (
            request.form.get(
                "code",
                "",
            ).strip().upper(),
            request.form.get(
                "valid_until",
                "",
            ),
            int(
                request.form.get(
                    "max_uses"
                )
                or 1
            ),
            int(
                request.form.get(
                    "service_id"
                )
                or 0
            )
            or None,
        ),
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


@app.post("/admin/settings")
@admin_required
def admin_settings_save():

    allowed = [
        "site_name",
        "manager",
        "phone",
        "logo",
        "warning_text",
        "currency",
        "support_enabled",
        "support_title",
        "support_description",
        "admin_request_notification",
        "customer_request_notification",
        "notifications_once_permission",
    ]

    con = get_connection()

    for key in allowed:

        value = request.form.get(
            key,
            "",
        )

        con.execute(
            """
            INSERT INTO settings(key,value)
            VALUES (?,?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (
                key,
                value,
            ),
        )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


@app.post("/admin/notifications/read-all")
@admin_required
def admin_notifications_read_all():

    mark_all_admin_notifications_read(
        session["admin_id"]
    )

    return redirect(
        url_for("admin")
    )


@app.post("/customer/notifications/read-all")
def customer_notifications_read_all():

    customer_id = request.form.get(
        "customer_id"
    )

    if customer_id:

        mark_all_customer_notifications_read(
            int(customer_id)
        )

    return redirect(
        request.referrer
        or url_for("home")
    )


@app.post("/admin/notifications/permission")
@admin_required
def admin_notification_permission():

    enabled = (
        request.form.get(
            "enabled"
        )
        == "1"
    )

    set_admin_notification_permission(
        session["admin_id"],
        enabled,
    )

    return redirect(
        url_for("admin")
    )


@app.route("/support")
def support():

    customer_id = request.args.get(
        "customer_id",
        type=int,
    )

    if not customer_id:
        return redirect(
            url_for("tracking")
        )

    con = get_connection()

    customer = con.execute(
        """
        SELECT *
        FROM customers
        WHERE id=?
        """,
        (
            customer_id,
        ),
    ).fetchone()

    con.close()

    if not customer:
        return redirect(
            url_for("home")
        )

    messages = get_support_messages(
        customer_id
    )

    return render_template(
        "support.html",
        customer=customer,
        messages=messages,
    )


@app.post("/support/message")
def support_message():

    customer_id = int(
        request.form.get(
            "customer_id"
        )
    )

    message = request.form.get(
        "message",
        "",
    ).strip()

    if message:

        create_support_request(
            customer_id
        )

        add_support_message(
            customer_id=customer_id,
            message=message,
        )

    return redirect(
        url_for(
            "support",
            customer_id=customer_id,
        )
    )


@app.get(
    "/files/<path:filename>"
)
@admin_required
def protected_file(filename):

    return send_from_directory(
        UPLOADS,
        filename,
        as_attachment=False,
    )


@app.get("/health")
def health():

    return jsonify(
        {
            "ok": True,
            "database": os.path.exists(DB_PATH)
            if "DB_PATH" in globals()
            else True,
        }
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000,
            )
        ),
    )
