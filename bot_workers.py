import asyncio, threading, json, os, datetime, random, re
from rubka import Robot
from rubka.context import Message

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

running_bots = {}


# ============================================================
#  ربات خام (raw)
# ============================================================
async def run_child_raw_bot(owner_id, bid, token, password):
    bot = Robot(token)
    dd = f"{DATA_DIR}/rawbot_{bid}"
    os.makedirs(dd, exist_ok=True)
    CF = f"{dd}/config.json"
    BF = f"{dd}/buttons.json"
    LF = f"{dd}/learn.json"

    config = load(CF, {"welcome_text": "👋 خوش آمدید!", "admin_ids": []})
    buttons = load(BF, [])
    learn = load(LF, {})
    admin_ids = set(config.get("admin_ids", []))
    if str(owner_id) not in admin_ids:
        admin_ids.add(str(owner_id))
        config["admin_ids"] = list(admin_ids)
        save(config, CF)

    @bot.on_message()
    async def handler(b, msg: Message):
        text = (msg.text or "").strip()
        uid = str(msg.chat_id)

        if text == password:
            admin_ids.add(uid)
            config["admin_ids"] = list(admin_ids)
            save(config, CF)
            await msg.reply("✅ پنل ادمین فعال شد")
            return

        if text.startswith("/start"):
            await msg.reply(config.get("welcome_text", "👋"))
            return

        for btn in buttons:
            if isinstance(btn, dict) and btn.get("text") == text:
                await msg.reply(btn.get("response", "✅"))
                return

        if text in learn:
            await msg.reply(learn[text])
            return

        await msg.reply("❓ پیام شما دریافت شد")

    running_bots[bid] = {"bot": bot, "running": True}
    try:
        await bot.run()
    finally:
        running_bots.pop(bid, None)


# ============================================================
#  ربات چت ناشناس (anonymous)
# ============================================================
async def run_child_anonymous(owner_id, bid, token, password):
    bot = Robot(token)
    uf = f"{DATA_DIR}/anon_{bid}_users.json"
    users = load(uf, {})
    waiting = []
    active = {}
    admin_ids = set()

    def su():
        save(uf, users)

    @bot.on_message()
    async def handler(b, msg: Message):
        uid = str(msg.chat_id)
        text = (msg.text or "").strip()

        if uid not in users:
            users[uid] = {"coins": 10, "name": "کاربر", "state": "name"}
            su()

        if text == password:
            admin_ids.add(uid)
            await msg.reply("✅ پنل ادمین")
            return

        u = users[uid]

        if u.get("state") == "name":
            u["name"] = text
            u["state"] = None
            su()
            await msg.reply(f"✅ خوش آمدی {text}!\n\n💬 برای چت ناشناس بنویس: چت")
            return

        if text in ("چت", "چت ناشناس"):
            if u.get("coins", 0) < 3:
                await msg.reply("❌ نیاز ۳ سکه")
                return
            partner = None
            for w in waiting[:]:
                if w != uid:
                    partner = w
                    waiting.remove(w)
                    break
            if partner:
                active[uid] = partner
                active[partner] = uid
                u["coins"] -= 3
                users[partner]["coins"] -= 3
                su()
                await msg.reply("✅ وصل شدی! پیام بفرست.")
                await bot.send_message(partner, "✅ وصل شدی! پیام بفرست.")
            else:
                waiting.append(uid)
                await msg.reply("⏳ در حال جستجو...")
            return

        if text in ("قطع", "پایان"):
            if uid in active:
                p = active.pop(uid)
                active.pop(p, None)
                await msg.reply("❌ قطع شد.")
                await bot.send_message(p, "❌ طرف مقابل قطع کرد.")
            elif uid in waiting:
                waiting.remove(uid)
                await msg.reply("✅ لغو شد.")
            return

        if uid in active:
            try:
                await bot.send_message(active[uid], text)
            except Exception:
                pass
            return

        await msg.reply("❓ /start برای شروع")

    running_bots[bid] = {"bot": bot, "running": True}
    try:
        await bot.run()
    finally:
        running_bots.pop(bid, None)


# ============================================================
#  ربات هوش مصنوعی (ai)
# ============================================================
AI_DATA = {
    "greetings": ["سلام", "درود", "hi", "hello", "سلم"],
    "thanks": ["ممنون", "مرسی", "تشکر", "thanks"],
    "bye": ["خداحافظ", "بای", "bye"],
    "how": ["چطوری", "خوبی", "حالت چطوره"],
}
AI_RESP = {
    "greetings": ["سلام عزیزم 🌹", "درود! ✨", "سلام! خوشحالم 😊"],
    "thanks": ["خواهش می‌کنم 🌹", "کاری نکردم ❤️", "قابل نداشت ✨"],
    "bye": ["خدانگهدار 👋", "به امید دیدار 🌹"],
    "how": ["عالی! تو چطوری؟ 😊", "خوبم ممنون 🌹"],
}

async def run_child_ai_bot(owner_id, bid, token, password):
    bot = Robot(token)

    @bot.on_message()
    async def handler(b, msg: Message):
        text = (msg.text or "").strip()
        low = text.lower()
        if not text:
            return

        if text == password:
            await msg.reply("✅ پنل ادمین فعال شد")
            return

        math_txt = low.replace("×", "*").replace("÷", "/")
        clean = re.sub(r"[^0-9+\-*/().\s]", "", math_txt)
        if re.search(r"\d", clean) and any(op in clean for op in "+-*/"):
            try:
                res = eval(clean)
                if isinstance(res, (int, float)):
                    out = int(res) if res == int(res) else res
                    await msg.reply(f"🧮 جواب: {out}")
                    return
            except Exception:
                pass

        for intent, patterns in AI_DATA.items():
            for p in patterns:
                if p in low:
                    await msg.reply(random.choice(AI_RESP[intent]))
                    return

        await msg.reply(random.choice([
            "🤔 جالب بود! بیشتر توضیح بده...",
            "😊 متوجه شدم!",
            "💭 نمی‌دونم چی بگم، ولی خوبه که حرف می‌زنی!",
            "✨ یه چیز دیگه بپرس!",
        ]))

    running_bots[bid] = {"bot": bot, "running": True}
    try:
        await bot.run()
    finally:
        running_bots.pop(bid, None)


# ============================================================
#  ربات فروشگاه (shop)
# ============================================================
async def run_child_shop_bot(owner_id, bid, token, password):
    bot = Robot(token)
    dd = f"{DATA_DIR}/shopbot_{bid}"
    os.makedirs(dd, exist_ok=True)
    PF = f"{dd}/products.json"
    OF = f"{dd}/orders.json"
    products = load(PF, [])
    orders = load(OF, [])
    admin_ids = set()

    @bot.on_message()
    async def handler(b, msg: Message):
        uid = str(msg.chat_id)
        text = (msg.text or "").strip()

        if text == password:
            admin_ids.add(uid)
            await msg.reply("✅ پنل ادمین فروشگاه")
            return

        if text.startswith("/start"):
            await msg.reply("🛍 به فروشگاه خوش آمدید!\n\n«محصولات» برای مشاهده")
            return

        if text in ("محصولات", "لیست"):
            if not products:
                await msg.reply("📭 هنوز محصولی اضافه نشده")
                return
            out = "🛍 محصولات:\n\n"
            for i, p in enumerate(products, 1):
                out += f"{i}. {p['name']} — {p['price']} تومان\n"
            await msg.reply(out)
            return

        await msg.reply("❓ /start")

    running_bots[bid] = {"bot": bot, "running": True}
    try:
        await bot.run()
    finally:
        running_bots.pop(bid, None)


# ============================================================
#  ربات مدیریت گروه (group_manager)
# ============================================================
async def run_child_group_manager(owner_id, bid, token, password):
    bot = Robot(token)
    admin_ids = set()

    @bot.on_message()
    async def handler(b, msg: Message):
        text = (msg.text or "").strip()
        uid = str(msg.chat_id)

        if text == password:
            admin_ids.add(uid)
            await msg.reply("✅ پنل ادمین گروه فعال شد")
            return

        if text.startswith("/start"):
            await msg.reply("👥 ربات مدیریت گروه\n\n«پنل» برای تنظیمات")
            return

        if text in ("پنل", "داشبورد") and uid in admin_ids:
            await msg.reply(
                "🎛 پنل مدیریت گروه\n\n"
                "🔗 ضد لینک: 🟢\n"
                "🚫 ضد رکیک: 🔴\n"
                "👋 خوش‌آمد: 🟢\n\n"
                "برای تغییر بگو: «ضد لینک خاموش»"
            )
            return

    running_bots[bid] = {"bot": bot, "running": True}
    try:
        await bot.run()
    finally:
        running_bots.pop(bid, None)


# ============================================================
#  راه‌انداز
# ============================================================
BOT_RUNNERS = {
    "raw": run_child_raw_bot,
    "anonymous": run_child_anonymous,
    "ai": run_child_ai_bot,
    "shop": run_child_shop_bot,
    "group_manager": run_child_group_manager,
}


def start_bot_async(bid, owner_id, token, password, bot_type):
    if bid in running_bots and running_bots[bid].get("running"):
        print(f"⚠️ ربات {bid} قبلاً در حال اجراست")
        return

    runner = BOT_RUNNERS.get(bot_type)
    if not runner:
        print(f"❌ نوع ربات نامعتبر: {bot_type}")
        return

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            print(f"🚀 روشن شدن ربات {bid} (نوع: {bot_type})")
            loop.run_until_complete(runner(owner_id, bid, token, password))
        except Exception as e:
            print(f"❌ خطای ربات {bid}: {e}")
        finally:
            loop.close()
            running_bots.pop(bid, None)
            print(f"🛑 ربات {bid} خاموش شد")

    t = threading.Thread(target=_run, daemon=True, name=f"bot_{bid}")
    t.start()


def stop_bot_async(bid):
    info = running_bots.get(bid)
    if info and info.get("bot"):
        try:
            info["bot"].stop()
        except Exception as e:
            print(f"stop err {bid}: {e}")
    running_bots.pop(bid, None)
    print(f"🛑 ربات {bid} متوقف شد")


def list_running():
    return list(running_bots.keys())
