# main.py

"""
Main entry point for the Telegram bot deployment on render.com
"""
import os
import logging
from flask import Flask, request, jsonify
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
        
        if full_webhook_url and not config.WEBHOOK_URL.startswith('https://.repl.co'):
            logger.info(f"🔗 Tentative de configuration webhook: {full_webhook_url}")
            success = bot.set_webhook(full_webhook_url)
            if success:
                logger.info(f"✅ Webhook configuré avec succès.")
            else:
                logger.error("❌ Échec configuration webhook.")
    except Exception as e:
        logger.error(f"❌ Erreur critique lors du setup du webhook: {e}")

# --- RÉINITIALISATION PROGRAMMÉE DES PRÉDICTIONS ---

def reset_non_inter_predictions():
    """Reset complet à 00h59 heure du Bénin."""
    try:
        files_to_clear = [
            'predictions.json', 'inter_data.json', 'smart_rules.json',
            'collected_games.json', 'sequential_history.json', 'pending_edits.json',
            'quarantined_rules.json', 'last_prediction_time.json',
            'last_predicted_game_number.json', 'consecutive_fails.json',
            'single_trigger_until.json', 'inter_mode_status.json',
            'last_analysis_time.json', 'last_inter_update.json',
            'last_report_sent.json', 'wait_until_next_update.json',
            'inter_rules_last_used.json'
        ]
        
        for file in files_to_clear:
            if os.path.exists(file):
                os.remove(file)
        
        if bot.handlers.card_predictor:
            predictor = bot.handlers.card_predictor
            predictor.predictions = {}
            predictor.inter_data = []
            predictor.smart_rules = []
            predictor.collected_games = set()
            predictor.sequential_history = {}
            predictor.pending_edits = {}
            predictor.quarantined_rules = {}
            predictor.inter_rules_last_used = {}
            predictor.is_inter_mode_active = True
            predictor._save_all_data()
            logger.info("🔄 RESET COMPLET EFFECTUÉ À 00h59")
    except Exception as e:
        logger.error(f"❌ Erreur lors du reset complet: {e}")

def send_startup_message():
    """Envoie un message de démarrage de session."""
    try:
        if bot.handlers.card_predictor:
            predictor = bot.handlers.card_predictor
            if not predictor.telegram_message_sender or not predictor.prediction_channel_id:
                return
            
            now = predictor.now()
            last_update = predictor.get_inter_version()
            session_label = predictor.current_session_label()
            inter_active = "✅ ACTIF" if predictor.is_inter_mode_active else "❌ INACTIF"
            
            msg = (f"🎬 **LES PRÉDICTIONS REPRENNENT !**\n\n"
                   f"🚀 **version : hyper intelligent 2026 est activé**\n\n"
                   f"⏰ Heure de Bénin : {now.strftime('%H:%M:%S - %d/%m/%Y')}\n"
                   f"📅 Session : {session_label}\n"
                   f"🧠 Mode Intelligent : {inter_active}\n"
                   f"🔄 Mise à jour des règles : {last_update}\n\n"
                   f"👨‍💻 **Développeur** : Sossou Kouamé\n"
                   f"🎟️ **Code Promo** : Koua229")
            
            predictor.telegram_message_sender(predictor.prediction_channel_id, msg)
            logger.info("📢 Message de démarrage de session envoyé")
    except Exception as e:
        logger.error(f"❌ Erreur envoi message démarrage: {e}")

def send_session_reports():
    """Envoie les rapports de session et redémarre le bot."""
    try:
        if bot.handlers.card_predictor:
            logger.info("📊 Envoi du rapport de session...")
            bot.handlers.card_predictor.check_and_send_reports()
            import time
            time.sleep(5)
            logger.info("🔄 Redémarrage du bot après envoi du bilan...")
            os._exit(0)
    except Exception as e:
        logger.error(f"❌ Erreur envoi rapport ou redémarrage: {e}")

def update_inter_rules():
    """Mise à jour automatique des règles INTER toutes les 30 min."""
    try:
        if bot.handlers.card_predictor:
            logger.info("🧠 Mise à jour automatique des règles INTER (30 min)...")
            bot.handlers.card_predictor.analyze_and_set_smart_rules()
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour INTER: {e}")

def setup_scheduler():
    """Configure le planificateur."""
    try:
        scheduler = BackgroundScheduler()
        benin_tz = pytz.timezone('Africa/Porto-Novo')
        
        # INTER rules update every 30 min
        scheduler.add_job(update_inter_rules, 'interval', minutes=30, id='inter_rules_update')
        
        # Daily reset at 00:59
        scheduler.add_job(reset_non_inter_predictions, CronTrigger(hour=0, minute=59, timezone=benin_tz), id='daily_reset')
        
        # Session reports & restarts
        for hour in [6, 12, 17, 23, 1]:
            scheduler.add_job(send_session_reports, CronTrigger(hour=hour, minute=0, timezone=benin_tz), id=f'report_{hour}h')
        
        # Startup messages
        for hour in [2, 10, 15, 20, 0]:
            scheduler.add_job(send_startup_message, CronTrigger(hour=hour, minute=1, timezone=benin_tz), id=f'startup_{hour}h')
        
        scheduler.start()
        logger.info("⏰ Planificateur configuré.")
        send_startup_message()
        return scheduler
    except Exception as e:
        logger.error(f"❌ Erreur scheduler: {e}")
        return None

setup_webhook()
scheduler = setup_scheduler()

if __name__ == '__main__':
    port = int(os.getenv('PORT') or 5000)
    if os.getenv('RENDER'):
        port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
