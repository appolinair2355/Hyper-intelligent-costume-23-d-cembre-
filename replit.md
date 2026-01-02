# Telegram Bot - Card Predictor

## Overview
A Telegram bot that predicts card suits (Enseigne) using static rules and machine learning (INTER mode). Built with Flask for webhook handling.

## Project Structure
- `main.py` - Main Flask app with webhook endpoints and scheduler
- `bot.py` - TelegramBot class for API interactions
- `handlers.py` - Command handlers and message processing
- `card_predictor.py` - Prediction logic with static and INTER (intelligent) rules
- `config.py` - Configuration management
- `iobo.zip` - Deployment package for Render.com

## How to Run
The bot runs as a Flask web server on port 5000. It requires:
- `BOT_TOKEN` - Your Telegram bot token (required secret)
- `WEBHOOK_URL` - Optional, auto-detected on Replit

## Bot Commands
- `/start` - Welcome message
- `/stat` - Bot status
- `/inter status` - View learned rules
- `/inter activate` - Enable intelligent mode
- `/inter default` - Use static rules
- `/collect` - View collected data
- `/reset` - Reset predictions
- `/config` - Configure channels
- `/deploy` - Download deployment package

## Recent Changes (Dec 29, 2025)
### Automatic Follow-up Predictions
- Added automatic prediction for the next game when a prediction receives ❌ status
- When a prediction fails (card not found in games +0, +1, +2), the bot automatically creates a new prediction for the next game (+3)
- Implemented via new `_predict_next_game_after_failure()` method in `card_predictor.py`
- Follows the same suit as the failed prediction

### Deployment Package
- Created `iobo.zip` containing all project files ready for deployment to Render.com

## Technical Notes
- Uses APScheduler for cron jobs (daily resets, reports)
- Timezone: Africa/Porto-Novo (Benin)
- Prediction sessions: 1-6h, 9-12h, 15-18h, 21-24h
- Auto follow-up: Triggered when game_number > predicted_game + 2 (failed verification)
