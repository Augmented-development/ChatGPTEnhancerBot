# a version that combines all parts of the code. MVP
# uses 2_openai_chatbot
# and semi-smart telegram bot on a better platform that just default python api.


"""a simple bot that just forwards queries to openai and sends the response"""
import logging
import os
import time
import traceback
from typing import Dict

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from chatgpt_enhancer_bot.openai_chatbot import telegram_commands_registry
from openai_chatbot import ChatBot
from utils import get_secrets, generate_funny_reason, generate_funny_consolation

secrets = get_secrets()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

TOUCH_FILE_PATH = os.path.expanduser('~/heartbeat/chatgpt_enhancer_last_alive')
os.makedirs(os.path.dirname(TOUCH_FILE_PATH), exist_ok=True)

bots = {}  # type: Dict[str, ChatBot]

default_model = "text-ada:001"

history_dir = os.path.join(os.path.dirname(__file__), 'history')
os.makedirs(history_dir, exist_ok=True)


def get_bot(user):
    if user not in bots:
        history_path = os.path.join(history_dir, f'history_{user}.json')
        new_bot = ChatBot(conversations_history_path=history_path, model=default_model, user=user)
        bots[user] = new_bot
    return bots[user]


def chat(prompt, user):
    bot = get_bot(user)
    return bot.chat(prompt=prompt)


def chat_handler(update: Update, context: CallbackContext) -> None:
    response = chat(update.message.text, user=update.effective_user.username)
    update.message.reply_markdown_v2(response)


# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


# Define the error handler function
def error_handler(update: Update, context: CallbackContext):
    if isinstance(context.error, NetworkError):
        # Do something when the "Bad Gateway" error occurs
        logger.info('NetworkError occurred')
        time.sleep(1)

    else:
        # todo: send error to admin - petrlavrov
        # for now: just log
        logger.warning(traceback.format_exc())

    # Give user the info? Naah, let's rather joke around
    funny_reason = generate_funny_reason().lower()
    update.message.reply_text(
        f"Sorry, {funny_reason}. You can use /dev command to see the traceback.. For now - Retrying")
    # todo: create a /dev command to get the traceback
    prompt = update.message.text
    user = update.effective_user.username
    try:
        # todo: retrying the 'new_chat' command is stupid
        # do I need to process the commands differently? I have a special parser inside chat() method.. should be ok
        time.sleep(5)  # give it some time...
        chat(prompt, user)
    except Exception as e:
        bot = get_bot(user)
        bot.save_traceback(traceback.format_exc())
        update.message.reply_text(f"Nah, it's hopeless.. {generate_funny_consolation().lower()}")


def make_command_handler(method_name):
    def command_handler(update: Update, context: CallbackContext) -> None:
        user = update.effective_user.username
        bot = get_bot(user)
        method = bot.__getattribute__(method_name)

        prompt = update.message.text
        command, qargs, qkwargs = bot.parse_query(prompt)
        result = method(*qargs, **qkwargs)  # todo: parse kwargs from the command
        if not result:
            result = f"Command {command} finished successfully"
        update.message.reply_markdown_v2(result)

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
        function_name = telegram_commands_registry.get_function(command)
        command_handler = make_command_handler(function_name)
        dispatcher.add_handler(CommandHandler(command.lstrip('/'), command_handler))

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
