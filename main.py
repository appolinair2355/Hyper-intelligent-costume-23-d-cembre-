# main.py

import os
import logging
import time
from datetime import datetime
import pytz
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler

# Import local modules
import config
from bot import telegram_bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load config instance
bot_config = config.Config()

# --- ENDPOINTS ---

@app.route('/')
def home():
    """Root endpoint"""
    return {'message': 'Telegram Bot is running', 'status': 'active'}, 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    if request.method == "POST":
        update = request.get_json()
        if update and telegram_bot:
            telegram_bot.handle_update(update)
        return "OK", 200
    return "Forbidden", 403

# --- SETUP FUNCTIONS ---

def setup_webhook():
    """Set up webhook on startup"""
    try:
        if not telegram_bot:
            logger.error("❌ Telegram bot instance is None, skipping webhook setup.")
            return

        # Use config's logic to get the full URL
        full_webhook_url = bot_config.get_webhook_url()
        logger.info(f"🔍 Checking webhook configuration...")
        
        if full_webhook_url:
            logger.info(f"🔗 Setting webhook: {full_webhook_url}")
            success = telegram_bot.set_webhook(full_webhook_url)
            if success:
                logger.info(f"✅ Webhook configured successfully.")
            else:
                logger.error("❌ Failed to configure webhook.")
        else:
            logger.warning("⚠️ WEBHOOK_URL not configured.")
    except Exception as e:
        logger.error(f"❌ Webhook setup error: {e}")

def reset_non_inter_predictions():
    """Reset all prediction data at 00h59 Benin time"""
    try:
        if hasattr(telegram_bot, 'handlers') and telegram_bot.handlers.card_predictor:
            predictor = telegram_bot.handlers.card_predictor
            # Files to remove
            files_to_clear = [
                'predictions.json', 'inter_data.json', 'smart_rules.json',
                'collected_games.json', 'inter_mode_status.json'
            ]
            for file in files_to_clear:
                if os.path.exists(file):
                    os.remove(file)
            
            # Reset in-memory data
            predictor.predictions = {}
            predictor.inter_data = []
            predictor.smart_rules = []
            predictor.collected_games = set()
            predictor.last_prediction_time = 0
            predictor.last_predicted_game_number = 0
            predictor.is_inter_mode_active = True
            predictor._save_all_data()
            logger.info("🔄 Daily reset performed successfully.")
    except Exception as e:
        logger.error(f"❌ Reset error: {e}")

def send_startup_message():
    """Send startup message to the prediction channel"""
    try:
        if hasattr(telegram_bot, 'handlers') and telegram_bot.handlers.card_predictor:
            predictor = telegram_bot.handlers.card_predictor
            if not predictor.telegram_message_sender or not predictor.prediction_channel_id:
                return
            
            now = datetime.now(pytz.timezone('Africa/Porto-Novo'))
            inter_active = "✅ ACTIF" if predictor.is_inter_mode_active else "❌ INACTIF"
            
            msg = (f"🎬 **LES PRÉDICTIONS REPRENNENT !**\n\n"
                   f"⏰ Heure de Bénin : {now.strftime('%H:%M:%S - %d/%m/%Y')}\n"
                   f"🧠 Mode Intelligent : {inter_active}\n"
                   f"🔄 Mise à jour des règles : Toutes les 10 min\n\n"
                   f"👨‍💻 **Développeur** : Sossou Kouamé\n"
                   f"🎟️ **Code Promo** : Koua229")
            
            predictor.telegram_message_sender(predictor.prediction_channel_id, msg)
            logger.info("📢 Startup message sent.")
    except Exception as e:
        logger.error(f"❌ Startup message error: {e}")

def send_session_reports():
    """Send reports"""
    try:
        if hasattr(telegram_bot, 'handlers') and telegram_bot.handlers.card_predictor:
            predictor = telegram_bot.handlers.card_predictor
            report = predictor.get_session_report_preview()
            if predictor.prediction_channel_id and predictor.telegram_message_sender:
                predictor.telegram_message_sender(predictor.prediction_channel_id, report)
    except Exception as e:
        logger.error(f"❌ Report error: {e}")

def update_pending_ki():
    """Tâche planifiée pour mettre à jour le ki des prédictions en attente chaque minute"""
    try:
        from bot import telegram_bot
        if telegram_bot and hasattr(telegram_bot, 'handlers') and telegram_bot.handlers.card_predictor:
            cp = telegram_bot.handlers.card_predictor
            now = datetime.now(pytz.timezone('Africa/Porto-Novo'))
            
            for game_num, pred in list(cp.predictions.items()):
                if pred.get('status') == 'pending':
                    msg_id = pred['message_id']
                    suit = pred['predicted_costume']
                    ki_base = pred.get('ki_base', 0)
                    
                    # Le ki actuel est le temps écoulé depuis la prédiction (en minutes) + ki_base
                    start_time = pred.get('timestamp', time.time())
                    elapsed_min = int((time.time() - start_time) / 60)
                    current_ki = ki_base + elapsed_min
                    
                    # On ne met à jour que si le ki a changé pour éviter l'erreur "message is not modified"
                    if pred.get('last_updated_ki') == current_ki:
                        continue
                    
                    # Mise à jour du message (ki toujours masqué dans le texte, mais stocké dans l'entité invisible)
                    # On ne l'affiche visiblement que lors de la validation (statut won/lost)
                    new_text = cp.prepare_prediction_text(game_num, suit, ki=current_ki, show_ki=False)
                    
                    # On utilise l'API pour éditer
                    success_mid = telegram_bot.handlers.send_message(cp.prediction_channel_id, new_text, message_id=msg_id, edit=True, parse_mode='HTML')
                    if success_mid:
                        pred['last_updated_ki'] = current_ki
                    logger.debug(f"⏰ Ki dynamique mis à jour pour Jeu {game_num} (ki={current_ki})")
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour ki dynamique: {e}")

def setup_scheduler():
    """Configure the background scheduler for tasks"""
    try:
        scheduler = BackgroundScheduler()
        benin_tz = pytz.timezone('Africa/Porto-Novo')
        
        # Daily reset at 00:59
        scheduler.add_job(reset_non_inter_predictions, 'cron', hour=0, minute=59, timezone=benin_tz)
        
        # Periodic inter analysis every 10 minutes
        scheduler.add_job(
            run_inter_analysis, 
            'interval', 
            minutes=10, 
            timezone=benin_tz,
            id='inter_analysis_job',
            replace_existing=True,
            next_run_time=datetime.now(benin_tz)
        )
        
        # Mise à jour dynamique du ki chaque minute
        scheduler.add_job(
            update_pending_ki,
            'interval',
            minutes=1,
            timezone=benin_tz,
            id='dynamic_ki_job',
            replace_existing=True
        )
        
        # Reports at specific hours
        for hour in [0, 6, 12, 18]:
            scheduler.add_job(send_session_reports, 'cron', hour=hour, minute=0, timezone=benin_tz)
            
        scheduler.start()
        logger.info("⏰ Scheduler started (Benin TZ) - Analysis every 10m + Dynamic Ki every 1m")
    except Exception as e:
        logger.error(f"❌ Scheduler setup error: {e}")

def run_inter_analysis():
    """Task function for the scheduler"""
    try:
        from bot import telegram_bot
        if telegram_bot and hasattr(telegram_bot, 'handlers') and telegram_bot.handlers.card_predictor:
            logger.info("🔄 Lancement de l'analyse automatique INTER...")
            predictor = telegram_bot.handlers.card_predictor
            predictor.analyze_and_set_smart_rules()
            
            # Envoyer notification de mise à jour réussie à l'admin (le compte de l'utilisateur)
            target_id = os.getenv('ADMIN_ID')
            if target_id and predictor.telegram_message_sender:
                now = datetime.now(pytz.timezone('Africa/Porto-Novo'))
                msg = (f"🔄 **MISE À JOUR RÉUSSIE !**\n\n"
                       f"✅ Analyse INTER effectuée avec succès.\n"
                       f"📊 {len(predictor.smart_rules)} règles actives.\n"
                       f"🕒 Dernière mise à jour : {now.strftime('%H:%M:%S')}\n"
                       f"🚀 Les 8 tops sont réellement à jour.")
                telegram_bot.handlers.send_message(int(target_id), msg)
                logger.info(f"📢 Notification de mise à jour envoyée à l'ID {target_id}")
            else:
                logger.warning("⚠️ ADMIN_ID non configuré, impossible d'envoyer la notification.")
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'analyse planifiée: {e}")

# Global setup
setup_webhook()
setup_scheduler()

if __name__ == "__main__":
    # Configure Port (10000 for Render, 5000 for Replit)
    # Sur Replit, on FORCE le port 5000 pour que le webview fonctionne
    is_replit = os.getenv('REPLIT_DOMAINS') is not None
    port = 5000 if is_replit else int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Server starting on port {port}")
    app.run(host='0.0.0.0', port=port)
