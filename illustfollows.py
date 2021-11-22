#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
------------------------------------
# @FileName    :illustfollows.py
# @Time        :2021/11/21
# @Author      :hexsix
# @description :
------------------------------------
"""

import asyncio
import json
import os
import pickle
import re
from typing import Dict, List, Any
import traceback

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import feedparser
import httpx

from log_handler import logger


config = json.load(open('config.json', 'r', encoding='utf8'))
rss_url = config['rss_url']


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
        self.minimize()
        pickle.dump(self.already_sent, open(self.filepath, 'wb'))

    def add(self, item):
        self.already_sent.add(item)

    def minimize(self):
        pass


already_sent = Pickle()


async def download() -> Dict:
    logger.info('Downloading RSS ...')
    rss_json = None
    for retry in range(3):
        logger.info(f'The {retry + 1}th attempt, 3 attempts in total.')
        try:
            if config['use_proxies']:
                async with httpx.AsyncClient(proxies=config['proxies']) as client:
                    r = await client.get(rss_url, timeout=10.0)
            else:
                async with httpx.AsyncClient() as client:
                    r = await client.get(rss_url, timeout=10.0)
            rss_json = feedparser.parse(r.text)
        except:
            logger.warning('Failed to download RSS, the next attempt will start in 2 seconds.')
            await asyncio.sleep(6)
        else:
            break
    if not rss_json:
        logger.error('Failed to download RSS.')
        return dict()
    logger.info('Succeed to download RSS.')
    return rss_json


async def parse(rss_json: Dict) -> List[Dict[str, Any]]:
    logger.info('Parsing RSS ...')
    items = []
    for entry in rss_json['entries']:
        try:
            item = dict()
            item['title'] = entry['title']
            item['link'] = entry['link']
            item['author'] = entry['author']
            item['summary'] = entry['summary']
            item['pid'] = item['link'].split('/')[-1]
            item['photo_urls'] = re.findall(r'https://i.pixiv.cat/[^"]*', item['summary'])
            items.append(item)
        except Exception as e:
            continue
    logger.info(f'Parse RSS End.')
    return items


def construct_json_serialized(item: Dict[str, Any]) -> str:
    caption = f"title: {item['title']}\nauthor: {item['author']}\nlink: {item['link']}"
    medias = []
    for i in range(min(len(item['photo_urls']), 6)):
        if i == 0:
            medias.append({
                'type': 'photo',
                'media': item['photo_urls'][i],
                'caption': caption
            })
        else:
            medias.append({
                'type': 'photo',
                'media': item['photo_urls'][i]
            })
    json_serialized = json.dumps(medias, ensure_ascii=True)
    return json_serialized


async def send(json_serialized: str) -> bool:
    target = f"https://api.telegram.org/bot{config['bot_token']}/sendMediaGroup"
    params = {
        'chat_id': config['chat_id'],
        'media': json_serialized
    }
    for _ in range(3):
        try:
            if config['use_proxies']:
                async with httpx.AsyncClient(proxies=config['proxies']) as client:
                    r = await client.post(target, params=params)
            else:
                async with httpx.AsyncClient() as client:
                    r = await client.post(target, params=params)
            if r.json()['ok']:
                logger.info(f'Succeed to send.')
                return True
            elif r.json()['error_code'] == 429:
                # Too Many Requests: retry after 30s
                logger.info(f'Too Many Requests')
                await asyncio.sleep(31)
            else:
                if _ == 0:
                    logger.info(f'Bad response call telegram api {r.json()}')
                    logger.debug(f'json_serialized: {json_serialized}')
                await asyncio.sleep(6)
        except Exception as e:
            await asyncio.sleep(6)
    logger.error(f'Failed to send.')
    return False


async def main():
    logger.info('============ Crontab start ============')
    rss_json = await download()
    items = await parse(rss_json)
    already_sent.load()
    for item in items:
        if item['pid'] in already_sent:
            continue
        json_serialized = construct_json_serialized(item)
        if await send(json_serialized):
            already_sent.add(item['pid'])
            already_sent.dump()
    logger.info('============ Crontab end ============')


if __name__ == '__main__':
    scheduler = AsyncIOScheduler()
    scheduler.add_job(main, 'cron', hour='*', minute=0)
    scheduler.start()
    asyncio.get_event_loop().run_forever()
