# a version that combines all parts of the code. MVP
# uses 2_openai_chatbot
# and semi-smart telegram bot on a better platform that just default python api.


"""a simple bot that just forwards queries to openai and sends the response"""
import logging
import os
import time
import traceback
from typing import Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from telegram.utils.helpers import escape_markdown

from .openai_chatbot import ChatBot, telegram_commands_registry
from .utils import get_secrets, generate_funny_reason, generate_funny_consolation, split_to_code_blocks, parse_query

secrets = get_secrets()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

TOUCH_FILE_PATH = os.path.expanduser('~/heartbeat/chatgpt_enhancer_last_alive')
os.makedirs(os.path.dirname(TOUCH_FILE_PATH), exist_ok=True)

bot_registry = {}  # type: Dict[str, ChatBot]

default_model = "text-ada:001"

history_dir = os.path.join(os.path.dirname(__file__), 'history')
os.makedirs(history_dir, exist_ok=True)


def get_bot(user) -> ChatBot:
    if user not in bot_registry.keys():
        history_path = os.path.join(history_dir, f'history_{user}.json')
        new_bot = ChatBot(conversations_history_path=history_path, model=default_model, user=user)
        bot_registry[user] = new_bot
    return bot_registry[user]


def send_message_with_markdown(message_to_reply_to, message, enable_markdown=False, escape_markdown_flag=False):
    if enable_markdown:
        if escape_markdown_flag:
            message = escape_markdown(message, version=2)
        try:
            return message_to_reply_to.reply_markdown_v2(message)
        except:  # can't parse entities
            error_message = "Unable to parse markdown in this response. Here's the raw text:\n\n" + message
            return message_to_reply_to.reply_text(error_message)
    else:
        return message_to_reply_to.reply_text(message)


def send_message_to_user(message_to_reply_to, message):
    # just always send as plain text for now
    # step 1: tell the bot to always use ``` for the code
    # step 2: parse the code blocks in text
    blocks = split_to_code_blocks(message)
    sent_messages = []
    for block in blocks:
        if block['is_code_block']:
            text = f"```{block['text']}```"
        else:
            text = block['text']
        msg = send_message_with_markdown(message_to_reply_to, text, enable_markdown=block['is_code_block'])
        sent_messages.append(msg)

    if len(sent_messages) == 1:
        # todo: add support for multiple messages everywhere where this is used
        return sent_messages[0]
    return sent_messages


def chat_handler(update: Update, context: CallbackContext) -> None:
    user = update.effective_user.username
    bot = get_bot(user)
    reply = bot.chat(prompt=update.message.text)
    # send_message_to_user(update.message, reply, enable_markdown=bot.markdown_enabled, escape_markdown_flag=False)
    send_message_to_user(update.message, reply)


def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


def send_menu(update, context, menu: dict, message, n_cols=2):
    button_list = [InlineKeyboardButton(k, callback_data=v) for k, v in menu.items()]
    reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=n_cols))
    update.message.reply_text(message, reply_markup=reply_markup)


def topics_menu_handler(update: Update, context: CallbackContext) -> None:
    user = update.effective_user.username
    bot = get_bot(user)
    send_menu(update, context, bot.get_topics_menu(), "Choose a topic to switch to:")


def button_callback(update, context):
    prompt = update.callback_query.data
    user = update.effective_user.username
    bot = get_bot(user)

    if prompt.startswith('/'):
        command, qargs, qkwargs = parse_query(prompt)
        method_name = bot.command_registry.get_function(command)
        method = getattr(bot, method_name)
        result = method(*qargs, **qkwargs)
        if not result:
            result = f"Command {command} finished successfully"
    else:
        result = bot.chat(prompt)

    # markdown_safe =
    # escape_markdown_flag = not markdown_safe
    # response_message = send_message_to_user(update.effective_message, result, enable_markdown=bot.markdown_enabled,
    #                                         escape_markdown_flag=escape_markdown_flag)
    response_message = send_message_to_user(update.effective_message, result)
    if result.startswith("Active topic"):
        response_message.pin()


# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


def error_handler(update: Update, context: CallbackContext):
    # step 1: Save the error, so that /dev command can show it
    # What I want to save: timestamp, error, traceback, prompt
    user = update.effective_user.username
    bot = get_bot(user)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    prompt = None
    if update.message:
        prompt = update.message.text
    elif update.callback_query:
        prompt = update.callback_query.data
    bot.save_error(timestamp=timestamp, error=context.error, traceback=traceback.format_exc(),
                   message_text=prompt)
    # todo: make save_error also save error to file somewhere
    logger.warning(traceback.format_exc())

    # # step 1.5: todo, retry after 1 second
    # time.sleep(1)
    # prompt = update.message.text
    # try:
    #     # todo: retrying the 'new_chat' command is stupid
    #     # do I need to process the commands differently? I have a special parser inside chat() method.. should be ok
    #     chat(prompt, user)
    # except Exception as e:
    #     bot = get_bot(user)
    #     bot.save_traceback(traceback.format_exc())
    #     update.message.reply_text(f"Nah, it's hopeless.. {generate_funny_consolation().lower()}")

    # step 2: Send a funny reason to the user, (but also an error message)
    # Give user the info? Naah, let's rather joke around
    funny_reason = generate_funny_reason().lower()
    funny_consolation = generate_funny_consolation().lower()
    error_message = f"""Sorry, seems {funny_reason}. 
There was an error: {context.error}. 
You can use /error command to see the traceback.. or bump @petr_lavrov about it
Please, accept my sincere apologies. And.. {funny_consolation}.
If the error persists, you can also try /new_chat command to start a new conversation.
"""
    # if bot.markdown_enabled:
    #     error_message += "\n Or /disable_markdown to disable markdown in this chat"
    update.message.reply_text(error_message)


ANNOUNCEMENT_TEMPLATE = """
Hey, this is an announcement from @petr_lavrov.
{message}
P.s. yes, I am shamelessly abusing my powers to send you this message.
AND I HAVE NOT YET IMPLEMENTED THE OPTION TO DISABLE THIS MESSAGING
Please use /stop_announcements command to stop receiving these messages.
Please use /stop command to stop EVERYTHING.
"""


def announce_command(update: Update, context: CallbackContext):
    user = update.effective_user.username
    if user == "petr_lavrov":
        message = update.message.text
        message = message.replace("/announce", "").strip()
        message = ANNOUNCEMENT_TEMPLATE.format(message=message)
        for user in bot_registry.values():
            # send_message(user, message)
            # todo: implement user registry! Can't send messages to users without that!
            raise NotImplementedError
    else:
        update.message.reply_text("Haaa, you sneaky! You can't do that!")


def make_command_handler(method_name):
    def command_handler(update: Update, context: CallbackContext) -> None:
        user = update.effective_user.username
        bot = get_bot(user)
        method = bot.__getattribute__(method_name)

        prompt = update.message.text
        command, qargs, qkwargs = parse_query(prompt)
        # todo: if necessary args are missing, ask for them or at least handle the exception gracefully
        result = method(*qargs, **qkwargs)  # todo: parse kwargs from the command
        if not result:
            result = f"Command {command} finished successfully"
        # escape_markdown_flag = not bot.command_registry.is_markdown_safe(command)
        # response_message = send_message_to_user(update.effective_message, result, enable_markdown=bot.markdown_enabled,
        #                                         escape_markdown_flag=escape_markdown_flag)
        response_message = send_message_to_user(update.effective_message, result)
        if result.startswith("Active topic"):
            response_message.pin()

    return command_handler


def main(expensive: bool) -> None:
    """
    Start the bot
    :param expensive: Use 'text-davinci-003' model instead of 'text-ada:001'
    :return:
    """
    # Create the Updater and pass it your bot's token.
    token = secrets["telegram_api_token"]
    updater = Updater(token)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    globals()['default_model'] = "text-davinci-003" if expensive else "text-ada:001"
    # on non command i.e message - echo the message on Telegram
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, chat_handler))

    for command in telegram_commands_registry.list_commands():
        match command:
            case "/get_topics_menu":
                command_handler = topics_menu_handler
            case other:
                function_name = telegram_commands_registry.get_function(command)
                command_handler = make_command_handler(function_name)
        dispatcher.add_handler(CommandHandler(command.lstrip('/'), command_handler))
    dispatcher.add_handler(CommandHandler("/announce", announce_command))

    # Add the callback handler to the dispatcher
    dispatcher.add_handler(CallbackQueryHandler(button_callback))

    # Update commands list
    commands = [BotCommand(command, telegram_commands_registry.get_description(command)) for command in
                telegram_commands_registry.list_commands()]
    dispatcher.bot.set_my_commands(commands)

    # Add the error handler to the dispatcher
    dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    count = 0
    while True:
        time.sleep(1)

        # heartbeat
        count += 1
        if count % 60 == 0:
            # touch the touch file
            with open(TOUCH_FILE_PATH, 'w'):
                pass


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--expensive", action="store_true",
                        help="use expensive calculation - 'text-davinci-003' model instead of 'text-ada:001' ")
    args = parser.parse_args()

    main(expensive=args.expensive)
