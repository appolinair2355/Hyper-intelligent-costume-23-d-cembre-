# handlers.py

import logging
import time
import json
from collections import defaultdict
from typing import Dict, Any, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Importation Robuste
try:
    # Assurez-vous d'utiliser la version de CardPredictor que j'ai corrigée (avec Top 2 par enseigne)
    from card_predictor import CardPredictor
except ImportError:
    logger.error("❌ IMPOSSIBLE D'IMPORTER CARDPREDICTOR")
    CardPredictor = None

user_message_counts = defaultdict(list)

# --- MESSAGES UTILISATEUR NETTOYÉS ---
WELCOME_MESSAGE = """
👋 **BIENVENUE SUR LE BOT ENSEIGNE !** ♠️♥️♦️♣️

Je prédis la prochaine Enseigne (Couleur) en utilisant :
1. **Règles statiques** : Patterns prédéfinis (ex: 10♦️ → ♠️)
2. **Intelligence artificielle (Mode INTER)** : Apprend des données réelles

━━━━━━━━━━━━━━━━━━━━━
📋 **COMMANDES DISPONIBLES**
━━━━━━━━━━━━━━━━━━━━━

**🔹 Informations Générales**
• `/start` - Afficher ce message d'aide
• `/stat` - Voir l'état du bot (canaux, mode actif)

**🔹 Mode Intelligent (INTER)**
• `/inter status` - Voir les règles apprises (Top 2 par enseigne)
• `/inter activate` - **Activer manuellement** le mode intelligent
• `/inter default` - Désactiver et revenir aux règles statiques

**🔹 Collecte de Données**
• `/collect` - Voir toutes les données collectées par enseigne
• `/reset` - Réinitialiser les prédictions automatiques (garde INTER/Collect)

**🔹 Configuration**
• `/config` - Configurer les rôles des canaux (Source/Prédiction)

**🔹 Déploiement & Maintenance**
• `/deploy` - Télécharger le package pour Render.com
• `/qua` - État de la quarantaine et statistiques
• `/reset` - ⚠️ Réinitialiser COMPLÈTEMENT le bot

━━━━━━━━━━━━━━━━━━━━━
**💡 Comment ça marche ?**
━━━━━━━━━━━━━━━━━━━━━

1️⃣ Le bot surveille le canal SOURCE
2️⃣ Détecte les cartes et fait des prédictions
3️⃣ Envoie les prédictions dans le canal PRÉDICTION
4️⃣ Vérifie automatiquement les résultats
5️⃣ Collecte les données en continu pour apprentissage

🧠 **Mode INTER** : 
• Collecte automatique des données de jeu
• Mise à jour des règles toutes les 30 min
• **Activation MANUELLE uniquement** (commande `/inter activate`)
• Utilise les Top 2 déclencheurs par enseigne (♠️♥️♦️♣️)

━━━━━━━━━━━━━━━━━━━━━
⚠️ **Important** : Le mode INTER doit être activé manuellement avec `/inter activate`
"""

HELP_MESSAGE = """
🤖 **AIDE COMMANDE /INTER**

• `/inter status` : Voir les règles apprises (Top 2 par Enseigne).
• `/inter activate` : Forcer l'activation de l'IA et relancer l'analyse.
• `/inter default` : Revenir aux règles statiques.
"""

class TelegramHandlers:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        if CardPredictor:
            # On passe la fonction d'envoi pour les notifs INTER
            self.card_predictor = CardPredictor(telegram_message_sender=self.send_message)
        else:
            self.card_predictor = None

    # --- MESSAGERIE ---
    def _check_rate_limit(self, user_id):
        now = time.time()
        user_message_counts[user_id] = [t for t in user_message_counts[user_id] if now - t < 60]
        user_message_counts[user_id].append(now)
        return len(user_message_counts[user_id]) <= 30

    def send_message(self, chat_id: int, text: str, parse_mode='Markdown', message_id: Optional[int] = None, edit=False, reply_markup: Optional[Dict] = None) -> Optional[int]:
        if not chat_id or not text: return None
        
        method = 'editMessageText' if (message_id or edit) else 'sendMessage'
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
        
        if message_id: payload['message_id'] = message_id
        if reply_markup: 
            payload['reply_markup'] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup

        try:
            r = requests.post(f"{self.base_url}/{method}", json=payload, timeout=10)
            if r.status_code == 200:
                return r.json().get('result', {}).get('message_id')
            else:
                logger.error(f"Erreur Telegram {r.status_code}: {r.text}")
        except Exception as e:
            logger.error(f"Exception envoi message: {e}")
        return None

    # --- GESTION COMMANDE /deploy ---
    def _handle_command_deploy(self, chat_id: int):
        try:
            self.send_message(chat_id, "📦 **Envoi du package koopp.zip pour déploiement...**")
            
            # Fichier zip pré-généré
            zip_filename = 'koopp.zip'
            
            import os
            
            if not os.path.exists(zip_filename):
                self.send_message(chat_id, f"❌ Fichier {zip_filename} non trouvé!")
                return
            
            # Envoyer le fichier
            url = f"{self.base_url}/sendDocument"
            with open(zip_filename, 'rb') as f:
                files = {'document': (zip_filename, f, 'application/zip')}
                # Compter les données collectées
                data_count = len(self.card_predictor.inter_data) if self.card_predictor else 0
                rules_count = len(self.card_predictor.smart_rules) if self.card_predictor else 0
                
                data = {
                    'chat_id': chat_id,
                    'caption': f'📦 **koopp.zip - Package Complet Bot ENSEIGNE v5.3**\n\n✅ Fichier: koopp.zip\n✅ Port : 10000 (Render.com)\n✅ Tous les fichiers inclus\n✅ **{data_count} jeux collectés**\n✅ **{rules_count} règles INTER**\n✅ Sessions: 1-6h, 9-12h, 15-18h, 21-24h\n✅ Rapports automatiques: 6h, 12h, 18h, 00h\n✅ Statuts: ✅0️⃣ (N), ✅1️⃣ (N+1), ✅2️⃣ (N+2), ❌ (pas trouvé)\n✅ Vérification: PREMIÈRE carte uniquement\n✅ Logique corrigée et testée\n✅ **Canaux préconfigurés (sans configuration manuelle)**\n\n**Déploiement Render.com:**\n1. Extraire koopp.zip\n2. Configurer: BOT_TOKEN, WEBHOOK_URL\n3. Lancer: `gunicorn main:app --bind 0.0.0.0:10000`\n\n👨‍💻 Développeur: Sossou Kouamé\n🎟️ Code Promo: Koua229\n🇧🇯 Timezone: Africa/Porto-Novo',
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=60)
            
            if response.json().get('ok'):
                logger.info(f"✅ koopp.zip envoyé avec succès")
                self.send_message(chat_id, f"✅ **{zip_filename} envoyé avec succès!**\n\n🎯 v5.3 FINAL - Bot corrigé et prêt pour production 🚀")
            else:
                self.send_message(chat_id, f"❌ Erreur : {response.text}")
                    
        except Exception as e:
            logger.error(f"Erreur /deploy : {e}")
            self.send_message(chat_id, f"❌ Erreur : {str(e)}")


    # --- GESTION COMMANDE /collect ---
    def _handle_command_collect(self, chat_id: int):
        if not self.card_predictor: 
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        # Récupérer les informations
        is_active = self.card_predictor.is_inter_mode_active
        total_collected = len(self.card_predictor.inter_data)
        
        # Message d'état
        message = "🧠 **ETAT DU MODE INTELLIGENT**\n\n"
        message += f"Actif : {'✅ OUI' if is_active else '❌ NON'}\n"
        message += f"Données collectées : {total_collected}\n\n"
        
        # Afficher TOUS les déclencheurs collectés par enseigne
        if self.card_predictor.inter_data:
            from collections import defaultdict
            
            # Grouper par enseigne de résultat
            by_result_suit = defaultdict(list)
            for entry in self.card_predictor.inter_data:
                result_suit = entry.get('result_suit', '?')
                trigger = entry.get('declencheur', '?').replace("♥️", "❤️")
                by_result_suit[result_suit].append(trigger)
            
            message += "📊 **TOUS LES DÉCLENCHEURS COLLECTÉS:**\n\n"
            
            for suit in ['♠️', '❤️', '♦️', '♣️']:
                if suit in by_result_suit:
                    triggers = by_result_suit[suit]
                    message += f"**Pour enseigne {suit}:**\n"
                    # Compter les occurrences
                    from collections import Counter
                    trigger_counts = Counter(triggers)
                    for trigger, count in trigger_counts.most_common():
                        message += f"  • {trigger} ({count}x)\n"
                    message += "\n"
        else:
            message += "⚠️ **Aucune donnée collectée.**\n"
        
        # Avertissement si pas assez de données
        if total_collected < 3:
            message += f"\n⚠️ Minimum 3 jeux requis pour créer des règles (actuellement: {total_collected})."
        
        # Boutons d'action
        keyboard = {'inline_keyboard': []}
        
        if total_collected >= 3:
            if is_active:
                keyboard['inline_keyboard'].append([
                    {'text': '🔄 Relancer Analyse', 'callback_data': 'inter_apply'},
                    {'text': '❌ Désactiver INTER', 'callback_data': 'inter_default'}
                ])
            else:
                keyboard['inline_keyboard'].append([
                    {'text': '✅ Activer INTER', 'callback_data': 'inter_apply'}
                ])
        else:
            keyboard['inline_keyboard'].append([
                {'text': '🔄 Analyser les données', 'callback_data': 'inter_apply'}
            ])
        
        self.send_message(chat_id, message, reply_markup=keyboard)

    # --- GESTION COMMANDE /bilan (APERÇU DU RAPPORT) ---
    def _handle_command_bilan(self, chat_id: int):
        """Affiche un aperçu du bilan de fin de session."""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        try:
            msg = self.card_predictor.get_session_report_preview()
            self.send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"❌ Erreur aperçu bilan: {e}")
            self.send_message(chat_id, "❌ Erreur lors du calcul du bilan.")
    
    # --- GESTION COMMANDE /qua (QUARANTAINE) ---
    def _handle_command_qua(self, chat_id: int):
        """Affiche l'état et les informations secrètes du bot."""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        try:
            cp = self.card_predictor
            now = cp.now()
            
            message = "🔒 ÉTAT ET INFORMATIQUE SECRET DU BOT\n\n"
            
            # TOP en quarantaine
            qua_list = cp.quarantined_rules if cp.quarantined_rules else {}
            if qua_list:
                message += "🔒 TOP EN QUARANTAINE:\n"
                for key in qua_list.keys():
                    try:
                        trigger, suit = key.split("_", 1)
                        message += f"  • {trigger} → {suit}\n"
                    except:
                        message += f"  • {key}\n"
                message += "\n"
            else:
                message += "✅ Aucun TOP en quarantaine\n\n"
            
            # Les 5 dernières prédictions
            recent_preds = sorted(
                [(k, v) for k, v in cp.predictions.items() if v.get('timestamp')],
                key=lambda x: x[1].get('timestamp', 0),
                reverse=True
            )[:5]
            
            message += "📊 Les 5 dernières prédictions envoyées\n"
            if recent_preds:
                for game_num, pred in recent_preds:
                    trigger = pred.get('predicted_from_trigger', '?')
                    suit = pred.get('predicted_costume', '?')
                    status = pred.get('status', 'pending')
                    is_inter = "🧠 INTER" if pred.get('is_inter') else "📋 STATIQUE"
                    status_display = {
                        'pending': '⏳',
                        'won': '✅',
                        'lost': '❌'
                    }.get(status, '?')
                    message += f"  • Jeu {game_num}: {suit} ({status_display}) - Déclencheur: {trigger} [{is_inter}]\n"
            else:
                message += "  Aucune prédiction\n"
            message += "\n"
            
            # Prochain bilan
            next_report_hour = None
            report_hours = [6, 12, 18, 0]
            for h in report_hours:
                if h > now.hour:
                    next_report_hour = h
                    break
            if next_report_hour is None:
                next_report_hour = report_hours[0]
            minutes_until = ((next_report_hour - now.hour) * 60 - now.minute) % (24 * 60)
            hours = minutes_until // 60
            mins = minutes_until % 60
            message += f"⏰ Prochain bilan dans: {hours}h{mins:02d}\n\n"
            
            # Mode INTER
            message += f"🧠 Mode INTER: {'✅ ACTIF' if cp.is_inter_mode_active else '❌ INACTIF'}\n\n"
            
            # Données collectées
            message += f"📈 Donnees collectees: {len(cp.inter_data)} jeux\n"
            
            # Règles INTER complètes
            if cp.smart_rules:
                message += "📋 Regles UTILISER INTELLIGENT :\n\n"
                rules_by_suit = defaultdict(list)
                for rule in cp.smart_rules:
                    rules_by_suit[rule.get('predict', rule.get('result_suit'))].append(rule)
                
                for suit in ['♠️', '❤️', '♦️', '♣️']:
                    if suit in rules_by_suit:
                        message += f"Pour predire {suit}:\n"
                        for rule in rules_by_suit[suit]:
                            trigger = rule.get('trigger', '?')
                            count = rule.get('count', 0)
                            message += f"  • {trigger} ({count}x)\n"
                        message += "\n"
            else:
                message += "📋 Pas encore de regles INTER\n"
            
            self.send_message(chat_id, message)
        except Exception as e:
            logger.error(f"Erreur /qua : {e}")
            self.send_message(chat_id, f"❌ Erreur : {str(e)}")

    # --- GESTION COMMANDE /reset ---
    def _handle_command_reset(self, chat_id: int):
        """⚠️ RÉINITIALISE COMPLÈTEMENT LE BOT - efface TOUT sauf les IDs des canaux."""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        try:
            cp = self.card_predictor
            
            saved_target_id = cp.target_channel_id
            saved_pred_id = cp.prediction_channel_id
            
            # Compter avant suppression
            pred_count = len(cp.predictions)
            inter_count = len(cp.inter_data)
            rules_count = len(cp.smart_rules)
            qua_count = len(cp.quarantined_rules)
            games_count = len(cp.collected_games)
            
            # Réinitialiser COMPLÈTEMENT
            cp.predictions = {}
            cp.inter_data = []
            cp.smart_rules = []
            cp.collected_games = set()
            cp.sequential_history = {}
            cp.quarantined_rules = {}
            cp.pending_edits = {}
            cp.last_report_sent = {}
            cp.last_prediction_time = 0
            cp.last_predicted_game_number = 0
            cp.consecutive_fails = 0
            cp.last_analysis_time = 0
            cp.single_trigger_until = 0
            cp.wait_until_next_update = 0
            cp.target_channel_id = saved_target_id
            cp.prediction_channel_id = saved_pred_id
            cp.is_inter_mode_active = False
            cp._save_all_data()
            
            message = (f"✅ RÉINITIALISATION COMPLÈTE\n\n"
                       f"📋 DONNÉES SUPPRIMÉES:\n"
                       f"  • {pred_count} prédictions\n"
                       f"  • {inter_count} jeux collectés\n"
                       f"  • {rules_count} règles TOP 2\n"
                       f"  • {qua_count} TOP en quarantaine\n"
                       f"  • {games_count} jeux dans collections\n"
                       f"  • historique_sequentiel.json\n"
                       f"  • pending_edits.json\n\n"
                       f"✅ DONNÉES CONSERVÉES:\n"
                       f"  • Canal Source: {saved_target_id}\n"
                       f"  • Canal Prédiction: {saved_pred_id}\n\n"
                       f"Mode INTER: DÉSACTIVÉ ❌\n"
                       f"Bot: VIERGE ET PRÊT 🎯")
            
            self.send_message(chat_id, message)
            logger.info("🔄 Reset complet effectué")
        except Exception as e:
            logger.error(f"Erreur /reset : {e}")
            self.send_message(chat_id, f"❌ Erreur lors de la réinitialisation: {e}")

    # --- GESTION COMMANDE /inter ---
    def _handle_command_inter(self, chat_id: int, text: str):
        if not self.card_predictor: 
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
            
        parts = text.lower().split()
        
        action = parts[1] if len(parts) > 1 else 'status'
        
        if action == 'activate':
            self.card_predictor.analyze_and_set_smart_rules(chat_id=chat_id, force_activate=True)
            self.send_message(chat_id, "✅ **MODE INTER ACTIVÉ**\nL'analyse Top 2 par enseigne est en cours...")
        
        elif action == 'default':
            self.card_predictor.is_inter_mode_active = False
            self.card_predictor._save_all_data()
            self.send_message(chat_id, "❌ **MODE INTER DÉSACTIVÉ**\nRetour aux règles statiques.")
            
        elif action == 'status':
            msg, kb = self.card_predictor.get_inter_status()
            self.send_message(chat_id, msg, reply_markup=kb)
        
        else:
            self.send_message(chat_id, HELP_MESSAGE)

    # --- CALLBACKS (BOUTONS) ---
    def _handle_callback_query(self, update_obj):
        data = update_obj['data']
        chat_id = update_obj['message']['chat']['id']
        msg_id = update_obj['message']['message_id']
        
        if not self.card_predictor: return

        # Actions INTER
        if data == 'inter_apply':
            self.card_predictor.analyze_and_set_smart_rules(chat_id=chat_id, force_activate=True)
            # Mise à jour du message pour confirmer l'action
            msg, kb = self.card_predictor.get_inter_status()
            self.send_message(chat_id, msg, message_id=msg_id, edit=True, reply_markup=kb)
        
        elif data == 'inter_default':
            self.card_predictor.is_inter_mode_active = False
            self.card_predictor._save_all_data()
            # Mise à jour du message pour confirmer l'action
            msg, kb = self.card_predictor.get_inter_status()
            self.send_message(chat_id, msg, message_id=msg_id, edit=True, reply_markup=kb)
            
        # Actions CONFIG
        elif data.startswith('config_'):
            if 'cancel' in data:
                self.send_message(chat_id, "Configuration annulée.", message_id=msg_id, edit=True)
            else:
                type_c = 'source' if 'source' in data else 'prediction'
                self.card_predictor.set_channel_id(chat_id, type_c)
                self.send_message(chat_id, f"✅ Ce canal est maintenant défini comme **{type_c.upper()}**.\n(L'ID forcé dans le code sera utilisé si le bot redémarre sans ce fichier de config)", message_id=msg_id, edit=True)

    # --- UPDATES (PARTIE CORRIGÉE) ---
    def handle_update(self, update: Dict[str, Any]):
        try:
            if not self.card_predictor: return

            if ('message' in update and 'text' in update['message']) or ('channel_post' in update and 'text' in update['channel_post']):
                
                msg = update.get('message') or update.get('channel_post')
                if not msg: return
                chat_id = msg.get('chat', {}).get('id')
                text = msg.get('text', '')
                user_id = msg.get('from', {}).get('id', 0)
                if not chat_id or not text: return

                if not self._check_rate_limit(user_id): return
                
                # Commandes (le code des commandes reste inchangé)
                if text.startswith('/inter'):
                    self._handle_command_inter(chat_id, text)
                elif text.startswith('/config'):
                    kb = {'inline_keyboard': [[{'text': 'Source', 'callback_data': 'config_source'}, {'text': 'Prediction', 'callback_data': 'config_prediction'}, {'text': 'Annuler', 'callback_data': 'config_cancel'}]]}
                    self.send_message(chat_id, "⚙️ **CONFIGURATION**\nQuel est le rôle de ce canal ?", reply_markup=kb)
                elif text.startswith('/start'):
                    self.send_message(chat_id, WELCOME_MESSAGE)
                elif text.startswith('/stat'):
                    sid = self.card_predictor.target_channel_id or self.card_predictor.HARDCODED_SOURCE_ID or "Non défini"
                    pid = self.card_predictor.prediction_channel_id or self.card_predictor.HARDCODED_PREDICTION_ID or "Non défini"
                    mode = "IA" if self.card_predictor.is_inter_mode_active else "Statique"
                    self.send_message(chat_id, f"📊 **STATUS**\nSource (Input): `{sid}`\nPrédiction (Output): `{pid}`\nMode: {mode}")
                elif text.startswith('/deploy'):
                    self._handle_command_deploy(chat_id)
                elif text.startswith('/collect'):
                    self._handle_command_collect(chat_id)
                elif text.startswith('/qua'):
                    self._handle_command_qua(chat_id)
                elif text.startswith('/reset'):
                    self._handle_command_reset(chat_id)
                elif text.startswith('/bilan'):
                    self._handle_command_bilan(chat_id)
                
                # Traitement Canal Source
                elif str(chat_id) == str(self.card_predictor.target_channel_id):
                    
                    # A. Collecter TOUJOURS (même messages temporaires ⏰)
                    game_num = self.card_predictor.extract_game_number(text)
                    if game_num:
                        self.card_predictor.collect_inter_data(game_num, text)
                    
                    # B. Vérifier UNIQUEMENT sur messages finalisés (✅ ou 🔰)
                    if self.card_predictor.has_completion_indicators(text) or '🔰' in text:
                        res = self.card_predictor._verify_prediction_common(text)
                        
                        if res and res['type'] == 'edit_message':
                            mid_to_edit = res.get('message_id_to_edit')
                            pred_channel = self.card_predictor.prediction_channel_id
                            
                            if mid_to_edit and pred_channel: 
                                self.send_message(pred_channel, res['new_message'], message_id=mid_to_edit, edit=True)
                    
                    # C. Prédire (même sur messages temporaires ⏰)
                    ok, num, val, is_inter = self.card_predictor.should_predict(text)
                    if ok and num and val:
                        txt = self.card_predictor.prepare_prediction_text(num, val)
                        pred_channel = self.card_predictor.prediction_channel_id
                        if pred_channel:
                            mid = self.send_message(pred_channel, txt)
                            if mid:
                                trigger = self.card_predictor._last_trigger_used or '?'  # ✅ Assurer str, jamais None
                                self.card_predictor.make_prediction(num, val, mid, is_inter=is_inter or False, trigger_used=trigger)

            # 2. Messages édités (CRITIQUE pour vérification)
            elif ('edited_message' in update and 'text' in update['edited_message']) or ('edited_channel_post' in update and 'text' in update['edited_channel_post']):
                
                msg = update.get('edited_message') or update.get('edited_channel_post')
                if not msg: return
                chat_id = msg.get('chat', {}).get('id')
                text = msg.get('text', '')
                if not chat_id or not text: return
                
                # Traitement Canal Source - Vérification sur messages édités
                if str(chat_id) == str(self.card_predictor.target_channel_id):
                    # Collecter TOUJOURS
                    game_num = self.card_predictor.extract_game_number(text)
                    if game_num:
                        self.card_predictor.collect_inter_data(game_num, text)
                    
                    # Vérifier UNIQUEMENT sur messages finalisés (✅ ou 🔰)
                    if self.card_predictor.has_completion_indicators(text) or '🔰' in text:
                        res = self.card_predictor.verify_prediction_from_edit(text)
                        
                        if res and res['type'] == 'edit_message':
                            mid_to_edit = res.get('message_id_to_edit')
                            pred_channel = self.card_predictor.prediction_channel_id
                            
                            if mid_to_edit and pred_channel:
                                self.send_message(pred_channel, res['new_message'], message_id=mid_to_edit, edit=True)

            # 3. Callbacks
            elif 'callback_query' in update:
                self._handle_callback_query(update['callback_query'])
            
            # 4. Ajout au groupe (inchangé)
            elif 'my_chat_member' in update:
                m = update['my_chat_member']
                if m['new_chat_member']['status'] in ['member', 'administrator']:
                    bot_id_part = self.bot_token.split(':')[0]
                    if str(m['new_chat_member']['user']['id']).startswith(bot_id_part):
                         self.send_message(m['chat']['id'], "✨ Merci de m'avoir ajouté ! Veuillez utiliser `/config` pour définir mon rôle (Source ou Prédiction).")


        except Exception as e:
            logger.error(f"Update error: {e}")
