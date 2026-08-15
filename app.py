import os, json, sqlite3, secrets
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "site.db")
UPLOADS = os.path.join(BASE, "uploads")
os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "123456")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS customers(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      national_id TEXT NOT NULL, phone TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS services(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      description TEXT DEFAULT '', price INTEGER DEFAULT 0,
      active INTEGER DEFAULT 1, image TEXT DEFAULT '',
      fields_json TEXT DEFAULT '[]'
    );
    CREATE TABLE IF NOT EXISTS requests(
      id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER,
      service_id INTEGER, data_json TEXT DEFAULT '{}',
      status TEXT DEFAULT 'جدید', tracking_code TEXT UNIQUE,
      total_price INTEGER DEFAULT 0, paid_price INTEGER DEFAULT 0,
      payment_mode TEXT DEFAULT 'full',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS admins(
      id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
      password TEXT NOT NULL, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS settings(
      key TEXT PRIMARY KEY, value TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS discount_codes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
      kind TEXT, value INTEGER DEFAULT 0, active INTEGER DEFAULT 1
    );
    """)
    if not con.execute("SELECT 1 FROM admins LIMIT 1").fetchone():
        con.execute("INSERT INTO admins(username,password) VALUES(?,?)", ("admin", ADMIN_PASSWORD))
    defaults = {
      "site_name":"کافی‌نت آنلاین نوین",
      "manager":"احمد محمدی مهر",
      "phone":"09920345139",
      "sms_enabled":"0",
      "payment_enabled":"0",
      "customer_login_mode":"phone",
      "customer_otp_enabled":"0"
    }
    for k,v in defaults.items():
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
    if not con.execute("SELECT 1 FROM services LIMIT 1").fetchone():
        seed = [
          ("مسکن ملی","ثبت درخواست و بارگذاری مدارک",0),
          ("ثبت‌نام سهام نوزاد","ثبت اطلاعات پدر و فرزند",0),
          ("ثبت‌نام خودرو","ایران‌خودرو، سایپا، بهمن موتور",0),
          ("چک صیادی","ثبت / تأیید یا رد چک",0),
          ("ثبت قرارداد","اجاره‌نامه / قولنامه",0),
          ("جواز کسب","ثبت درخواست جواز کسب",0)
        ]
        for n,d,p in seed:
            con.execute("INSERT INTO services(name,description,price) VALUES(?,?,?)",(n,d,p))
    con.commit(); con.close()

def admin_required():
    return session.get("admin") is True

@app.route("/")
def home():
    con=db(); services=con.execute("SELECT * FROM services WHERE active=1 ORDER BY id DESC").fetchall()
    settings=dict(con.execute("SELECT key,value FROM settings").fetchall())
    con.close()
    return render_template("home.html", services=services, settings=settings)

@app.route("/service/<int:sid>", methods=["GET","POST"])
def service(sid):
    con=db(); s=con.execute("SELECT * FROM services WHERE id=?", (sid,)).fetchone()
    con.close()
    if not s or not s["active"]: return "خدمت فعال نیست",404
    fields=json.loads(s["fields_json"] or "[]")
    if request.method=="POST":
        name=request.form.get("name","").strip()
        nid=request.form.get("national_id","").strip()
        phone=request.form.get("phone","").strip()
        if not name or not nid or not phone:
            flash("نام، کد ملی و تلفن الزامی است.")
            return redirect(request.url)
        con=db()
        c=con.execute("SELECT id FROM customers WHERE national_id=? OR phone=?",(nid,phone)).fetchone()
        if c: cid=c["id"]; con.execute("UPDATE customers SET name=?,phone=? WHERE id=?",(name,phone,cid))
        else:
            cur=con.execute("INSERT INTO customers(name,national_id,phone) VALUES(?,?,?)",(name,nid,phone)); cid=cur.lastrowid
        data={k:request.form.get(k,"") for k in request.form.keys() if k not in ("name","national_id","phone")}
        code="NV-"+secrets.token_hex(4).upper()
        con.execute("""INSERT INTO requests(customer_id,service_id,data_json,tracking_code,total_price)
                       VALUES(?,?,?,?,?)""",(cid,sid,json.dumps(data,ensure_ascii=False),code,s["price"]))
        con.commit(); con.close()
        return render_template("success.html", code=code)
    return render_template("service.html", service=s, fields=fields)


@app.route("/customer/login", methods=["GET","POST"])
def customer_login():
    if request.method == "POST":
        phone = request.form.get("phone","").strip()
        if not phone:
            flash("شماره موبایل را وارد کنید.")
            return redirect(request.url)
        con=db()
        c=con.execute("SELECT * FROM customers WHERE phone=?", (phone,)).fetchone()
        if not c:
            cur=con.execute(
                "INSERT INTO customers(name,national_id,phone) VALUES(?,?,?)",
                ("مشتری جدید","",phone)
            )
            cid=cur.lastrowid
        else:
            cid=c["id"]
        con.commit(); con.close()
        session["customer_id"]=cid
        return redirect(url_for("customer_dashboard"))
    return render_template("customer_login.html")

@app.route("/customer/logout")
def customer_logout():
    session.pop("customer_id", None)
    return redirect(url_for("customer_login"))

@app.route("/customer")
def customer_dashboard():
    cid=session.get("customer_id")
    if not cid:
        return redirect(url_for("customer_login"))
    con=db()
    c=con.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    reqs=con.execute("""SELECT r.*,s.name service_name
      FROM requests r JOIN services s ON s.id=r.service_id
      WHERE r.customer_id=? ORDER BY r.id DESC""",(cid,)).fetchall()
    con.close()
    return render_template("customer.html", customer=c, requests=reqs)

@app.route("/tracking", methods=["GET","POST"])
def tracking():
    result=None
    if request.values.get("code"):
        con=db()
        result=con.execute("""SELECT r.*,s.name service_name,c.name customer_name
          FROM requests r JOIN services s ON s.id=r.service_id
          JOIN customers c ON c.id=r.customer_id WHERE r.tracking_code=?""",
          (request.values["code"].strip(),)).fetchone()
        con.close()
    return render_template("tracking.html", result=result)

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        u=request.form.get("username",""); p=request.form.get("password","")
        con=db(); a=con.execute("SELECT * FROM admins WHERE username=? AND active=1",(u,)).fetchone(); con.close()
        if a and secrets.compare_digest(p,a["password"]):
            session["admin"]=True; session["admin_id"]=a["id"]; return redirect(url_for("admin"))
        flash("نام کاربری یا رمز عبور اشتباه است.")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear(); return redirect(url_for("admin_login"))

@app.route("/admin")
def admin():
    if not admin_required(): return redirect(url_for("admin_login"))
    con=db()
    services=con.execute("SELECT * FROM services ORDER BY id DESC").fetchall()
    customers=con.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    settings=dict(con.execute("SELECT key,value FROM settings").fetchall())
    reqs=con.execute("""SELECT r.*,s.name service_name,c.name customer_name
      FROM requests r JOIN services s ON s.id=r.service_id JOIN customers c ON c.id=r.customer_id
      ORDER BY r.id DESC""").fetchall()
    con.close()
    return render_template("admin.html",services=services,customers=customers,requests=reqs,settings=settings)

@app.post("/admin/service/save")
def admin_service_save():
    if not admin_required(): return redirect(url_for("admin_login"))
    sid=request.form.get("id")
    name=request.form.get("name","").strip()
    desc=request.form.get("description","").strip()
    price=int(request.form.get("price") or 0)
    active=1 if request.form.get("active")=="1" else 0
    fields_raw=request.form.get("fields_json","[]")
    try: json.loads(fields_raw)
    except: fields_raw="[]"
    con=db()
    if sid:
        con.execute("UPDATE services SET name=?,description=?,price=?,active=?,fields_json=? WHERE id=?",
                    (name,desc,price,active,fields_raw,sid))
    else:
        con.execute("INSERT INTO services(name,description,price,active,fields_json) VALUES(?,?,?,?,?)",
                    (name,desc,price,active,fields_raw))
    con.commit(); con.close(); return redirect(url_for("admin"))

@app.post("/admin/request/status")
def admin_request_status():
    if not admin_required(): return redirect(url_for("admin_login"))
    rid=request.form.get("id"); status=request.form.get("status")
    con=db(); con.execute("UPDATE requests SET status=? WHERE id=?",(status,rid)); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/admin/settings")
def admin_settings():
    if not admin_required(): return redirect(url_for("admin_login"))
    con=db()
    for k in ("site_name","manager","phone","sms_enabled","payment_enabled","customer_login_mode","customer_otp_enabled"):
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(k,request.form.get(k,"")))
    con.commit(); con.close(); return redirect(url_for("admin"))

@app.post("/admin/password")
def admin_password():
    if not admin_required(): return redirect(url_for("admin_login"))
    new=request.form.get("password","")
    if len(new)>=6:
        con=db(); con.execute("UPDATE admins SET password=? WHERE id=?",(new,session["admin_id"])); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/admin/service/delete/<int:sid>")
def admin_service_delete(sid):
    if not admin_required(): return redirect(url_for("admin_login"))
    con=db(); con.execute("DELETE FROM services WHERE id=?",(sid,)); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.route("/health")
def health(): return jsonify(ok=True)

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))

