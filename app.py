import os, json, datetime, hashlib, secrets, threading
from functools import wraps
from flask import Flask, request, jsonify, session, send_file

from bot_workers import start_bot_async, stop_bot_async, list_running

OWNER_ID = "b0FbBmY0BD5G05ceee1577a1225d2a96"
ADMIN_PASS = "yasindev"
SUPPORT = "@Yasin002023"
VIP_COST = 100
INVITE_REWARD = 20
SIGNUP_BONUS = 10
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


def load(p, d):
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return d


def save(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def num(v, d=0):
    try:
        return int(v) if v is not None else d
    except Exception:
        return d


USERS_F = f"{DATA_DIR}/users.json"
BOTS_F = f"{DATA_DIR}/bots.json"
TICK_F = f"{DATA_DIR}/tickets.json"

users = load(USERS_F, {})
bots = load(BOTS_F, {})
tickets = load(TICK_F, {})


def save_users():
    save(USERS_F, users)


def save_bots():
    save(BOTS_F, bots)


def save_tickets():
    save(TICK_F, tickets)


app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = secrets.token_hex(32)


def is_vip(uid):
    u = users.get(str(uid), {})
    v = u.get("vip_until")
    if not v:
        return False
    try:
        return datetime.datetime.now() < datetime.datetime.fromisoformat(v)
    except Exception:
        return False


def bot_limit(uid):
    return 5 if is_vip(uid) else 1


def bot_count(uid):
    return len(bots.get(str(uid), []))


def need_login(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session:
            return jsonify({"ok": False, "err": "لطفاً وارد شوید"}), 401
        return f(*a, **k)
    return w


@app.route("/")
def home():
    return send_file("index.html")


@app.post("/api/register")
def register():
    d = request.json or {}
    uid = (d.get("uid") or "").strip()
    pwd = (d.get("password") or "").strip()
    name = (d.get("name") or "کاربر").strip()[:30]
    ref = (d.get("ref") or "").strip()

    if len(uid) < 4:
        return jsonify({"ok": False, "err": "شناسه حداقل ۴ کاراکتر"})
    if uid in users:
        return jsonify({"ok": False, "err": "این شناسه گرفته شده"})
    if len(pwd) < 4:
        return jsonify({"ok": False, "err": "رمز حداقل ۴ کاراکتر"})

    users[uid] = {
        "uid": uid, "name": name, "password": sha(pwd),
        "coins": SIGNUP_BONUS, "vip_until": None,
        "last_daily": None, "invites_count": 0,
        "created_at": datetime.datetime.now().isoformat(),
    }
    if ref and ref in users and ref != uid:
        users[ref]["coins"] = num(users[ref].get("coins")) + INVITE_REWARD
        users[ref]["invites_count"] = num(users[ref].get("invites_count")) + 1
    save_users()
    session["uid"] = uid
    return jsonify({"ok": True, "user": users[uid]})


@app.post("/api/login")
def login():
    d = request.json or {}
    uid = (d.get("uid") or "").strip()
    pwd = (d.get("password") or "").strip()
    if uid not in users:
        return jsonify({"ok": False, "err": "کاربر پیدا نشد"})
    if users[uid].get("password") != sha(pwd):
        return jsonify({"ok": False, "err": "رمز اشتباه"})
    session["uid"] = uid
    return jsonify({"ok": True, "user": users[uid]})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
@need_login
def me():
    uid = session["uid"]
    u = users.get(uid, {})
    days = 0
    if is_vip(uid) and u.get("vip_until"):
        try:
            days = max(0, (datetime.datetime.fromisoformat(u["vip_until"]) - datetime.datetime.now()).days)
        except Exception:
            pass
    return jsonify({
        "ok": True, "uid": uid, "name": u.get("name", "کاربر"),
        "coins": num(u.get("coins")), "vip": is_vip(uid), "vip_days": days,
        "bot_count": bot_count(uid), "bot_limit": bot_limit(uid),
        "invites_count": num(u.get("invites_count")),
        "is_owner": uid == OWNER_ID, "is_admin": session.get("admin", False),
    })


@app.post("/api/daily")
@need_login
def daily():
    uid = session["uid"]
    today = str(datetime.date.today())
    if users[uid].get("last_daily") == today:
        return jsonify({"ok": False, "err": "امروز گرفتی 🌹"})
    amt = 4 if is_vip(uid) else 2
    users[uid]["coins"] = num(users[uid].get("coins")) + amt
    users[uid]["last_daily"] = today
    save_users()
    return jsonify({"ok": True, "amount": amt, "coins": users[uid]["coins"]})


@app.get("/api/invite")
@need_login
def invite():
    uid = session["uid"]
    return jsonify({"ok": True, "code": uid, "reward": INVITE_REWARD,
                    "bonus": SIGNUP_BONUS,
                    "count": num(users[uid].get("invites_count"))})


BOT_TYPES = {
    "raw": {"name": "ربات خام", "price": 0, "icon": "🛠"},
    "anonymous": {"name": "چت ناشناس", "price": 1, "icon": "🤖"},
    "group_manager": {"name": "مدیریت گروه", "price": 5, "icon": "👥"},
    "shop": {"name": "فروشگاه", "price": 8, "icon": "🛍"},
    "ai": {"name": "هوش مصنوعی", "price": 10, "icon": "🧠"},
}


@app.get("/api/bots")
@need_login
def list_bots():
    uid = session["uid"]
    my_bots = bots.get(uid, [])
    for b in my_bots:
        b["running"] = b["bot_id"] in list_running()
    return jsonify({"ok": True, "bots": my_bots,
                    "count": bot_count(uid), "limit": bot_limit(uid)})


@app.get("/api/bot-types")
def bot_types():
    return jsonify({"ok": True, "types": BOT_TYPES})


@app.post("/api/bots/create")
@need_login
def create_bot():
    uid = session["uid"]
    d = request.json or {}
    bt = d.get("type", "")
    token = (d.get("token") or "").strip()
    pwd = (d.get("password") or "").strip()

    if bt not in BOT_TYPES:
        return jsonify({"ok": False, "err": "نوع نامعتبر"})
    if len(token) < 20:
        return jsonify({"ok": False, "err": "توکن کوتاه است"})
    if len(pwd) < 3:
        return jsonify({"ok": False, "err": "رمز حداقل ۳ کاراکتر"})
    if bot_count(uid) >= bot_limit(uid):
        return jsonify({"ok": False, "err": f"ظرفیت پر است ({bot_limit(uid)})"})

    price = BOT_TYPES[bt]["price"]
    if num(users[uid].get("coins")) < price:
        return jsonify({"ok": False, "err": f"سکه کافی نیست (نیاز: {price})"})

    users[uid]["coins"] -= price
    bid = f"b{uid}_{int(datetime.datetime.now().timestamp())}"
    bot = {
        "bot_id": bid, "token": token, "password": pwd,
        "type": bt, "active": True,
        "created_at": datetime.datetime.now().isoformat(),
    }
    bots.setdefault(uid, []).append(bot)
    save_users()
    save_bots()

    threading.Thread(target=start_bot_async,
                     args=(bid, uid, token, pwd, bt), daemon=True).start()

    return jsonify({"ok": True, "bot": bot, "coins": users[uid]["coins"]})


@app.post("/api/bots/toggle")
@need_login
def toggle_bot():
    uid = session["uid"]
    bid = (request.json or {}).get("bot_id")
    for b in bots.get(uid, []):
        if b["bot_id"] == bid:
            b["active"] = not b.get("active", True)
            save_bots()
            if b["active"]:
                threading.Thread(target=start_bot_async,
                                 args=(bid, uid, b["token"], b["password"], b["type"]),
                                 daemon=True).start()
            else:
                threading.Thread(target=stop_bot_async, args=(bid,), daemon=True).start()
            return jsonify({"ok": True, "active": b["active"]})
    return jsonify({"ok": False, "err": "پیدا نشد"})


@app.post("/api/bots/delete")
@need_login
def delete_bot():
    uid = session["uid"]
    bid = (request.json or {}).get("bot_id")
    lst = bots.get(uid, [])
    for i, b in enumerate(lst):
        if b["bot_id"] == bid:
            threading.Thread(target=stop_bot_async, args=(bid,), daemon=True).start()
            lst.pop(i)
            save_bots()
            return jsonify({"ok": True})
    return jsonify({"ok": False, "err": "پیدا نشد"})


@app.get("/api/leaderboard")
@need_login
def leaderboard():
    by = request.args.get("by", "coins")
    rows = []
    if by == "coins":
        rows = [(u, num(d.get("coins"))) for u, d in users.items()]
    elif by == "invites":
        rows = [(u, num(d.get("invites_count"))) for u, d in users.items()]
    elif by == "bots":
        rows = [(u, len(b)) for u, b in bots.items() if b]
    rows = [(u, v) for u, v in rows if v > 0]
    rows.sort(key=lambda x: x[1], reverse=True)
    top = []
    for uid, val in rows[:10]:
        u = users.get(uid, {})
        name = u.get("name") or (uid[:6] + "…" + uid[-4:] if len(uid) > 12 else uid)
        top.append({"uid": uid, "name": name, "value": val})
    return jsonify({"ok": True, "top": top})


@app.post("/api/buy-vip")
@need_login
def buy_vip():
    uid = session["uid"]
    if num(users[uid].get("coins")) < VIP_COST:
        return jsonify({"ok": False, "err": f"نیاز {VIP_COST} سکه"})
    users[uid]["coins"] -= VIP_COST
    now = datetime.datetime.now()
    if users[uid].get("vip_until"):
        try:
            ce = datetime.datetime.fromisoformat(users[uid]["vip_until"])
            if ce > now:
                now = ce
        except Exception:
            pass
    users[uid]["vip_until"] = (now + datetime.timedelta(days=30)).isoformat()
    save_users()
    return jsonify({"ok": True, "coins": users[uid]["coins"]})


@app.get("/api/tickets")
@need_login
def my_tickets():
    uid = session["uid"]
    mine = [{"id": k, **v} for k, v in tickets.items() if v.get("user_id") == uid]
    mine.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify({"ok": True, "tickets": mine[:20]})


@app.post("/api/tickets")
@need_login
def new_ticket():
    uid = session["uid"]
    d = request.json or {}
    sub = (d.get("subject") or "").strip()[:80]
    msg = (d.get("message") or "").strip()
    if not sub or not msg:
        return jsonify({"ok": False, "err": "موضوع و پیام الزامی"})
    tid = f"T{int(datetime.datetime.now().timestamp())}"
    tickets[tid] = {
        "user_id": uid, "user_name": users[uid].get("name", "کاربر"),
        "subject": sub, "messages": [{"from": "user", "text": msg}],
        "status": "open", "created_at": datetime.datetime.now().isoformat(),
    }
    save_tickets()
    return jsonify({"ok": True, "id": tid})


@app.post("/api/admin/login")
@need_login
def admin_login():
    if session["uid"] != OWNER_ID:
        return jsonify({"ok": False, "err": "دسترسی نداری"})
    if (request.json or {}).get("password") != ADMIN_PASS:
        return jsonify({"ok": False, "err": "رمز اشتباه"})
    session["admin"] = True
    return jsonify({"ok": True})


@app.get("/api/admin/stats")
@need_login
def admin_stats():
    if not session.get("admin") or session["uid"] != OWNER_ID:
        return jsonify({"ok": False}), 403
    return jsonify({
        "ok": True, "users": len(users),
        "vips": sum(1 for u in users if is_vip(u)),
        "bots": sum(len(b) for b in bots.values()),
        "tickets": len(tickets),
    })


@app.post("/api/admin/give-coins")
@need_login
def give_coins():
    if not session.get("admin") or session["uid"] != OWNER_ID:
        return jsonify({"ok": False}), 403
    d = request.json or {}
    target = d.get("uid")
    amt = num(d.get("amount"))
    if target not in users:
        return jsonify({"ok": False, "err": "کاربر نیست"})
    users[target]["coins"] = num(users[target].get("coins")) + amt
    save_users()
    return jsonify({"ok": True, "coins": users[target]["coins"]})


@app.get("/api/settings")
def get_settings():
    return jsonify({"ok": True, "support": SUPPORT, "vip_cost": VIP_COST})


def restore_bots():
    for uid, blist in bots.items():
        for b in blist:
            if b.get("active", True):
                print(f"♻️ روشن کردن ربات {b['bot_id']}")
                start_bot_async(b["bot_id"], uid, b["token"], b["password"], b["type"])


if __name__ == "__main__":
    print("🚀 http://127.0.0.1:5000")
    print(f"🔐 Owner: {OWNER_ID}")
    restore_bots()
    app.run(host="0.0.0.0", port=5000, debug=False)
