"""
Telegram Sticker / Emoji Pack Bot  +  Номерные знаки
Токен берётся из переменной окружения BOT_TOKEN.
"""

import io
import logging
import os
import random
import re
import string

from PIL import Image, ImageDraw, ImageFont

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputSticker,
    Update,
)
from telegram.constants import StickerFormat, StickerType
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Состояния ─────────────────────────────────────────────────────────────────
(
    MAIN_MENU,        # 0
    CHOOSE_TYPE,      # 1
    PACK_NAME,        # 2
    PACK_LINK,        # 3
    ADDING_STICKER,   # 4
    WAITING_EMOJI,    # 5
    PACK_SELECTED,    # 6
    ADD_STICKER_FILE, # 7
    ADD_STICKER_EMOJI,# 8
    DELETE_STICKER,   # 9
    CHANGE_ICON,      # 10
    PLATE_COUNTRY,    # 11
    PLATE_REGION,     # 12
    PLATE_INPUT,      # 13
) = range(14)

MAX_STICKER_BYTES = 500 * 1024
MAX_INPUT_BYTES   = 10 * 1024 * 1024

FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

# ── Данные регионов ───────────────────────────────────────────────────────────

REGIONS = {
    "RU": {
        "01":"Респ. Адыгея","101":"Респ. Адыгея",
        "02":"Респ. Башкортостан","102":"Респ. Башкортостан","702":"Респ. Башкортостан",
        "03":"Респ. Бурятия","103":"Респ. Бурятия",
        "04":"Респ. Алтай",
        "05":"Респ. Дагестан","105":"Респ. Дагестан",
        "06":"Респ. Ингушетия",
        "07":"Кабардино-Балкарская Респ.",
        "08":"Респ. Калмыкия",
        "09":"Карачаево-Черкесская Респ.",
        "10":"Респ. Карелия",
        "11":"Респ. Коми",
        "12":"Респ. Марий Эл",
        "13":"Респ. Мордовия","113":"Респ. Мордовия",
        "14":"Респ. Саха (Якутия)",
        "15":"Респ. Северная Осетия",
        "16":"Респ. Татарстан","116":"Респ. Татарстан","716":"Респ. Татарстан",
        "17":"Респ. Тыва",
        "18":"Удмуртская Респ.",
        "19":"Респ. Хакасия",
        "21":"Чувашская Респ.","121":"Чувашская Респ.",
        "22":"Алтайский край","122":"Алтайский край",
        "23":"Краснодарский край","93":"Краснодарский край","123":"Краснодарский край","193":"Краснодарский край",
        "24":"Красноярский край","84":"Красноярский край","88":"Красноярский край","124":"Красноярский край",
        "25":"Приморский край","125":"Приморский край",
        "26":"Ставропольский край","126":"Ставропольский край",
        "27":"Хабаровский край",
        "28":"Амурская обл.",
        "29":"Архангельская обл.",
        "30":"Астраханская обл.",
        "31":"Белгородская обл.",
        "32":"Брянская обл.",
        "33":"Владимирская обл.",
        "34":"Волгоградская обл.","134":"Волгоградская обл.",
        "35":"Вологодская обл.",
        "36":"Воронежская обл.","136":"Воронежская обл.",
        "37":"Ивановская обл.",
        "38":"Иркутская обл.","138":"Иркутская обл.",
        "39":"Калининградская обл.","91":"Калининградская обл.",
        "40":"Калужская обл.",
        "41":"Камчатский край",
        "42":"Кемеровская обл.","142":"Кемеровская обл.",
        "43":"Кировская обл.",
        "44":"Костромская обл.",
        "45":"Курганская обл.",
        "46":"Курская обл.",
        "47":"Ленинградская обл.","147":"Ленинградская обл.",
        "48":"Липецкая обл.",
        "49":"Магаданская обл.",
        "50":"Московская обл.","90":"Московская обл.","150":"Московская обл.","190":"Московская обл.",
        "250":"Московская обл.","550":"Московская обл.","750":"Московская обл.","790":"Московская обл.",
        "51":"Мурманская обл.",
        "52":"Нижегородская обл.","152":"Нижегородская обл.","252":"Нижегородская обл.",
        "53":"Новгородская обл.",
        "54":"Новосибирская обл.","154":"Новосибирская обл.",
        "55":"Омская обл.","155":"Омская обл.",
        "56":"Оренбургская обл.","156":"Оренбургская обл.",
        "57":"Орловская обл.",
        "58":"Пензенская обл.",
        "59":"Пермский край","81":"Пермский край","159":"Пермский край",
        "60":"Псковская обл.",
        "61":"Ростовская обл.","161":"Ростовская обл.","761":"Ростовская обл.",
        "62":"Рязанская обл.",
        "63":"Самарская обл.","163":"Самарская обл.","763":"Самарская обл.",
        "64":"Саратовская обл.","164":"Саратовская обл.",
        "65":"Сахалинская обл.",
        "66":"Свердловская обл.","96":"Свердловская обл.","196":"Свердловская обл.",
        "67":"Смоленская обл.",
        "68":"Тамбовская обл.",
        "69":"Тверская обл.",
        "70":"Томская обл.",
        "71":"Тульская обл.",
        "72":"Тюменская обл.","172":"Тюменская обл.",
        "73":"Ульяновская обл.",
        "74":"Челябинская обл.","174":"Челябинская обл.","774":"Челябинская обл.",
        "75":"Забайкальский край","80":"Забайкальский край",
        "76":"Ярославская обл.",
        "77":"г. Москва","97":"г. Москва","99":"г. Москва","177":"г. Москва",
        "197":"г. Москва","199":"г. Москва","777":"г. Москва","797":"г. Москва",
        "799":"г. Москва","977":"г. Москва",
        "78":"г. Санкт-Петербург","98":"г. Санкт-Петербург","178":"г. Санкт-Петербург","198":"г. Санкт-Петербург",
        "79":"Еврейская авт. обл.",
        "82":"Респ. Крым",
        "83":"Ненецкий авт. окр.",
        "85":"Запорожская обл.","185":"Запорожская обл.",
        "86":"Ханты-Мансийский авт. окр.","186":"Ханты-Мансийский авт. окр.",
        "87":"Чукотский авт. окр.",
        "89":"Ямало-Ненецкий авт. окр.",
        "92":"г. Севастополь",
        "95":"Чеченская Респ.",
        "180":"Донецкая Нар. Респ.",
        "181":"Луганская Нар. Респ.",
        "184":"Херсонская обл.",
    },
    "UA": {
        "AA":"г. Киев","КА":"г. Киев",
        "AI":"Киевская обл.","КI":"Киевская обл.",
        "BC":"Львовская обл.","КС":"Львовская обл.",
        "AC":"Волынская обл. (Луцк)",
        "AO":"Закарпатская обл. (Ужгород)","КО":"Закарпатская обл. (Ужгород)",
        "AT":"Ивано-Франковская обл.","КТ":"Ивано-Франковская обл.",
        "AM":"Житомирская обл.","КМ":"Житомирская обл.",
        "BK":"Ровненская обл.","НК":"Ровненская обл.",
        "BO":"Тернопольская обл.","НО":"Тернопольская обл.",
        "BX":"Хмельницкая обл.","НХ":"Хмельницкая обл.",
        "CE":"Черновицкая обл.","ІЕ":"Черновицкая обл.",
        "BA":"Кировоградская обл. (Кропивницкий)","НА":"Кировоградская обл. (Кропивницкий)",
        "BI":"Полтавская обл.","НI":"Полтавская обл.",
        "CA":"Черкасская обл.","IA":"Черкасская обл.",
        "CB":"Черниговская обл.","IB":"Черниговская обл.",
        "BM":"Сумская обл.","НМ":"Сумская обл.",
        "AB":"Винницкая обл.","КВ":"Винницкая обл.",
        "AX":"Харьковская обл.","КХ":"Харьковская обл.",
        "AE":"Днепропетровская обл.","КЕ":"Днепропетровская обл.",
        "AH":"Донецкая обл.","КН":"Донецкая обл.",
        "BB":"Луганская обл.","НВ":"Луганская обл.",
        "BH":"Николаевская обл.","НН":"Николаевская обл.",
        "BT":"Херсонская обл.","НТ":"Херсонская обл.",
        "BВ":"Запорожская обл.","НЗ":"Запорожская обл.",
        "BI":"Полтавская обл.","НI":"Полтавская обл.",
        "ВА":"Одесская обл.","ОА":"Одесская обл.",
    },
    "BY": {
        "1":"Брестская область",
        "2":"Витебская область",
        "3":"Гомельская область",
        "4":"Гродненская область",
        "5":"Минская область",
        "6":"Могилёвская область",
        "7":"г. Минск",
    },
    "KZ": {
        "01":"г. Астана","02":"г. Алматы",
        "03":"Акмолинская обл.","04":"Актюбинская обл.",
        "05":"Алматинская обл.","06":"Атырауская обл.",
        "07":"Западно-Казахстанская обл.","08":"Жамбылская обл.",
        "09":"Карагандинская обл.","10":"Костанайская обл.",
        "11":"Кызылординская обл.","12":"Мангистауская обл.",
        "13":"Туркестанская обл.","14":"Павлодарская обл.",
        "15":"Северо-Казахстанская обл.","16":"Восточно-Казахстанская обл.",
        "17":"г. Шымкент","18":"Абайская обл.",
        "19":"Жетысуская обл.","20":"Улытауская обл.",
    },
}

COUNTRY_NAMES = {"RU": "🇷🇺 Россия", "UA": "🇺🇦 Украина", "BY": "🇧🇾 Беларусь", "KZ": "🇰🇿 Казахстан"}

PLATE_SCHEMES = {
    "RU": (
        "Схема: <b>Л ЦЦЦ ЛЛ</b>\n"
        "Л = буква: А В Е К М Н О Р С Т У Х\n"
        "Ц = цифра: 0–9\n\n"
        "Пример: <code>В 131 ОР</code>"
    ),
    "UA": (
        "Схема: <b>ЦЦЦЦ ЛЛ</b>\n"
        "Ц = цифра: 0–9\n"
        "Л = буква: А–Я (кириллица)\n\n"
        "Пример: <code>1234 АВ</code>"
    ),
    "BY": (
        "Схема: <b>ЦЦЦЦ ЛЛ</b>\n"
        "Ц = цифра: 0–9\n"
        "Л = буква: А–Я (кириллица)\n\n"
        "Пример: <code>1234 АВ</code>"
    ),
    "KZ": (
        "Схема: <b>ЦЦЦ ЛЛЛ</b>\n"
        "Ц = цифра: 0–9\n"
        "Л = латинская буква: A–Z\n\n"
        "Пример: <code>001 ABС</code>"
    ),
}

REGIONS_PER_PAGE = 24   # 6 рядов × 4 кнопки

# ── Генерация изображения номерного знака ─────────────────────────────────────

def _dot_grid(draw, w, h):
    for x in range(0, w + 1, 20):
        for y in range(0, h + 1, 20):
            draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill="#d0d0d0")


def _ru_flag(draw, fx, fy, fw=32, fh=22):
    """Рисует флаг РФ в позиции fx, fy."""
    th = fh // 3
    draw.rectangle([fx, fy, fx + fw, fy + th], fill="white", outline="#cccccc", width=1)
    draw.rectangle([fx, fy + th, fx + fw, fy + th * 2], fill="#003DA5")
    draw.rectangle([fx, fy + th * 2, fx + fw, fy + fh], fill="#CC0000")


def _ua_flag(draw, fx, fy, fw=32, fh=22):
    hh = fh // 2
    draw.rectangle([fx, fy, fx + fw, fy + hh], fill="#005BBB")
    draw.rectangle([fx, fy + hh, fx + fw, fy + fh], fill="#FFD500")


def _by_flag(draw, fx, fy, fw=32, fh=22):
    th = fh // 3
    draw.rectangle([fx, fy, fx + fw, fy + th], fill="#CF101A")
    draw.rectangle([fx, fy + th, fx + fw, fy + th * 2], fill="#009A44")
    draw.rectangle([fx, fy + th * 2, fx + fw, fy + fh], fill="#CF101A")


def _kz_flag(draw, fx, fy, fw=32, fh=22):
    draw.rectangle([fx, fy, fx + fw, fy + fh], fill="#00AFCA")
    fnt = ImageFont.truetype(FONT_BOLD, 10)
    draw.text((fx + fw // 2, fy + fh // 2), "☀", fill="#FFD700", font=fnt, anchor="mm")


def generate_plate_image(country: str, chars: str, region: str, region_name: str) -> bytes:
    W, H = 580, 290
    img  = Image.new("RGB", (W, H), "#efefef")
    draw = ImageDraw.Draw(img)
    _dot_grid(draw, W, H)

    fnt_hdr = ImageFont.truetype(FONT_REG, 13)
    fnt_ftr = ImageFont.truetype(FONT_REG, 12)
    draw.text((W // 2, 22), "HOMEPA  —  CARDROP", fill="#aaaaaa", font=fnt_hdr, anchor="mm")

    cx, cy = W // 2, H // 2

    if country == "RU":
        pw, ph = 365, 118
        px, py = cx - pw // 2, cy - ph // 2
        # Shadow
        draw.rounded_rectangle([px + 5, py + 5, px + pw + 5, py + ph + 5], radius=10, fill="#b8b8b8")
        # Plate body
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=10, fill="white",
                                outline="#111111", width=4)
        # Vertical divider
        rdx = px + pw - 84
        draw.line([(rdx, py + 6), (rdx, py + ph - 6)], fill="#111111", width=3)
        # Main characters
        fnt_pl = ImageFont.truetype(FONT_BOLD, 66)
        draw.text((px + (pw - 84) // 2, py + ph // 2), chars,
                  fill="#111111", font=fnt_pl, anchor="mm")
        # Region code
        fnt_r = ImageFont.truetype(FONT_BOLD, 20)
        draw.text((px + pw - 41, py + 30), region, fill="#111111", font=fnt_r, anchor="mm")
        # Flag
        fx = px + pw - 76; fy = py + ph - 42
        _ru_flag(draw, fx, fy)
        fnt_s = ImageFont.truetype(FONT_BOLD, 11)
        draw.text((fx + 35, fy + 11), "RUS", fill="#111111", font=fnt_s, anchor="lm")

    elif country == "UA":
        pw, ph = 380, 118
        px, py = cx - pw // 2, cy - ph // 2
        draw.rounded_rectangle([px + 5, py + 5, px + pw + 5, py + ph + 5], radius=10, fill="#b8b8b8")
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=10, fill="white",
                                outline="#111111", width=4)
        # Blue left strip
        strip_w = 52
        draw.rounded_rectangle([px, py, px + strip_w, py + ph], radius=10, fill="#003DA5",
                                outline="#111111", width=0)
        draw.rectangle([px + strip_w // 2, py, px + strip_w, py + ph], fill="#003DA5")
        draw.line([(px + strip_w, py + 4), (px + strip_w, py + ph - 4)], fill="#111111", width=3)
        # Flag inside strip
        _ua_flag(draw, px + 10, py + 18, fw=30, fh=20)
        fnt_code = ImageFont.truetype(FONT_BOLD, 14)
        draw.text((px + 26, py + 52), "UA", fill="white", font=fnt_code, anchor="mm")
        # Region + chars
        fnt_pl = ImageFont.truetype(FONT_BOLD, 54)
        body = f"{region}  {chars[:4]}  {chars[4:]}" if len(chars) >= 4 else chars
        draw.text((px + strip_w + (pw - strip_w) // 2, cy), body,
                  fill="#111111", font=fnt_pl, anchor="mm")

    elif country == "BY":
        pw, ph = 380, 118
        px, py = cx - pw // 2, cy - ph // 2
        draw.rounded_rectangle([px + 5, py + 5, px + pw + 5, py + ph + 5], radius=10, fill="#b8b8b8")
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=10, fill="white",
                                outline="#111111", width=4)
        strip_w = 52
        # Red-green left strip
        _by_flag(draw, px + 4, py + 8, fw=strip_w - 10, fh=ph - 16)
        draw.rounded_rectangle([px, py, px + strip_w, py + ph], radius=10, fill=None,
                                outline="#111111", width=0)
        draw.rectangle([px + strip_w // 2, py, px + strip_w, py + ph],
                       fill="white")
        draw.line([(px + strip_w, py + 4), (px + strip_w, py + ph - 4)], fill="#111111", width=3)
        fnt_code = ImageFont.truetype(FONT_BOLD, 12)
        draw.text((px + 26, py + ph - 20), "BY", fill="#111111", font=fnt_code, anchor="mm")
        # Main chars
        fnt_pl = ImageFont.truetype(FONT_BOLD, 54)
        body = f"{chars}  -{region}" if chars else chars
        draw.text((px + strip_w + (pw - strip_w) // 2, cy), body,
                  fill="#111111", font=fnt_pl, anchor="mm")

    elif country == "KZ":
        pw, ph = 365, 118
        px, py = cx - pw // 2, cy - ph // 2
        draw.rounded_rectangle([px + 5, py + 5, px + pw + 5, py + ph + 5], radius=10, fill="#b8b8b8")
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=10, fill="white",
                                outline="#111111", width=4)
        # Left blue strip
        strip_w = 48
        draw.rounded_rectangle([px, py, px + strip_w, py + ph], radius=10, fill="#00AFCA",
                                outline="#111111", width=0)
        draw.rectangle([px + strip_w // 2, py, px + strip_w, py + ph], fill="#00AFCA")
        draw.line([(px + strip_w, py + 4), (px + strip_w, py + ph - 4)], fill="#111111", width=3)
        fnt_code = ImageFont.truetype(FONT_BOLD, 11)
        draw.text((px + 24, py + ph // 2), "KZ", fill="white", font=fnt_code, anchor="mm")
        # Right region panel
        rdx = px + pw - 80
        draw.line([(rdx, py + 6), (rdx, py + ph - 6)], fill="#111111", width=3)
        fnt_r = ImageFont.truetype(FONT_BOLD, 20)
        draw.text((rdx + (pw - rdx - px) // 2 + px + pw // 2 - rdx // 2 - 8,
                   py + ph // 2), region,
                  fill="#111111", font=fnt_r, anchor="mm")
        draw.text((px + pw - 38, py + ph // 2), region, fill="#111111", font=fnt_r, anchor="mm")
        # Main chars
        fnt_pl = ImageFont.truetype(FONT_BOLD, 58)
        draw.text((px + strip_w + (rdx - px - strip_w) // 2, cy), chars,
                  fill="#111111", font=fnt_pl, anchor="mm")

    # Region name below plate
    fnt_rn = ImageFont.truetype(FONT_REG, 13)
    draw.text((W // 2, cy + 82), region_name, fill="#888888", font=fnt_rn, anchor="mm")

    draw.text((W // 2, H - 18), "@your_bot", fill="#aaaaaa", font=fnt_ftr, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ── Утилиты (стикеры) ─────────────────────────────────────────────────────────

def random_suffix(length: int = 10) -> str:
    first = random.choice(string.ascii_lowercase)
    rest  = "".join(random.choices(string.ascii_lowercase + string.digits, k=length - 1))
    return first + rest


def sanitize_suffix(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]", "", raw.lower())
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "s" + cleaned
    cleaned = cleaned[:64]
    if len(cleaned) < 5:
        cleaned = cleaned + random_suffix(5 - len(cleaned))
    return cleaned


def build_pack_name(bot_username: str, suffix: str) -> str:
    return f"{suffix}_by_{bot_username}"


def plural_sticker(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return "стикеров"
    r = n % 10
    if r == 1:      return "стикер"
    if 2 <= r <= 4: return "стикера"
    return "стикеров"


def pack_url(pack_name: str) -> str:
    return f"https://t.me/addstickers/{pack_name}"


def get_packs(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> list:
    return context.bot_data.setdefault(str(user_id), {}).setdefault("packs", [])


def back_btn(label: str = "◀️ Назад", data: str = "begin") -> list:
    return [InlineKeyboardButton(label, callback_data=data)]


def _friendly_tg_error(err: str) -> str:
    if "STICKERSET_INVALID" in err or "invalid" in err.lower():
        return "Недопустимое название пака. Попробуй другое."
    if "PEER_ID_INVALID" in err:
        return "Сначала напиши боту /start в личке Telegram."
    if "file is too big" in err.lower():
        return "Файл слишком большой даже после сжатия."
    if "STICKERS_TOO_MUCH" in err:
        return "В паке уже максимальное количество стикеров (120)."
    if "bot was blocked" in err.lower():
        return "Бот заблокирован. Разблокируй его и попробуй снова."
    return err


# ── Обработка изображений ─────────────────────────────────────────────────────

def process_image(raw_bytes: bytes, size: int, max_bytes: int = MAX_STICKER_BYTES) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - img.width) // 2, (size - img.height) // 2)
    canvas.paste(img, offset, img)
    for compress in range(1, 10):
        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True, compress_level=compress)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data
    scale = 0.9
    while len(data) > max_bytes and scale > 0.3:
        inner  = (int(size * scale), int(size * scale))
        resized = canvas.resize(inner, Image.LANCZOS)
        final  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        off    = ((size - inner[0]) // 2, (size - inner[1]) // 2)
        final.paste(resized, off, resized)
        buf = io.BytesIO()
        final.save(buf, format="PNG", optimize=True, compress_level=9)
        data = buf.getvalue()
        scale -= 0.1
    return data


def process_image_for_sticker(raw_bytes: bytes, pack_type: str = "sticker") -> bytes:
    return process_image(raw_bytes, 512 if pack_type == "sticker" else 100)


def process_image_for_thumbnail(raw_bytes: bytes) -> bytes:
    return process_image(raw_bytes, 100, max_bytes=32 * 1024)


async def get_sticker_data(bot, msg, pack_type: str = "sticker"):
    async def dl(file_id: str) -> bytes:
        f   = await bot.get_file(file_id)
        buf = io.BytesIO()
        await f.download_to_memory(buf)
        return buf.getvalue()

    if msg.sticker:
        s   = msg.sticker
        fmt = s.format if hasattr(s, "format") else StickerFormat.STATIC
        raw = await dl(s.file_id)
        return (process_image_for_sticker(raw, pack_type), fmt) if fmt == StickerFormat.STATIC else (raw, fmt)
    if msg.document:
        d    = msg.document
        mime = (d.mime_type or "").lower()
        name = (d.file_name or "").lower()
        if "webm" in mime or name.endswith(".webm"):
            return await dl(d.file_id), StickerFormat.VIDEO
        if "tgs" in mime or name.endswith(".tgs"):
            return await dl(d.file_id), StickerFormat.ANIMATED
        return process_image_for_sticker(await dl(d.file_id), pack_type), StickerFormat.STATIC
    if msg.photo:
        return process_image_for_sticker(await dl(msg.photo[-1].file_id), pack_type), StickerFormat.STATIC
    if msg.video:
        return await dl(msg.video.file_id), StickerFormat.VIDEO
    if msg.animation:
        return await dl(msg.animation.file_id), StickerFormat.VIDEO
    return None, None


# ── Главное меню ──────────────────────────────────────────────────────────────

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [
        [InlineKeyboardButton("🖼  Создать стикер-пак",      callback_data="create_sticker")],
        [InlineKeyboardButton("✨  Создать эмодзи-пак",       callback_data="create_emoji")],
        [InlineKeyboardButton("🚗  Создать номерной знак",    callback_data="create_plate")],
        [InlineKeyboardButton("📋  Мои паки",                 callback_data="list_packs")],
    ]
    text = (
        "👋 <b>Что хочешь создать?</b>\n\n"
        "• <b>Стикер-пак</b> — обычные стикеры\n"
        "• <b>Эмодзи-пак</b> — premium emoji\n"
        "• <b>Номерной знак</b> — красивое фото номера\n\n"
        "<i>Поддерживаются: фото, PNG, WEBP, WEBM, TGS</i>"
    )
    markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    return CHOOSE_TYPE


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    name = f"@{user.username}" if user.username else user.first_name
    kb   = [[InlineKeyboardButton("😎 Начать", callback_data="begin")]]
    await update.message.reply_text(
        f"Привет, {name}!\n\nСоздавай стикеры, premium emoji и номерные знаки 🚗",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return MAIN_MENU


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in (
        "new_pack_title", "new_pack_suffix", "new_pack_stickers",
        "creating_type", "selected_pack_index", "pending_data", "pending_fmt",
        "plate_country", "plate_region", "file_queue", "file_queue_done",
    ):
        context.user_data.pop(key, None)
    return await send_main_menu(update, context)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await menu_command(update, context)
    return CHOOSE_TYPE


async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_main_menu(update, context)


# ── Список паков ──────────────────────────────────────────────────────────────

async def list_packs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    packs   = get_packs(context, user_id)

    if not packs:
        await query.edit_message_text(
            "У тебя пока нет созданных паков.",
            reply_markup=InlineKeyboardMarkup([back_btn()]),
        )
        return CHOOSE_TYPE

    kb = []
    for i, p in enumerate(packs):
        icon = "🖼" if p["type"] == "sticker" else "✨"
        n    = p.get("count", 0)
        kb.append([InlineKeyboardButton(
            f"{icon} {p['title']} ({n} {plural_sticker(n)})",
            callback_data=f"select_pack_{i}",
        )])
    kb.append(back_btn())
    await query.edit_message_text(
        "📋 <b>Твои паки:</b>\n\nВыбери пак для управления.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


async def select_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx   = int(query.data.replace("select_pack_", ""))
    context.user_data["selected_pack_index"] = idx
    user_id = update.effective_user.id
    pack    = get_packs(context, user_id)[idx]
    icon    = "🖼" if pack["type"] == "sticker" else "✨"
    n       = pack.get("count", 0)
    url     = pack_url(pack["name"])
    kb = [
        [InlineKeyboardButton("🔗 Открыть пак",        url=url)],
        [InlineKeyboardButton("➕ Добавить стикер",     callback_data="mgmt_add")],
        [InlineKeyboardButton("🗑 Удалить стикер",      callback_data="mgmt_delete")],
        [InlineKeyboardButton("🖼 Сменить иконку пака", callback_data="mgmt_icon")],
        [InlineKeyboardButton("❌ Удалить весь пак",    callback_data="mgmt_delete_all")],
        back_btn("◀️ К списку паков", "list_packs"),
    ]
    await query.edit_message_text(
        f"{icon} <b>{pack['title']}</b>\nСтикеров: {n}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


# ── Создание пака ─────────────────────────────────────────────────────────────

async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query     = update.callback_query
    await query.answer()
    pack_type = "sticker" if query.data == "create_sticker" else "emoji"
    context.user_data["creating_type"] = pack_type
    word = "стикер-пак" if pack_type == "sticker" else "эмодзи-пак"
    await query.edit_message_text(
        f"📝 <b>Создание {word}</b>\n\nНапиши <b>название</b> набора:\n\n/cancel — отменить",
        parse_mode="HTML",
    )
    return PACK_NAME


async def receive_pack_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Название не может быть пустым:")
        return PACK_NAME
    context.user_data["new_pack_title"]    = title
    context.user_data["new_pack_stickers"] = []
    kb = [[InlineKeyboardButton("🎲 Случайная ссылка", callback_data="random_link")]]
    await update.message.reply_text(
        "🔗 <b>Придумай короткую ссылку</b>\n\nТолько латиница, цифры и <code>_</code>.\n\n/cancel — отменить",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_LINK


async def _prompt_first_sticker(update: Update, suffix: str) -> int:
    text = (
        f"✅ Ссылка: <code>{suffix}</code>\n\n"
        "Отправь первый стикер 👇\n"
        "<i>Поддерживаются: фото, PNG, WEBP, WEBM, TGS, готовые стикеры TG.</i>\n\n/cancel — отменить"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")
    return ADDING_STICKER


async def use_random_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    suffix = random_suffix()
    context.user_data["new_pack_suffix"] = suffix
    return await _prompt_first_sticker(update, suffix)


async def receive_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw    = update.message.text.strip()
    suffix = sanitize_suffix(raw)
    context.user_data["new_pack_suffix"] = suffix
    if suffix != raw.lower():
        await update.message.reply_text(
            f"ℹ️ Ссылка скорректирована: <code>{suffix}</code>", parse_mode="HTML"
        )
    return await _prompt_first_sticker(update, suffix)


async def _ask_emoji_for_next(update_or_msg, context: ContextTypes.DEFAULT_TYPE) -> int:
    queue = context.user_data.get("file_queue", [])
    done  = context.user_data.get("file_queue_done", 0)
    total = len(queue)
    msg   = update_or_msg.message if hasattr(update_or_msg, "message") else update_or_msg
    if done >= total:
        return await _finish_batch(update_or_msg, context)
    idx_label = f" {done + 1}/{total}" if total > 1 else ""
    await msg.reply_text(
        f"😊 <b>Укажи эмодзи</b> для стикера{idx_label}\n"
        "Можно несколько через пробел: <code>😎 🔥</code>\n\n/cancel — отменить",
        parse_mode="HTML",
    )
    return WAITING_EMOJI


async def _finish_batch(update_or_msg, context: ContextTypes.DEFAULT_TYPE) -> int:
    stickers_buf = context.user_data.get("new_pack_stickers", [])
    suffix       = context.user_data.get("new_pack_suffix") or random_suffix()
    bot_username = context.user_data.get("_bot_username", "")
    pack_name    = build_pack_name(bot_username, suffix)
    n            = len(stickers_buf)
    url          = pack_url(pack_name)
    title        = context.user_data.get("new_pack_title", "My Pack")
    kb = [
        [InlineKeyboardButton("🔗 Открыть пак",  url=url)],
        [InlineKeyboardButton("➕ Добавить ещё", callback_data="add_more")],
        [InlineKeyboardButton("💾 Сохранить пак",callback_data="save_pack")],
    ]
    added = context.user_data.pop("file_queue_added", 0)
    text  = (
        f"🎉 Пак создан!\n<b>{title}</b>\n\nДобавь ещё или сохрани 👇"
        if n == added
        else f"✅ Добавлено {added} {plural_sticker(added)}!\nВсего: {n} {plural_sticker(n)}\n\nПродолжай или сохрани 👇"
    )
    msg = update_or_msg.message if hasattr(update_or_msg, "message") else update_or_msg
    await msg.reply_text(text, parse_mode="HTML", disable_web_page_preview=True,
                         reply_markup=InlineKeyboardMarkup(kb))
    context.user_data.pop("file_queue", None)
    context.user_data.pop("file_queue_done", None)
    return ADDING_STICKER


async def receive_sticker_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pack_type = context.user_data.get("creating_type", "sticker")
    msg       = update.message
    file_size = None
    if msg.document:    file_size = msg.document.file_size
    elif msg.photo:     file_size = msg.photo[-1].file_size
    elif msg.video:     file_size = msg.video.file_size
    elif msg.animation: file_size = msg.animation.file_size
    if file_size and file_size > MAX_INPUT_BYTES:
        await msg.reply_text(
            f"❌ Файл слишком большой ({file_size/1024/1024:.1f} МБ). Максимум — 10 МБ.")
        return ADDING_STICKER
    bot_me = await context.bot.get_me()
    context.user_data["_bot_username"] = bot_me.username
    context.user_data["_user_id"]      = update.effective_user.id
    data, fmt = await get_sticker_data(context.bot, msg, pack_type)
    if data is None:
        await msg.reply_text("❌ Не получилось распознать файл. Отправь PNG, WEBP, WEBM или TGS.")
        return ADDING_STICKER
    queue = context.user_data.setdefault("file_queue", [])
    queue.append({"data": data, "fmt": fmt})
    if len(queue) == 1:
        context.user_data["file_queue_done"]  = 0
        context.user_data["file_queue_added"] = 0
        return await _ask_emoji_for_next(update, context)
    await msg.reply_text(f"📥 Файл #{len(queue)} принят.")
    return ADDING_STICKER


async def receive_emoji_for_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод эмодзи при создании нового пака."""
    text       = update.message.text.strip()
    emoji_list = [e for e in text.split() if e] or ["😊"]
    user_id    = update.effective_user.id
    pack_type  = context.user_data.get("creating_type", "sticker")
    title      = context.user_data.get("new_pack_title", "My Pack")
    suffix     = context.user_data.get("new_pack_suffix") or random_suffix()
    bot_username = context.user_data.get("_bot_username", "")
    pack_name  = build_pack_name(bot_username, suffix)
    stickers_buf = context.user_data.get("new_pack_stickers", [])
    queue      = context.user_data.get("file_queue", [])
    done       = context.user_data.get("file_queue_done", 0)
    if done >= len(queue):
        return await _finish_batch(update, context)
    item       = queue[done]
    data, fmt  = item["data"], item["fmt"]
    await update.message.reply_text("⏳ Добавляю стикер...")
    err = await _push_sticker_to_tg(context.bot, user_id, pack_name, pack_type,
                                     title, data, fmt, emoji_list, stickers_buf)
    if err:
        await update.message.reply_text(f"❌ {err}")
    else:
        stickers_buf.append({"fmt": str(fmt)})
        context.user_data["new_pack_stickers"] = stickers_buf
        context.user_data["file_queue_done"]   = done + 1
        context.user_data["file_queue_added"]  = context.user_data.get("file_queue_added", 0) + 1
    return await _ask_emoji_for_next(update, context)


async def _push_sticker_to_tg(bot, user_id: int, pack_name: str, pack_type: str,
                                title: str, data, fmt, emoji_list: list, stickers_buf: list):
    sticker_type  = StickerType.REGULAR if pack_type == "sticker" else StickerType.CUSTOM_EMOJI
    input_sticker = InputSticker(sticker=data, emoji_list=emoji_list[:20], format=fmt)
    if not stickers_buf:
        try:
            await bot.create_new_sticker_set(user_id=user_id, name=pack_name, title=title,
                                              stickers=[input_sticker], sticker_type=sticker_type)
        except TelegramError as e:
            return _friendly_tg_error(str(e))
    else:
        try:
            await bot.add_sticker_to_set(user_id=user_id, name=pack_name, sticker=input_sticker)
        except TelegramError as e:
            return _friendly_tg_error(str(e))
    return None


async def add_more(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Отправь следующий файл 👇\n\n/cancel — отменить"
    )
    return ADDING_STICKER


async def save_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query        = update.callback_query
    await query.answer()
    user_id      = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    title        = context.user_data.get("new_pack_title", "My Pack")
    suffix       = context.user_data.get("new_pack_suffix") or random_suffix()
    pack_type    = context.user_data.get("creating_type", "sticker")
    stickers     = context.user_data.get("new_pack_stickers", [])
    pack_name    = build_pack_name(bot_username, suffix)
    get_packs(context, user_id).append({
        "title": title, "name": pack_name, "suffix": suffix,
        "type": pack_type, "count": len(stickers),
    })
    for key in ("new_pack_title", "new_pack_suffix", "new_pack_stickers", "creating_type"):
        context.user_data.pop(key, None)
    url  = pack_url(pack_name)
    icon = "🖼" if pack_type == "sticker" else "✨"
    kb   = [
        [InlineKeyboardButton("🔗 Открыть пак", url=url)],
        [InlineKeyboardButton("🏠 В меню",      callback_data="begin")],
    ]
    await query.edit_message_text(
        f"{icon} <b>Пак сохранён!</b>\n\nНазвание: <b>{title}</b>\nСтикеров: {len(stickers)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ConversationHandler.END


# ── Управление паком ──────────────────────────────────────────────────────────

async def mgmt_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx     = context.user_data.get("selected_pack_index", 0)
    pack    = get_packs(context, user_id)[idx]
    word    = "стикер" if pack["type"] == "sticker" else "эмодзи"
    await query.edit_message_text(
        f"➕ Отправь <b>{word}</b> для пака <b>{pack['title']}</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([back_btn("◀️ Отмена", f"select_pack_{idx}")]),
    )
    return ADD_STICKER_FILE


async def receive_add_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id   = update.effective_user.id
    idx       = context.user_data.get("selected_pack_index", 0)
    pack      = get_packs(context, user_id)[idx]
    pack_type = pack["type"]
    msg       = update.message
    file_size = None
    if msg.document:    file_size = msg.document.file_size
    elif msg.photo:     file_size = msg.photo[-1].file_size
    elif msg.video:     file_size = msg.video.file_size
    elif msg.animation: file_size = msg.animation.file_size
    if file_size and file_size > MAX_INPUT_BYTES:
        await msg.reply_text(f"❌ Файл слишком большой. Максимум — 10 МБ.")
        return ADD_STICKER_FILE
    data, fmt = await get_sticker_data(context.bot, msg, pack_type)
    if data is None:
        await msg.reply_text("❌ Не получилось распознать файл.")
        return ADD_STICKER_FILE
    context.user_data["pending_data"] = data
    context.user_data["pending_fmt"]  = fmt
    context.user_data["pending_pack_idx"] = idx
    await msg.reply_text(
        "😊 <b>Укажи эмодзи</b> для этого стикера.\nМожно несколько: <code>😎 🔥</code>",
        parse_mode="HTML",
    )
    return ADD_STICKER_EMOJI


async def receive_add_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Эмодзи для стикера при управлении существующим паком."""
    text       = update.message.text.strip()
    emoji_list = [e for e in text.split() if e] or ["😊"]
    user_id    = update.effective_user.id
    idx        = context.user_data.get("pending_pack_idx",
                  context.user_data.get("selected_pack_index", 0))
    pack       = get_packs(context, user_id)[idx]
    data       = context.user_data.pop("pending_data", None)
    fmt        = context.user_data.pop("pending_fmt", StickerFormat.STATIC)
    if data is None:
        await update.message.reply_text("❌ Данные файла потерялись. Попробуй снова.")
        return PACK_SELECTED
    await update.message.reply_text("⏳ Добавляю стикер...")
    bot_username = (await context.bot.get_me()).username
    pack_name    = pack["name"]
    stickers_buf = [True] * pack.get("count", 1)   # любой непустой список
    err = await _push_sticker_to_tg(context.bot, user_id, pack_name, pack["type"],
                                     pack["title"], data, fmt, emoji_list, stickers_buf)
    if err:
        await update.message.reply_text(f"❌ {err}")
        return PACK_SELECTED
    pack["count"] = pack.get("count", 0) + 1
    n = pack["count"]
    await update.message.reply_text(
        f"✅ Стикер добавлен! Теперь в паке: {n} {plural_sticker(n)}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]),
    )
    return PACK_SELECTED


async def mgmt_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx     = context.user_data.get("selected_pack_index", 0)
    pack    = get_packs(context, user_id)[idx]
    try:
        tg_pack = await context.bot.get_sticker_set(pack["name"])
    except TelegramError as e:
        await query.answer(_friendly_tg_error(str(e)), show_alert=True)
        return PACK_SELECTED
    if not tg_pack.stickers:
        await query.answer("В паке нет стикеров.", show_alert=True)
        return PACK_SELECTED
    kb = []
    for i, s in enumerate(tg_pack.stickers[:50]):
        kb.append([InlineKeyboardButton(f"#{i+1} {s.emoji or '?'}",
                                         callback_data=f"del_sticker_{s.file_unique_id}")])
    kb.append(back_btn("◀️ Отмена", f"select_pack_{idx}"))
    await query.edit_message_text("🗑 Выбери стикер для удаления:",
                                   reply_markup=InlineKeyboardMarkup(kb))
    return DELETE_STICKER


async def confirm_delete_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query          = update.callback_query
    await query.answer()
    user_id        = update.effective_user.id
    idx            = context.user_data.get("selected_pack_index", 0)
    pack           = get_packs(context, user_id)[idx]
    file_unique_id = query.data.replace("del_sticker_", "")
    try:
        tg_pack = await context.bot.get_sticker_set(pack["name"])
    except TelegramError as e:
        await query.answer(_friendly_tg_error(str(e)), show_alert=True)
        return PACK_SELECTED
    target = next((s for s in tg_pack.stickers if s.file_unique_id == file_unique_id), None)
    if not target:
        await query.answer("Стикер не найден.", show_alert=True)
        return DELETE_STICKER
    try:
        await context.bot.delete_sticker_from_set(target.file_id)
    except TelegramError as e:
        await query.answer(_friendly_tg_error(str(e)), show_alert=True)
        return DELETE_STICKER
    pack["count"] = max(0, pack.get("count", 1) - 1)
    await query.edit_message_text(
        f"✅ Стикер удалён. Осталось: {pack['count']} {plural_sticker(pack['count'])}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]),
    )
    return PACK_SELECTED


async def mgmt_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx   = context.user_data.get("selected_pack_index", 0)
    await query.edit_message_text(
        "🖼 <b>Сменить иконку пака</b>\n\nОтправь стикер из этого пака:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([back_btn("◀️ Отмена", f"select_pack_{idx}")]),
    )
    return CHANGE_ICON


async def receive_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg     = update.message
    user_id = update.effective_user.id
    idx     = context.user_data.get("selected_pack_index", 0)
    pack    = get_packs(context, user_id)[idx]
    if not msg.sticker:
        await msg.reply_text("Нужен стикер из этого пака.")
        return CHANGE_ICON
    try:
        f   = await context.bot.get_file(msg.sticker.file_id)
        buf = io.BytesIO()
        await f.download_to_memory(buf)
        thumb = process_image_for_thumbnail(buf.getvalue())
    except Exception as e:
        await msg.reply_text(f"❌ Ошибка: {e}")
        return CHANGE_ICON
    try:
        await context.bot.set_sticker_set_thumbnail(
            name=pack["name"], user_id=user_id, thumbnail=thumb,
            format=msg.sticker.format if hasattr(msg.sticker, "format") else StickerFormat.STATIC,
        )
    except TelegramError as e:
        await msg.reply_text(f"❌ {_friendly_tg_error(str(e))}")
        return CHANGE_ICON
    await msg.reply_text(
        "✅ Иконка обновлена!",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]),
    )
    return PACK_SELECTED


async def mgmt_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx   = context.user_data.get("selected_pack_index", 0)
    await query.edit_message_text(
        "⚠️ <b>Удалить весь пак?</b>\n\nЭто нельзя отменить.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_pack_{idx}")],
            back_btn("◀️ Отмена", f"select_pack_{idx}"),
        ]),
    )
    return PACK_SELECTED


async def confirm_delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx     = int(query.data.replace("confirm_delete_pack_", ""))
    packs   = get_packs(context, user_id)
    pack    = packs[idx]
    try:
        await context.bot.delete_sticker_set(pack["name"])
    except TelegramError:
        pass
    name = pack["title"]
    packs.pop(idx)
    context.user_data.pop("selected_pack_index", None)
    await query.edit_message_text(
        f"🗑 Пак <b>{name}</b> удалён.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([back_btn("📋 К списку паков", "list_packs")]),
    )
    return CHOOSE_TYPE


# ── Номерные знаки: выбор страны ──────────────────────────────────────────────

async def plate_choose_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("🇷🇺 Россия",    callback_data="pc_RU"),
         InlineKeyboardButton("🇺🇦 Украина",   callback_data="pc_UA")],
        [InlineKeyboardButton("🇧🇾 Беларусь",  callback_data="pc_BY"),
         InlineKeyboardButton("🇰🇿 Казахстан", callback_data="pc_KZ")],
        back_btn(),
    ]
    await query.edit_message_text(
        "🚗 <b>Создать номерной знак</b>\n\nВыбери страну:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PLATE_COUNTRY


# ── Номерные знаки: выбор региона (с пагинацией) ─────────────────────────────

def _region_page_kb(country: str, page: int) -> InlineKeyboardMarkup:
    codes  = list(REGIONS[country].keys())
    total  = len(codes)
    start  = page * REGIONS_PER_PAGE
    chunk  = codes[start: start + REGIONS_PER_PAGE]
    kb     = []
    row    = []
    for i, code in enumerate(chunk):
        row.append(InlineKeyboardButton(code, callback_data=f"pr_{country}_{code}"))
        if len(row) == 4:
            kb.append(row); row = []
    if row:
        kb.append(row)
    # навигация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"prp_{country}_{page-1}"))
    pages = (total + REGIONS_PER_PAGE - 1) // REGIONS_PER_PAGE
    nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
    if start + REGIONS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"prp_{country}_{page+1}"))
    kb.append(nav)
    kb.append(back_btn("◀️ Назад к странам", "create_plate"))
    return InlineKeyboardMarkup(kb)


async def plate_select_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    country = query.data.replace("pc_", "")
    context.user_data["plate_country"] = country
    flag    = COUNTRY_NAMES[country]
    await query.edit_message_text(
        f"🚗 {flag}\n\nВыбери код региона:",
        parse_mode="HTML",
        reply_markup=_region_page_kb(country, 0),
    )
    return PLATE_REGION


async def plate_region_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    _, country, page_str = query.data.split("_", 2)
    page    = int(page_str)
    flag    = COUNTRY_NAMES[country]
    await query.edit_message_text(
        f"🚗 {flag}\n\nВыбери код региона:",
        parse_mode="HTML",
        reply_markup=_region_page_kb(country, page),
    )
    return PLATE_REGION


async def plate_select_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    # data format: pr_RU_77
    parts   = query.data.split("_", 2)
    country = parts[1]
    region  = parts[2]
    context.user_data["plate_country"] = country
    context.user_data["plate_region"]  = region
    region_name = REGIONS[country].get(region, "")
    scheme_text = PLATE_SCHEMES[country]
    await query.edit_message_text(
        f"✅ Регион: <b>{region}</b> — {region_name}\n\n"
        f"📋 {scheme_text}\n\n"
        "Напиши номер (только символы, без кода региона):\n\n"
        "/cancel — отменить",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            back_btn("◀️ Сменить регион", f"pc_{country}")
        ]),
    )
    return PLATE_INPUT


async def plate_receive_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw     = update.message.text.strip().upper()
    country = context.user_data.get("plate_country", "RU")
    region  = context.user_data.get("plate_region", "77")
    region_name = REGIONS.get(country, {}).get(region, "")

    # Базовая валидация длины
    min_len = {"RU": 6, "UA": 6, "BY": 6, "KZ": 6}
    if len(raw.replace(" ", "")) < min_len.get(country, 4):
        await update.message.reply_text(
            f"❌ Слишком короткий номер. Проверь схему:\n\n{PLATE_SCHEMES[country]}",
            parse_mode="HTML",
        )
        return PLATE_INPUT

    await update.message.reply_text("⏳ Генерирую номерной знак...")

    try:
        img_bytes = generate_plate_image(country, raw, region, region_name)
        kb = [
            [InlineKeyboardButton("🔄 Другой номер",      callback_data=f"pc_{country}")],
            [InlineKeyboardButton("🏠 В меню",             callback_data="begin")],
        ]
        await update.message.reply_photo(
            photo=InputFile(io.BytesIO(img_bytes), filename="plate.png"),
            caption=f"🚗 <b>{raw}</b> | <b>{region}</b>\n{region_name}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    except Exception as e:
        logger.exception("plate generation error")
        await update.message.reply_text(f"❌ Ошибка генерации: {e}")

    return PLATE_INPUT


async def plate_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return PLATE_REGION


# ── Сборка ────────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start",  start),
            CommandHandler("menu",   menu_command),
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(begin, pattern="^begin$"),
        ],
        states={
            MAIN_MENU: [CallbackQueryHandler(begin, pattern="^begin$")],
            CHOOSE_TYPE: [
                CallbackQueryHandler(begin,                pattern="^begin$"),
                CallbackQueryHandler(start_create,         pattern="^create_(sticker|emoji)$"),
                CallbackQueryHandler(list_packs,           pattern="^list_packs$"),
                CallbackQueryHandler(plate_choose_country, pattern="^create_plate$"),
            ],
            PACK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_name),
            ],
            PACK_LINK: [
                CallbackQueryHandler(use_random_link, pattern="^random_link$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_link),
            ],
            ADDING_STICKER: [
                CallbackQueryHandler(save_pack, pattern="^save_pack$"),
                CallbackQueryHandler(add_more,  pattern="^add_more$"),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Sticker.ALL |
                    filters.ANIMATION | filters.Document.ALL,
                    receive_sticker_file,
                ),
            ],
            WAITING_EMOJI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_emoji_for_new),
            ],
            PACK_SELECTED: [
                CallbackQueryHandler(begin,                  pattern="^begin$"),
                CallbackQueryHandler(list_packs,             pattern="^list_packs$"),
                CallbackQueryHandler(select_pack,            pattern="^select_pack_\\d+$"),
                CallbackQueryHandler(mgmt_add,               pattern="^mgmt_add$"),
                CallbackQueryHandler(mgmt_delete,            pattern="^mgmt_delete$"),
                CallbackQueryHandler(confirm_delete_sticker, pattern="^del_sticker_.+$"),
                CallbackQueryHandler(mgmt_icon,              pattern="^mgmt_icon$"),
                CallbackQueryHandler(mgmt_delete_all,        pattern="^mgmt_delete_all$"),
                CallbackQueryHandler(confirm_delete_pack,    pattern="^confirm_delete_pack_\\d+$"),
            ],
            ADD_STICKER_FILE: [
                CallbackQueryHandler(select_pack, pattern="^select_pack_\\d+$"),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Sticker.ALL |
                    filters.ANIMATION | filters.Document.ALL,
                    receive_add_file,
                ),
            ],
            ADD_STICKER_EMOJI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_emoji),
            ],
            DELETE_STICKER: [
                CallbackQueryHandler(select_pack,            pattern="^select_pack_\\d+$"),
                CallbackQueryHandler(confirm_delete_sticker, pattern="^del_sticker_.+$"),
            ],
            CHANGE_ICON: [
                CallbackQueryHandler(select_pack, pattern="^select_pack_\\d+$"),
                MessageHandler(filters.Sticker.ALL, receive_icon),
            ],
            # ── Номерные знаки ──────────────────────────────────────────────
            PLATE_COUNTRY: [
                CallbackQueryHandler(begin,                pattern="^begin$"),
                CallbackQueryHandler(plate_choose_country, pattern="^create_plate$"),
                CallbackQueryHandler(plate_select_country, pattern="^pc_(RU|UA|BY|KZ)$"),
            ],
            PLATE_REGION: [
                CallbackQueryHandler(plate_choose_country, pattern="^create_plate$"),
                CallbackQueryHandler(plate_select_country, pattern="^pc_(RU|UA|BY|KZ)$"),
                CallbackQueryHandler(plate_region_page,    pattern="^prp_(RU|UA|BY|KZ)_\\d+$"),
                CallbackQueryHandler(plate_select_region,  pattern="^pr_(RU|UA|BY|KZ)_.+$"),
                CallbackQueryHandler(plate_noop,           pattern="^noop$"),
            ],
            PLATE_INPUT: [
                CallbackQueryHandler(begin,                pattern="^begin$"),
                CallbackQueryHandler(plate_choose_country, pattern="^create_plate$"),
                CallbackQueryHandler(plate_select_country, pattern="^pc_(RU|UA|BY|KZ)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, plate_receive_input),
            ],
        },
        fallbacks=[
            CommandHandler("start",  start),
            CommandHandler("menu",   menu_command),
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(begin, pattern="^begin$"),
        ],
        allow_reentry=True,
        per_message=False,
    )

    async def post_init(application):
        await application.bot.set_my_commands([
            ("start",  "👋 Приветствие"),
            ("menu",   "🏠 Главное меню"),
            ("cancel", "❌ Отменить текущее действие"),
        ])

    app.post_init = post_init
    app.add_handler(conv)
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("menu",   menu_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(begin, pattern="^begin$"))
    logger.info("Бот запущен ✅")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
