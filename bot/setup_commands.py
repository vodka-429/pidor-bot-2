import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot

commands = [
    # ('slap', 'simulate /slap command from IRC'),
    # ('me', 'simulate /me command from IRC'),
    # ('shrug', 'shrug ¯\_(ツ)_/¯'),
    # ('google', '<query> let me google that for you'),
    ('get', '<key> get specific entry by key'),
    ('list', 'list entries for current chat'),
    ('set', '<key on none> <value> set specific value for key'),
    ('del', '<key> remove specific key'),
    ('pidor', 'play the game, see /pidorules first'),
    ('pidorules', 'POTD game rules'),
    ('pidoreg', 'register to the POTD game'),
    ('pidoregmany', 'register many users to the POTD game'),
    ('pidorunreg', 'unregister from the POTD game'),
    ('pidorstats', 'POTD game stats for this year'),
    ('pidorall', 'POTD game stats for all time'),
    ('pidorme', 'POTD personal stats'),
    ('pidormissed', 'show missed days in current year'),
    ('pidorfinal', 'start final voting for missed days (Dec 29-30)'),
    ('pidorfinalstatus', 'show final voting status'),
    ('pidorfinalclose', 'close final voting (admins only)'),
    ('pidorcoinsme', 'show your pidorcoin balance'),
    ('pidorcoinsstats', 'show pidorcoin stats for current year'),
    ('pidorcoinsall', 'show pidorcoin stats for all time'),
    # ('meme', 'get some random meme'),
    # ('memeru', 'get some random russian meme'),
    # ('ttvideo', 'get video from tiktok'),
    # ('ttlink', 'get depersonalized tiktok link'),
    # ('about', 'some info about github repo'),
]

async def main():
    load_dotenv()
    async with Bot(os.environ['TELEGRAM_BOT_API_SECRET']) as bot:
        await bot.delete_my_commands()
        # Setup similar commands for both 'en' and 'ru' users
        await bot.set_my_commands(commands)
        bot_info = await bot.get_me()
        print('Updated commands for', bot_info.username)

if __name__ == '__main__':
    asyncio.run(main())
