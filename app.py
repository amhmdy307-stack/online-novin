from flask import Flask, request, redirect, session, render_template_string
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "online_novin_secret"

DB = "online_novin.db"
ADMIN_PASSWORD = "123456"


def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service TEXT,
        action TEXT,
        data TEXT,
        status TEXT,
        created TEXT
    )
    """)
    con.commit()
    con.close()


def save_data(service, action, data):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
    INSERT INTO requests(service,action,data,status,created)
    VALUES(?,?,?,?,?)
    """,(
        service,
        action,
        data,
        "جدید",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))
    con.commit()
    con.close()


STYLE = """
body{
direction:rtl;
font-family:tahoma;
background:#f2f2f2;
margin:0;
}

header{
background:#006699;
color:white;
text-align:center;
padding:20px;
}

.logo{
width:100px;
height:100px;
border-radius:50%;
}

.box{
background:white;
margin:20px;
padding:20px;
border-radius:15px;
}

a,button{
display:block;
background:#0077aa;
color:white;
padding:12px;
margin:10px 0;
text-decoration:none;
border-radius:10px;
text-align:center;
}

input,select{
width:100%;
padding:10px;
margin:8px 0;
border-radius:8px;
border:1px solid #ccc;
}
"""


def page(title,body):
    return render_template_string("""
<html>
<head>
<meta charset="utf-8">
<title>{{title}}</title>
<style>{{style}}</style>
</head>

<body>

<header>
<h2>
کافی نت آنلاین نوین - با مدیریت : محمدی مهر
</h2>
</header>

<div class="box">
{{body|safe}}
</div>

</body>
</html>
""",
title=title,
style=STYLE,
    body=body
)

FIELDS = {

"marriage": {
"ثبتنام اولیه":[
("کدملی متقاضی","national_id"),
("کدملی همسر","spouse_id"),
("تلفن بنام","phone"),
("کد پستی","postal"),
("وضعیت سربازی","military"),
("ایثارگری","isargari")
],

"انتخاب بانک":[
("کدملی","national_id"),
("بانک موردنظر","bank")
],

"ویرایش اطلاعات و تلفن جدید":[
("تلفن جدید","phone"),
("کدملی","national_id")
],

"ویرایش شعبه":[
("کدملی","national_id"),
("کد رهگیری","tracking")
],

"حذف درخواست":[
("کدملی","national_id"),
("کد رهگیری","tracking")
],

"مشاهده وضعیت":[
("کدملی","national_id"),
("کد رهگیری","tracking")
],

"بازیابی کد رهگیری":[
("کدملی","national_id"),
("نام و نام خانوادگی","name"),
("تاریخ تولد","birth"),
("تاریخ ازدواج","marriage_date")
]
},


"child": {

"ثبتنام جدید":[
("کدملی","national_id"),
("تلفن بنام پدر","father_phone")
],

"ویرایش ثبتنام قبلی":[
("کدملی پدر","father_id"),
("کدملی فرزند","child_id"),
("کد رهگیری","tracking")
],

"حذف ثبتنام":[
("کدملی پدر","father_id"),
("کدملی فرزند","child_id"),
("کد رهگیری","tracking")
],

"شماره تلفن سرپرست":[
("شماره تلفن سرپرست","phone")
],

"مشاهده وضعیت":[
("کدملی سرپرست","parent_id"),
("کدملی فرزند","child_id"),
("کد رهگیری","tracking")
],

"بازیابی کد رهگیری":[
("کدملی پدر","father_id"),
("کدملی فرزند","child_id"),
("تاریخ تولد پدر","father_birth"),
("تاریخ تولد فرزند","child_birth"),
("نام و نام خانوادگی فرزند","child_name")
]

}
}


@app.route("/")
def home():

    return page("صفحه اصلی", """
    <h3>انتخاب خدمت</h3>

    <a href="/marriage">
    وام ازدواج
    </a>

    <a href="/child">
    وام فرزندآوری
    </a>

    """)


@app.route("/marriage")
def marriage():

    buttons=""

    for x in FIELDS["marriage"]:
        buttons += f"""
        <a href="/form/marriage/{x}">
        {x}
        </a>
        """

    return page("وام ازدواج",
    "<h3>وام ازدواج</h3>"+buttons)



@app.route("/child")
def child():

    buttons=""

    for x in FIELDS["child"]:
        buttons += f"""
        <a href="/form/child/{x}">
        {x}
        </a>
        """
@app.route("/form/<service>/<action>", methods=["GET", "POST"])
def form(service, action):

    fields = FIELDS.get(service, {}).get(action)

    if fields is None:
        return "فرم پیدا نشد", 404

    if request.method == "POST":

        data = []

        for label, key in fields:
            value = request.form.get(key, "").strip()
            data.append(label + ": " + value)

        save_data(
            "وام ازدواج" if service == "marriage" else "وام فرزندآوری",
            action,
            "\n".join(data)
        )

        return page("ثبت شد", """
        <h3>درخواست با موفقیت ثبت شد ✅</h3>
        <p>درخواست شما برای کافی نت آنلاین نوین ارسال شد.</p>

        <a href="/">
        بازگشت به صفحه اصلی
        </a>
        """)

    inputs = ""

    for label, key in fields:

        if key == "military":

            inputs += """
            <label>وضعیت سربازی</label>

            <select name="military" required>

            <option value="">
            انتخاب کنید
            </option>

            <option>
            پایان خدمت
            </option>

            <option>
            معافیت
            </option>

            <option>
            سایر
            </option>

            </select>
            """

        elif key == "isargari":

            inputs += """
            <label>ایثارگری</label>

            <select name="isargari" required>

            <option value="">
            انتخاب کنید
            </option>

            <option>
            دارم
            </option>

            <option>
            ندارم
            </option>

            </select>
            """

        elif key == "bank":

            inputs += """
            <label>بانک موردنظر</label>

            <select name="bank" required>

            <option value="">
            انتخاب بانک
            </option>

            <option>بانک ملت</option>
            <option>بانک ملی</option>
            <option>بانک صادرات</option>
            <option>بانک تجارت</option>
            <option>بانک رفاه</option>
            <option>بانک مسکن</option>
            <option>سایر</option>

            </select>
            """

        else:

            inputs += f"""
            <label>{label}</label>
            <input
                type="text"
                name="{key}"
                required
            >
            """

    back = "/marriage" if service == "marriage" else "/child"

    return page(action, f"""
    <h3>{action}</h3>

    <form method="POST">

    {inputs}

    <button type="submit">
    ثبت درخواست
    </button>

    </form>

    <a href="{back}">
    بازگشت
    </a>
    """)


init_db()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
        )
    return page("وام فرزندآوری",
    "<h3>وام فرزندآوری</h3>"+buttons)@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        password = request.form.get("password", "")

        if password == ADMIN_PASSWORD:

            session["admin"] = True

            return redirect("/admin")

        return page("خطا", """
        <h3>رمز عبور اشتباه است ❌</h3>

        <a href="/admin/login">
        دوباره تلاش کنید
        </a>
        """)

    return page("پنل مدیریت", """
    <h3>ورود به پنل مدیریت</h3>

    <form method="POST">

    <label>
    رمز عبور
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
    """)


@app.route("/admin")
def admin():

    if not session.get("admin"):

        return redirect("/admin/login")

    con = sqlite3.connect(DB)

    con.row_factory = sqlite3.Row

    rows = con.execute("""
    SELECT *
    FROM requests
    ORDER BY id DESC
    """).fetchall()

    con.close()

    html = """
    <h3>پنل مدیریت</h3>

    <a href="/admin/logout">
    خروج از پنل
    </a>

    <hr>

    """

    if not rows:

        html += """
        <p>
        هنوز هیچ درخواستی ثبت نشده است.
        </p>
        """

    else:

        for row in rows:

            data = row["data"].replace(
                "\n",
                "<br>"
            )

            html += f"""
            <div style="
            border:1px solid #ddd;
            padding:15px;
            margin:15px 0;
            border-radius:10px;
            ">

            <b>
            درخواست شماره {row["id"]}
            </b>

            <p>
            خدمت:
            {row["service"]}
            </p>

            <p>
            گزینه:
            {row["action"]}
            </p>

            <p>
            {data}
            </p>

            <p>
            وضعیت:
            <b>{row["status"]}</b>
            </p>

            <p>
            زمان:
            {row["created"]}
            </p>

            </div>
            """

    return page(
        "پنل مدیریت",
        html
    )


@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect("/")


@app.route("/health")
def health():

    return "OK"


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
