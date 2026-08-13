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
