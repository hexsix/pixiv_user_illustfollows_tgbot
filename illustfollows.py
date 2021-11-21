import asyncio
from io import BytesIO
import json
import os
import pickle
import re
import ssl
import time
import datetime
import traceback

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import feedparser
import httpx
from PIL import Image

config = json.load(open('config.json', 'r', encoding='utf8'))
ssl_context = httpx.create_ssl_context()
ssl_context.options ^= ssl.OP_NO_TLSv1  # Enable TLS 1.0 back


def now():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())


class Pickle:
    filepath: str
    already_sent: set

    def __init__(self):
        self.filepath = config['pkl_filepath']

    def __contains__(self, item):
        return item in self.already_sent

    def load(self):
        if os.path.exists(self.filepath):
            self.already_sent = pickle.load(open(self.filepath, 'rb'))
        else:
            self.already_sent = set()

    def dump(self):
        self.clear()
        pickle.dump(self.already_sent, open(self.filepath, 'wb'))

    def add(self, item):
        self.already_sent.add(item)

    def clear(self):
        pass


already_sent = Pickle()


class Illustration:
    pid: str
    url: str
    filename: str

    def __init__(self, url: str):
        print(url)
        self.pid = url.split('/')[-1].split('.')[0]
        self.url = url
        if config['use_proxies']:
            with httpx.Client(proxies=config['proxies']) as client:
                response = client.get(self.url, timeout=100.0)
        else:
            with httpx.Client() as client:
                response = client.get(self.url, timeout=100.0)
        image = Image.open(BytesIO(response.content))
        image.thumbnail((4000, 4000))
        self.filename = f'{self.pid}.thumbnail'
        image.save(self.filename, 'JPEG')

    def delete(self):
        os.remove(self.filename)


class Rss:
    rss_url: str
    target: str

    def __init__(self):
        self.rss_url = config['rss_url']
        self.target = f"https://api.telegram.org/bot{config['bot_token']}" \
                      f"/sendMediaGroup?chat_id={config['chat_id']}"

    def log(self, text):
        print(f'{now()} {text}')

    async def _send(self, photos, caption):
        if not photos:
            return
        illus = []
        for photo in photos:
            try:
                illus.append(Illustration(photo))
            except Exception as e:
                self.log(traceback.format_exc())
                self.log(e)
                continue
        files = {}
        for i, illu in enumerate(illus):
            files[f'illu-{i}'] = open(illu.filename, 'rb')
        json_serialized = json.dumps([{
                'type': 'photo',
                'media': f'attach://illu-{i}',
                'caption': caption
            } for i in range(len(illus))], ensure_ascii=False)
        for _ in range(3):
            try:
                if config['use_proxies']:
                    async with httpx.AsyncClient(proxies=config['proxies']) as client:
                        r = await client.post(f'{self.target}&media={json_serialized}', files=files)
                else:
                    async with httpx.AsyncClient() as client:
                        r = await client.post(f'{self.target}&media={json_serialized}', files=files)
                if r.json()['ok']:
                    return True
                else:
                    self.log(r.json())
            except Exception as e:
                self.log(traceback.format_exc())
                self.log(e)
                await asyncio.sleep(2)
        self.log(f'[WARNING]: Failed to Send {photos}')
        return False

    async def run(self):
        self.log(f'[INFO]: Crontab Start ...')
        # download rss
        self.log(f'[INFO]: Downloading RSS ...')
        rss_json = None
        for _ in range(3):
            self.log(f'[INFO]: The {_ + 1}th attempt, 3 attempts in total.')
            try:
                if config['use_proxies']:
                    async with httpx.AsyncClient(proxies=config['proxies']) as client:
                        r = await client.get(self.rss_url, timeout=10.0)
                else:
                    async with httpx.AsyncClient() as client:
                        r = await client.get(self.rss_url, timeout=10.0)
                rss_json = feedparser.parse(r.text)
            except:
                self.log(f'[WARNING]: Failed to download RSS, the next attempt will start in 2 seconds.')
                await asyncio.sleep(2)
            else:
                break
        if not rss_json:
            self.log(f'[ERROR]: Failed to download RSS.')
            return
        self.log(f'[INFO]: Succeed to download RSS.')

        try:
            self.log(f'[INFO]: Loading already sent list ...')
            already_sent.load()
        except:
            self.log(f'[ERROR]: Failed to load already sent list.')
        else:
            self.log(f'[INFO]: Succeed to load already sent list.')

        # parse rss and send message
        self.log(f'[INFO]: Now send images ...')
        for entry in rss_json['entries']:
            try:
                title = entry['title']
                link = entry['link']
                author = entry['author']
                pid = link.split('/')[-1]
                summary = entry['summary']
                photo_urls = re.findall(r'https://pixiv.cat/[^"]*', summary)
                self.log(photo_urls)
                if pid in already_sent:
                    continue
                if await self._send(photo_urls, f'title: {title}\nauthor: {author}\nlink: {link}'):
                    already_sent.add(pid)
                    already_sent.dump()
                    self.log(f'[INFO]: Succeed to send {photo_urls}.')
            except Exception as e:
                self.log(traceback.format_exc())
                self.log(e)
                continue
        self.log(f'[INFO]: End.')


async def main():
    await Rss().run()


def temp():
    with httpx.Client(proxies=config['proxies']) as client:
        r = client.get(config['rss_url'])
        rss_json = feedparser.parse(r.text)
        json.dump(rss_json, open('sample.json', 'w', encoding='utf8'), indent=4, ensure_ascii=False)


if __name__ == '__main__':
    _now = datetime.datetime.now()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(main, 'cron', hour='*', minute=0)
    scheduler.start()
    asyncio.get_event_loop().run_forever()
