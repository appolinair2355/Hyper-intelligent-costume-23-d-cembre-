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

# --- REMISE À ZÉRO TOTALE CHAQUE JOUR À 00h59 ---

def reset_all_bot_data():
    """
    ⚠️ EFFACE TOUTES LES DONNÉES DU BOT CHAQUE JOUR À 00h59 (heure du Bénin)
    Remet à zéro : prédictions, règles, historique, données INTER, etc.
    """
    try:
        files_to_reset = [
            'predictions.json',
            'inter_data.json',
            'smart_rules.json',
            'sequential_history.json',
            'collected_games.json',
            'processed.json',
            'last_prediction_time.json',
            'last_predicted_game_number.json',
            'consecutive_fails.json',
            'pending_edits.json',
            'quarantined_rules.json',
            'wait_until_next_update.json',
            'last_inter_update.json',
            'last_report_sent.json'
        ]

        for filename in files_to_reset:
            try:
                if os.path.exists(filename):
                    os.remove(filename)
                    logger.info(f"🗑️ Fichier supprimé : {filename}")
                else:
                    logger.debug(f"📭 Fichier non trouvé : {filename}")
            except Exception as e:
                logger.error(f"❌ Erreur suppression {filename} : {e}")

        logger.info("🔄 Toutes les données du bot ont été remises à zéro à 00h59 (heure du Bénin).")

    except Exception as e:
        logger.error(f"❌ Erreur lors de la remise à zéro complète : {e}")

# --- MESSAGES DE SESSION & RAPPORTS ---

def send_startup_message():
    """Envoie un message de redémarrage à 1h, 9h, 15h, 21h avec la dernière mise à jour INTER."""
    try:
        if bot.handlers.card_predictor:
            predictor = bot.handlers.card_predictor
            if not predictor.telegram_message_sender or not predictor.prediction_channel_id:
                return
            
            now = predictor.now()
            last_update = predictor.get_inter_version()
            
            msg = (f"🎬 LES PRÉDICTIONS REPRENNENT !\n\n"
                   f"⏰ Heure de Bénin : {now.strftime('%H:%M:%S')} - {now.strftime('%d/%m/%Y')}\n"
                   f"📅 Session : {predictor.current_session_label()}\n"
                   f"🧠 Mode Intelligent : {'✅ ACTIF' if predictor.is_inter_mode_active else '❌ INACTIF'}\n"
                   f"🔄 Mise à jour des règles : {last_update}\n"
                   f"📌 Version : {last_update}\n\n"
                   f"👨‍💻 Développeur : Sossou Kouamé\n"
                   f"🎟️ Code Promo : Koua229")
            
            predictor.telegram_message_sender(predictor.prediction_channel_id, msg)
            logger.info("📢 Message de redémarrage envoyé")
    except Exception as e:
        logger.error(f"❌ Erreur envoi message redémarrage: {e}")

def send_session_reports():
    """Envoie les rapports de session à 6h, 12h, 18h, 00h (heure du Bénin)."""
    try:
        if bot.handlers.card_predictor:
            bot.handlers.card_predictor.check_and_send_reports()
    except Exception as e:
        logger.error(f"❌ Erreur envoi rapport: {e}")

# --- PLANIFICATEUR DES TÂCHES ---

def setup_scheduler():
    """Configure le planificateur pour la réinitialisation quotidienne et les rapports."""
    try:
        scheduler = BackgroundScheduler()
        benin_tz = pytz.timezone('Africa/Porto-Novo')
        
        # ✅ Remise à zéro complète à 00h59
        trigger_reset = CronTrigger(hour=0, minute=59, timezone=benin_tz)
        scheduler.add_job(
            reset_all_bot_data,
            trigger=trigger_reset,
            id='daily_full_reset',
            name='Remise à zéro complète des données du bot',
            replace_existing=True
        )
        
        # Message de redémarrage à 1h, 9h, 15h, 21h
        for hour in [1, 9, 15, 21]:
            trigger_startup = CronTrigger(hour=hour, minute=0, timezone=benin_tz)
            scheduler.add_job(
                send_startup_message,
                trigger=trigger_startup,
                id=f'startup_message_{hour}h',
                name=f'Message redémarrage à {hour}h00',
                replace_existing=True
            )
        
        # Rapports automatiques à 6h, 12h, 18h, 00h
        for hour in [6, 12, 18, 0]:
            trigger_report = CronTrigger(hour=hour, minute=0, timezone=benin_tz)
            scheduler.add_job(
                send_session_reports,
                trigger=trigger_report,
                id=f'session_report_{hour}h',
                name=f'Rapport de session à {hour}h00',
                replace_existing=True
            )
        
        scheduler.start()
        logger.info("⏰ Planificateur configuré:")
        logger.info("   - Remise à zéro complète à 00h59 (heure du Bénin)")
        logger.info("   - Rapports à 6h00, 12h00, 18h00, 00h00 (heure du Bénin)")
        
        return scheduler
    except Exception as e:
        logger.error(f"❌ Erreur configuration planificateur: {e}")
        return None

# --- DÉMARRAGE ---
setup_webhook()
scheduler = setup_scheduler()

if __name__ == '__main__':
    port = config.PORT
    app.run(host='0.0.0.0', port=port, debug=config.DEBUG)
