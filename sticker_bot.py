"""
Telegram Sticker & Premium Emoji Pack Bot
Токен берётся из переменной окружения BOT_TOKEN.

Автоматически обрабатывает изображения:
  - Ресайз до 512x512 (стикеры) или 100x100 (эмодзи)
  - Конвертация в PNG с прозрачностью
  - Сжатие если файл слишком большой
"""

import asyncio
import io
import logging
import os
import random
import re
import string

from PIL import Image

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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


def auto_detect_emoji(image_bytes: bytes) -> list[str]:
    """
    Локальный анализ изображения по цвету, яркости и насыщенности.
    Без API-ключей. Возвращает 1-2 подходящих эмодзи.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        # Уменьшаем для скорости
        img.thumbnail((64, 64))

        pixels = list(img.getdata())
        # Убираем прозрачные пиксели (альфа < 30)
        opaque = [(r, g, b, a) for r, g, b, a in pixels if a > 30]
        if not opaque:
            return ["🙂"]

        # Средние значения RGB
        avg_r = sum(p[0] for p in opaque) / len(opaque)
        avg_g = sum(p[1] for p in opaque) / len(opaque)
        avg_b = sum(p[2] for p in opaque) / len(opaque)
        brightness = (avg_r + avg_g + avg_b) / 3

        # Насыщенность = разброс между каналами
        saturation = max(avg_r, avg_g, avg_b) - min(avg_r, avg_g, avg_b)

        # Доля прозрачных пикселей (много = силуэт/простой стикер)
        transparency_ratio = 1 - len(opaque) / len(pixels)

        result = []

        # Определяем доминирующий цвет
        if saturation < 30:
            # Ахроматический (серый/чёрно-белый)
            if brightness > 200:
                result.append("🤍")
            elif brightness > 100:
                result.append("🩶")
            else:
                result.append("🖤")
        else:
            # Определяем оттенок
            if avg_r > avg_g and avg_r > avg_b:
                if avg_g > avg_b * 1.3:
                    result.append("🟠")   # оранжевый
                else:
                    result.append("❤️")   # красный
            elif avg_g > avg_r and avg_g > avg_b:
                if avg_b > avg_r * 1.2:
                    result.append("💚")   # сине-зелёный
                else:
                    result.append("🌿")   # зелёный
            elif avg_b > avg_r and avg_b > avg_g:
                if avg_r > avg_g * 1.1:
                    result.append("💜")   # фиолетовый
                else:
                    result.append("💙")   # синий
            elif avg_r > 180 and avg_g > 150 and avg_b < 100:
                result.append("💛")       # жёлтый
            elif avg_r > 180 and avg_g < 120 and avg_b > 150:
                result.append("🩷")       # розовый
            else:
                result.append("🎨")

        # Добавляем эмодзи по яркости/стилю
        if brightness > 210 and saturation > 40:
            result.append("✨")
        elif brightness < 60:
            result.append("🌑")
        elif transparency_ratio > 0.6:
            result.append("💫")
        elif saturation > 120:
            result.append("🔥")

        return result[:2] if result else ["🙂"]

    except Exception as e:
        return ["🙂"]


def is_auto_emoji(context) -> bool:
    """Проверяет включено ли автоопределение эмодзи для пользователя."""
    return context.user_data.get("auto_emoji", True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

(
    MAIN_MENU,
    CHOOSE_TYPE,
    SETTINGS,
    PACK_NAME,
    PACK_LINK,
    ADDING_STICKER,
    WAITING_EMOJI,
    PACK_SELECTED,
    ADD_STICKER_FILE,
    ADD_STICKER_EMOJI,
    DELETE_STICKER,
    CHANGE_ICON,
) = range(12)

# Максимальный размер файла стикера (512 КБ с запасом)
MAX_STICKER_BYTES = 500 * 1024


# ── Утилиты ───────────────────────────────────────────────────────────────────

def random_suffix(length: int = 10) -> str:
    """Генерирует суффикс: только строчные буквы и цифры, начинается с буквы."""
    first = random.choice(string.ascii_lowercase)
    rest  = "".join(random.choices(string.ascii_lowercase + string.digits, k=length - 1))
    return first + rest


def sanitize_suffix(raw: str) -> str:
    """
    Приводит пользовательский ввод к допустимому суффиксу имени пака:
    только a-z, 0-9, _, длина 5-64, начинается с буквы.
    """
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
    if r == 1:   return "стикер"
    if 2 <= r <= 4: return "стикера"
    return "стикеров"


def pack_url(pack_name: str) -> str:
    return f"https://t.me/addstickers/{pack_name}"


def get_packs(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> list:
    return context.bot_data.setdefault(str(user_id), {}).setdefault("packs", [])


def back_btn(label: str = "◀️ Назад", data: str = "begin") -> list:
    return [InlineKeyboardButton(label, callback_data=data)]


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
        inner = (int(size * scale), int(size * scale))
        resized = canvas.resize(inner, Image.LANCZOS)
        final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        off = ((size - inner[0]) // 2, (size - inner[1]) // 2)
        final.paste(resized, off, resized)
        buf = io.BytesIO()
        final.save(buf, format="PNG", optimize=True, compress_level=9)
        data = buf.getvalue()
        scale -= 0.1
    return data


def process_image_for_sticker(raw_bytes: bytes, pack_type: str = "sticker") -> bytes:
    size = 512 if pack_type == "sticker" else 100
    return process_image(raw_bytes, size)


def process_image_for_thumbnail(raw_bytes: bytes) -> bytes:
    """Иконка пака: строго 100x100 PNG, до 32 КБ."""
    return process_image(raw_bytes, 100, max_bytes=32 * 1024)


# ── Получение и подготовка файла для InputSticker ────────────────────────────

async def get_sticker_data(bot, msg, pack_type: str = "sticker"):
    """
    Скачивает файл, при необходимости обрабатывает и возвращает (bytes, fmt).
    - Статичные изображения: автоматически ресайзятся и конвертируются в PNG
    - Видео/анимации: скачиваются как есть (WEBM/TGS)
    - Готовые TG-стикеры: file_id передаётся напрямую

    Возвращает (None, None) если файл не распознан.
    """

    async def dl(file_id: str) -> bytes:
        f   = await bot.get_file(file_id)
        buf = io.BytesIO()
        await f.download_to_memory(buf)
        return buf.getvalue()

    # Готовый стикер TG — скачиваем байты (file_id нельзя использовать для видео-стикеров)
    if msg.sticker:
        s   = msg.sticker
        fmt = s.format if hasattr(s, "format") else StickerFormat.STATIC
        raw = await dl(s.file_id)
        if fmt == StickerFormat.STATIC:
            # Статичные стикеры — обрабатываем пикселями для правильного размера
            return process_image_for_sticker(raw, pack_type), fmt
        else:
            # Видео/анимация — передаём байты как есть
            return raw, fmt

    # Документ (файл без сжатия)
    if msg.document:
        d    = msg.document
        mime = (d.mime_type or "").lower()
        name = (d.file_name or "").lower()

        if "webm" in mime or name.endswith(".webm"):
            # Видео-стикер — не обрабатываем пикселями
            return await dl(d.file_id), StickerFormat.VIDEO

        if "tgs" in mime or name.endswith(".tgs"):
            # Анимированный стикер
            return await dl(d.file_id), StickerFormat.ANIMATED

        # PNG, WEBP, JPEG, BMP и т.д. — обрабатываем
        raw = await dl(d.file_id)
        return process_image_for_sticker(raw, pack_type), StickerFormat.STATIC

    # Сжатое фото — Telegram уже JPEG, обрабатываем
    if msg.photo:
        raw = await dl(msg.photo[-1].file_id)
        return process_image_for_sticker(raw, pack_type), StickerFormat.STATIC

    # Видео
    if msg.video:
        return await dl(msg.video.file_id), StickerFormat.VIDEO

    # GIF / анимация
    if msg.animation:
        return await dl(msg.animation.file_id), StickerFormat.VIDEO

    return None, None


# ── Главное меню ──────────────────────────────────────────────────────────────

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [
        [InlineKeyboardButton("🖼  Создать стикер-пак",  callback_data="create_sticker")],
        [InlineKeyboardButton("✨  Создать эмодзи-пак",   callback_data="create_emoji")],
        [InlineKeyboardButton("📋  Мои паки",             callback_data="list_packs")],
        [InlineKeyboardButton("⚙️  Настройки",            callback_data="settings")],
    ]
    text = (
        "👋 <b>Что хочешь создать?</b>\n\n"
        "• <b>Стикер-пак</b> — обычные стикеры\n"
        "• <b>Эмодзи-пак</b> — premium emoji\n\n"
        "<i>Поддерживаются: фото, PNG, WEBP, WEBM, TGS, готовые стикеры TG</i>"
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
        f"Привет, {name}!\n\nСоздавай стикеры и premium emoji прямо в Telegram 🚀",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return MAIN_MENU


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in (
        "new_pack_title", "new_pack_suffix", "new_pack_stickers",
        "creating_type", "selected_pack_index", "pending_data", "pending_fmt",
    ):
        context.user_data.pop(key, None)
    return await send_main_menu(update, context)




async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет создание пака и возвращает в главное меню."""
    for key in (
        "new_pack_title", "new_pack_suffix", "new_pack_stickers",
        "creating_type", "selected_pack_index", "pending_data", "pending_fmt",
    ):
        context.user_data.pop(key, None)
    await update.message.reply_text(
        "❌ Создание пака отменено.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 В меню", callback_data="begin")]]
        ),
    )
    return ConversationHandler.END

async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_main_menu(update, context)

# ── Настройки ─────────────────────────────────────────────────────────────────

def _settings_kb(context) -> InlineKeyboardMarkup:
    auto = is_auto_emoji(context)
    status = "✅ Включено" if auto else "❌ Выключено"
    toggle = "Выключить" if auto else "Включить"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🤖 Авто-эмодзи: {status}",
            callback_data="settings_noop",
        )],
        [InlineKeyboardButton(
            f"{'🔴 ' if auto else '🟢 '}{toggle} авто-эмодзи",
            callback_data="toggle_auto_emoji",
        )],
        [InlineKeyboardButton("◀️ Назад", callback_data="begin")],
    ])


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    auto = is_auto_emoji(context)
    desc = (
        "🤖 <b>Авто-эмодзи включено</b>\n"
        "Бот сам подбирает подходящий эмодзи для каждого стикера.\n\n"
        "<i>Выключи, чтобы указывать эмодзи вручную.</i>"
        if auto else
        "✏️ <b>Авто-эмодзи выключено</b>\n"
        "Бот будет спрашивать эмодзи для каждого стикера вручную.\n\n"
        "<i>Включи, чтобы бот подбирал эмодзи автоматически.</i>"
    )
    text = f"⚙️ <b>Настройки</b>\n\n{desc}"
    kb   = _settings_kb(context)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    return SETTINGS


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await show_settings(update, context)


async def toggle_auto_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    current = context.user_data.get("auto_emoji", True)
    context.user_data["auto_emoji"] = not current
    return await show_settings(update, context)


async def settings_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer("Это текущий статус настройки", show_alert=False)
    return SETTINGS




# ── Список паков ──────────────────────────────────────────────────────────────

async def list_packs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
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


# ── Выбор пака ────────────────────────────────────────────────────────────────

async def select_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx  = int(query.data.replace("select_pack_", ""))
    context.user_data["selected_pack_index"] = idx
    user_id = update.effective_user.id
    pack = get_packs(context, user_id)[idx]
    icon = "🖼" if pack["type"] == "sticker" else "✨"
    n    = pack.get("count", 0)
    url  = pack_url(pack["name"])
    kb   = [
        [InlineKeyboardButton("🔗 Открыть пак",         url=url)],
        [InlineKeyboardButton("➕ Добавить стикер",      callback_data="mgmt_add")],
        [InlineKeyboardButton("🗑 Удалить стикер",       callback_data="mgmt_delete")],
        [InlineKeyboardButton("🖼 Сменить иконку пака",  callback_data="mgmt_icon")],
        [InlineKeyboardButton("❌ Удалить весь пак",     callback_data="mgmt_delete_all")],
        back_btn("◀️ К списку паков", "list_packs"),
    ]
    await query.edit_message_text(
        f"{icon} <b>{pack['title']}</b>\n"
        f"Стикеров: {n}\n"
        f"Ссылка: <a href='{url}'>{url}</a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED



# ── Создание пака: шаг 1 — тип ────────────────────────────────────────────────

async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query     = update.callback_query
    await query.answer()
    pack_type = "sticker" if query.data == "create_sticker" else "emoji"
    context.user_data["creating_type"] = pack_type
    word = "стикер-пак" if pack_type == "sticker" else "эмодзи-пак"
    await query.edit_message_text(
        f"📝 <b>Создание {word}</b>\n\nНапиши <b>название</b> набора:\n\n/cancel — отменить создание пака",
        parse_mode="HTML",
    )
    return PACK_NAME


# ── Создание пака: шаг 2 — название ──────────────────────────────────────────

async def receive_pack_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Название не может быть пустым:")
        return PACK_NAME
    context.user_data["new_pack_title"]    = title
    context.user_data["new_pack_stickers"] = []
    kb = [[InlineKeyboardButton("🎲 Случайная ссылка", callback_data="random_link")]]
    await update.message.reply_text(
        "🔗 <b>Придумай короткую ссылку</b>\n\n"
        "Только латиница, цифры и <code>_</code>."
        "\n\n/cancel — отменить создание пака",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_LINK


# ── Создание пака: шаг 3 — ссылка ────────────────────────────────────────────

async def _prompt_first_sticker(update: Update, suffix: str) -> int:
    text = (
        f"✅ Ссылка: <code>{suffix}</code>\n\n"
        "Отправь первый стикер 👇\n"
        "<i>Поддерживаются: фото, PNG, WEBP, WEBM, TGS, готовые стикеры TG.</i>\n\n/cancel — отменить создание пака"
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
            f"ℹ️ Ссылка скорректирована: <code>{suffix}</code>",
            parse_mode="HTML",
        )
    return await _prompt_first_sticker(update, suffix)


# ── Создание пака: шаг 4 — файл(ы) ──────────────────────────────────────────
# Поддерживает как один файл, так и сразу несколько (альбом или последовательная отправка).
# Все файлы складываются в очередь file_queue, затем поочерёдно запрашивается эмодзи.

async def _ask_emoji_for_next(update_or_msg, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Задаёт вопрос про эмодзи для следующего файла в очереди.
    Если авто-эмодзи включено — определяет эмодзи через Claude и сразу идёт дальше."""
    queue = context.user_data.get("file_queue", [])
    done  = context.user_data.get("file_queue_done", 0)
    total = len(queue)
    msg   = update_or_msg.message if hasattr(update_or_msg, "message") else update_or_msg

    if done >= total:
        return await _finish_batch(update_or_msg, context)

    # Если авто-эмодзи включено — определяем автоматически для всех оставшихся
    if is_auto_emoji(context):
        # Обрабатываем все оставшиеся файлы подряд без вопросов
        user_id      = context.user_data.get("_user_id")
        bot_username = context.user_data.get("_bot_username", "")
        pack_type    = context.user_data.get("creating_type", "sticker")
        suffix       = context.user_data.get("new_pack_suffix") or random_suffix()
        title        = context.user_data.get("new_pack_title", "My Pack")
        pack_name    = build_pack_name(bot_username, suffix)
        stickers_buf = context.user_data.setdefault("new_pack_stickers", [])
        bot          = msg.get_bot() if hasattr(msg, "get_bot") else context.application.bot

        for i in range(done, total):
            item       = queue[i]
            data, fmt  = item["data"], item["fmt"]
            emoji_list = auto_detect_emoji(data if isinstance(data, bytes) else b"")
            err = await _push_sticker_to_tg(bot, user_id, pack_name, pack_type,
                                             title, data, fmt, emoji_list, stickers_buf)
            if err:
                logger.error("auto push sticker %d: %s", i+1, err)
                await msg.reply_text(f"⚠️ Файл #{i+1} пропущен: <code>{err}</code>", parse_mode="HTML")
            else:
                stickers_buf.append({"fmt": str(fmt), "emojis": emoji_list})
                context.user_data["file_queue_added"] = context.user_data.get("file_queue_added", 0) + 1

        context.user_data["file_queue_done"] = total
        return await _finish_batch(update_or_msg, context)

    # Ручной режим — спрашиваем эмодзи
    idx_label = f"{done + 1}/{total}" if total > 1 else ""
    prompt = (
        f"😊 <b>Укажи эмодзи</b> для файла {idx_label}\n"
        "Можно несколько через пробел: <code>😎 🔥</code>\n\n/cancel — отменить создание пака"
    )
    await msg.reply_text(prompt, parse_mode="HTML")
    return WAITING_EMOJI


async def _finish_batch(update_or_msg, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает итог после того как все эмодзи указаны."""
    user_id      = context._user_id if hasattr(context, "_user_id") else context.user_data.get("_user_id")
    stickers_buf = context.user_data.get("new_pack_stickers", [])
    suffix       = context.user_data.get("new_pack_suffix") or random_suffix()
    bot_username = context.user_data.get("_bot_username", "")
    pack_name    = build_pack_name(bot_username, suffix)
    n            = len(stickers_buf)
    url          = pack_url(pack_name)
    title        = context.user_data.get("new_pack_title", "My Pack")

    kb = [
        [InlineKeyboardButton("🔗 Открыть пак",   url=url)],
        [InlineKeyboardButton("➕ Добавить ещё",  callback_data="add_more")],
        [InlineKeyboardButton("💾 Сохранить пак", callback_data="save_pack")],
    ]
    added = context.user_data.pop("file_queue_added", 0)
    text = (
        f"🎉 Пак создан!\n<b>{title}</b>\n\n<a href='{url}'>{url}</a>\n\nДобавь ещё или сохрани 👇"
        if n == added else  # первый батч
        f"✅ Добавлено {added} {plural_sticker(added)}!\nВсего: {n} {plural_sticker(n)}\n\nПродолжай или сохрани 👇"
    )
    msg = update_or_msg.message if hasattr(update_or_msg, "message") else update_or_msg
    await msg.reply_text(text, parse_mode="HTML", disable_web_page_preview=False,
                         reply_markup=InlineKeyboardMarkup(kb))
    # Очищаем очередь
    context.user_data.pop("file_queue", None)
    context.user_data.pop("file_queue_done", None)
    return ADDING_STICKER


async def receive_sticker_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает один или несколько файлов и начинает очередь запросов эмодзи."""
    pack_type = context.user_data.get("creating_type", "sticker")

    # Сохраняем user_id и bot_username для _finish_batch
    bot_me = await context.bot.get_me()
    context.user_data["_bot_username"] = bot_me.username
    context.user_data["_user_id"] = update.effective_user.id

    data, fmt = await get_sticker_data(context.bot, update.message, pack_type)
    if data is None:
        await update.message.reply_text("❌ Не могу распознать файл. Отправь фото или изображение.")
        return ADDING_STICKER

    # Добавляем в очередь (пользователь может слать файлы один за другим быстро)
    queue = context.user_data.setdefault("file_queue", [])
    queue.append({"data": data, "fmt": fmt})

    # Если это первый файл — сразу спрашиваем эмодзи
    # Если уже идёт опрос (WAITING_EMOJI) — просто добавили в очередь молча
    if len(queue) == 1:
        context.user_data["file_queue_done"] = 0
        context.user_data["file_queue_added"] = 0
        return await _ask_emoji_for_next(update, context)

    # Сообщаем что файл принят и встал в очередь
    await update.message.reply_text(
        f"📥 Файл #{len(queue)} принят, жду пока укажешь эмодзи для предыдущих."
    )
    return WAITING_EMOJI


# ── Создание пака: шаг 5 — эмодзи + API ──────────────────────────────────────

async def _push_sticker_to_tg(bot, user_id: int, pack_name: str, pack_type: str,
                                title: str, data, fmt, emoji_list: list,
                                stickers_buf: list):
    """Создаёт пак или добавляет стикер. Возвращает None при успехе, строку ошибки при неудаче."""
    sticker_type = StickerType.REGULAR if pack_type == "sticker" else StickerType.CUSTOM_EMOJI
    input_sticker = InputSticker(sticker=data, emoji_list=emoji_list[:20], format=fmt)

    if not stickers_buf:
        try:
            await bot.create_new_sticker_set(
                user_id=user_id, name=pack_name, title=title,
                stickers=[input_sticker], sticker_type=sticker_type,
            )
        except TelegramError as e:
            return str(e)
    else:
        try:
            await bot.add_sticker_to_set(user_id=user_id, name=pack_name, sticker=input_sticker)
        except TelegramError as e:
            return str(e)
    return None


async def receive_sticker_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    emoji_list = update.message.text.strip().split()
    if not emoji_list:
        await update.message.reply_text("Напиши хотя бы один эмодзи:")
        return WAITING_EMOJI

    queue = context.user_data.get("file_queue", [])
    done  = context.user_data.get("file_queue_done", 0)

    if done >= len(queue):
        await update.message.reply_text("Что-то пошло не так, отправь файлы заново.")
        return ADDING_STICKER

    item = queue[done]
    data, fmt = item["data"], item["fmt"]

    user_id      = context.user_data.get("_user_id", update.effective_user.id)
    bot          = context.bot
    pack_type    = context.user_data.get("creating_type", "sticker")
    suffix       = context.user_data.get("new_pack_suffix") or random_suffix()
    title        = context.user_data.get("new_pack_title", "My Pack")
    bot_username = context.user_data.get("_bot_username") or (await bot.get_me()).username
    pack_name    = build_pack_name(bot_username, suffix)
    stickers_buf = context.user_data.setdefault("new_pack_stickers", [])

    err = await _push_sticker_to_tg(bot, user_id, pack_name, pack_type, title,
                                     data, fmt, emoji_list, stickers_buf)
    if err:
        logger.error("push_sticker: %s", err)
        await update.message.reply_text(f"❌ <b>Ошибка для файла #{done+1}:</b> <code>{err}</code>",
                                        parse_mode="HTML")
        # Пропускаем этот файл, продолжаем с остальными
        context.user_data["file_queue_done"] = done + 1
        return await _ask_emoji_for_next(update, context)

    stickers_buf.append({"fmt": str(fmt), "emojis": emoji_list})
    context.user_data["file_queue_done"] = done + 1
    context.user_data["file_queue_added"] = context.user_data.get("file_queue_added", 0) + 1

    # Если ещё есть файлы в очереди — спрашиваем следующий
    if done + 1 < len(queue):
        return await _ask_emoji_for_next(update, context)

    # Все файлы обработаны — показываем итог
    return await _finish_batch(update, context)


async def add_more(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Отправь следующий файл — фото, PNG, WEBP, WEBM или TGS 👇\n\n/cancel — отменить создание пака")
    return ADDING_STICKER


# ── Сохранение пака ───────────────────────────────────────────────────────────

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
        f"{icon} <b>Пак сохранён!</b>\n\n"
        f"Название: <b>{title}</b>\nСтикеров: {len(stickers)}\n"
        f"Ссылка: <a href='{url}'>{url}</a>",
        parse_mode="HTML",
        disable_web_page_preview=False,
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ConversationHandler.END


# ── Управление: добавить стикер ───────────────────────────────────────────────

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
    data, fmt = await get_sticker_data(context.bot, update.message, pack_type)
    if data is None:
        await update.message.reply_text("❌ Не могу распознать файл. Попробуй ещё раз.")
        return ADD_STICKER_FILE
    context.user_data["pending_data"] = data
    context.user_data["pending_fmt"]  = fmt
    await update.message.reply_text(
        "😊 Укажи <b>эмодзи</b> для этого стикера:",
        parse_mode="HTML",
    )
    return ADD_STICKER_EMOJI


async def receive_add_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    emoji_list = update.message.text.strip().split()
    if not emoji_list:
        await update.message.reply_text("Напиши хотя бы один эмодзи:")
        return ADD_STICKER_EMOJI

    data    = context.user_data.pop("pending_data", None)
    fmt     = context.user_data.pop("pending_fmt",  StickerFormat.STATIC)
    user_id = update.effective_user.id
    idx     = context.user_data.get("selected_pack_index", 0)
    pack    = get_packs(context, user_id)[idx]

    try:
        await context.bot.add_sticker_to_set(
            user_id=user_id,
            name=pack["name"],
            sticker=InputSticker(sticker=data, emoji_list=emoji_list[:20], format=fmt),
        )
    except TelegramError as e:
        logger.error("add_sticker_to_set (mgmt): %s", e)
        await update.message.reply_text(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")
        return ADD_STICKER_FILE

    pack["count"] = pack.get("count", 0) + 1
    await update.message.reply_text(
        f"✅ Стикер добавлен! В паке: {pack['count']} {plural_sticker(pack['count'])}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]),
    )
    return PACK_SELECTED


# ── Управление: удалить стикер ────────────────────────────────────────────────

async def mgmt_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx     = context.user_data.get("selected_pack_index", 0)
    pack    = get_packs(context, user_id)[idx]
    try:
        tg_pack = await context.bot.get_sticker_set(pack["name"])
    except TelegramError as e:
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return PACK_SELECTED
    if not tg_pack.stickers:
        await query.answer("В паке нет стикеров.", show_alert=True)
        return PACK_SELECTED
    kb = []
    for i, s in enumerate(tg_pack.stickers[:50]):
        kb.append([InlineKeyboardButton(
            f"#{i+1} {s.emoji or '?'}",
            callback_data=f"del_sticker_{s.file_unique_id}",
        )])
    kb.append(back_btn("◀️ Отмена", f"select_pack_{idx}"))
    await query.edit_message_text("🗑 Выбери стикер для удаления:", reply_markup=InlineKeyboardMarkup(kb))
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
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return PACK_SELECTED
    target = next((s for s in tg_pack.stickers if s.file_unique_id == file_unique_id), None)
    if not target:
        await query.answer("Стикер не найден.", show_alert=True)
        return DELETE_STICKER
    try:
        await context.bot.delete_sticker_from_set(target.file_id)
    except TelegramError as e:
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return DELETE_STICKER
    pack["count"] = max(0, pack.get("count", 1) - 1)
    await query.edit_message_text(
        f"✅ Стикер удалён. Осталось: {pack['count']} {plural_sticker(pack['count'])}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]),
    )
    return PACK_SELECTED


# ── Управление: сменить иконку ────────────────────────────────────────────────

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
        await msg.reply_text("Нужен стикер из этого пака. Попробуй ещё раз.")
        return CHANGE_ICON
    # Скачиваем стикер и ресайзим до строго 100x100 PNG (требование Telegram для thumbnail)
    try:
        tg_file = await context.bot.get_file(msg.sticker.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        thumb_bytes = process_image_for_thumbnail(buf.getvalue())
    except Exception as e:
        await msg.reply_text(f"❌ Ошибка обработки: <code>{e}</code>", parse_mode="HTML")
        return CHANGE_ICON
    try:
        await context.bot.set_sticker_set_thumbnail(
            name=pack["name"],
            user_id=user_id,
            thumbnail=thumb_bytes,
            format=msg.sticker.format if hasattr(msg.sticker, "format") else StickerFormat.STATIC,
        )
    except TelegramError as e:
        await msg.reply_text(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")
        return CHANGE_ICON
    await msg.reply_text(
        "✅ Иконка обновлена!",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]),
    )
    return PACK_SELECTED


# ── Управление: удалить весь пак ─────────────────────────────────────────────

async def mgmt_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx   = context.user_data.get("selected_pack_index", 0)
    await query.edit_message_text(
        "⚠️ <b>Удалить весь пак?</b>\n\nЭто действие нельзя отменить.",
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
    except TelegramError as e:
        logger.warning("delete_sticker_set: %s", e)
    name = pack["title"]
    packs.pop(idx)
    context.user_data.pop("selected_pack_index", None)
    await query.edit_message_text(
        f"🗑 Пак <b>{name}</b> удалён.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([back_btn("📋 К списку паков", "list_packs")]),
    )
    return CHOOSE_TYPE


# ── Сборка ────────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start",    start),
            CommandHandler("menu",     menu_command),
            CommandHandler("cancel",   cancel_command),
            CommandHandler("settings", settings_command),
            CallbackQueryHandler(begin,        pattern="^begin$"),
            CallbackQueryHandler(show_settings,pattern="^settings$"),
        ],
        states={
            MAIN_MENU: [CallbackQueryHandler(begin, pattern="^begin$")],
            SETTINGS: [
                CallbackQueryHandler(begin,            pattern="^begin$"),
                CallbackQueryHandler(toggle_auto_emoji,pattern="^toggle_auto_emoji$"),
                CallbackQueryHandler(settings_noop,    pattern="^settings_noop$"),
            ],
            CHOOSE_TYPE: [
                CallbackQueryHandler(begin,        pattern="^begin$"),
                CallbackQueryHandler(start_create, pattern="^create_(sticker|emoji)$"),
                CallbackQueryHandler(list_packs,   pattern="^list_packs$"),
                CallbackQueryHandler(show_settings,pattern="^settings$"),
            ],
            PACK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_name)],
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
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_sticker_emoji),
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
        },
        fallbacks=[
            CommandHandler("start",    start),
            CommandHandler("menu",     menu_command),
            CommandHandler("cancel",   cancel_command),
            CommandHandler("settings", settings_command),
            CallbackQueryHandler(begin,        pattern="^begin$"),
            CallbackQueryHandler(show_settings,pattern="^settings$"),
        ],
        allow_reentry=True,
        per_message=False,
    )

    # Регистрируем команды бота (кнопка "Меню" в интерфейсе TG)
    async def post_init(application):
        await application.bot.set_my_commands([
            ("start",  "👋 Приветствие"),
            ("menu",   "🏠 Главное меню"),
            ("cancel",   "❌ Отменить создание пака"),
            ("settings", "⚙️ Настройки"),
        ])

    app.post_init = post_init

    app.add_handler(conv)
    # Глобальный хэндлер для кнопки "В меню" вне ConversationHandler
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("menu",   menu_command))
    app.add_handler(CommandHandler("cancel",   cancel_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(begin,        pattern="^begin$"))
    app.add_handler(CallbackQueryHandler(show_settings,pattern="^settings$"))
    logger.info("Бот запущен ✅")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
