"""
OLX iPhone Monitor - professional Telegram bot (+ kanalga avtomatik yuborish)
O'rnatish:  pip install "aiogram>=3.7" aiohttp
Ishga tushirish:  python olx_iphone_pro_bot.py
"""
import asyncio
import html
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, FSInputFile, InlineKeyboardButton, KeyboardButton,
    LinkPreviewOptions, Message, ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============================ SOZLAMALAR ============================
# MUHIM: eski token ochiq qolgan. BotFather orqali yangi token oling (Revoke)
# va uni shu yerga yozing yoki BOT_TOKEN muhit o'zgaruvchisiga qo'ying.
# Render: Environment bo'limida BOT_TOKEN o'zgaruvchisini yarating (tirnoqsiz, bo'sh joysiz).
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().strip("\"'").strip()
ADMIN_IDS = [8578660273]                 # admin Telegram ID lari
ADMIN_USERNAME = "Kar1mov_ww"  # @ belgisiz
BANNER = ""                             # obuna banneri: rasm yo'li yoki file_id (ixtiyoriy)
CHECK_EVERY = 20                        # OLX ni necha soniyada tekshirish
MAX_FILTERS = 5                         # bitta foydalanuvchiga maksimal filtr
SUB_DAYS = 30
TZ = ZoneInfo("Asia/Tashkent")

# ---------- KANAL SOZLAMALARI ----------
# Render Environment: CHANNEL_ID=@kanal_username yoki -1001234567890. Bot kanalda admin bo'lishi shart
_ch = os.getenv("CHANNEL_ID", "@kanal_username").strip().strip("\"'").strip()
CHANNEL_ID = int(_ch) if _ch.lstrip("-").isdigit() else _ch
# Baza fayli. Render'da Persistent Disk ni /data ga ulang, shunda ma'lumotlar o'chmaydi.
DB_PATH = os.getenv("DB_PATH") or ("/data/bot.db" if os.path.isdir("/data") else "bot.db")
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
CHANNEL_ENABLED = True                  # False qilsangiz kanalga yuborish o'chadi
CHANNEL_QUERIES = ["iphone", "айфон"]   # OLX da qaysi so'zlar bo'yicha qidirish
# Faqat YANGI e'lonlar: e'lon qo'yilganiga necha daqiqadan oshmagan bo'lsa yuboriladi.
# OLX moderatsiyasi 5-10 daqiqa oladi, shuning uchun 30 daqiqa xavfsiz chegara.
CHANNEL_MAX_AGE_MIN = 30
# Sara e'lonlar uchun qo'shimcha shartlar (kerak bo'lmasa False / 0 qiling):
CHANNEL_REQUIRE_PHOTO = True            # rasmi bor e'lonlar
CHANNEL_REQUIRE_PRICE = True            # narxi ko'rsatilgan e'lonlar
CHANNEL_MIN_PRICE = {"UZS": 1_000_000, "USD": 80}   # bundan arzon bo'lsa (aksessuar/aldov) o'tkazilmaydi
# Faqat shu hududdagi e'lonlar (manzilda shu so'zlardan biri bo'lsa o'tadi). Bo'sh [] = butun O'zbekiston.
CHANNEL_REGIONS = ["toshkent", "ташкент", "tashkent"]
# Toshkent viloyatini olib tashlamoqchi bo'lsangiz (faqat shahar): ["viloyat", "область"]
CHANNEL_REGION_EXCLUDE = []

# Tariflar: delay - soniyada kechikish, price - so'm
PLANS = {
    "p0": {"delay": 0,   "price": 499000, "icon": "bolt"},
    "p1": {"delay": 60,  "price": 279000, "icon": "timer"},
    "p3": {"delay": 180, "price": 119000, "icon": "timer"},
}

# ===================== PREMIUM EMOJI ID LAR =====================
# Har bir emoji uchun premium emoji ID ni ikkinchi joyga qo'ying.
# ID bo'sh bo'lsa oddiy emoji ishlatiladi.
# ID olish: admin sifatida botga premium emoji yuboring, bot ID ni qaytaradi.
EMOJI = {
    "diamond": ("💎", "5197350061012436657"),
    "bolt":    ("⚡", "5438539112070002676"),
    "timer":   ("⏱", "5366043289633962337"),
    "gift":    ("🎁", "5193085063998224234"),
    "card":    ("💳", "5445353829304387411"),
    "phone":   ("📱", "5467539229468793355"),
    "money":   ("💰", "5409048419211682843"),
    "pin":     ("📍", "5796440171364749940"),
    "clock":   ("🕒", "5348289410955754971"),
    "note":    ("📝", "5267470401461564700"),
    "link":    ("🔗", "5271604874419647061"),
    "star":    ("⭐", "5807791714093502248"),
    "ok":      ("✅", "5206607081334906820"),
    "no":      ("❌", "5283283384418707920"),
    "info":    ("ℹ️", "6021618194228187816"),
    "filter":  ("🎛", ""),
    "bell":    ("🔔", "5451927229506268442"),
    "chart":   ("📊", "6084477132254218612"),
    "scroll":  ("📜", "6206354659003600828"),
    "fire":    ("🔥", "5424972470023104089"),
}
# ===============================================================

OLX_API = "https://www.olx.uz/api/v1/offers/"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
    "Referer": "https://www.olx.uz/",
    "Origin": "https://www.olx.uz",
}
# OLX Render IP sini 403 bilan bloklasa, proxy ulang (Render > Environment > PROXY_URL).
# Format: http://login:parol@host:port  (faqat HTTP/HTTPS proxy)
PROXY_URL = os.getenv("PROXY_URL", "").strip().strip("\"'").strip() or None

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("olxbot")


def em(name):
    fb, cid = EMOJI[name]
    return f'<tg-emoji emoji-id="{cid}">{fb}</tg-emoji>' if cid else fb


def money(n):
    return f"{int(n):,}".replace(",", " ")


# ============================ MATNLAR ============================
BTN = {
    "uz": {
        "b_filters": "🎛 Filtrlarim", "b_newf": "➕ Yangi filtr",
        "b_fav": "⭐ Saralangan", "b_stats": "📊 Statistika",
        "b_pause": "🔕 Pauza", "b_resume": "🔔 Davom ettirish",
        "b_help": "❓ Yordam", "b_sub": "💳 Obuna", "b_lang": "🌐 Til",
        "manager": "💬 Menejerga yozish", "paid": "✅ To'lovni amalga oshirdim",
        "rules": "📜 Qoidalar", "status": "ℹ️ Obuna holati",
        "open": "🔗 OLX'da ochish", "save": "⭐ Saqlash",
        "skip": "⏭ Farqi yo'q",
    },
    "ru": {
        "b_filters": "🎛 Мои фильтры", "b_newf": "➕ Новый фильтр",
        "b_fav": "⭐ Избранное", "b_stats": "📊 Статистика",
        "b_pause": "🔕 Пауза", "b_resume": "🔔 Возобновить",
        "b_help": "❓ Помощь", "b_sub": "💳 Подписка", "b_lang": "🌐 Язык",
        "manager": "💬 Написать менеджеру", "paid": "✅ Я оплатил",
        "rules": "📜 Правила", "status": "ℹ️ Статус подписки",
        "open": "🔗 Открыть на OLX", "save": "⭐ Сохранить",
        "skip": "⏭ Неважно",
    },
}

TEXTS = {
    "uz": {
        "pick_lang": "🌐 Tilni tanlang / Выберите язык",
        "welcome": (
            "{phone} <b>OLX iPhone Monitor</b>\n\n"
            "OLX.uz da yangi iPhone e'loni chiqishi bilan sizga rasm, narx, manzil "
            "va barcha ma'lumotlari bilan yuboraman.\n\n"
            "{filter} <b>Yangi filtr</b> orqali model, narx va hududni sozlang.\n"
            "{card} <b>Obuna</b> bo'limidan tarifni tanlang."
        ),
        "plans_title": "{diamond} <b>Tariflar — 30 kun</b>",
        "pn_p0": "Kechikishsiz", "pd_p0": "E'lonlar chiqishi bilanoq",
        "pn_p1": "1 daqiqa kechikish", "pd_p1": "E'lonlar 1 daqiqadan keyin",
        "pn_p3": "3 daqiqa kechikish", "pd_p3": "E'lonlar 3 daqiqadan keyin",
        "sum": "so'm",
        "trial": (
            "{gift} <b>1 kunlik bepul sinov</b> — administratorga yozing: @{admin}. "
            "U sizga sinov kunini ochib beradi."
        ),
        "pay_note": (
            "{card} To'lov administrator orqali. To'lagandan keyin "
            "«{ok} To'lovni amalga oshirdim» tugmasini bosing."
        ),
        "rules": (
            "{scroll} <b>Qoidalar</b>\n\n"
            "1. Obuna shaxsiy, uni boshqalarga berish mumkin emas.\n"
            "2. To'langan obuna puli qaytarilmaydi.\n"
            "3. Bot e'lonlarni OLX.uz dan avtomatik oladi, e'lon to'g'riligiga biz javob bermaymiz.\n"
            "4. Sotuvchi bilan kelishuvdan oldin telefonni ko'rib, ehtiyot bo'lib xarid qiling.\n"
            "5. Qoidabuzarlikda obuna bekor qilinishi mumkin."
        ),
        "status_on": (
            "{ok} <b>Obuna faol</b>\n\nTarif: <b>{plan}</b>\n"
            "Tugash sanasi: <b>{date}</b>\nQolgan: <b>{days} kun</b>"
        ),
        "status_off": "{no} <b>Obuna yo'q.</b>\n\nTarifni tanlash uchun «Obuna» bo'limiga o'ting.",
        "pay_choose": "{card} Qaysi tarif uchun to'lov qildingiz?",
        "pay_sent": "{ok} So'rovingiz administratorga yuborildi. Tasdiqlangach xabar olasiz.",
        "pay_admin": (
            "{card} <b>Yangi to'lov so'rovi</b>\n\nFoydalanuvchi: {user}\nID: <code>{uid}</code>\n"
            "Tarif: <b>{plan}</b> — {price} so'm"
        ),
        "approved": "{ok} To'lov tasdiqlandi! <b>{plan}</b> tarifi {days} kunga yoqildi.\nTugash: {date}",
        "rejected": "{no} To'lovingiz tasdiqlanmadi. Savol bo'lsa @{admin} ga yozing.",
        "trial_on": "{gift} Sizga <b>1 kunlik sinov</b> ochildi! Filtr qo'shib, e'lonlarni kuting.",
        "expired": "{no} Obunangiz tugadi. Davom etish uchun «Obuna» bo'limidan yangilang.",
        "nf_query": "{phone} Qidiruv so'zini yozing.\nMasalan: <code>iphone 15 pro</code>",
        "nf_cur": "{money} Narx filtri valyutasini tanlang:",
        "nf_min": "Minimal narx? (raqam yozing, yo'q bo'lsa <code>-</code>)",
        "nf_max": "Maksimal narx? (raqam yozing, yo'q bo'lsa <code>-</code>)",
        "nf_region": "{pin} Hudud yoki shahar? Masalan: <code>Toshkent</code>\nFarqi yo'q bo'lsa <code>-</code> yozing.",
        "nf_done": "{ok} Filtr qo'shildi!\n\n{summary}",
        "nf_limit": "{no} Filtrlar soni chegarasiga yetdingiz ({n}). Keraksizini o'chiring.",
        "nf_nosub": "\n\n{info} Eslatma: e'lonlar faqat faol obuna bilan yuboriladi.",
        "flt_head": "{filter} <b>Filtrlarim</b>\n\n",
        "flt_empty": "{filter} Filtrlar yo'q. «➕ Yangi filtr» tugmasini bosing.",
        "any_price": "narx farqi yo'q", "any_region": "butun O'zbekiston",
        "fav_head": "{star} <b>Saralangan e'lonlar</b>\n\n",
        "fav_empty": "{star} Saralangan e'lonlar yo'q. E'lon ostidagi «Saqlash» tugmasini bosing.",
        "fav_saved": "Saqlandi ⭐", "fav_removed": "O'chirildi",
        "stats": (
            "{chart} <b>Statistika</b>\n\nYuborilgan e'lonlar: <b>{sent}</b>\n"
            "Faol filtrlar: <b>{filters}</b>\nSaralanganlar: <b>{favs}</b>\n"
            "Obuna: <b>{sub}</b>"
        ),
        "sub_none": "yo'q", "sub_days": "{days} kun qoldi",
        "paused": "🔕 Bildirishnomalar to'xtatildi.", "resumed": "🔔 Bildirishnomalar yoqildi.",
        "help": (
            "{info} <b>Yordam</b>\n\n"
            "1. «➕ Yangi filtr» — model, narx va hududni kiriting.\n"
            "2. «💳 Obuna» — tarifni tanlang va to'lang.\n"
            "3. Mos e'lonlar avtomatik keladi.\n"
            "4. «⭐ Saqlash» bilan e'lonni saralanganlarga qo'shing.\n"
            "5. «🔕 Pauza» — vaqtincha to'xtatish.\n\n"
            "Savollar: @{admin}"
        ),
        "lbl_price": "Narx", "lbl_addr": "Manzil",
        "lang_set": "✅ Til o'zgartirildi.",
        "no_price": "Narx ko'rsatilmagan",
    },
    "ru": {
        "pick_lang": "🌐 Tilni tanlang / Выберите язык",
        "welcome": (
            "{phone} <b>OLX iPhone Monitor</b>\n\n"
            "Как только на OLX.uz появляется новое объявление об iPhone, я присылаю его "
            "с фото, ценой, адресом и всеми данными.\n\n"
            "{filter} Настройте модель, цену и регион через <b>Новый фильтр</b>.\n"
            "{card} Выберите тариф в разделе <b>Подписка</b>."
        ),
        "plans_title": "{diamond} <b>Тарифы — 30 дней</b>",
        "pn_p0": "Без задержки", "pd_p0": "Объявления сразу после публикации",
        "pn_p1": "Задержка 1 минута", "pd_p1": "Объявления через 1 минуту",
        "pn_p3": "Задержка 3 минуты", "pd_p3": "Объявления через 3 минуты",
        "sum": "сум",
        "trial": (
            "{gift} <b>1 день бесплатно</b> — напишите администратору: @{admin}. "
            "Он активирует пробный день."
        ),
        "pay_note": (
            "{card} Оплата через администратора. После оплаты нажмите «{ok} Я оплатил»."
        ),
        "rules": (
            "{scroll} <b>Правила</b>\n\n"
            "1. Подписка личная, передавать её другим нельзя.\n"
            "2. Оплаченная подписка не возвращается.\n"
            "3. Бот берёт объявления с OLX.uz автоматически, за их достоверность мы не отвечаем.\n"
            "4. Перед сделкой проверяйте телефон и будьте осторожны.\n"
            "5. При нарушении подписка может быть отменена."
        ),
        "status_on": (
            "{ok} <b>Подписка активна</b>\n\nТариф: <b>{plan}</b>\n"
            "Действует до: <b>{date}</b>\nОсталось: <b>{days} дн.</b>"
        ),
        "status_off": "{no} <b>Подписки нет.</b>\n\nВыберите тариф в разделе «Подписка».",
        "pay_choose": "{card} За какой тариф вы оплатили?",
        "pay_sent": "{ok} Запрос отправлен администратору. Вы получите уведомление после проверки.",
        "pay_admin": (
            "{card} <b>Новый запрос на оплату</b>\n\nПользователь: {user}\nID: <code>{uid}</code>\n"
            "Тариф: <b>{plan}</b> — {price} сум"
        ),
        "approved": "{ok} Оплата подтверждена! Тариф <b>{plan}</b> активирован на {days} дней.\nДо: {date}",
        "rejected": "{no} Оплата не подтверждена. Вопросы: @{admin}",
        "trial_on": "{gift} Вам открыт <b>пробный день</b>! Добавьте фильтр и ждите объявлений.",
        "expired": "{no} Подписка закончилась. Продлите её в разделе «Подписка».",
        "nf_query": "{phone} Введите поисковый запрос.\nНапример: <code>iphone 15 pro</code>",
        "nf_cur": "{money} Выберите валюту для фильтра цены:",
        "nf_min": "Минимальная цена? (число, или <code>-</code> если не нужно)",
        "nf_max": "Максимальная цена? (число, или <code>-</code> если не нужно)",
        "nf_region": "{pin} Регион или город? Например: <code>Ташкент</code>\nЕсли неважно, отправьте <code>-</code>.",
        "nf_done": "{ok} Фильтр добавлен!\n\n{summary}",
        "nf_limit": "{no} Достигнут лимит фильтров ({n}). Удалите ненужные.",
        "nf_nosub": "\n\n{info} Внимание: объявления приходят только при активной подписке.",
        "flt_head": "{filter} <b>Мои фильтры</b>\n\n",
        "flt_empty": "{filter} Фильтров нет. Нажмите «➕ Новый фильтр».",
        "any_price": "любая цена", "any_region": "весь Узбекистан",
        "fav_head": "{star} <b>Избранные объявления</b>\n\n",
        "fav_empty": "{star} Избранного нет. Нажмите «Сохранить» под объявлением.",
        "fav_saved": "Сохранено ⭐", "fav_removed": "Удалено",
        "stats": (
            "{chart} <b>Статистика</b>\n\nОтправлено объявлений: <b>{sent}</b>\n"
            "Активных фильтров: <b>{filters}</b>\nВ избранном: <b>{favs}</b>\n"
            "Подписка: <b>{sub}</b>"
        ),
        "sub_none": "нет", "sub_days": "осталось {days} дн.",
        "paused": "🔕 Уведомления приостановлены.", "resumed": "🔔 Уведомления включены.",
        "help": (
            "{info} <b>Помощь</b>\n\n"
            "1. «➕ Новый фильтр» — укажите модель, цену и регион.\n"
            "2. «💳 Подписка» — выберите тариф и оплатите.\n"
            "3. Подходящие объявления приходят автоматически.\n"
            "4. «⭐ Сохранить» — добавить в избранное.\n"
            "5. «🔕 Пауза» — временно остановить.\n\n"
            "Вопросы: @{admin}"
        ),
        "lbl_price": "Цена", "lbl_addr": "Адрес",
        "lang_set": "✅ Язык изменён.",
        "no_price": "Цена не указана",
    },
}


def t(lang, key, **kw):
    lang = lang if lang in TEXTS else "uz"
    emojis = {k: em(k) for k in EMOJI}
    return TEXTS[lang][key].format(**emojis, admin=ADMIN_USERNAME, **kw)


def b(lang, key):
    return BTN.get(lang, BTN["uz"])[key]


def B(*keys):
    """Barcha tillardagi tugma matnlariga mos keladigan filtr."""
    return F.text.in_({BTN[l][k] for l in BTN for k in keys})


# ============================ BAZA ============================
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'uz', username TEXT, name TEXT,
    plan TEXT, expires INTEGER DEFAULT 0, paused INTEGER DEFAULT 0,
    trial_used INTEGER DEFAULT 0, notified INTEGER DEFAULT 1,
    joined INTEGER, sent INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS filters(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query TEXT,
    currency TEXT, pmin REAL, pmax REAL, region TEXT,
    active INTEGER DEFAULT 1, created INTEGER);
CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY, data TEXT, first_seen INTEGER);
CREATE TABLE IF NOT EXISTS delivered(
    user_id INTEGER, offer_id INTEGER, PRIMARY KEY(user_id, offer_id));
CREATE TABLE IF NOT EXISTS favorites(
    user_id INTEGER, offer_id INTEGER, title TEXT, url TEXT, price TEXT,
    PRIMARY KEY(user_id, offer_id));
CREATE TABLE IF NOT EXISTS queries(query TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS channel_sent(offer_id INTEGER PRIMARY KEY);
""")
db.commit()


def q(sql, *args):
    cur = db.execute(sql, args)
    db.commit()
    return cur.fetchall()


def get_user(uid):
    rows = q("SELECT * FROM users WHERE id=?", uid)
    return rows[0] if rows else None


def ensure_user(tg_user):
    """Foydalanuvchini yaratadi. (user, yangi_mi) qaytaradi."""
    u = get_user(tg_user.id)
    is_new = u is None
    if is_new:
        q("INSERT INTO users(id, username, name, joined) VALUES(?,?,?,?)",
          tg_user.id, tg_user.username, tg_user.full_name, int(time.time()))
    else:
        q("UPDATE users SET username=?, name=? WHERE id=?",
          tg_user.username, tg_user.full_name, tg_user.id)
    return get_user(tg_user.id), is_new


def is_active(u):
    if u and u["id"] in ADMIN_IDS:   # adminlarga obuna shart emas
        return True
    return bool(u and u["plan"] and u["expires"] > time.time())


def fmt_date(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m.%Y %H:%M")


def activate(uid, plan, days):
    u = get_user(uid)
    base = max(int(time.time()), u["expires"] or 0)
    exp = base + days * 86400
    q("UPDATE users SET plan=?, expires=?, notified=0 WHERE id=?", plan, exp, uid)
    return exp


# ============================ KLAVIATURA ============================
def main_kb(lang, paused=False):
    p = b(lang, "b_resume" if paused else "b_pause")
    rows = [
        [b(lang, "b_filters"), b(lang, "b_newf")],
        [b(lang, "b_fav"), b(lang, "b_stats")],
        [p, b(lang, "b_help")],
        [b(lang, "b_sub"), b(lang, "b_lang")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=x) for x in row] for row in rows],
        resize_keyboard=True,
    )


def lang_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🇺🇿 O'zbekcha", callback_data="lang:uz")
    kb.button(text="🇷🇺 Русский", callback_data="lang:ru")
    kb.adjust(2)
    return kb.as_markup()


def sub_text(lang):
    lines = [t(lang, "plans_title"), ""]
    for key, p in PLANS.items():
        lines.append(f"{em(p['icon'])} <b>{t(lang, 'pn_' + key)}</b> — "
                     f"{money(p['price'])} {t(lang, 'sum')}")
        lines.append(f"<i>{t(lang, 'pd_' + key)}</i>")
        lines.append("")
    lines.append(t(lang, "trial"))
    lines.append("")
    lines.append(t(lang, "pay_note"))
    return "\n".join(lines)


def sub_kb(lang):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=b(lang, "manager"), url=f"https://t.me/{ADMIN_USERNAME}"))
    kb.row(InlineKeyboardButton(text=b(lang, "paid"), callback_data="pay:start"))
    kb.row(
        InlineKeyboardButton(text=b(lang, "rules"), callback_data="sub:rules"),
        InlineKeyboardButton(text=b(lang, "status"), callback_data="sub:status"),
    )
    return kb.as_markup()


def status_text(u, lang):
    if u["id"] in ADMIN_IDS:
        return "👑 <b>Admin</b> — obuna shart emas, cheksiz kirish."
    if is_active(u):
        days = max(0, int((u["expires"] - time.time()) // 86400))
        return t(lang, "status_on", plan=t(lang, "pn_" + u["plan"]),
                 date=fmt_date(u["expires"]), days=days)
    return t(lang, "status_off")


# ============================ OLX ============================
def parse_price(o):
    for p in o.get("params", []):
        if p.get("key") == "price":
            v = p.get("value", {}) or {}
            return v.get("value"), (v.get("currency") or "").upper(), v.get("label")
    return None, None, None


def address(o):
    loc = o.get("location", {}) or {}
    parts = [
        (loc.get("region") or {}).get("name"),
        (loc.get("city") or {}).get("name"),
        (loc.get("district") or {}).get("name"),
    ]
    return ", ".join(p for p in parts if p)


def photos(o, limit=1):
    out = []
    for ph in (o.get("photos") or [])[:limit]:
        link = ph.get("link", "")
        if link:
            out.append(link.replace("{width}", "800").replace("{height}", "800"))
    return out


def matches(o, f):
    text = (o.get("title", "") + " " + (o.get("description") or "")).lower()
    if not all(w in text for w in f["query"].lower().split()):
        return False
    if f["pmin"] is not None or f["pmax"] is not None:
        val, cur, _ = parse_price(o)
        if val is None or cur != (f["currency"] or ""):
            return False
        if f["pmin"] is not None and val < f["pmin"]:
            return False
        if f["pmax"] is not None and val > f["pmax"]:
            return False
    if f["region"] and f["region"].lower() not in address(o).lower():
        return False
    return True


def build_caption(o, lang):
    title = html.escape(o.get("title", ""))
    _, _, label = parse_price(o)
    price = html.escape(label) if label else t(lang, "no_price")
    addr = html.escape(address(o)) or "—"
    lines = [
        f"{em('phone')} <b>{title}</b>",
        "",
        f"{em('money')} <b>{t(lang, 'lbl_price')}:</b> {price}",
        f"{em('pin')} <b>{t(lang, 'lbl_addr')}:</b> {addr}",
    ]
    extra = []
    for p in o.get("params", []):
        if p.get("key") == "price":
            continue
        name, lab = p.get("name"), (p.get("value") or {}).get("label")
        if name and lab:
            extra.append(f"▫️ {html.escape(str(name))}: {html.escape(str(lab))}")
    if extra:
        lines += [""] + extra
    created = (o.get("created_time") or "")[:16].replace("T", " ")
    if created:
        lines += ["", f"{em('clock')} {created}"]
    desc = (o.get("description") or "").strip()
    if desc:
        desc = html.escape(desc)
        if len(desc) > 380:
            desc = desc[:380] + "..."
        lines += ["", f"{em('note')} {desc}"]
    text = "\n".join(lines)
    return text if len(text) <= 1024 else text[:1000] + "..."


def offer_kb(o, lang):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=b(lang, "open"), url=o.get("url")))
    kb.row(InlineKeyboardButton(text=b(lang, "save"), callback_data=f"fav:{o['id']}"))
    return kb.as_markup()


async def send_offer(bot, u, o):
    lang = u["lang"]
    caption = build_caption(o, lang)
    kb = offer_kb(o, lang)
    ph = photos(o)
    try:
        try:
            if ph:
                await bot.send_photo(u["id"], ph[0], caption=caption, reply_markup=kb)
            else:
                raise ValueError("no photo")
        except Exception:
            await bot.send_message(u["id"], caption, reply_markup=kb)
        q("UPDATE users SET sent=sent+1 WHERE id=?", u["id"])
    except Exception as e:
        log.warning("send fail %s: %s", u["id"], e)


# ============================ FONDAGI JARAYONLAR ============================
async def poller():
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        while True:
            try:
                blocked = False
                queries = {r["query"].lower() for r in
                           q("SELECT DISTINCT query FROM filters WHERE active=1")}
                if CHANNEL_ENABLED:
                    queries |= {x.lower() for x in CHANNEL_QUERIES}
                for query in queries:
                    try:
                        async with s.get(
                            OLX_API,
                            params={"offset": 0, "limit": 40, "query": query,
                                    "sort_by": "created_at:desc"},
                            timeout=aiohttp.ClientTimeout(total=30),
                            proxy=PROXY_URL,
                        ) as r:
                            r.raise_for_status()
                            data = (await r.json()).get("data", [])
                    except Exception as e:
                        log.warning("OLX xato (%s): %s", query, e)
                        if "403" in str(e):
                            blocked = True
                        continue
                    boot = not q("SELECT 1 FROM queries WHERE query=?", query)
                    if boot:
                        q("INSERT INTO queries VALUES(?)", query)
                    now = int(time.time())
                    for o in data:
                        # yangi so'z birinchi marta qidirilganda eski e'lonlar "eski" deb belgilanadi
                        q("INSERT OR IGNORE INTO offers VALUES(?,?,?)",
                          o["id"], json.dumps(o, ensure_ascii=False), 0 if boot else now)
                    await asyncio.sleep(1)
                q("DELETE FROM offers WHERE first_seen>0 AND first_seen<?",
                  int(time.time()) - 30 * 86400)
                if blocked:
                    log.error("OLX 403 qaytaryapti (IP bloklangan). PROXY_URL ulang yoki botni "
                              "boshqa serverda ishga tushiring. 60 soniya kutaman...")
                    await asyncio.sleep(60)
            except Exception as e:
                log.exception("poller: %s", e)
            await asyncio.sleep(CHECK_EVERY)


async def deliverer(bot):
    while True:
        try:
            now = int(time.time())
            users = [u for u in q("SELECT * FROM users WHERE paused=0") if is_active(u)]
            for u in users:
                if u["id"] in ADMIN_IDS or u["plan"] not in PLANS:
                    delay = 0   # adminlarga kechikishsiz
                else:
                    delay = PLANS[u["plan"]]["delay"]
                fl = q("SELECT * FROM filters WHERE user_id=? AND active=1", u["id"])
                if not fl:
                    continue
                rows = q(
                    "SELECT * FROM offers WHERE first_seen>? AND first_seen<=? "
                    "AND id NOT IN (SELECT offer_id FROM delivered WHERE user_id=?) "
                    "ORDER BY first_seen LIMIT 10",
                    now - 3600, now - delay, u["id"])
                for row in rows:
                    o = json.loads(row["data"])
                    q("INSERT OR IGNORE INTO delivered VALUES(?,?)", u["id"], row["id"])
                    if any(matches(o, f) and row["first_seen"] >= f["created"] for f in fl):
                        await send_offer(bot, u, o)
                        await asyncio.sleep(0.5)

            # obunasi tugaganlarga xabar
            for u in q("SELECT * FROM users WHERE plan IS NOT NULL AND expires<=? AND notified=0", now):
                q("UPDATE users SET notified=1 WHERE id=?", u["id"])
                try:
                    await bot.send_message(u["id"], t(u["lang"], "expired"))
                except Exception:
                    pass
        except Exception as e:
            log.exception("deliverer: %s", e)
        await asyncio.sleep(3)


# ============================ KANALGA YUBORISH ============================
def offer_age_min(o):
    """E'lon qo'yilganiga necha daqiqa bo'lganini qaytaradi (bilib bo'lmasa None)."""
    raw = o.get("created_time")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return (time.time() - dt.timestamp()) / 60
    except Exception:
        return None


def is_phone_offer(o):
    """Faqat yangi va sara iPhone e'lonlarini o'tkazadi."""
    title = o.get("title", "").lower()
    text = title + " " + (o.get("description") or "").lower()
    if not any(k in text for k in ("iphone", "айфон", "ayfon")):
        return False

    # 1) faqat yangi e'lon (eski yoki yangilab qo'yilganlar o'tmaydi)
    age = offer_age_min(o)
    if age is None or age > CHANNEL_MAX_AGE_MIN:
        return False

    # 2) hudud (faqat Toshkent)
    addr = address(o).lower()
    if CHANNEL_REGIONS and not any(x in addr for x in CHANNEL_REGIONS):
        return False
    if any(x in addr for x in CHANNEL_REGION_EXCLUDE):
        return False

    # 3) sifat shartlari
    if CHANNEL_REQUIRE_PHOTO and not photos(o):
        return False
    val, cur, _ = parse_price(o)
    if CHANNEL_REQUIRE_PRICE and val is None:
        return False
    if val is not None and val < CHANNEL_MIN_PRICE.get(cur, 0):
        return False
    return True


async def channel_poster(bot):
    """OLX dagi har bir yangi iPhone e'lonini kanalga yuboradi."""
    while True:
        try:
            now = int(time.time())
            rows = q(
                "SELECT * FROM offers WHERE first_seen>? "
                "AND id NOT IN (SELECT offer_id FROM channel_sent) "
                "ORDER BY first_seen LIMIT 10",
                now - 3600)
            for row in rows:
                q("INSERT OR IGNORE INTO channel_sent VALUES(?)", row["id"])
                o = json.loads(row["data"])
                if not is_phone_offer(o):
                    continue
                caption = build_caption(o, "uz")
                kb = InlineKeyboardBuilder()
                kb.row(InlineKeyboardButton(text="🔗 OLX'da ochish", url=o.get("url")))
                ph = photos(o)
                try:
                    if ph:
                        await bot.send_photo(CHANNEL_ID, ph[0], caption=caption,
                                             reply_markup=kb.as_markup())
                    else:
                        raise ValueError("no photo")
                except Exception:
                    try:
                        await bot.send_message(CHANNEL_ID, caption,
                                               reply_markup=kb.as_markup())
                    except Exception as e:
                        log.warning("channel send fail: %s", e)
                await asyncio.sleep(3)   # Telegram limitiga tushmaslik uchun
        except Exception as e:
            log.exception("channel_poster: %s", e)
        await asyncio.sleep(5)


# ============================ HANDLERLAR ============================
r = Router()


class NF(StatesGroup):
    query = State()
    currency = State()
    pmin = State()
    pmax = State()
    region = State()


async def to_menu(m: Message, lang, text):
    u = get_user(m.chat.id)
    await m.answer(text, reply_markup=main_kb(lang, bool(u and u["paused"])))


@r.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    u, is_new = ensure_user(m.from_user)
    if is_new:
        await m.answer(t("uz", "pick_lang"), reply_markup=lang_kb())
    else:
        await to_menu(m, u["lang"], t(u["lang"], "welcome"))


@r.message(B("b_lang"))
async def lang_btn(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(t("uz", "pick_lang"), reply_markup=lang_kb())


@r.callback_query(F.data.startswith("lang:"))
async def lang_cb(c: CallbackQuery):
    lang = c.data.split(":")[1]
    ensure_user(c.from_user)
    q("UPDATE users SET lang=? WHERE id=?", lang, c.from_user.id)
    await c.message.delete()
    u = get_user(c.from_user.id)
    await c.message.answer(t(lang, "welcome"), reply_markup=main_kb(lang, bool(u["paused"])))
    await c.answer(t(lang, "lang_set"))


# ---------- Obuna ----------
@r.message(B("b_sub"))
async def sub_btn(m: Message, state: FSMContext):
    await state.clear()
    u, _ = ensure_user(m.from_user)
    lang = u["lang"]
    text = sub_text(lang)
    if BANNER:
        photo = FSInputFile(BANNER) if os.path.exists(BANNER) else BANNER
        await m.answer_photo(photo)
    await m.answer(text, reply_markup=sub_kb(lang), link_preview_options=NO_PREVIEW)


@r.callback_query(F.data == "sub:rules")
async def sub_rules(c: CallbackQuery):
    u = get_user(c.from_user.id)
    await c.message.answer(t(u["lang"], "rules"))
    await c.answer()


@r.callback_query(F.data == "sub:status")
async def sub_status(c: CallbackQuery):
    u = get_user(c.from_user.id)
    await c.message.answer(status_text(u, u["lang"]))
    await c.answer()


@r.callback_query(F.data == "pay:start")
async def pay_start(c: CallbackQuery):
    u = get_user(c.from_user.id)
    lang = u["lang"]
    kb = InlineKeyboardBuilder()
    for key, p in PLANS.items():
        kb.row(InlineKeyboardButton(
            text=f"{EMOJI[p['icon']][0]} {t(lang, 'pn_' + key)} — {money(p['price'])}",
            callback_data=f"pay:plan:{key}"))
    await c.message.answer(t(lang, "pay_choose"), reply_markup=kb.as_markup())
    await c.answer()


@r.callback_query(F.data.startswith("pay:plan:"))
async def pay_plan(c: CallbackQuery, bot: Bot):
    plan = c.data.split(":")[2]
    u = get_user(c.from_user.id)
    lang = u["lang"]
    uname = f"@{u['username']}" if u["username"] else html.escape(u["name"] or "")
    for admin in ADMIN_IDS:
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm:ok:{u['id']}:{plan}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm:no:{u['id']}"),
        )
        try:
            await bot.send_message(
                admin,
                t("uz", "pay_admin", user=uname, uid=u["id"],
                  plan=t("uz", "pn_" + plan), price=money(PLANS[plan]["price"])),
                reply_markup=kb.as_markup())
        except Exception as e:
            log.warning("admin notify fail: %s", e)
    await c.message.edit_text(t(lang, "pay_sent"))
    await c.answer()


@r.callback_query(F.data.startswith("adm:"))
async def admin_decide(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo'q", show_alert=True)
    parts = c.data.split(":")
    uid = int(parts[2])
    u = get_user(uid)
    if not u:
        return await c.answer("Foydalanuvchi topilmadi", show_alert=True)
    if parts[1] == "ok":
        plan = parts[3]
        exp = activate(uid, plan, SUB_DAYS)
        await bot.send_message(uid, t(u["lang"], "approved", plan=t(u["lang"], "pn_" + plan),
                                      days=SUB_DAYS, date=fmt_date(exp)))
        await c.message.edit_text(c.message.html_text + "\n\n✅ Tasdiqlandi")
    else:
        await bot.send_message(uid, t(u["lang"], "rejected"))
        await c.message.edit_text(c.message.html_text + "\n\n❌ Rad etildi")
    await c.answer()


# ---------- Filtrlar ----------
def filter_summary(f, lang):
    if f["pmin"] is None and f["pmax"] is None:
        price = t(lang, "any_price")
    else:
        lo = money(f["pmin"]) if f["pmin"] is not None else "0"
        hi = money(f["pmax"]) if f["pmax"] is not None else "∞"
        price = f"{lo} – {hi} {f['currency']}"
    region = html.escape(f["region"]) if f["region"] else t(lang, "any_region")
    return (f"{em('phone')} <b>{html.escape(f['query'])}</b>\n"
            f"{em('money')} {price}\n{em('pin')} {region}")


def render_filters(uid, lang):
    fl = q("SELECT * FROM filters WHERE user_id=? ORDER BY id", uid)
    if not fl:
        return t(lang, "flt_empty"), None
    text = t(lang, "flt_head")
    kb = InlineKeyboardBuilder()
    for i, f in enumerate(fl, 1):
        state = "✅" if f["active"] else "⏸"
        text += f"<b>{i}.</b> {state}\n{filter_summary(f, lang)}\n\n"
        kb.row(
            InlineKeyboardButton(text=f"{state} #{i} {f['query'][:20]}", callback_data=f"fl:t:{f['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fl:d:{f['id']}"),
        )
    return text, kb.as_markup()


@r.message(B("b_filters"))
async def filters_btn(m: Message, state: FSMContext):
    await state.clear()
    u, _ = ensure_user(m.from_user)
    text, kb = render_filters(u["id"], u["lang"])
    await m.answer(text, reply_markup=kb)


@r.callback_query(F.data.startswith("fl:"))
async def filter_action(c: CallbackQuery):
    _, act, fid = c.data.split(":")
    u = get_user(c.from_user.id)
    f = q("SELECT * FROM filters WHERE id=? AND user_id=?", int(fid), u["id"])
    if f:
        if act == "t":
            q("UPDATE filters SET active=1-active, created=? WHERE id=?", int(time.time()), int(fid))
        else:
            q("DELETE FROM filters WHERE id=?", int(fid))
    text, kb = render_filters(u["id"], u["lang"])
    await c.message.edit_text(text, reply_markup=kb)
    await c.answer()


@r.message(B("b_newf"))
async def newf(m: Message, state: FSMContext):
    await state.clear()
    u, _ = ensure_user(m.from_user)
    n = q("SELECT COUNT(*) AS n FROM filters WHERE user_id=?", u["id"])[0]["n"]
    if n >= MAX_FILTERS:
        return await m.answer(t(u["lang"], "nf_limit", n=MAX_FILTERS))
    await state.set_state(NF.query)
    await m.answer(t(u["lang"], "nf_query"))


@r.message(NF.query, F.text)
async def nf_query(m: Message, state: FSMContext):
    u = get_user(m.from_user.id)
    await state.update_data(query=m.text.strip()[:60])
    kb = InlineKeyboardBuilder()
    kb.button(text="UZS", callback_data="cur:UZS")
    kb.button(text="USD", callback_data="cur:USD")
    kb.button(text=b(u["lang"], "skip"), callback_data="cur:-")
    kb.adjust(2, 1)
    await state.set_state(NF.currency)
    await m.answer(t(u["lang"], "nf_cur"), reply_markup=kb.as_markup())


@r.callback_query(NF.currency, F.data.startswith("cur:"))
async def nf_cur(c: CallbackQuery, state: FSMContext):
    lang = get_user(c.from_user.id)["lang"]
    cur = c.data.split(":")[1]
    await c.message.edit_reply_markup(reply_markup=None)
    if cur == "-":
        await state.update_data(currency=None, pmin=None, pmax=None)
        await state.set_state(NF.region)
        await c.message.answer(t(lang, "nf_region"))
    else:
        await state.update_data(currency=cur)
        await state.set_state(NF.pmin)
        await c.message.answer(t(lang, "nf_min"))
    await c.answer()


def num(s):
    digits = re.sub(r"\D", "", s or "")
    return float(digits) if digits and float(digits) > 0 else None


@r.message(NF.pmin, F.text)
async def nf_min(m: Message, state: FSMContext):
    await state.update_data(pmin=num(m.text))
    await state.set_state(NF.pmax)
    await m.answer(t(get_user(m.from_user.id)["lang"], "nf_max"))


@r.message(NF.pmax, F.text)
async def nf_max(m: Message, state: FSMContext):
    await state.update_data(pmax=num(m.text))
    await state.set_state(NF.region)
    await m.answer(t(get_user(m.from_user.id)["lang"], "nf_region"))


@r.message(NF.region, F.text)
async def nf_region(m: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    u = get_user(m.from_user.id)
    region = m.text.strip()
    region = None if region in ("-", "") else region[:40]
    q("INSERT INTO filters(user_id, query, currency, pmin, pmax, region, created) "
      "VALUES(?,?,?,?,?,?,?)",
      u["id"], d["query"], d.get("currency"), d.get("pmin"), d.get("pmax"),
      region, int(time.time()))
    f = q("SELECT * FROM filters WHERE user_id=? ORDER BY id DESC LIMIT 1", u["id"])[0]
    text = t(u["lang"], "nf_done", summary=filter_summary(f, u["lang"]))
    if not is_active(u):
        text += t(u["lang"], "nf_nosub")
    await to_menu(m, u["lang"], text)


# ---------- Saralangan ----------
@r.callback_query(F.data.startswith("fav:"))
async def fav_save(c: CallbackQuery):
    oid = int(c.data.split(":")[1])
    u = get_user(c.from_user.id)
    row = q("SELECT data FROM offers WHERE id=?", oid)
    if row:
        o = json.loads(row[0]["data"])
        _, _, label = parse_price(o)
        q("INSERT OR REPLACE INTO favorites VALUES(?,?,?,?,?)",
          u["id"], oid, o.get("title", ""), o.get("url", ""), label or "")
    await c.answer(t(u["lang"], "fav_saved"))


def render_favs(uid, lang):
    fl = q("SELECT * FROM favorites WHERE user_id=? ORDER BY rowid DESC LIMIT 20", uid)
    if not fl:
        return t(lang, "fav_empty"), None
    text = t(lang, "fav_head")
    kb = InlineKeyboardBuilder()
    for i, f in enumerate(fl, 1):
        title = html.escape(f["title"])
        text += (f"<b>{i}.</b> <a href=\"{f['url']}\">{title}</a>\n"
                 f"{em('money')} {html.escape(f['price'] or '—')}\n\n")
        kb.row(InlineKeyboardButton(text=f"🗑 #{i}", callback_data=f"fd:{f['offer_id']}"))
    return text, kb.as_markup()


@r.message(B("b_fav"))
async def fav_btn(m: Message, state: FSMContext):
    await state.clear()
    u, _ = ensure_user(m.from_user)
    text, kb = render_favs(u["id"], u["lang"])
    await m.answer(text, reply_markup=kb, link_preview_options=NO_PREVIEW)


@r.callback_query(F.data.startswith("fd:"))
async def fav_del(c: CallbackQuery):
    u = get_user(c.from_user.id)
    q("DELETE FROM favorites WHERE user_id=? AND offer_id=?", u["id"], int(c.data.split(":")[1]))
    text, kb = render_favs(u["id"], u["lang"])
    await c.message.edit_text(text, reply_markup=kb, link_preview_options=NO_PREVIEW)
    await c.answer(t(u["lang"], "fav_removed"))


# ---------- Statistika / Pauza / Yordam ----------
@r.message(B("b_stats"))
async def stats_btn(m: Message, state: FSMContext):
    await state.clear()
    u, _ = ensure_user(m.from_user)
    lang = u["lang"]
    nf = q("SELECT COUNT(*) AS n FROM filters WHERE user_id=? AND active=1", u["id"])[0]["n"]
    nv = q("SELECT COUNT(*) AS n FROM favorites WHERE user_id=?", u["id"])[0]["n"]
    if u["id"] in ADMIN_IDS:
        sub = "∞ (admin)"
    elif is_active(u):
        sub = t(lang, "sub_days", days=max(0, int((u["expires"] - time.time()) // 86400)))
    else:
        sub = t(lang, "sub_none")
    await m.answer(t(lang, "stats", sent=u["sent"], filters=nf, favs=nv, sub=sub))


@r.message(B("b_pause", "b_resume"))
async def pause_btn(m: Message, state: FSMContext):
    await state.clear()
    u, _ = ensure_user(m.from_user)
    new = 0 if u["paused"] else 1
    q("UPDATE users SET paused=? WHERE id=?", new, u["id"])
    await m.answer(t(u["lang"], "paused" if new else "resumed"),
                   reply_markup=main_kb(u["lang"], bool(new)))


@r.message(B("b_help"))
async def help_btn(m: Message, state: FSMContext):
    await state.clear()
    u, _ = ensure_user(m.from_user)
    await m.answer(t(u["lang"], "help"))


# ---------- Admin ----------
@r.message(Command("grant"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_grant(m: Message, bot: Bot):
    """/grant <user_id> <p0|p1|p3> <kun>"""
    try:
        _, uid, plan, days = m.text.split()
        uid, days = int(uid), int(days)
        assert plan in PLANS and get_user(uid)
    except Exception:
        return await m.answer("Foydalanish: /grant user_id p0|p1|p3 kun")
    exp = activate(uid, plan, days)
    u = get_user(uid)
    await bot.send_message(uid, t(u["lang"], "approved", plan=t(u["lang"], "pn_" + plan),
                                  days=days, date=fmt_date(exp)))
    await m.answer(f"✅ {uid} → {plan}, {days} kun, {fmt_date(exp)} gacha")


@r.message(Command("trial"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_trial(m: Message, bot: Bot):
    """/trial <user_id> - 1 kunlik bepul sinov"""
    try:
        uid = int(m.text.split()[1])
        u = get_user(uid)
        assert u
    except Exception:
        return await m.answer("Foydalanish: /trial user_id")
    if u["trial_used"]:
        return await m.answer("Bu foydalanuvchi sinovdan foydalangan.")
    activate(uid, "p0", 1)
    q("UPDATE users SET trial_used=1 WHERE id=?", uid)
    await bot.send_message(uid, t(u["lang"], "trial_on"))
    await m.answer(f"🎁 {uid} ga 1 kunlik sinov ochildi.")


@r.message(Command("astats"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_astats(m: Message):
    now = int(time.time())
    total = q("SELECT COUNT(*) AS n FROM users")[0]["n"]
    act = q("SELECT COUNT(*) AS n FROM users WHERE plan IS NOT NULL AND expires>?", now)[0]["n"]
    sent = q("SELECT COALESCE(SUM(sent),0) AS n FROM users")[0]["n"]
    ch = q("SELECT COUNT(*) AS n FROM channel_sent")[0]["n"]
    await m.answer(f"👥 Jami: {total}\n💎 Obunali: {act}\n📨 Yuborilgan e'lonlar: {sent}\n"
                   f"📢 Kanal uchun ko'rilgan e'lonlar: {ch}")


@r.message(Command("broadcast"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_broadcast(m: Message, bot: Bot):
    text = m.text.partition(" ")[2].strip()
    if not text:
        return await m.answer("Foydalanish: /broadcast matn")
    ok = 0
    for u in q("SELECT id FROM users"):
        try:
            await bot.send_message(u["id"], text)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await m.answer(f"📨 Yuborildi: {ok}")


@r.message(F.from_user.id.in_(ADMIN_IDS), StateFilter(None), F.entities)
async def emoji_id_helper(m: Message):
    """Admin botga premium emoji yuborsa, uning ID sini qaytaradi."""
    ids = [e.custom_emoji_id for e in m.entities if e.type == "custom_emoji"]
    if ids:
        await m.answer("Premium emoji ID:\n" + "\n".join(f"<code>{i}</code>" for i in ids))


# ============================ ISHGA TUSHIRISH ============================
async def start_web():
    """Render Web Service port kutadi. PORT bo'lsa kichik health-server ishga tushadi."""
    port = os.getenv("PORT")
    if not port:
        return None

    async def ok(_):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(port)).start()
    log.info("Health server port %s da ishlayapti", port)
    return runner


async def main():
    if not re.fullmatch(r"\d{6,}:[A-Za-z0-9_-]{30,}", BOT_TOKEN):
        log.error("BOT_TOKEN noto'g'ri yoki bo'sh. Render > Environment ga BotFather tokenini "
                  "tirnoqsiz va bo'sh joysiz yozing.")
        sys.exit(1)

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(r)

    web_runner = await start_web()
    await bot.delete_webhook(drop_pending_updates=True)

    tasks = [asyncio.create_task(poller()), asyncio.create_task(deliverer(bot))]
    if CHANNEL_ENABLED:
        tasks.append(asyncio.create_task(channel_poster(bot)))
    log.info("Bot ishga tushdi. DB: %s", DB_PATH)
    try:
        await dp.start_polling(bot)
    finally:
        for task in tasks:
            task.cancel()
        if web_runner:
            await web_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())