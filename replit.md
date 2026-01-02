# Telegram Enseigne Bot

## Overview
A Telegram bot that predicts card suits (enseignes) using:
1. Static rules - Predefined patterns
2. INTER mode (AI) - Learns from real game data

## Project Structure
- `main.py` - Flask server entry point with webhook handling and scheduled tasks
- `bot.py` - TelegramBot class for Telegram API interactions
- `handlers.py` - Command handlers and update processing
- `card_predictor.py` - Core prediction logic with static and AI rules
- `config.py` - Configuration management

## Running the App
The bot runs a Flask server on port 5000 that receives Telegram webhook updates.

### Required Environment Variables
- `BOT_TOKEN` - Your Telegram bot token (required)
- `WEBHOOK_URL` - Optional, auto-detected on Replit

### Commands
- `/start` - Welcome message
- `/stat` - Bot status
- `/inter status` - View AI rules
- `/inter activate` - Enable AI mode
- `/inter default` - Use static rules
- `/collect` - View collected data
- `/reset` - Reset predictions
- `/config` - Configure channels
- `/deploy` - Download deployment package

## Dependencies
- Flask - Web framework
- APScheduler - Scheduled tasks
- requests - HTTP client
- pytz - Timezone handling

## Deployment
Configured to work with Render.com and Replit. Uses port 5000 on Replit.
