# main.py

"""
Main entry point for the Telegram bot deployment on render.com
"""
import os
import json
import logging
from flask import Flask, request, jsonify
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Importe la configuration et le bot
from config import Config
from bot import TelegramBot 

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize bot and config
try:
    config = Config()
except ValueError as e:
    logger.error(f"❌ Erreur d'initialisation de la configuration: {e}")
    exit(1) 

# 'bot' est l'instance de la classe TelegramBot
bot = TelegramBot(config.BOT_TOKEN) 

# Initialize Flask app
app = Flask(__name__)


# --- LOGIQUE WEBHOOK ---

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook from Telegram"""
    try:
        update = request.get_json(silent=True)
        if not update:
            return jsonify({'status': 'ok'}), 200

        # Délégation du traitement complet à bot.handle_update
        if update:
            bot.handle_update(update)
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return 'Error', 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for render.com"""
    return {'status': 'healthy', 'service': 'telegram-bot'}, 200

@app.route('/', methods=['GET'])
def home():
    """Root endpoint"""
    return {'message': 'Telegram Bot is running', 'status': 'active'}, 200

# --- CONFIGURATION WEBHOOK ---

def setup_webhook():
    """Set up webhook on startup"""
    try:
        full_webhook_url = config.get_webhook_url()
        
        # Log de diagnostic
        logger.info(f"🔍 Environnement détecté:")
        logger.info(f"  - PORT: {config.PORT}")
        logger.info(f"  - WEBHOOK_URL (env): {os.getenv('WEBHOOK_URL', 'NON DÉFINI')}")
        logger.info(f"  - RENDER: {os.getenv('RENDER', 'false')}")
        logger.info(f"  - REPLIT_DOMAINS: {os.getenv('REPLIT_DOMAINS', 'NON DÉFINI')}")
        
        if full_webhook_url and not config.WEBHOOK_URL.startswith('https://.repl.co'):
            logger.info(f"🔗 Tentative de configuration webhook: {full_webhook_url}")

            success = bot.set_webhook(full_webhook_url)
            
            if success:
                logger.info(f"✅ Webhook configuré avec succès.")
                logger.info(f"🎯 Bot prêt pour prédictions automatiques et vérifications via webhook")
            else:
                logger.error("❌ Échec configuration webhook.")
                logger.error("💡 Vérifiez que WEBHOOK_URL est correctement défini dans les variables d'environnement Render")
        else:
            logger.warning("⚠️ WEBHOOK_URL non configurée ou non valide. Le webhook ne sera PAS configuré.")
            if os.getenv('RENDER'):
                logger.error("🚨 SUR RENDER.COM : Vous DEVEZ définir WEBHOOK_URL dans les variables d'environnement !")
    except Exception as e:
        logger.error(f"❌ Erreur critique lors du setup du webhook: {e}")

# --- RÉINITIALISATION PROGRAMMÉE DES PRÉDICTIONS ---

def reset_non_inter_predictions():
    """
    Réinitialise les prédictions automatiques (non-INTER) à 00h59 heure du Bénin.
    Garde les données 'collected_games.json' et 'inter_data.json' intactes.
    """
    try:
        predictions_file = 'predictions.json'
        
        if not os.path.exists(predictions_file):
            logger.info("📊 Aucun fichier predictions.json à réinitialiser.")
            return
        
        with open(predictions_file, 'r') as f:
            content = f.read().strip()
            if not content:
                logger.info("📊 Fichier predictions.json vide, rien à réinitialiser.")
                return
            predictions = json.loads(content)
        
        inter_predictions = {}
        non_inter_count = 0
        
        for game_num, prediction in predictions.items():
            if prediction.get('is_inter', False):
                inter_predictions[game_num] = prediction
            else:
                non_inter_count += 1
        
        with open(predictions_file, 'w') as f:
            json.dump(inter_predictions, f, indent=4)
        
        logger.info(f"🔄 Réinitialisation programmée effectuée à 00h59 (Bénin):")
        logger.info(f"   - {non_inter_count} prédictions automatiques supprimées")
        logger.info(f"   - {len(inter_predictions)} prédictions INTER conservées")
        logger.info(f"   - collected_games.json et inter_data.json NON modifiés")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la réinitialisation programmée: {e}")

def setup_scheduler():
    """Configure le planificateur pour la réinitialisation quotidienne."""
    try:
        scheduler = BackgroundScheduler()
        
        benin_tz = pytz.timezone('Africa/Porto-Novo')
        
        trigger = CronTrigger(
            hour=0,
            minute=59,
            timezone=benin_tz
        )
        
        scheduler.add_job(
            reset_non_inter_predictions,
            trigger=trigger,
            id='daily_prediction_reset',
            name='Réinitialisation quotidienne des prédictions automatiques',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("⏰ Planificateur configuré: réinitialisation à 00h59 (heure du Bénin)")
        
        return scheduler
    except Exception as e:
        logger.error(f"❌ Erreur configuration planificateur: {e}")
        return None

# Configure webhook au démarrage (fonctionne avec Gunicorn)
setup_webhook()

scheduler = setup_scheduler()

if __name__ == '__main__':
    # Get port from environment 
    port = config.PORT

    # Run the Flask app
    app.run(host='0.0.0.0', port=port, debug=config.DEBUG)
