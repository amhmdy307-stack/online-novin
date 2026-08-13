from flask import Flask, request, redirect, session
from database import (
    create_tables,
    create_customer,
    add_service,
    get_connection
)
from validators import (
    check_mobile,
    check_national_id,
    check_postal,
    check_price
)
from services import get_all_services, get_service
from datetime import datetime
from functools import wraps
import os


app = Flask(__name__)

app.secret_key = "online_novin_secret_key"


# اطلاعات کافی نت

SITE_NAME = "کافی نت آنلاین نوین"

MANAGER = "احمد محمدی مهر"

PHONE = "09920345139"



# ساخت دیتابیس

create_tables()



# -------------------------
# قالب ساده سایت
# -------------------------


def layout(title, body):

    return f"""

<!DOCTYPE html>

<html lang="fa" dir="rtl">

<head>

<meta charset="UTF-8">

<meta name="viewport" content="width=device-width, initial-scale=1">


<title>{title}</title>


<style>

body {{

font-family:tahoma;

background:#f2f2f2;

padding:20px;

}}


.box {{

background:white;

max-width:700px;

margin:auto;

padding:20px;

border-radius:15px;

}}


input,textarea,button,select {{

width:100%;

padding:12px;

margin:8px 0;

font-size:16px;

}}


button {{

background:#0077aa;

color:white;

border:0;

border-radius:8px;

}}


a {{

display:block;

background:#0077aa;

color:white;

padding:12px;

margin:10px;

text-align:center;

text-decoration:none;

border-radius:8px;

}}


</style>


</head>


<body>


<div class="box">


<h2>{SITE_NAME}</h2>

<p>
مدیریت : {MANAGER}
</p>

<p>
تماس : {PHONE}
</p>


<hr>


{body}


</div>


</body>

</html>

"""



# -------------------------
# صفحه اصلی
# -------------------------


@app.route("/")
def home():


    services = get_all_services()


    links = ""


    for key,item in services.items():

        links += f"""

        <a href="/service/{key}">

        {item['title']}

        </a>

        """



    links += """

    <a href="/tracking">

    پیگیری وضعیت درخواست

    </a>


    <a href="/admin/login">

    ورود مدیریت

    </a>

    """



    return layout(

        "خانه",

        links

    )

# -------------------------
# صفحه هر خدمت
# -------------------------


@app.route("/service/<service_id>", methods=["GET","POST"])
def service_page(service_id):


    service = get_service(service_id)


    if not service:

        return layout(
            "خطا",
            "خدمت پیدا نشد"
        )



    error = ""



    if request.method == "POST":


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


        postal = request.form.get(
            "postal",
            ""
        ).strip()



        if not name:

            error = "نام و نام خانوادگی الزامی است"



        elif not check_national_id(national_id):

            error = "کد ملی صحیح نیست"



        elif not check_mobile(phone):

            error = "شماره موبایل صحیح نیست"



        elif not check_postal(postal):

            error = "کد پستی صحیح نیست"



        else:


            customer_id = create_customer(

                name,

                phone,

                national_id

            )


            add_service(

                customer_id,

                service["title"]

            )


            return layout(

                "ثبت شد",

                f"""

                <h3>
                درخواست شما ثبت شد
                </h3>

                <p>
                کد پیگیری پرونده شما:
                {customer_id}
                </p>

                <a href="/tracking">
                پیگیری وضعیت
                </a>

                """

            )



    fields = ""



    for field in service["fields"]:


        fields += f"""

        <label>
        {field}
        </label>


        <input name="extra" placeholder="{field}">


        """



    body = f"""

    <h3>
    {service['title']}
    </h3>


    <p style="color:red">
    {error}
    </p>


    <form method="post">


    <input name="name"
    placeholder="نام و نام خانوادگی"
    required>


    <input name="national_id"
    placeholder="کد ملی"
    inputmode="numeric"
    maxlength="10"
    required>


    <input name="phone"
    placeholder="شماره موبایل"
    inputmode="numeric"
    maxlength="11"
    required>


    <input name="postal"
    placeholder="کد پستی"
    inputmode="numeric"
    maxlength="10"
    required>



    {fields}



    <button>
    ثبت درخواست
    </button>


    </form>


    """



    return layout(

        service["title"],

        body

    )

# -------------------------
# پیگیری وضعیت درخواست
# -------------------------

@app.route("/tracking", methods=["GET", "POST"])
def tracking():

    result = ""
    error = ""

    if request.method == "POST":

        tracking_id = request.form.get(
            "tracking_id",
            ""
        ).strip()

        if not tracking_id.isdigit():

            error = "کد پیگیری باید فقط شامل اعداد انگلیسی باشد."

        else:

            con = get_connection()

            customer = con.execute(
                """
                SELECT *
                FROM customers
                WHERE id = ?
                """,
                (int(tracking_id),)
            ).fetchone()

            if not customer:

                error = "پرونده‌ای با این کد پیگیری پیدا نشد."

            else:

                services = con.execute(
                    """
                    SELECT *
                    FROM customer_services
                    WHERE customer_id = ?
                    ORDER BY id DESC
                    """,
                    (customer["id"],)
                ).fetchall()

                con.close()

                cards = ""

                for item in services:

                    remaining = (
                        item["total_price"]
                        - item["paid_price"]
                    )

                    cards += f"""
                    <div style="
                        border:1px solid #ddd;
                        padding:15px;
                        margin:12px 0;
                        border-radius:10px;
                    ">

                        <h3>
                        {item["service_name"]}
                        </h3>

                        <p>
                        <b>وضعیت:</b>
                        {item["status"]}
                        </p>

                        <p>
                        <b>زمان تقریبی:</b>
                        {item["estimated_time"] or "اعلام نشده"}
                        </p>

                        <p>
                        <b>توضیحات:</b>
                        {item["customer_note"] or "توضیحی ثبت نشده"}
                        </p>

                        <hr>

                        <p>
                        <b>هزینه خدمت:</b>
                        {item["total_price"]:,} تومان
                        </p>

                        <p>
                        <b>پرداخت شده:</b>
                        {item["paid_price"]:,} تومان
                        </p>

                        <p>
                        <b>مانده:</b>
                        {remaining:,} تومان
                        </p>

                        <p class="small">
                        تاریخ ثبت:
                        {item["created_at"]}
                        </p>

                    </div>
                    """

                result = f"""
                <div class="box">

                    <h3>
                    پرونده {customer["name"]}
                    </h3>

                    <p>
                    شماره پیگیری:
                    {customer["id"]}
                    </p>

                    {cards}

                    <a href="/chat/{customer["id"]}">
                    💬 گفت‌وگو با پشتیبانی
                    </a>

                </div>
                """


    body = f"""

    <h2>
    پیگیری وضعیت درخواست
    </h2>

    <p style="color:red;">
    {error}
    </p>

    <form method="post">

        <label>
        کد پیگیری پرونده
        </label>

        <input
            type="text"
            name="tracking_id"
            inputmode="numeric"
            pattern="[0-9]+"
            oninput="this.value=this.value.replace(/[^0-9]/g,'')"
            required
        >

        <button type="submit">
        مشاهده وضعیت
        </button>

    </form>

    {result}

    """

    return layout(
        "پیگیری وضعیت",
        body
    )

# -------------------------
# چت مشتری و پشتیبانی
# -------------------------

@app.route("/chat/<int:customer_id>", methods=["GET", "POST"])
def customer_chat(customer_id):

    con = get_connection()

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

        return layout(
            "خطا",
            "<h3>پرونده پیدا نشد.</h3>"
        )


    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()

        if message:

            con.execute(
                """
                INSERT INTO messages
                (customer_id, sender, message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    customer_id,
                    "customer",
                    message,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )

            con.commit()


    messages = con.execute(
        """
        SELECT *
        FROM messages
        WHERE customer_id = ?
        ORDER BY id ASC
        """,
        (customer_id,)
    ).fetchall()

    con.close()


    chat_html = ""

    for msg in messages:

        if msg["sender"] == "customer":

            title = "شما"

        else:

            title = "پشتیبانی"


        chat_html += f"""
        <div style="
            background:#f3f3f3;
            padding:12px;
            margin:10px 0;
            border-radius:10px;
        ">

            <b>{title}</b>

            <p>
            {msg["message"]}
            </p>

            <small>
            {msg["created_at"]}
            </small>

        </div>
        """


    body = f"""

    <h2>
    گفت‌وگو با پشتیبانی
    </h2>

    <p>
    مشتری: {customer["name"]}
    </p>

    <hr>

    {chat_html}

    <form method="post">

        <textarea
            name="message"
            placeholder="پیام خود را بنویسید..."
            required
        ></textarea>

        <button type="submit">
        ارسال پیام
        </button>

    </form>

    <a href="/tracking">
    بازگشت به پیگیری
    </a>

    """


    return layout(
        "گفت‌وگو با پشتیبانی",
        body
    )

# -------------------------
# ورود مدیریت
# -------------------------

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "123456"
)


def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if not session.get("admin_logged_in"):

            return redirect("/admin/login")

        return func(*args, **kwargs)

    return wrapper


@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    error = ""

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        if password == ADMIN_PASSWORD:

            session["admin_logged_in"] = True

            return redirect("/admin")

        error = "رمز عبور اشتباه است."


    body = f"""

    <h2>
    ورود مدیریت
    </h2>

    <p style="color:red;">
    {error}
    </p>

    <form method="post">

        <label>
        رمز عبور مدیریت
        </label>

        <input
            type="password"
            name="password"
            required
        >

        <button type="submit">
        ورود
        </button>

    </form>

    """

    return layout(
        "ورود مدیریت",
        body
    )


# -------------------------
# پنل مدیریت
# -------------------------

@app.route("/admin")
@admin_required
def admin_panel():

    con = get_connection()

    customers = con.execute(
        """
        SELECT *
        FROM customers
        ORDER BY id DESC
        """
    ).fetchall()

    con.close()


    rows = ""

    for customer in customers:

        rows += f"""

        <div style="
            border:1px solid #ddd;
            padding:15px;
            margin:12px 0;
            border-radius:10px;
        ">

            <h3>
            {customer["name"]}
            </h3>

            <p>
            تلفن:
            {customer["phone"] or "-"}
            </p>

            <p>
            کد ملی:
            {customer["national_id"] or "-"}
            </p>

            <a href="/admin/customer/{customer["id"]}">
            📁 مشاهده پرونده
            </a>

        </div>

        """


    if not rows:

        rows = """
        <p>
        هنوز مشتری‌ای ثبت نشده است.
        </p>
        """


    body = f"""

    <h2>
    پنل مدیریت
    </h2>

    <a href="/admin/messages">
    💬 پیام‌های پشتیبانی
    </a>

    <a href="/admin/logout">
    خروج از مدیریت
    </a>

    <hr>

    <h3>
    👥 لیست مشتریان
    </h3>

    {rows}

    """

    return layout(
        "لیست مشتریان",
        body
    )


# -------------------------
# پرونده مشتری
# -------------------------

@app.route("/admin/customer/<int:customer_id>")
@admin_required
def admin_customer(customer_id):

    con = get_connection()

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

        return layout(
            "خطا",
            "<h3>مشتری پیدا نشد.</h3>"
        )


    services = con.execute(
        """
        SELECT *
        FROM customer_services
        WHERE customer_id = ?
        ORDER BY id DESC
        """,
        (customer_id,)
    ).fetchall()


    con.close()


    service_html = ""


    for service in services:

        remaining = (
            service["total_price"]
            - service["paid_price"]
        )


        service_html += f"""

        <div style="
            border:1px solid #ddd;
            padding:15px;
            margin:15px 0;
            border-radius:10px;
        ">

            <h3>
            {service["service_name"]}
            </h3>

            <p>
            وضعیت:
            <b>{service["status"]}</b>
            </p>

            <p>
            هزینه:
            {service["total_price"]:,}
            تومان
            </p>

            <p>
            پرداخت:
            {service["paid_price"]:,}
            تومان
            </p>

            <p>
            مانده:
            {remaining:,}
            تومان
            </p>

            <p>
            زمان تقریبی:
            {service["estimated_time"] or "-"}
            </p>

            <p>
            توضیحات:
            {service["customer_note"] or "-"}
            </p>

            <a href="/admin/service/{service["id"]}">
            ✏️ مدیریت این خدمت
            </a>

        </div>

        """


    if not service_html:

        service_html = """
        <p>
        هنوز خدمتی برای این مشتری ثبت نشده است.
        </p>
        """


    body = f"""

    <h2>
    📁 پرونده مشتری
    </h2>

    <h3>
    {customer["name"]}
    </h3>

    <p>
    شماره تماس:
    {customer["phone"] or "-"}
    </p>

    <p>
    کد ملی:
    {customer["national_id"] or "-"}
    </p>

    <hr>

    <h3>
    خدمات این مشتری
    </h3>

    {service_html}

    <a href="/admin">
    بازگشت به لیست مشتریان
    </a>

    """

    return layout(
        "پرونده مشتری",
        body
    )

# -------------------------
# مدیریت یک خدمت
# -------------------------

@app.route(
    "/admin/service/<int:service_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_service(service_id):

    con = get_connection()

    service = con.execute(
        """
        SELECT
            cs.*,
            c.name AS customer_name
        FROM customer_services cs
        JOIN customers c
            ON c.id = cs.customer_id
        WHERE cs.id = ?
        """,
        (service_id,)
    ).fetchone()

    if not service:

        con.close()

        return layout(
            "خطا",
            "<h3>خدمت پیدا نشد.</h3>"
        )

    error = ""

    if request.method == "POST":

        status = request.form.get(
            "status",
            "جدید"
        ).strip()

        estimated_time = request.form.get(
            "estimated_time",
            ""
        ).strip()

        customer_note = request.form.get(
            "customer_note",
            ""
        ).strip()

        total_price = request.form.get(
            "total_price",
            "0"
        ).strip()

        paid_price = request.form.get(
            "paid_price",
            "0"
        ).strip()

        if not check_price(total_price):

            error = "هزینه کل باید فقط عدد انگلیسی باشد."

        elif not check_price(paid_price):

            error = "مبلغ پرداختی باید فقط عدد انگلیسی باشد."

        else:

            total_price = int(total_price or 0)
            paid_price = int(paid_price or 0)

            if paid_price > total_price:

                error = (
                    "مبلغ پرداختی نمی‌تواند "
                    "بیشتر از هزینه کل باشد."
                )

            else:

                con.execute(
                    """
                    UPDATE customer_services
                    SET
                        status = ?,
                        estimated_time = ?,
                        customer_note = ?,
                        total_price = ?,
                        paid_price = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        estimated_time,
                        customer_note,
                        total_price,
                        paid_price,
                        service_id
                    )
                )

                con.commit()

                customer_id = service["customer_id"]

                con.close()

                return redirect(
                    f"/admin/customer/{customer_id}"
                )

    con.close()

    body = f"""

    <h2>
    مدیریت خدمت
    </h2>

    <p>
    <b>مشتری:</b>
    {service["customer_name"]}
    </p>

    <p>
    <b>خدمت:</b>
    {service["service_name"]}
    </p>

    <p style="color:red;">
    {error}
    </p>

    <form method="post">

        <label>
        وضعیت خدمت
        </label>

        <select name="status">

            <option
            value="جدید"
            {"selected" if service["status"] == "جدید" else ""}
            >
            جدید
            </option>

            <option
            value="در حال بررسی"
            {"selected" if service["status"] == "در حال بررسی" else ""}
            >
            در حال بررسی
            </option>

            <option
            value="در حال انجام"
            {"selected" if service["status"] == "در حال انجام" else ""}
            >
            در حال انجام
            </option>

            <option
            value="نیاز به پیگیری"
            {"selected" if service["status"] == "نیاز به پیگیری" else ""}
            >
            نیاز به پیگیری
            </option>

            <option
            value="منتظر پاسخ سازمان"
            {"selected" if service["status"] == "منتظر پاسخ سازمان" else ""}
            >
            منتظر پاسخ سازمان
            </option>

            <option
            value="انجام شده"
            {"selected" if service["status"] == "انجام شده" else ""}
            >
            انجام شده
            </option>

            <option
            value="رد درخواست"
            {"selected" if service["status"] == "رد درخواست" else ""}
            >
            رد درخواست
            </option>

            <option
            value="لغو شده"
            {"selected" if service["status"] == "لغو شده" else ""}
            >
            لغو شده
            </option>

        </select>


        <label>
        هزینه کل (تومان)
        </label>

        <input
            type="text"
            name="total_price"
            inputmode="numeric"
            pattern="[0-9]*"
            value="{service["total_price"]}"
            oninput="this.value=this.value.replace(/[^0-9]/g,'')"
            required
        >


        <label>
        مبلغ پرداخت شده (تومان)
        </label>

        <input
            type="text"
            name="paid_price"
            inputmode="numeric"
            pattern="[0-9]*"
            value="{service["paid_price"]}"
            oninput="this.value=this.value.replace(/[^0-9]/g,'')"
            required
        >


        <label>
        زمان تقریبی انجام
        </label>

        <input
            type="text"
            name="estimated_time"
            value="{service["estimated_time"] or ""}"
            placeholder="مثلاً ۳ روز کاری"
        >


        <label>
        توضیحات برای مشتری
        </label>

        <textarea
            name="customer_note"
            rows="5"
            placeholder="توضیحات دلخواه برای مشتری"
        >{service["customer_note"] or ""}</textarea>


        <button type="submit">
        ذخیره تغییرات
        </button>

    </form>

    <

                    # -------------------------
# پیام‌های پشتیبانی
# -------------------------

@app.route("/admin/messages")
@admin_required
def admin_messages():

    con = get_connection()

    messages = con.execute(
        """
        SELECT
            m.*,
            c.name AS customer_name
        FROM messages m
        JOIN customers c
            ON c.id = m.customer_id
        ORDER BY m.id DESC
        """
    ).fetchall()

    con.close()

    items = ""

    for msg in messages:

        items += f"""
        <div style="
            border:1px solid #ddd;
            padding:15px;
            margin:12px 0;
            border-radius:10px;
        ">

            <h3>
            {msg["customer_name"]}
            </h3>

            <p>
            <b>
            {"مشتری" if msg["sender"] == "customer" else "پشتیبانی"}
            </b>
            </p>

            <p>
            {msg["message"]}
            </p>

            <small>
            {msg["created_at"]}
            </small>

            <a href="/admin/chat/{msg["customer_id"]}">
            💬 پاسخ به مشتری
            </a>

        </div>
        """

    if not items:

        items = """
        <p>
        هنوز پیامی ثبت نشده است.
        </p>
        """

    body = f"""
    <h2>
    💬 پیام‌های پشتیبانی
    </h2>

    {items}

    <a href="/admin">
    بازگشت به پنل مدیریت
    </a>
    """

    return layout(
        "پیام‌های پشتیبانی",
        body
    )


# -------------------------
# پاسخ مدیریت به مشتری
# -------------------------

@app.route(
    "/admin/chat/<int:customer_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_chat(customer_id):

    con = get_connection()

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

        return layout(
            "خطا",
            "<h3>مشتری پیدا نشد.</h3>"
        )

    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()

        if message:

            con.execute(
                """
                INSERT INTO messages
                (customer_id, sender, message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    customer_id,
                    "admin",
                    message,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )

            con.commit()

    messages = con.execute(
        """
        SELECT *
        FROM messages
        WHERE customer_id = ?
        ORDER BY id ASC
        """,
        (customer_id,)
    ).fetchall()

    con.close()

    chat = ""

    for msg in messages:

        sender = (
            "مشتری"
            if msg["sender"] == "customer"
            else "پشتیبانی"
        )

        chat += f"""
        <div style="
            background:#f3f3f3;
            padding:12px;
            margin:10px 0;
            border-radius:10px;
        ">

            <b>
            {sender}
            </b>

            <p>
            {msg["message"]}
            </p>

            <small>
            {msg["created_at"]}
            </small>

        </div>
        """

    body = f"""
    <h2>
    گفت‌وگو با {customer["name"]}
    </h2>

    {chat}

    <form method="post">

        <textarea
            name="message"
            rows="5"
            placeholder="پاسخ خود را بنویسید..."
            required
        ></textarea>

        <button type="submit">
        ارسال پاسخ
        </button>

    </form>

    <a href="/admin/messages">
    بازگشت به پیام‌ها
    </a>

    <a href="/admin/customer/{customer_id}">
    مشاهده پرونده مشتری
    </a>
    """

    return layout(
        "پاسخ پشتیبانی",
        body
    )


# -------------------------
# خروج از پنل مدیریت
# -------------------------

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect("/admin/login")
