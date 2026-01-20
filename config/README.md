# API Keys Configuration

This file contains API keys for external services. **DO NOT commit with real keys!**

## Setup

1. Copy `api_keys.json.example` to `api_keys.json`
2. Fill in your API keys

## Webshare Proxy API

Get your API key from: https://proxy.webshare.io/

```json
{
  "webshare": {
    "api_keys": ["your_key_1", "your_key_2"]
  }
}
```

## Telegram API

Get from: https://my.telegram.org/apps

```json
{
  "telegram": {
    "api_id": "1234567",
    "api_hash": "your_hash_here"
  }
}
```
