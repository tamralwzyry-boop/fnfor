import random
import re
import asyncio
import json
import os
import threading
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from flask import Flask

# ─────────────────────────────────────────────
#  Flask
# ─────────────────────────────────────────────
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    web_app.run(host='0.0.0.0', port=7860)

# ─────────────────────────────────────────────
#  ⚠️  غيّر هذه القيم قبل التشغيل
# ─────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN")
RESULTS_DESTINATION = 1449739390
AU_LINK    = "https://t.me/arab_union3"
DATA_FILE  = "war_data.json"
SUPER_ADMINS = ["mwsa_20", "levil_8"]

# ─────────────────────────────────────────────
#  البيانات
# ─────────────────────────────────────────────
wars = {}

def save():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(wars, f, ensure_ascii=False, indent=2)

def load():
    global wars
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        wars = {int(k): v for k, v in data.items()}
        print("✅ بيانات محملة")

def emoji(n):
    d = {'0':'0️⃣','1':'1️⃣','2':'2️⃣','3':'3️⃣','4':'4️⃣',
         '5':'5️⃣','6':'6️⃣','7':'7️⃣','8':'8️⃣','9':'9️⃣'}
    return "".join(d.get(c,c) for c in str(n))

def clean(text):
    if not text: return ""
    t = text.lower()
    t = t.replace('ة','ه').replace('أ','ا').replace('إ','ا').replace('آ','ا')
    return t

# ─────────────────────────────────────────────
#  إرسال رابط المواجهة
# ─────────────────────────────────────────────
async def send_war_link(context, chat_id: int, reason: str):
    w = wars.get(chat_id)
    if not w or w.get("link_sent"):
        return

    c1, c2   = w["c1"]["n"], w["c2"]["n"]
    s1, s2   = w["c1"]["s"], w["c2"]["s"]
    src_link = w.get("source_link", "—")

    text = (
        f"📋 {reason}\n\n"
        f"⚔️ المواجهة: {c1} {s1} - {s2} {c2}\n"
        f"🔗 رابط المواجهة: {src_link}\n"
        f"🆔 ID الجروب: {chat_id}"
    )
    try:
        await context.bot.send_message(
            RESULTS_DESTINATION, text, disable_web_page_preview=True
        )
        w["link_sent"] = True
        save()
        print(f"✅ تم إرسال الرابط إلى {RESULTS_DESTINATION}")
    except Exception as e:
        print(f"❌ فشل إرسال الرابط: {e}")
        print("💡 تأكد أن RESULTS_DESTINATION صحيح وأن المستخدم بعت /start للبوت")

# ─────────────────────────────────────────────
#  مهام الخلفية
# ─────────────────────────────────────────────
async def task_remind_referee(chat_id: int, context):
    await asyncio.sleep(2 * 24 * 3600)

    w = wars.get(chat_id)
    if not w or not w.get("active"):
        return

    mentions = " ".join(f"@{a}" for a in SUPER_ADMINS)
    await context.bot.send_message(
        chat_id,
        f"⏰ مرت يومان على القرعة.\n"
        f"📢 تنبيه للحكام: {mentions}\n"
        f"❓ هل انتهت المواجهة؟ يرجى إنهاؤها أو تأكيد استمرارها.\n\n"
        f"(مالك الجروب يمكنه كتابة: انهاء مواجهه)"
    )

    asyncio.create_task(task_remind_owner(chat_id, context))


async def task_remind_owner(chat_id: int, context):
    await asyncio.sleep(1 * 24 * 3600)

    w = wars.get(chat_id)
    if not w or not w.get("active"):
        return

    owner_mention = "مالك الجروب"
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for a in admins:
            if a.status == 'creator':
                if a.user.username:
                    owner_mention = f"@{a.user.username}"
                else:
                    owner_mention = f'<a href="tg://user?id={a.user.id}">المالك</a>'
                break
    except:
        pass

    await context.bot.send_message(
        chat_id,
        f"⚠️ {owner_mention} مرت 3 أيام ولم تنتهِ المواجهة.\n"
        f"اكتب انهاء مواجهه لإنهائها وإرسال الرابط.",
        parse_mode="HTML"
    )


async def task_auto_send_after_6h(chat_id: int, context):
    await asyncio.sleep(6 * 3600)

    await send_war_link(
        context, chat_id,
        "✅ أُرسل تلقائياً بعد 6 ساعات من انتهاء المواجهة."
    )

# ─────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 أهلاً {name}!\n"
        f"🆔 الـ chat_id الخاص بك: {uid}\n\n"
        f"ضع هذا الرقم في RESULTS_DESTINATION داخل الكود لتستقبل روابط المواجهات."
    )
    print(f"✅ /start من: {name} | ID: {uid}")

# ─────────────────────────────────────────────
#  المعالج الرئيسي
# ─────────────────────────────────────────────
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    cid         = update.effective_chat.id
    msg         = update.message.text
    msg_up      = msg.upper().strip()
    msg_cl      = clean(msg)
    user        = update.effective_user
    u_tag       = f"@{user.username}" if user.username else f"ID:{user.id}"

    # صلاحيات
    try:
        cm         = await context.bot.get_chat_member(cid, user.id)
        is_creator = (cm.status == 'creator')
        is_ref     = (user.username in SUPER_ADMINS) or is_creator
    except:
        is_creator = False
        is_ref     = (user.username in SUPER_ADMINS)

    w = wars.get(cid)

    # ══════════════════════════════════════════
    # 1. بدء المواجهة:  CLAN X VS CLAN Y
    # ══════════════════════════════════════════
    if "CLAN" in msg_up and "VS" in msg_up and "+1" not in msg_up and "+ 1" not in msg_up:
        parts = msg_up.split(" VS ")
        if len(parts) == 2:
            c1 = parts[0].replace("CLAN","").strip()
            c2 = parts[1].replace("CLAN","").strip()
            wars[cid] = {
                "c1": {"n": c1, "s": 0, "p": [], "stats": [], "leader": None},
                "c2": {"n": c2, "s": 0, "p": [], "stats": [], "leader": None},
                "active": True, "mid": None, "matches": [],
                "source_link": f"https://t.me/c/{str(cid).replace('-100','')}/1",
                "link_sent": False,
                "waiting_objection": False
            }
            save()
            await update.message.reply_text(
                f"⚔️ بدأت الحرب!\n🔥 {c1}  VS  {c2}"
            )
            # ✅ تغيير اسم الجروب فقط إذا كان المُرسل هو Owner
            if is_creator:
                try:
                    await context.bot.set_chat_title(cid, f"⚔️ {c1} 0 - 0 {c2} ⚔️")
                except: pass
        return

    if not w:
        return

    # ══════════════════════════════════════════
    # 2. انهاء مواجهه — Owner فقط
    # ══════════════════════════════════════════
    if "انهاء مواجهه" in msg_cl or "انهاء مواجهة" in msg_cl:
        if not is_creator:
            await update.message.reply_text("🚫 هذا الأمر لمالك الجروب (Owner) فقط.")
            return
        if w.get("link_sent"):
            await update.message.reply_text("⚠️ تم إرسال الرابط مسبقاً، لا يمكن الإرسال مرة أخرى.")
            return
        await send_war_link(context, cid, "📌 أنهى المالك المواجهة يدوياً.")
        await update.message.reply_text("✅ تم إرسال رابط المواجهة للجهة المعنية.")
        return

    # ══════════════════════════════════════════
    # 3. الاعتراض — عندي اعتراض
    # ══════════════════════════════════════════
    if "عندي اعتراض" in msg_cl or msg_cl.strip() == "اعتراض":
        is_leader = u_tag in [w["c1"].get("leader"), w["c2"].get("leader")]
        if not (is_ref or is_leader):
            await update.message.reply_text("❌ الاعتراض متاح للحكام والقادة فقط.")
            return
        w["waiting_objection"] = True
        w["objection_by"]      = u_tag
        save()
        await update.message.reply_text(
            "📝 اكتب نص اعتراضك كاملاً في رسالة واحدة.\n"
            "أو أرسل: الغاء  للتراجع."
        )
        return

    # استقبال نص الاعتراض
    if w.get("waiting_objection"):
        if msg_cl.strip() == "الغاء":
            w["waiting_objection"] = False
            save()
            await update.message.reply_text("✅ تم إلغاء الاعتراض.")
            return

        objector = w.get("objection_by", u_tag)
        w["waiting_objection"] = False
        save()

        c1n = w["c1"]["n"]
        c2n = w["c2"]["n"]
        s1  = w["c1"]["s"]
        s2  = w["c2"]["s"]
        objection_summary = (
            f"⚖️ اعتراض رسمي مسجّل\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 مقدّم الاعتراض: {objector}\n"
            f"📊 النتيجة الحالية: {c1n} {s1} - {s2} {c2n}\n"
            f"📝 نص الاعتراض:\n{msg}\n"
            f"━━━━━━━━━━━━━━\n"
            f"⏳ سيتم البت فيه من الحكام."
        )
        await update.message.reply_text(objection_summary)
        return

    # ══════════════════════════════════════════
    # 4. تسجيل القائمة — رد على رسالة اللاعبين
    # ══════════════════════════════════════════
    if "قائم" in msg_cl and update.message.reply_to_message:
        target_k = None
        if w["c1"]["n"].upper() in msg_up: target_k = "c1"
        elif w["c2"]["n"].upper() in msg_up: target_k = "c2"

        if not target_k:
            await update.message.reply_text("❌ اكتب اسم الكلان بشكل صحيح مع كلمة قائمة.")
            return

        players = [
            p.strip() for p in update.message.reply_to_message.text.split('\n')
            if p.strip().startswith('@')
        ]
        if not players:
            await update.message.reply_text("❌ لا يوجد لاعبون في الرسالة (يجب أن تبدأ بـ @).")
            return

        w[target_k]["leader"] = u_tag
        w[target_k]["p"]      = players
        save()

        await update.message.reply_text(
            f"✅ قائمة {w[target_k]['n']} مقبولة ({len(players)} لاعبين) بواسطة {u_tag}."
        )

        if w["c1"]["p"] and w["c2"]["p"]:
            await _make_draw(update, context, cid, w)
        return

    # ══════════════════════════════════════════
    # 5. إضافة نقطة:  CLAN + 1 @p1 @p2 3 1
    # ══════════════════════════════════════════
    if ("+1" in msg_up or "+ 1" in msg_up) and w.get("active"):
        win_k = (
            "c1" if w["c1"]["n"].upper() in msg_up
            else "c2" if w["c2"]["n"].upper() in msg_up
            else None
        )
        if not win_k:
            return

        players = re.findall(r'@\w+', msg)
        scores  = re.findall(r'\b(\d+)\b', msg)

        if len(players) >= 2 and len(scores) >= 2:
            asst = (
                context.bot_data
                .get(f"asst_{cid}_{w[win_k]['n'].upper()}")
            )
            if not (is_ref or u_tag == w[win_k]["leader"] or u_tag == asst):
                await update.message.reply_text("❌ التسجيل للحكام والقادة/المساعدين فقط.")
                return

            u1, u2   = players[0], players[1]
            sc1, sc2 = int(scores[0]), int(scores[1])
            p_win    = u1 if sc1 > sc2 else u2

            w[win_k]["s"] += 1
            w[win_k]["stats"].append({
                "name": p_win, "goals": max(sc1,sc2),
                "rec": min(sc1,sc2), "is_free": False
            })
            for m in w["matches"]:
                p1u, p2u = m["p1"].upper(), m["p2"].upper()
                if u1.upper() in (p1u,p2u) and u2.upper() in (p1u,p2u):
                    m["s1"],m["s2"] = (sc1,sc2) if u1.upper()==p1u else (sc2,sc1)
            save()

            await update.message.reply_text(
                f"✅ نقطة لـ {w[win_k]['n']}  |  "
                f"{u1} {sc1} - {sc2} {u2}"
            )
            await _update_table(context, cid, w)

            # ✅ تغيير اسم الجروب فقط إذا كان المُرسل هو Owner
            if is_creator:
                try:
                    await context.bot.set_chat_title(
                        cid,
                        f"⚔️ {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']} ⚔️"
                    )
                except: pass

            for pl in players:
                try:
                    mem = await context.bot.get_chat_member(cid, pl)
                    await context.bot.ban_chat_member(cid, mem.user.id)
                    await context.bot.unban_chat_member(cid, mem.user.id)
                except: pass

        else:
            if not is_ref:
                await update.message.reply_text("❌ النقطة الفري للإدارة فقط.")
                return
            w[win_k]["s"] += 1
            w[win_k]["stats"].append({"name":"Free","goals":0,"rec":0,"is_free":True})
            save()
            await update.message.reply_text(f"⚖️ نقطة فري لكلان {w[win_k]['n']}.")
            await _update_table(context, cid, w)

        if w[win_k]["s"] >= 4:
            await _end_war(update, context, cid, w, win_k)
        return


# ─────────────────────────────────────────────
#  دوال مساعدة
# ─────────────────────────────────────────────
async def _make_draw(update, context, cid, w):
    p1 = list(w["c1"]["p"])
    p2 = list(w["c2"]["p"])
    random.shuffle(p1)
    random.shuffle(p2)
    pairs = list(zip(p1, p2))
    w["matches"] = [{"p1":a,"p2":b,"s1":0,"s2":0} for a,b in pairs]
    save()

    rows = [
        f"{i+1} | {m['p1']} {emoji(0)}|🆚|{emoji(0)} {m['p2']}"
        for i,m in enumerate(w["matches"])
    ]
    table = (
        f"🎲 القرعة الرسمية\n"
        f"A- [ {w['c1']['n']} ]  VS  B- [ {w['c2']['n']} ]\n"
        f"{'─'*30}\n"
        + "\n".join(rows) +
        f"\n{'─'*30}\n"
        f"⌛ يومين وينتهي الوقت\n"
        f"🔗 {AU_LINK}"
    )
    sent = await update.message.reply_text(table, disable_web_page_preview=True)
    w["mid"] = sent.message_id
    save()

    try:
        await context.bot.pin_chat_message(cid, sent.message_id)
    except Exception as e:
        print(f"تعذّر التثبيت: {e}")

    await update.message.reply_text(
        "✅ تمت القرعة وتم تثبيت الجدول!\n"
        "⏰ سيصلك تذكير بعد يومين."
    )

    asyncio.create_task(task_remind_referee(cid, context))


async def _update_table(context, cid, w):
    if not w.get("mid"):
        return
    rows = [
        f"{i+1} | {m['p1']} {emoji(m['s1'])}|🆚|{emoji(m['s2'])} {m['p2']}"
        for i,m in enumerate(w["matches"])
    ]
    table = (
        f"⚔️ {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
        f"{'─'*30}\n"
        + "\n".join(rows) +
        f"\n{'─'*30}\n🔗 {AU_LINK}"
    )
    try:
        await context.bot.edit_message_text(
            table, cid, w["mid"], disable_web_page_preview=True
        )
    except: pass


async def _end_war(update, context, cid, w, win_k):
    w["active"] = False
    save()

    real = [h for h in w[win_k]["stats"] if not h["is_free"]]
    if real:
        hasm        = real[-1]["name"]
        star_data   = max(real, key=lambda x: x["goals"] - x["rec"])
        star        = star_data["name"]
        star_g      = star_data["goals"]
        star_r      = star_data["rec"]
        result_msg  = (
            f"🎊 فاز كلان {w[win_k]['n']} 🎊\n\n"
            f"🎯 الحاسم: {hasm}\n"
            f"⭐ النجم: {star} (سجّل {star_g} واستقبل {star_r})"
        )
    else:
        result_msg = f"🎊 فوز إداري لكلان {w[win_k]['n']} 🎊"

    await update.message.reply_text(result_msg)

    detail = "\n".join(
        f"{i+1}. {m['p1']} {emoji(m['s1'])} - {emoji(m['s2'])} {m['p2']}"
        for i,m in enumerate(w["matches"])
    )
    await update.message.reply_text(f"📊 النتائج الكاملة:\n\n{detail}")

    asyncio.create_task(task_auto_send_after_6h(cid, context))


# ─────────────────────────────────────────────
#  تشغيل البوت
# ─────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    load()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    print("✅ البوت يعمل...")
    print(f"📤 الرابط سيُرسل إلى: {RESULTS_DESTINATION}")
    print("💡 لمعرفة chat_id الخاص بك: ابعت /start للبوت")

    app.run_polling(drop_pending_updates=True)
