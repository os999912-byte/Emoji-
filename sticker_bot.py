import logging
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ─── Токен бота ───────────────────────────────────────────────────────────────
BOT_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"

# ─── Логирование ──────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Состояния ConversationHandler ────────────────────────────────────────────
(
    MAIN_MENU,
    CHOOSE_PACK_TYPE,
    STICKER_PACK_NAME,
    STICKER_PACK_LINK,
    STICKER_ADDING,
) = range(5)

# ─── Хранилище паков (в памяти; для продакшена замените на БД) ────────────────
# user_data[user_id]["packs"] = [{"name": ..., "link": ..., "type": ..., "stickers": [...]}]


def random_link(length: int = 8) -> str:
    """Генерирует случайную ссылку из букв и цифр."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    name = f"@{user.username}" if user.username else user.first_name

    keyboard = [[InlineKeyboardButton("😎 Начать", callback_data="begin")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Привет, {name}!\n\nСоздавай свои стикеры и премиум эмодзи!",
        reply_markup=reply_markup,
    )
    return MAIN_MENU


# ─── Главное меню (после «Начать») ────────────────────────────────────────────
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🖼 Создать стикер-пак", callback_data="create_sticker")],
        [InlineKeyboardButton("✨ Создать эмодзи-пак", callback_data="create_emoji")],
        [InlineKeyboardButton("📋 Список созданных паков", callback_data="list_packs")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Что ты хочешь создать?", reply_markup=reply_markup)
    return CHOOSE_PACK_TYPE


# ─── /menu — возврат в меню через команду ─────────────────────────────────────
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🖼 Создать стикер-пак", callback_data="create_sticker")],
        [InlineKeyboardButton("✨ Создать эмодзи-пак", callback_data="create_emoji")],
        [InlineKeyboardButton("📋 Список созданных паков", callback_data="list_packs")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что ты хочешь создать?", reply_markup=reply_markup)
    return CHOOSE_PACK_TYPE


# ─── Список паков ─────────────────────────────────────────────────────────────
async def list_packs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    packs = context.bot_data.get(user_id, {}).get("packs", [])

    if not packs:
        text = "У тебя пока нет созданных паков."
    else:
        lines = []
        for i, p in enumerate(packs, 1):
            icon = "🖼" if p["type"] == "sticker" else "✨"
            lines.append(
                f"{i}. {icon} {p['name']} — /{p['link']} ({len(p['stickers'])} шт.)"
            )
        text = "📋 Твои паки:\n\n" + "\n".join(lines)

    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="begin")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_PACK_TYPE


# ─── Начало создания стикер-пака ──────────────────────────────────────────────
async def start_sticker_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["creating_type"] = "sticker"
    await query.edit_message_text("Напиши название своего набора:")
    return STICKER_PACK_NAME


# ─── Начало создания эмодзи-пака (заглушка) ───────────────────────────────────
async def start_emoji_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["creating_type"] = "emoji"
    await query.edit_message_text("Напиши название своего набора:")
    return STICKER_PACK_NAME


# ─── Получение названия пака ──────────────────────────────────────────────────
async def receive_pack_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    context.user_data["new_pack_name"] = name

    keyboard = [
        [InlineKeyboardButton("🎲 Пропустить (случайная ссылка)", callback_data="random_link")]
    ]
    await update.message.reply_text(
        "Придумай короткую ссылку на пак (английские буквы, цифры, без пробелов):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return STICKER_PACK_LINK


# ─── Генерация случайной ссылки ───────────────────────────────────────────────
async def use_random_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    link = random_link()
    context.user_data["new_pack_link"] = link

    await query.edit_message_text(
        f"Ссылка на пак: <code>{link}</code>\n\nТеперь отправь мне фото / видео / стикер / гифку для пака 👇",
        parse_mode="HTML",
    )
    return STICKER_ADDING


# ─── Пользователь ввёл ссылку вручную ────────────────────────────────────────
async def receive_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    link = update.message.text.strip()

    # Простая валидация
    if not link.replace("_", "").isalnum():
        await update.message.reply_text(
            "❌ Ссылка может содержать только английские буквы, цифры и _. Попробуй ещё раз:"
        )
        return STICKER_PACK_LINK

    context.user_data["new_pack_link"] = link
    await update.message.reply_text(
        f"Ссылка: <code>{link}</code>\n\nТеперь отправь мне фото / видео / стикер / гифку для пака 👇",
        parse_mode="HTML",
    )
    return STICKER_ADDING


# ─── Приём стикеров/медиа ─────────────────────────────────────────────────────
async def receive_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message

    # Определяем file_id в зависимости от типа медиа
    if msg.sticker:
        file_id = msg.sticker.file_id
        media_type = "sticker"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        media_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        media_type = "video"
    elif msg.animation:
        file_id = msg.animation.file_id
        media_type = "gif"
    elif msg.document:
        file_id = msg.document.file_id
        media_type = "document"
    else:
        await msg.reply_text("Пожалуйста, отправь фото, видео, стикер или гифку.")
        return STICKER_ADDING

    # Инициализируем временный список, если нужно
    if "new_pack_stickers" not in context.user_data:
        context.user_data["new_pack_stickers"] = []

    context.user_data["new_pack_stickers"].append(
        {"file_id": file_id, "type": media_type}
    )

    count = len(context.user_data["new_pack_stickers"])

    keyboard = [[InlineKeyboardButton("💾 Сохранить пак", callback_data="save_pack")]]
    await msg.reply_text(
        f"✅ Стикер добавлен в пак!\n"
        f"Всего в паке: {count} {'стикер' if count == 1 else 'стикеров' if 5 <= count % 100 <= 20 else ['стикера', 'стикера', 'стикера', 'стикера', 'стикеров'][min(count % 10, 4)]}\n\n"
        f"Продолжай отправлять или сохрани пак 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return STICKER_ADDING


# ─── Сохранение пака ──────────────────────────────────────────────────────────
async def save_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    # Сохраняем пак в bot_data (общее хранилище, ключ — user_id)
    if user_id not in context.bot_data:
        context.bot_data[user_id] = {"packs": []}

    pack = {
        "name": context.user_data.get("new_pack_name", "Без названия"),
        "link": context.user_data.get("new_pack_link", random_link()),
        "type": context.user_data.get("creating_type", "sticker"),
        "stickers": context.user_data.get("new_pack_stickers", []),
    }
    context.bot_data[user_id]["packs"].append(pack)

    # Очищаем временные данные
    for key in ("new_pack_name", "new_pack_link", "new_pack_stickers", "creating_type"):
        context.user_data.pop(key, None)

    await query.edit_message_text(
        f"🎉 Пак <b>{pack['name']}</b> сохранён!\n"
        f"Стикеров в паке: {len(pack['stickers'])}\n\n"
        f"/menu — вернуться в меню",
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ─── Отмена / fallback ────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено. /start — начать заново.")
    return ConversationHandler.END


# ─── Сборка приложения ────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu, pattern="^begin$"),
            ],
            CHOOSE_PACK_TYPE: [
                CallbackQueryHandler(main_menu, pattern="^begin$"),
                CallbackQueryHandler(start_sticker_pack, pattern="^create_sticker$"),
                CallbackQueryHandler(start_emoji_pack, pattern="^create_emoji$"),
                CallbackQueryHandler(list_packs, pattern="^list_packs$"),
            ],
            STICKER_PACK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_name),
            ],
            STICKER_PACK_LINK: [
                CallbackQueryHandler(use_random_link, pattern="^random_link$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_link),
            ],
            STICKER_ADDING: [
                CallbackQueryHandler(save_pack, pattern="^save_pack$"),
                MessageHandler(
                    (filters.PHOTO | filters.VIDEO | filters.Sticker.ALL | filters.ANIMATION | filters.Document.ALL),
                    receive_sticker,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", menu_command),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    # /menu вне диалога тоже работает
    app.add_handler(CommandHandler("menu", menu_command))

    logger.info("Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
