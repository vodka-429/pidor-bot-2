import time
import uuid

from telegram import Update

from bot.app.models import KVItem
from bot.utils import ECallbackContext


# Key-Value commands
def get_cmd(update: Update, context: ECallbackContext):
    if len(context.args) < 1:
        list_cmd(update, context)
        return

    kv_item: KVItem = context.db_session.query(KVItem).filter_by(
        chat_id=update.effective_chat.id, key=context.args[0]).one_or_none()
    if kv_item is None:
        update.message.reply_text('no such key(')
    else:
        update.message.reply_text(kv_item.value)


def list_cmd(update: Update, context: ECallbackContext):
    ans = ""

    items = context.db_session.query(KVItem).filter_by(
        chat_id=update.effective_chat.id).all()
    if not items:
        update.effective_chat.send_message("no keys yet(")

    for i, item in enumerate(items, 1):
        # ans += "{}) {} - {}\n".format(i, item.key, item.value)
        line = "{}) {}\n".format(i, item.value)
        if (len(ans) + len(line)) > 4096:
            update.effective_chat.send_message(ans)
            ans = ""
            time.sleep(1)
        else:
            ans += line
    if ans:
        update.effective_chat.send_message(ans)


def set_cmd(update: Update, context: ECallbackContext):
    if context.args[0].startswith('key_'):
        key = context.args[0]
        value = " ".join(context.args[1:])
    else:
        key = 'key_' + uuid.uuid4().hex[:8]
        value = " ".join(context.args)

    kv_item: KVItem = context.db_session.query(KVItem).filter_by(
        chat_id=update.effective_chat.id,
        key=key).one_or_none()
    if kv_item is None:
        kv_item = KVItem(chat_id=update.effective_chat.id,
                         key=key,
                         value=value)
    else:
        kv_item.value = value
    context.db_session.add(kv_item)
    context.db_session.commit()
    update.message.reply_text(
        'Key {} successfully added'.format(key))


def del_cmd(update: Update, context: ECallbackContext):
    if len(context.args) < 1:
        update.message.reply_text('give me the keeeey')
    kv_item: KVItem = context.db_session.query(KVItem).filter_by(
        chat_id=update.effective_chat.id,
        key=context.args[0]).one_or_none()
    if kv_item is None:
        update.effective_chat.send_message('no such key')
    else:
        context.db_session.delete(kv_item)
        context.db_session.commit()
        update.effective_chat.send_message(
            'OK! Key {} successfully deleted'.format(context.args[0]))
