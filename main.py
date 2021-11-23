"""
author: hexsix
date: 2021/11/22
description: 写给 heroku 云服务
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List

import httpx
import feedparser
import redis


REDIS = redis.from_url(os.environ['REDIS_URL'])
logger = logging.getLogger('app')
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


def download() -> Any:
    logger.info('Downloading RSS ...')
    for retry in range(3):
        logger.info(f'The {retry + 1}th attempt, 3 attempts in total.')
        try:
            with httpx.Client() as client:
                response = client.get(os.environ['RSS_URL'], timeout=10.0)
            rss_json = feedparser.parse(response.text)
            if rss_json:
                break
        except:
            logger.warning('Failed to download RSS, the next attempt will start in 6 seconds.')
            time.sleep(6)
    if not rss_json:
        raise Exception('Failed to download RSS.')
    logger.info('Succeed to download RSS.')
    return rss_json


def parse(rss_json: Dict) -> List[Dict[str, Any]]:
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
        except:
            continue
    logger.info(f"Parse RSS End. {len(items)}/{len(rss_json['entries'])} Succeed.")
    return items


def construct_json_serialized(item: Dict[str, Any]) -> str:
    caption = f"title: {item['title']}\nauthor: {item['author']}\nlink: {item['link']}"
    medias = []
    for i in range(min(len(item['photo_urls']), 3)):
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


def filter(item: Dict[str, Any]) -> bool:
    if REDIS.exists(item['post_id']):
        return True
    return False


def send(pid: str, json_serialized: str) -> bool:
    target = f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMediaGroup"
    params = {
        'chat_id': os.environ['CHAT_ID'],
        'media': json_serialized
    }
    for retry in range(3):
        logger.info(f'The {retry + 1}th attempt, 3 attempts in total.')
        try:
            with httpx.Client() as client:
                response = client.post(target, params=params)
            logger.info(f'Telegram api returns {response.json()}')
            if response.json()['ok']:
                logger.info(f'Succeed to send {pid}.')
                return True
        except:
            pass
        logger.warning(f'Failed to send {pid}, the next attempt will start in 6 seconds.')
        time.sleep(6)
    logger.error(f'Failed to send {pid}.')
    return False


def main():
    logger.info('============ App Start ============')
    rss_json = download()
    items = parse(rss_json)
    filtered_items = [item for item in items if not filter(item)]
    logger.info(f'{len(filtered_items)}/{len(items)} Filter.')
    count = 0
    for item in filtered_items:
        json_serialized = construct_json_serialized(item)
        if send(item['pid'], json_serialized):
            REDIS.set(item['pid'], 'sent', ex=2678400)  # expire after a month
            count += 1
    logger.info(f'{count}/{len(filtered_items)} Succeed.')
    logger.info('============ App End ============')


if __name__ == '__main__':
    main()
