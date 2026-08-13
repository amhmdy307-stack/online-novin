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
