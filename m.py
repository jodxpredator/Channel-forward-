import logging
import asyncio
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Configure logging to see debug output in the console.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # Change to DEBUG for more details.
)

# --- Dummy Flask Web Server for Koyeb Health Checks ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def run_flask():
    # Listen on 0.0.0.0 so that the port is accessible externally.
    app.run(host="0.0.0.0", port=8000)

# --- Telegram Bot Code ---
class MediaGroupForwarder:
    def __init__(self, sources, destinations, delay=2.5):
        """
        :param sources: List of source channel IDs.
        :param destinations: List of destination channel IDs.
        :param delay: Delay in seconds to allow media groups to gather all messages.
        """
        self.sources = sources
        self.destinations = destinations
        self.media_groups = {}
        self.lock = asyncio.Lock()
        self.delay = delay

    async def handle_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logging.debug(f"Received update: {update}")

        # Process only channel posts.
        if not update.channel_post:
            logging.debug("Update is not a channel post. Ignoring.")
            return

        chat_id = update.channel_post.chat.id
        if chat_id not in self.sources:
            logging.debug(f"Channel {chat_id} is not in the source list. Ignoring.")
            return

        source_id = chat_id
        msg = update.channel_post
        media_group_id = msg.media_group_id

        if media_group_id:
            key = (source_id, media_group_id)
            async with self.lock:
                if key not in self.media_groups:
                    self.media_groups[key] = {'messages': [], 'task': None}
                    self.media_groups[key]['task'] = asyncio.create_task(
                        self.process_group(key, context, source_id)
                    )
                self.media_groups[key]['messages'].append(msg)
                logging.info(f"Added message {msg.message_id} to media group {media_group_id} from source {source_id}")
        else:
            await self.forward_single(msg, context, source_id)

    async def process_group(self, key, context: ContextTypes.DEFAULT_TYPE, source_id: int):
        await asyncio.sleep(self.delay)
        async with self.lock:
            if key not in self.media_groups:
                return

            messages = sorted(self.media_groups[key]['messages'], key=lambda x: x.message_id)
            message_ids = [m.message_id for m in messages]
            media_group_id = key[1]

            for dest_id in self.destinations:
                try:
                    await context.bot.forward_messages(
                        chat_id=dest_id,
                        from_chat_id=source_id,
                        message_ids=message_ids
                    )
                    logging.info(
                        f"Forwarded media group {media_group_id} (messages: {message_ids}) "
                        f"from source {source_id} to destination {dest_id}"
                    )
                except Exception as e:
                    logging.error(f"Error forwarding media group {media_group_id} to destination {dest_id}: {e}")

            del self.media_groups[key]

    async def forward_single(self, message, context: ContextTypes.DEFAULT_TYPE, source_id: int):
        for dest_id in self.destinations:
            try:
                await context.bot.forward_message(
                    chat_id=dest_id,
                    from_chat_id=source_id,
                    message_id=message.message_id
                )
                logging.info(
                    f"Forwarded single message {message.message_id} from source {source_id} to destination {dest_id}"
                )
            except Exception as e:
                logging.error(f"Error forwarding message {message.message_id} to destination {dest_id}: {e}")

if __name__ == '__main__':
    # Start the Flask web server in a separate thread.
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Define source and destination channel IDs.
    sources = [
        -1001859547091,  # First source channel ID
        -1002379836408   # Second source channel ID (if needed)
    ]
    destinations = [
        -1002402044558
    ]

    forwarder = MediaGroupForwarder(sources, destinations)
    
    # Build the Telegram application.
    application = ApplicationBuilder().token('7893173971:AAH7v3zT8KKX3gCtDdIrkL9PsffZodPiTSM').build()

    # Add a message handler to process all updates.
    application.add_handler(MessageHandler(filters.ALL, forwarder.handle_update))

    # Run polling. The Flask server is already running in a separate thread.
    application.run_polling()
