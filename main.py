"""
author: hexsix
date: 2021/11/22
description: 写给 heroku 云服务
"""

import os
import re
import time
from typing import Any, Dict, List

import httpx
import feedparser
import redis


REDIS = redis.from_url(os.environ['REDIS_URL'])


def download() -> Any:
    print('Downloading RSS ...')
    for retry in range(3):
        print(f'The {retry + 1}th attempt, 3 attempts in total.')
        try:
            with httpx.Client() as client:
                response = client.get(os.environ['RSS_URL'], timeout=10.0)
            rss_json = feedparser.parse(response.text)
            if rss_json:
                break
        except Exception:
            print('Failed to download RSS, '
                  'the next attempt will start in 6 seconds.')
            time.sleep(6)
    if not rss_json:
        raise Exception('Failed to download RSS.')
    print('Succeed to download RSS.\n')
    return rss_json


def parse(rss_json: Dict) -> List[Dict[str, Any]]:
    print('Parsing RSS ...')
    items = []
    for entry in rss_json['entries']:
        try:
            item = dict()
            item['title'] = entry['title']
            item['link'] = entry['link']
            item['author'] = entry['author']
            item['summary'] = entry['summary']
            item['pid'] = item['link'].split('/')[-1]
            item['photo_urls'] = re.findall(r'https://i.pixiv.cat/[^"]*',
                                            item['summary'])
            items.append(item)
        except Exception as e:
            print(f'Exception: {e}')
            continue
    print(f"Parse RSS End. {len(items)}/{len(rss_json['entries'])} Succeed.\n")
    return items


def filter(item: Dict[str, Any]) -> bool:
    if REDIS.exists(item['pid']):
        return True
    return False


def send(item: Dict[str, Any]) -> bool:
    pid = item['pid']
    print(f"Send pid: {pid} ...")
    target = f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage"
    caption = f"title: {item['title']}\nauthor: {item['author']}\nlink: {item['link']}"
    params = {
        'chat_id': os.environ['CHAT_ID'],
        'text': caption
    }
    try:
        with httpx.Client() as client:
            response = client.post(target, params=params)
        if response.json()['ok']:
            print(f'Succeed to send {pid}.\n')
            return True
        else:
            print(f'Telegram api returns {response.json()}')
            print(f'caption: {caption}')
    except Exception as e:
        print(f'Exception: {e}')
        pass
    print(f'Failed to send {pid}.\n')
    return False


def redis_set(pid: str) -> bool:
    for retry in range(5):
        print(f'The {retry + 1}th attempt to set redis, 5 attempts in total.')
        try:
            if REDIS.set(pid, 'sent', ex=2678400):  # expire after a month
                print(f'Succeed to set redis {pid}.\n')
                return True
        except Exception:
            print('Failed to set redis, '
                  'the next attempt will start in 6 seconds.')
            time.sleep(6)
    print(f'Failed to set redis, {pid} may be sent twice.\n')
    return False


def main():
    print('============ App Start ============')
    rss_json = download()
    items = parse(rss_json)
    filtered_items = [item for item in items if not filter(item)]
    print(f'{len(filtered_items)}/{len(items)} filtered by already sent.\n')
    count = 0
    for item in filtered_items:
        if send(item):
            redis_set(item['pid'])
            count += 1
            time.sleep(10)
    print(f'{count}/{len(filtered_items)} Succeed.')
    print('============ App End ============')


if __name__ == '__main__':
    main()
