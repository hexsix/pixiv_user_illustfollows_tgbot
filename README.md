# A telegram bot for rsshub route: /pixiv/user/illustfollows

## Usage

1. Ask bot father to create a bot and get token
2. Create a group for you and bot, say to bot "/hello @bot"
3. Open "https://api.telegram.org/bot{token}/getUpdates" and get chat_id
4. The create an app on heroku
5. Add Config Var below on heroku settings
6. Install Add-on Heroku Scheduler, it is free
7. Install Add-on Heroku Redis, it is free too
8. Finally run Scheduler as you like

## Config Vars

```txt
RSS_URL=https://rsshub.app/pixiv/user/illustfollows
TG_TOKEN=1234567890:abcdefghijklmnopqrstuvwxyz
CHAT_ID=-0987654321
REDIS_URL will be automatically added
```

## WARNING

Only for self-hosted RSSHub
