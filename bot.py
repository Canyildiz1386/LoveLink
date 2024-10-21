import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)
from pymongo import MongoClient
from geopy.geocoders import Nominatim

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = '7476580536:AAFhZS6bM63fWJcSyPn0KfFNpWT5Jh5t4vE'

REG_NAME, REG_AGE, REG_CITY, REG_CONFIRM_CITY, REG_PHOTO = range(5)
EDIT_NAME, EDIT_AGE, EDIT_CITY, EDIT_CONFIRM_CITY, EDIT_PHOTO = range(5, 10)

client = MongoClient('mongodb://localhost:27017/')
db = client['telegram_bot']
users_collection = db['users']

geolocator = Nominatim(user_agent="telegram_bot")

def create_user_directory():
    if not os.path.exists('user_photos'):
        os.makedirs('user_photos')

async def start(update: Update, context):
    user = update.effective_user
    existing_user = users_collection.find_one({'id': user.id})

    if update.message:
        message = update.message
    elif update.callback_query:
        message = update.callback_query.message

    if existing_user and existing_user.get('is_registered'):
        keyboard = [
            [InlineKeyboardButton('📋 Profile 📋', callback_data='show_profile')],
            [InlineKeyboardButton('❓ Help ❓', callback_data='show_help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(
            '🎉 Welcome back! 🎉\nWhat would you like to do?',
            reply_markup=reply_markup
        )
    else:
        await message.reply_text('😄 Hello! 😄\nWhat is your name?')
        users_collection.update_one(
            {'id': user.id},
            {'$set': {
                'id': user.id,
                'username': user.username,
                'status': 'online',
                'is_registered': False
            }},
            upsert=True
        )
        return REG_NAME

async def reg_name(update: Update, context):
    user = update.effective_user
    name = update.message.text
    context.user_data['name'] = name

    users_collection.update_one(
        {'id': user.id},
        {'$set': {'name': name}}
    )
    await update.message.reply_text(f'😁 Nice to meet you, {name}! 😁\nHow old are you?')
    return REG_AGE

async def reg_age(update: Update, context):
    user = update.effective_user
    age = update.message.text

    if not age.isdigit():
        await update.message.reply_text('🔢 Please enter a valid age using numbers. 🔢')
        return REG_AGE

    context.user_data['age'] = int(age)

    users_collection.update_one(
        {'id': user.id},
        {'$set': {'age': context.user_data['age']}}
    )
    await update.message.reply_text('🌆 Which city do you live in? 🌇')
    return REG_CITY

async def reg_city(update: Update, context):
    city_input = update.message.text
    context.user_data['city_input'] = city_input
    cities = geolocator.geocode(city_input, exactly_one=False, limit=5)

    if cities:
        context.user_data['city_options'] = cities
        keyboard = [
            [InlineKeyboardButton(city.address, callback_data=str(i))]
            for i, city in enumerate(cities)
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('🌆 Select your city 🌆:', reply_markup=reply_markup)
        return REG_CONFIRM_CITY
    else:
        await update.message.reply_text('😟 City not found, please try again 😟')
        return REG_CITY

async def reg_confirm_city(update: Update, context):
    query = update.callback_query
    await query.answer()

    try:
        city_index = int(query.data)
        selected_city = context.user_data['city_options'][city_index].address
        context.user_data['city'] = selected_city

        user = query.from_user
        users_collection.update_one({'id': user.id}, {'$set': {'city': selected_city}})

        await query.message.delete()
        await query.message.reply_text(f'😊 You selected {selected_city} 😊\nPlease send me your photo 🖼️🖼️')
        return REG_PHOTO
    except (IndexError, ValueError):
        await query.message.reply_text('😟 Invalid selection. Please try again 😟')
        return REG_CITY

async def reg_photo(update: Update, context):
    create_user_directory()

    try:
        user = update.effective_user

        if update.message and update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            photo_path = f'user_photos/{user.id}.jpg'
            await photo_file.download_to_drive(photo_path)

            context.user_data['photo'] = photo_path
            users_collection.update_one(
                {'id': user.id},
                {'$set': {
                    'photo': photo_path,
                    'is_registered': True
                }}
            )

            await show_profile(update, context)
            return ConversationHandler.END
        else:
            await update.message.reply_text('😟 Please send a valid photo. 😟')
            return REG_PHOTO

    except Exception as e:
        logger.error(f"Error processing photo for user {user.id if user else 'Unknown'}: {e}")
        await update.message.reply_text(f'😟 There was an error saving your photo: {str(e)}. Please try again. 😟')
        return REG_PHOTO

async def show_profile(update: Update, context):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    user_data = users_collection.find_one({'id': user.id})

    if user_data and 'photo' in user_data:
        photo_path = user_data['photo']
        caption = (
            f"📋 **Profile** 📋\n\n"
            f"📝 Name: {user_data['name']}\n"
            f"🔢 Age: {user_data['age']}\n"
            f"🌆 City: {user_data['city']}\n"
        )

        keyboard = [
            [InlineKeyboardButton('✏️ Edit Name ✏️', callback_data='edit_name')],
            [InlineKeyboardButton('🔢 Edit Age 🔢', callback_data='edit_age')],
            [InlineKeyboardButton('🌆 Edit City 🌆', callback_data='edit_city')],
            [InlineKeyboardButton('🖼️ Edit Photo 🖼️', callback_data='edit_photo')],
            [InlineKeyboardButton('🏠 Back to Home 🏠', callback_data='back_home')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.delete()

        with open(photo_path, 'rb') as photo:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo, 
                caption=caption, 
                reply_markup=reply_markup
            )

async def show_help(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton('🏠 Back to Home 🏠', callback_data='back_home')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    help_message = (
        "❓ **Help Section** ❓\n\n"
        "This bot helps you manage your profile. Here’s what you can do:\n"
        "• View and edit your profile.\n"
        "• Update your name, age, city, or photo.\n"
        "• Use the buttons to navigate through different options."
    )
    
    await query.edit_message_text(help_message, reply_markup=reply_markup)

async def back_home(update: Update, context):
    query = update.callback_query
    await query.message.delete()
    await start(update, context)

async def edit_name(update: Update, context):
    query = update.callback_query
    user = query.from_user
    current_name = users_collection.find_one({'id': user.id})['name']
    await query.answer()
    await query.message.delete()
    await query.message.reply_text(f'✏️ Please enter your new name 😄 (Current: {current_name}) ✏️')
    return EDIT_NAME

async def process_edit_name(update: Update, context):
    user = update.effective_user
    new_name = update.message.text
    context.user_data['name'] = new_name

    users_collection.update_one({'id': user.id}, {'$set': {'name': new_name}})
    keyboard = [[InlineKeyboardButton('🏠 Back to Home 🏠', callback_data='back_home')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f'🎉 Your name has been updated to {new_name}! 🎉', reply_markup=reply_markup)
    return ConversationHandler.END

async def edit_age(update: Update, context):
    query = update.callback_query
    user = query.from_user
    current_age = users_collection.find_one({'id': user.id})['age']
    await query.answer()
    await query.message.delete()
    await query.message.reply_text(f'🔢 Please enter your new age 🔢 (Current: {current_age})')
    return EDIT_AGE

async def process_edit_age(update: Update, context):
    user = update.effective_user
    new_age = update.message.text

    if not new_age.isdigit():
        await update.message.reply_text('🔢 Please enter a valid age using numbers. 🔢')
        return EDIT_AGE

    context.user_data['age'] = int(new_age)

    users_collection.update_one({'id': user.id}, {'$set': {'age': context.user_data['age']}})
    keyboard = [[InlineKeyboardButton('🏠 Back to Home 🏠', callback_data='back_home')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f'🎉 Your age has been updated to {new_age}! 🎉', reply_markup=reply_markup)
    return ConversationHandler.END

async def edit_city(update: Update, context):
    query = update.callback_query
    user = query.from_user
    current_city = users_collection.find_one({'id': user.id})['city']
    await query.answer()
    await query.message.delete()
    await query.message.reply_text(f'🌆 Please enter your new city 🌆 (Current: {current_city})')
    return EDIT_CITY

async def process_edit_city(update: Update, context):
    city_input = update.message.text
    context.user_data['city_input'] = city_input
    cities = geolocator.geocode(city_input, exactly_one=False, limit=5)

    if cities:
        context.user_data['city_options'] = cities
        keyboard = [
            [InlineKeyboardButton(city.address, callback_data=str(i))]
            for i, city in enumerate(cities)
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('🌆 Select your new city 🌆:', reply_markup=reply_markup)
        return EDIT_CONFIRM_CITY
    else:
        await update.message.reply_text('😟 City not found, please try again 😟')
        return EDIT_CITY

async def process_edit_confirm_city(update: Update, context):
    query = update.callback_query
    await query.answer()

    try:
        city_index = int(query.data)
        selected_city = context.user_data['city_options'][city_index].address
        context.user_data['city'] = selected_city

        user = query.from_user
        users_collection.update_one({'id': user.id}, {'$set': {'city': selected_city}})
        keyboard = [[InlineKeyboardButton('🏠 Back to Home 🏠', callback_data='back_home')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.delete()
        await query.message.reply_text(f'🎉 Your city has been updated to {selected_city}! 🎉', reply_markup=reply_markup)
        return ConversationHandler.END
    except (IndexError, ValueError):
        await query.message.reply_text('😟 Invalid selection. Please try again 😟')
        return EDIT_CITY

async def edit_photo(update: Update, context):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    await query.message.delete()
    await query.message.reply_text('🖼️ Please send me your new photo 🖼️')
    return EDIT_PHOTO

async def process_edit_photo(update: Update, context):
    user = update.effective_user
    create_user_directory()

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_path = f'user_photos/{user.id}.jpg'
        await photo_file.download_to_drive(photo_path)

        context.user_data['photo'] = photo_path

        users_collection.update_one(
            {'id': user.id},
            {'$set': {
                'photo': photo_path
            }}
        )
        keyboard = [[InlineKeyboardButton('🏠 Back to Home 🏠', callback_data='back_home')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('🎉 Your profile photo has been updated! 🎉', reply_markup=reply_markup)
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error processing photo for user {user.id}: {e}")
        await update.message.reply_text('😟 There was an error saving your photo, please try again. 😟')
        return EDIT_PHOTO

async def cancel(update: Update, context):
    await update.message.reply_text('😊 Operation cancelled. 😊', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    application = Application.builder().token(TOKEN).build()

    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_age)],
            REG_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_city)],
            REG_CONFIRM_CITY: [CallbackQueryHandler(reg_confirm_city)],
            REG_PHOTO: [MessageHandler(filters.PHOTO, reg_photo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    edit_name_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_name, pattern='^edit_name$')],
        states={
            EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    edit_age_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_age, pattern='^edit_age$')],
        states={
            EDIT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_age)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(reg_conv_handler)
    application.add_handler(edit_name_conv_handler)
    application.add_handler(edit_age_conv_handler)
    application.add_handler(CallbackQueryHandler(show_profile, pattern='^show_profile$'))
    
    edit_city_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_city, pattern='^edit_city$')],
        states={
            EDIT_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_city)],
            EDIT_CONFIRM_CITY: [CallbackQueryHandler(process_edit_confirm_city)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    edit_photo_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_photo, pattern='^edit_photo$')],
        states={
            EDIT_PHOTO: [MessageHandler(filters.PHOTO, process_edit_photo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(edit_city_conv_handler)
    application.add_handler(edit_photo_conv_handler)

    application.add_handler(CallbackQueryHandler(back_home, pattern='^back_home$'))
    application.add_handler(CallbackQueryHandler(show_help, pattern='^show_help$'))

    application.run_polling()

if __name__ == '__main__':
    main()
