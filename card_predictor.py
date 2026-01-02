# card_predictor.py

import re
import logging
import time
import os
import json
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from collections import defaultdict
import pytz

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

BENIN_TZ = pytz.timezone("Africa/Porto-Novo")

STATIC_RULES = {
    "10♦️": "♠️", "10♠️": "❤️",
    "9♣️": "❤️", "9♦️": "♠️",
    "8♣️": "♠️", "8♠️": "♣️",
    "7♠️": "♠️", "7♣️": "♣️",
    "6♦️": "♣️", "6♣️": "♦️",
    "A❤️": "❤️",
    "5❤️": "❤️", "5♠️": "♠️"
}

SYMBOL_MAP = {0: '✅0️⃣', 1: '✅1️⃣', 2: '✅2️⃣'}

PREDICTION_SESSIONS = [
    (1, 6),
    (9, 12),
    (15, 18),
    (21, 24)
]

class CardPredictor:
    def __init__(self, telegram_message_sender=None):
        self.HARDCODED_SOURCE_ID = -1002682552255
        self.HARDCODED_PREDICTION_ID = -1003329818758

        self.predictions = self._load_data('predictions.json')
        self.processed_messages = self._load_data('processed.json', is_set=True)
        self.last_prediction_time = self._load_data('last_prediction_time.json', is_scalar=True) or 0
        self.last_predicted_game_number = self._load_data('last_predicted_game_number.json', is_scalar=True) or 0
        self.consecutive_fails = self._load_data('consecutive_fails.json', is_scalar=True) or 0
        self.pending_edits: Dict[int, Dict] = self._load_data('pending_edits.json')

        raw_config = self._load_data('channels_config.json')
        self.config_data = raw_config if isinstance(raw_config, dict) else {}

        self.target_channel_id = self.config_data.get('target_channel_id') or self.HARDCODED_SOURCE_ID
        self.prediction_channel_id = self.config_data.get('prediction_channel_id') or self.HARDCODED_PREDICTION_ID

        self.telegram_message_sender = telegram_message_sender
        self.active_admin_chat_id = self._load_data('active_admin_chat_id.json', is_scalar=True)

        self.sequential_history: Dict[int, Dict] = self._load_data('sequential_history.json')
        self.inter_data: List[Dict] = self._load_data('inter_data.json')
        self.is_inter_mode_active = self._load_data('inter_mode_status.json', is_scalar=True)
        self.smart_rules = self._load_data('smart_rules.json')
        self.last_analysis_time = self._load_data('last_analysis_time.json', is_scalar=True) or 0
        self.collected_games = self._load_data('collected_games.json', is_set=True)

        self.single_trigger_until = self._load_data('single_trigger_until.json', is_scalar=True) or 0
        self.quarantined_rules = self._load_data('quarantined_rules.json')
        self.wait_until_next_update = self._load_data('wait_until_next_update.json', is_scalar=True) or 0
        self.last_inter_update_time = self._load_data('last_inter_update.json', is_scalar=True) or 0
        self.last_report_sent = self._load_data('last_report_sent.json')

        if self.is_inter_mode_active is None:
            self.is_inter_mode_active = True

        self.prediction_cooldown = 30

        if self.inter_data and not self.is_inter_mode_active and not self.smart_rules:
            self.analyze_and_set_smart_rules(initial_load=True)

    # --- Persistance ---
    def _load_data(self, filename: str, is_set: bool = False, is_scalar: bool = False) -> Any:
        try:
            is_dict = filename in ['channels_config.json', 'predictions.json', 'sequential_history.json', 'smart_rules.json', 'pending_edits.json']
            if not os.path.exists(filename):
                return set() if is_set else (None if is_scalar else ({} if is_dict else []))
            with open(filename, 'r') as f:
                content = f.read().strip()
                if not content:
                    return set() if is_set else (None if is_scalar else ({} if is_dict else []))
                data = json.loads(content)
                if is_set:
                    return set(data)
                if filename in ['sequential_history.json', 'predictions.json', 'pending_edits.json'] and isinstance(data, dict):
                    return {int(k): v for k, v in data.items()}
                return data
        except Exception as e:
            logger.error(f"⚠️ Erreur chargement {filename}: {e}")
            is_dict = filename in ['channels_config.json', 'predictions.json', 'sequential_history.json', 'smart_rules.json', 'pending_edits.json']
            return set() if is_set else (None if is_scalar else ({} if is_dict else []))

    def _save_data(self, data: Any, filename: str):
        try:
            if isinstance(data, set):
                data = list(data)
            if filename == 'channels_config.json' and isinstance(data, dict):
                if 'target_channel_id' in data and data['target_channel_id'] is not None:
                    data['target_channel_id'] = int(data['target_channel_id'])
                if 'prediction_channel_id' in data and data['prediction_channel_id'] is not None:
                    data['prediction_channel_id'] = int(data['prediction_channel_id'])
            with open(filename, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde {filename}: {e}")

    def _save_all_data(self):
        self._save_data(self.predictions, 'predictions.json')
        self._save_data(self.processed_messages, 'processed.json')
        self._save_data(self.last_prediction_time, 'last_prediction_time.json')
        self._save_data(self.last_predicted_game_number, 'last_predicted_game_number.json')
        self._save_data(self.consecutive_fails, 'consecutive_fails.json')
        self._save_data(self.inter_data, 'inter_data.json')
        self._save_data(self.sequential_history, 'sequential_history.json')
        self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
        self._save_data(self.smart_rules, 'smart_rules.json')
        self._save_data(self.active_admin_chat_id, 'active_admin_chat_id.json')
        self._save_data(self.last_analysis_time, 'last_analysis_time.json')
        self._save_data(self.pending_edits, 'pending_edits.json')
        self._save_data(self.collected_games, 'collected_games.json')
        self._save_data(self.single_trigger_until, 'single_trigger_until.json')
        self._save_data(self.quarantined_rules, 'quarantined_rules.json')
        self._save_data(self.wait_until_next_update, 'wait_until_next_update.json')
        self._save_data(self.last_inter_update_time, 'last_inter_update.json')
        self._save_data(self.last_report_sent, 'last_report_sent.json')

    # ======== TEMPS & SESSIONS ========
    def now(self):
        return datetime.now(BENIN_TZ)

    def is_in_session(self):
        h = self.now().hour
        return any(start <= h < end for start, end in PREDICTION_SESSIONS)

    def current_session_label(self):
        h = self.now().hour
        for start, end in PREDICTION_SESSIONS:
            if start <= h < end:
                return f"{start:02d}h00 – {end:02d}h00"
        return "Hors session"

    # ======== RAPPORTS ========
    def check_and_send_reports(self):
        if not self.telegram_message_sender or not self.prediction_channel_id:
            return

        now = self.now()
        key_date = now.strftime("%Y-%m-%d")
        report_hours = {6: ("01h00", "06h00"), 12: ("09h00", "12h00"), 18: ("15h00", "18h00"), 0: ("21h00", "00h00")}

        if now.hour in report_hours and now.minute == 0:
            key = f"{key_date}_{now.hour}"
            if self.last_report_sent.get(key):
                return

            start, end = report_hours[now.hour]
            total = len(self.predictions)
            wins = sum(1 for p in self.predictions.values() if str(p.get("status", "")).startswith("✅"))
            fails = sum(1 for p in self.predictions.values() if p.get("status") == "❌")
            rate = (wins / total * 100) if total else 0

            msg = (f"🎬 BILAN DE SESSION !\n\n"
                   f"⏰ Heure de Bénin : {now.strftime('%H:%M:%S')} - {now.strftime('%d/%m/%Y')}\n"
                   f"📅 Session fin de session : {start} – {end}\n"
                   f"🧠 Mode Intelligent : {'✅ ACTIF' if self.is_inter_mode_active else '❌ INACTIF'}\n"
                   f"🔄 Mise à jour des règles : {self.get_inter_version()}\n"
                   f"📌 Version : {self.get_inter_version()}\n\n"
                   f"📊 Taux de réussite : {rate:.2f}%\n"
                   f"📉 Taux d’échec : {100 - rate:.2f}%\n\n"
                   f"Merci à tous ceux qui ont utilisé le code promo ! 🎟️💙\n\n"
                   f"👨‍💻 Développeur : Sossou Kouamé\n"
                   f"🎟️ Code Promo : Koua229")

            self.telegram_message_sender(self.prediction_channel_id, msg)
            self.last_report_sent[key] = True
            self._save_all_data()

    def get_inter_version(self):
        if not self.last_inter_update_time:
            return "Base neuve"
        return datetime.fromtimestamp(self.last_inter_update_time, BENIN_TZ).strftime("%Y-%m-%d | %Hh%M")

    def set_channel_id(self, channel_id: int, channel_type: str):
        if not isinstance(self.config_data, dict):
            self.config_data = {}
        if channel_type == 'source':
            self.target_channel_id = channel_id
            self.config_data['target_channel_id'] = channel_id
        elif channel_type == 'prediction':
            self.prediction_channel_id = channel_id
            self.config_data['prediction_channel_id'] = channel_id
        self._save_data(self.config_data, 'channels_config.json')
        return True

    # --- Outils d'Extraction/Comptage ---
    def _extract_parentheses_content(self, text: str) -> List[str]:
        pattern = r'\(([^)]+)\)'
        return re.findall(pattern, text)

    def _count_cards_in_content(self, content: str) -> int:
        normalized_content = content.replace("❤️", "♥️")
        return len(re.findall(r'(\d+|[AKQJ])(♠️|♥️|♦️|♣️)', normalized_content, re.IGNORECASE))

    def has_pending_indicators(self, text: str) -> bool:
        indicators = ['⏰', '▶', '🕐', '➡️']
        return any(indicator in text for indicator in indicators)

    def has_completion_indicators(self, text: str) -> bool:
        completion_indicators = ['✅', '🔰']
        return any(indicator in text for indicator in completion_indicators)

    def is_final_result_structurally_valid(self, text: str) -> bool:
        matches = self._extract_parentheses_content(text)
        num_sections = len(matches)
        if num_sections < 2:
            return False
        if ('#T' in text or '🔵#R' in text) and num_sections >= 2:
            return True
        if num_sections == 2:
            content_1 = matches[0]
            content_2 = matches[1]
            count_1 = self._count_cards_in_content(content_1)
            count_2 = self._count_cards_in_content(content_2)
            if (count_1 == 3 and count_2 == 2) or (count_1 == 3 and count_2 == 3) or (count_1 == 2 and count_2 == 3):
                return True
        return False

    def extract_game_number(self, message: str) -> Optional[int]:
        match = re.search(r'#N(\d+)\.', message, re.IGNORECASE)
        if not match:
            match = re.search(r'🔵(\d+)🔵', message)
        return int(match.group(1)) if match else None

    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        normalized_content = content.replace("♥️", "❤️")
        return re.findall(r'(\d+|[AKQJ])(♠️|❤️|♦️|♣️)', normalized_content, re.IGNORECASE)

    def get_first_card_info(self, message: str) -> Optional[Tuple[str, str]]:
        match = re.search(r'\(([^)]*)\)', message)
        if not match:
            return None
        details = self.extract_card_details(match.group(1))
        if details:
            v, c = details[0]
            if c == "❤️":
                c = "♥️"
            return f"{v.upper()}{c}", c
        return None

    def get_all_cards_in_first_group(self, message: str) -> List[str]:
        match = re.search(r'\(([^)]*)\)', message)
        if not match:
            return []
        details = self.extract_card_details(match.group(1))
        cards = []
        for v, c in details:
            normalized_c = "♥️" if c == "❤️" else c
            cards.append(f"{v.upper()}{normalized_c}")
        return cards

    # --- Logique INTER (Collecte et Analyse) ---
    def collect_inter_data(self, game_number: int, message: str):
        info = self.get_first_card_info(message)
        if not info:
            return
        full_card, suit = info
        result_suit_normalized = suit.replace("❤️", "♥️")
        if game_number in self.collected_games:
            existing_data = self.sequential_history.get(game_number)
            if existing_data and existing_data.get('carte') == full_card:
                logger.debug(f"🧠 Jeu {game_number} déjà collecté, ignoré.")
                return
            else:
                logger.info(f"🧠 Jeu {game_number} mis à jour: {existing_data.get('carte') if existing_data else 'N/A'} -> {full_card}")
                self.inter_data = [e for e in self.inter_data if e.get('numero_resultat') != game_number]
        self.sequential_history[game_number] = {'carte': full_card, 'date': datetime.now().isoformat()}
        self.collected_games.add(game_number)
        n_minus_2 = game_number - 2
        trigger_entry = self.sequential_history.get(n_minus_2)
        if trigger_entry:
            trigger_card = trigger_entry['carte']
            self.inter_data.append({
                'numero_resultat': game_number,
                'declencheur': trigger_card,
                'numero_declencheur': n_minus_2,
                'result_suit': result_suit_normalized,
                'date': datetime.now().isoformat()
            })
            logger.info(f"🧠 Jeu {game_number} collecté pour INTER: {trigger_card} -> {result_suit_normalized}")
        limit = game_number - 50
        self.sequential_history = {k: v for k, v in self.sequential_history.items() if k >= limit}
        self.collected_games = {g for g in self.collected_games if g >= limit}
        self._save_all_data()

    def analyze_and_set_smart_rules(self, chat_id: int = None, initial_load: bool = False, force_activate: bool = False):
        result_suit_groups = defaultdict(lambda: defaultdict(int))
        for entry in self.inter_data:
            trigger_card = entry['declencheur']
            result_suit = entry['result_suit']
            result_suit_groups[result_suit][trigger_card] += 1
        self.smart_rules = []
        for result_suit in ['♠️', '♥️', '♦️', '♣️']:
            result_normalized = "❤️" if result_suit == "♥️" else result_suit
            triggers_for_this_suit = result_suit_groups.get(result_suit, {})
            if not triggers_for_this_suit:
                continue
            top_triggers = sorted(triggers_for_this_suit.items(), key=lambda x: x[1], reverse=True)[:2]
            for trigger_card, count in top_triggers:
                self.smart_rules.append({
                    'trigger': trigger_card,
                    'predict': result_normalized,
                    'count': count,
                    'result_suit': result_normalized
                })
        if force_activate:
            self.is_inter_mode_active = True
            if chat_id:
                self.active_admin_chat_id = chat_id
        elif self.smart_rules:
            self.is_inter_mode_active = True
        elif not initial_load:
            self.is_inter_mode_active = False
        self.last_analysis_time = time.time()
        self._save_all_data()
        logger.info(f"🧠 Analyse terminée. Règles trouvées: {len(self.smart_rules)}. Mode actif: {self.is_inter_mode_active}")
        if chat_id is not None and self.telegram_message_sender:
            if self.smart_rules:
                msg = f"✅ **Analyse terminée !**\n\n{len(self.smart_rules)} règles créées à partir de {len(self.inter_data)} jeux collectés.\n\n🧠 **Mode INTER activé automatiquement**"
            else:
                msg = f"⚠️ **Pas assez de données**\n\n{len(self.inter_data)} jeux collectés. Continuez à jouer pour créer des règles."
            self.telegram_message_sender(chat_id, msg)
        for key in list(self.quarantined_rules.keys()):
            try:
                trigger, suit = key.split("_", 1)
                rule = next((r for r in self.smart_rules if r.get("trigger") == trigger and r.get("predict") == suit), None)
                if not rule or rule.get("count", 0) > self.quarantined_rules[key]:
                    del self.quarantined_rules[key]
                    logger.info(f"🔓 Quarantaine levée : {key}")
            except Exception as e:
                logger.error(f"Erreur traitement quarantaine {key}: {e}")

    def check_and_update_rules(self):
        if time.time() - self.last_analysis_time > 1800:
            logger.info("🧠 Mise à jour INTER périodique (30 min).")
            if len(self.inter_data) >= 3:
                self.analyze_and_set_smart_rules(chat_id=self.active_admin_chat_id, force_activate=True)
            else:
                self.analyze_and_set_smart_rules(chat_id=self.active_admin_chat_id)

    def check_and_send_automatic_predictions(self):
        if not self.telegram_message_sender or not self.prediction_channel_id or not self.smart_rules:
            return
        now = self.now()
        h = now.hour
        if not (h >= 22 or h < 2):
            return
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            rules_for_suit = [r for r in self.smart_rules if r.get('predict') == suit]
            if not rules_for_suit:
                continue
            sorted_rules = sorted(rules_for_suit, key=lambda x: x.get('count', 0), reverse=True)
            rule_to_use = sorted_rules[1] if len(sorted_rules) >= 2 else sorted_rules[0]
            game_num = 9000 + len([p for p in self.predictions if p.get('is_auto_prediction', False)])
            target_game = game_num + 2
            msg = f"🔵{target_game}🔵:{rule_to_use['predict']} statut :⏳\n\n🧠 Déclencheur INTER : {rule_to_use['trigger']} (TOP {'2' if len(sorted_rules) >= 2 and rule_to_use == sorted_rules[1] else '1'})"
            try:
                self.telegram_message_sender(self.prediction_channel_id, msg)
                logger.info(f"🤖 Prédiction auto envoyée: {rule_to_use['trigger']} → {suit}")
                self.predictions[target_game] = {
                    'predicted_costume': suit,
                    'status': 'auto_pending',
                    'predicted_from': game_num,
                    'predicted_from_trigger': rule_to_use['trigger'],
                    'is_auto_prediction': True,
                    'message_text': msg
                }
                self._save_all_data()
            except Exception as e:
                logger.error(f"Erreur envoi prédiction auto: {e}")

    def get_bot_status(self):
        total = len(self.predictions)
        wins = sum(1 for p in self.predictions.values() if str(p.get("status", "")).startswith("✅"))
        fails = sum(1 for p in self.predictions.values() if p.get("status") == "❌")
        return (f"📊 **STATUT DU BOT**\n\n"
                f"🧠 Mode intelligent : {'ACTIF' if self.is_inter_mode_active else 'INACTIF'}\n"
                f"🎯 Session : {self.current_session_label()}\n"
                f"📈 Prédictions : {total}\n"
                f"✅ Réussites : {wins}\n"
                f"❌ Échecs : {fails}\n\n"
                f"🔖 Version IA : {self.get_inter_version()}")

    def get_inter_status(self) -> Tuple[str, Dict]:
        data_count = len(self.inter_data)
        if not self.smart_rules:
            message = f"🧠 **MODE INTER - {'✅ ACTIF' if self.is_inter_mode_active else '❌ INACTIF'}**\n\n"
            message += f"📊 **{data_count} jeux collectés**\n"
            message += "⚠️ Pas encore assez de règles créées.\n\n"
            message += "**Cliquez sur 'Analyser' pour générer les règles !**"
            keyboard_buttons = [
                [{'text': '🔄 Analyser et Activer', 'callback_data': 'inter_apply'}]
            ]
            if self.is_inter_mode_active:
                keyboard_buttons.append([{'text': '❌ Désactiver', 'callback_data': 'inter_default'}])
            keyboard = {'inline_keyboard': keyboard_buttons}
        else:
            rules_by_result = defaultdict(list)
            for rule in self.smart_rules:
                rules_by_result[rule['result_suit']].append(rule)
            message = f"🧠 **MODE INTER - {'✅ ACTIF' if self.is_inter_mode_active else '❌ INACTIF'}**\n\n"
            message += f"📊 **{len(self.smart_rules)} règles** créées ({data_count} jeux analysés):\n\n"
            for suit in ['♠️', '❤️', '♦️', '♣️']:
                if suit in rules_by_result:
                    message += f"**Pour prédire {suit}:**\n"
                    for rule in rules_by_result[suit]:
                        message += f"  • {rule['trigger']} ({rule['count']}x)\n"
                    message += "\n"
            if self.is_inter_mode_active:
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '🔄 Relancer Analyse', 'callback_data': 'inter_apply'}],
                        [{'text': '❌ Désactiver', 'callback_data': 'inter_default'}]
                    ]
                }
            else:
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '🚀 Activer INTER', 'callback_data': 'inter_apply'}]
                    ]
                }
        return message, keyboard

    def _apply_quarantine(self, prediction):
        trigger_used = prediction.get('predicted_from_trigger')
        predicted_suit = prediction.get('predicted_costume')
        if not trigger_used or not predicted_suit:
            return
        key = f"{trigger_used}_{predicted_suit}"
        for rule in self.smart_rules:
            if rule.get('trigger') == trigger_used and rule.get('predict') == predicted_suit:
                self.quarantined_rules[key] = rule.get('count', 1)
                logger.info(f"🔒 Quarantaine appliquée: {key} (compte: {rule.get('count', 1)})")
                break
        self.wait_until_next_update = time.time() + 3600
        self._save_all_data()

    def _predict_next_game_after_failure(self, failed_predicted_game: int, failed_prediction: Dict):
        """Prédit automatiquement le jeu suivant après une prédiction échouée (❌)"""
        try:
            next_game_source = failed_predicted_game
            predicted_costume = failed_prediction.get('predicted_costume')
            
            if not predicted_costume or not self.telegram_message_sender or not self.prediction_channel_id:
                return
            
            # Créer la prédiction pour le jeu suivant
            next_predicted_game = next_game_source + 2
            prediction_text = f"🔵{next_predicted_game}🔵:{predicted_costume} statut :⏳"
            
            # Envoyer le message de prédiction
            try:
                self.telegram_message_sender(self.prediction_channel_id, prediction_text)
                logger.info(f"🎯 Prédiction automatique du jeu {next_predicted_game} après échec du jeu {failed_predicted_game}")
                
                # Enregistrer la nouvelle prédiction
                self.predictions[next_predicted_game] = {
                    'predicted_costume': predicted_costume,
                    'status': 'pending',
                    'predicted_from': next_game_source,
                    'predicted_from_trigger': failed_prediction.get('predicted_from_trigger'),
                    'message_text': prediction_text,
                    'is_follow_up': True,
                    'followed_up_from': failed_predicted_game
                }
                self._save_all_data()
            except Exception as e:
                logger.error(f"❌ Erreur envoi prédiction suivi: {e}")
        except Exception as e:
            logger.error(f"❌ Erreur création prédiction suivi: {e}")

    # --- CŒUR DU SYSTÈME : PRÉDICTION ---
    def should_wait_for_edit(self, text: str, message_id: int) -> bool:
        if self.has_pending_indicators(text):
            game_number = self.extract_game_number(text)
            if message_id not in self.pending_edits:
                self.pending_edits[message_id] = {
                    'game_number': game_number,
                    'original_text': text,
                    'timestamp': datetime.now().isoformat()
                }
                self._save_data(self.pending_edits, 'pending_edits.json')
            return True
        return False

    def should_predict(self, message: str) -> Tuple[bool, Optional[int], Optional[str], Optional[bool]]:
        self.check_and_send_reports()
        self.check_and_update_rules()
        self.check_and_send_automatic_predictions()
        if not self.is_in_session():
            return False, None, None, None
        if any(p.get('status') == 'pending' for p in self.predictions.values()):
            logger.info("⚠️ Une prédiction est en attente de vérification. Nouvelle prédiction annulée.")
            return False, None, None, None
        game_number = self.extract_game_number(message)
        if not game_number:
            return False, None, None, None
        if game_number in self.predictions and self.predictions[game_number].get('status') == 'pending':
            logger.debug(f"⚠️ Jeu {game_number} déjà prédit, en attente de vérification.")
            return False, None, None, None
        if self.last_predicted_game_number and (game_number - self.last_predicted_game_number < 3):
            return False, None, None, None
        info = self.get_first_card_info(message)
        if not info:
            return False, None, None, None
        first_card, _ = info
        predicted_suit = None
        trigger_used = None
        is_inter_prediction = False

        # A. PRIORITÉ 1 : MODE INTER - Utiliser les 2 TOP de CHAQUE costume
        if self.is_inter_mode_active and self.smart_rules:
            use_single_trigger_only = time.time() < self.single_trigger_until
            rules_by_suit = defaultdict(list)
            for rule in self.smart_rules:
                rules_by_suit[rule['predict']].append(rule)
            for suit in ['♠️', '♥️', '❤️', '♦️', '♣️']:
                if suit not in rules_by_suit:
                    continue
                suit_rules = sorted(rules_by_suit[suit], key=lambda x: x.get('count', 0), reverse=True)
                rules_to_check = suit_rules[:1] if use_single_trigger_only else suit_rules[:2]
                for rule in rules_to_check:
                    if rule['trigger'] == first_card:
                        key = f"{first_card}_{rule['predict']}"
                        if key in self.quarantined_rules and self.quarantined_rules[key] >= rule.get("count", 1):
                            logger.debug(f"🔒 Règle en quarantaine: {key}")
                            continue
                        predicted_suit = rule['predict']
                        trigger_used = rule['trigger']
                        is_inter_prediction = True
                        mode_info = "TOP1" if use_single_trigger_only else "TOP2"
                        logger.info(f"🔮 INTER ({mode_info}): Déclencheur {first_card} -> Prédit {predicted_suit}")
                        break
                if predicted_suit:
                    break

        # B. MODE STATIQUE UNIQUEMENT SI INTER EST INACTIF
        if not self.is_inter_mode_active and not predicted_suit and first_card in STATIC_RULES:
            predicted_suit = STATIC_RULES[first_card]
            trigger_used = first_card
            is_inter_prediction = False
            logger.info(f"🔮 STATIQUE: Déclencheur {first_card} -> Prédit {predicted_suit}")

        if predicted_suit:
            if self.last_prediction_time and time.time() < self.last_prediction_time + self.prediction_cooldown:
                return False, None, None, None
            return True, game_number, predicted_suit, is_inter_prediction

        return False, None, None, None

    def prepare_prediction_text(self, game_number_source: int, predicted_costume: str) -> str:
        target_game = game_number_source + 2
        return f"🔵{target_game}🔵:{predicted_costume} statut :⏳"

    def make_prediction(self, game_number_source: int, suit: str, message_id_bot: int, is_inter: bool = False):
        target = game_number_source + 2
        txt = self.prepare_prediction_text(game_number_source, suit)
        trigger_used = None
        info = self.get_first_card_info(self.sequential_history.get(game_number_source, {}).get('message', ''))
        if info:
            trigger_used = info[0]
        self.predictions[target] = {
            'predicted_costume': suit,
            'status': 'pending',
            'predicted_from': game_number_source,
            'predicted_from_trigger': trigger_used,
            'message_text': txt,
            'message_id': message_id_bot,
            'is_inter': is_inter
        }
        self.last_prediction_time = time.time()
        self.last_predicted_game_number = game_number_source
        self.consecutive_fails = 0
        self._save_all_data()

    # --- VERIFICATION LOGIQUE ---
    def verify_prediction(self, message: str) -> Optional[Dict]:
        return self._verify_prediction_common(message, is_edited=False)

    def verify_prediction_from_edit(self, message: str) -> Optional[Dict]:
        return self._verify_prediction_common(message, is_edited=True)

    def check_costume_in_first_parentheses(self, message: str, predicted_costume: str) -> bool:
        all_cards = self.get_all_cards_in_first_group(message)
        if not all_cards:
            logger.debug("🎯 Aucune carte trouvée dans le premier groupe")
            return False
        logger.info(f"🎯 Vérification: {len(all_cards)} carte(s) dans premier groupe: {', '.join(all_cards)}")
        normalized_costume = predicted_costume.replace("❤️", "♥️")
        for card in all_cards:
            if card.endswith(normalized_costume):
                logger.info(f"✅ Costume {normalized_costume} trouvé dans carte {card}")
                return True
        logger.debug(f"❌ Costume {normalized_costume} non trouvé dans {', '.join(all_cards)}")
        return False

    def _verify_prediction_common(self, message: str, is_edited: bool = False) -> Optional[Dict]:
        self.check_and_send_reports()
        game_number = self.extract_game_number(message)
        if not game_number:
            return None
        is_structurally_valid = self.is_final_result_structurally_valid(message)
        if not is_structurally_valid:
            return None
        if not self.predictions:
            return None
        verification_result = None
        for predicted_game in sorted(self.predictions.keys()):
            prediction = self.predictions[predicted_game]
            if prediction.get('status') != 'pending':
                continue
            predicted_costume = prediction.get('predicted_costume')
            if not predicted_costume:
                continue
            verification_found = False
            for offset in [0, 1, 2]:
                check_game_number = predicted_game + offset
                if game_number == check_game_number:
                    costume_found = self.check_costume_in_first_parentheses(message, predicted_costume)
                    if costume_found:
                        status_symbol = SYMBOL_MAP.get(offset, f"✅{offset}️⃣")
                        updated_message = f"🔵{predicted_game}🔵:{predicted_costume} statut :{status_symbol}"
                        prediction['status'] = 'won'
                        prediction['verification_count'] = offset
                        prediction['final_message'] = updated_message
                        self.consecutive_fails = 0
                        self._save_all_data()
                        verification_result = {
                            'type': 'edit_message',
                            'predicted_game': str(predicted_game),
                            'new_message': updated_message,
                            'message_id_to_edit': prediction.get('message_id')
                        }
                        verification_found = True
                        break
            if verification_found:
                break
            if game_number > predicted_game + 2:
                status_symbol = "❌"
                updated_message = f"🔵{predicted_game}🔵:{predicted_costume} statut :{status_symbol}"
                prediction['status'] = 'lost'
                prediction['final_message'] = updated_message
                if prediction.get('is_inter'):
                    self._apply_quarantine(prediction)
                    self.is_inter_mode_active = False
                    logger.info("❌ Échec INTER : Désactivation automatique + quarantaine.")
                else:
                    self.consecutive_fails += 1
                    if self.consecutive_fails >= 2:
                        self.single_trigger_until = time.time() + 3600
                        self.analyze_and_set_smart_rules(force_activate=True)
                        logger.info("⚠️ 2 Échecs Statiques : Activation INTER (TOP1 uniquement pendant 1h).")
                self._save_all_data()
                verification_result = {
                    'type': 'edit_message',
                    'predicted_game': str(predicted_game),
                    'new_message': updated_message,
                    'message_id_to_edit': prediction.get('message_id')
                }
                # Prédiction automatique du jeu suivant après ❌
                self._predict_next_game_after_failure(predicted_game, prediction)
                break
        return verification_result

    def reset_automatic_predictions(self) -> Dict[str, int]:
        inter_predictions = {}
        non_inter_count = 0
        inter_game_numbers = set()
        for game_num, prediction in self.predictions.items():
            if prediction.get('is_inter', False):
                inter_predictions[game_num] = prediction
                inter_game_numbers.add(game_num)
            else:
                non_inter_count += 1
        self.predictions = inter_predictions
        inter_message_ids = {pred.get('message_id') for pred in inter_predictions.values() if pred.get('message_id')}
        new_pending_edits = {}
        removed_pending = 0
        for msg_id, edit_data in self.pending_edits.items():
            game_num = edit_data.get('game_number')
            if game_num in inter_game_numbers or msg_id in inter_message_ids:
                new_pending_edits[msg_id] = edit_data
            else:
                removed_pending += 1
        self.pending_edits = new_pending_edits
        self.last_prediction_time = 0
        self.last_predicted_game_number = 0
        self.consecutive_fails = 0
        self.single_trigger_until = 0
        self._save_all_data()
        logger.info(f"🔄 Reset manuel: {non_inter_count} prédictions auto supprimées, {len(inter_predictions)} INTER conservées")
        return {
            'removed': non_inter_count,
            'kept_inter': len(inter_predictions),
            'removed_pending': removed_pending
        }

# Global instance
card_predictor = CardPredictor()
