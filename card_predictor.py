# card_predictor.py

import re
import json
import logging
import time
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

STATIC_RULES = {
    'A♠️': '❤️', '2♠️': '♣️', '3♠️': '♦️', '4♠️': '♠️',
    'A❤️': '♣️', '2❤️': '♦️', '3❤️': '♠️', '4❤️': '❤️',
    'A♦️': '♠️', '2♦️': '❤️', '3♦️': '♣️', '4♦️': '♦️',
    'A♣️': '♦️', '2♣️': '♠️', '3♣️': '❤️', '4♣️': '♣️'
}

class CardPredictor:
    def __init__(self, telegram_message_sender=None):
        self.telegram_message_sender = telegram_message_sender
        self.predictions = {}
        self.inter_data = []
        self.smart_rules = []
        self.collected_games = set()
        self.sequential_history = {} # Nouveau : historique séquentiel (N-2 -> N)
        # Configuration automatique forcée
        self.target_channel_id = -1002682552255
        self.prediction_channel_id = -1003554569009
        self.is_inter_mode_active = True # Activé par défaut
        self.auto_prediction_enabled = True
        self.last_predicted_game_number = 0
        self.last_prediction_time = 0.0
        self.prediction_cooldown = 120
        self._last_trigger_used = None
        self.ef_interval = 0 # Intervalle en minutes pour la commande /ef
        self.last_ef_time = 0
        self._load_all_data()
        # S'assurer que les IDs sont bien ceux demandés même après chargement
        self.target_channel_id = -1002682552255
        self.prediction_channel_id = -1003554569009
        self._save_all_data()

    def _load_all_data(self):
        try:
            if os.path.exists('predictions.json'):
                with open('predictions.json', 'r') as f: self.predictions = json.load(f)
            if os.path.exists('inter_data.json'):
                with open('inter_data.json', 'r') as f: self.inter_data = json.load(f)
            if os.path.exists('smart_rules.json'):
                with open('smart_rules.json', 'r') as f: self.smart_rules = json.load(f)
            if os.path.exists('sequential_history.json'):
                with open('sequential_history.json', 'r') as f: self.sequential_history = {int(k): v for k, v in json.load(f).items()}
            if os.path.exists('inter_mode_status.json'):
                with open('inter_mode_status.json', 'r') as f:
                    data = json.load(f)
                    self.is_inter_mode_active = data.get('active', True)
                    self.ef_interval = data.get('ef_interval', 0)
                    self.last_ef_time = data.get('last_ef_time', 0)
        except Exception as e:
            logger.error(f"Error loading data: {e}")

    def _save_all_data(self):
        try:
            with open('predictions.json', 'w') as f: json.dump(self.predictions, f)
            with open('inter_data.json', 'w') as f: json.dump(self.inter_data, f)
            with open('smart_rules.json', 'w') as f: json.dump(self.smart_rules, f)
            with open('sequential_history.json', 'w') as f: json.dump(self.sequential_history, f)
            with open('inter_mode_status.json', 'w') as f: 
                json.dump({
                    'active': self.is_inter_mode_active,
                    'ef_interval': self.ef_interval,
                    'last_ef_time': self.last_ef_time
                }, f)
            with open('config_ids.json', 'w') as f:
                json.dump({
                    'target_channel_id': self.target_channel_id,
                    'prediction_channel_id': self.prediction_channel_id
                }, f)
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def extract_game_number(self, text: str) -> Optional[int]:
        text = text.upper()
        m = re.search(r'(?:#|N|#N)(\d+)', text, re.IGNORECASE)
        if m: return int(m.group(1))
        m = re.search(r'🔵(\d+)🔵', text)
        if m: return int(m.group(1))
        return None

    def get_all_cards_in_first_group(self, text: str) -> List[str]:
        text = text.replace("❤️", "♥️").replace("❤️️", "♥️").replace(" ", "")
        cards = re.findall(r'([AJQK\d]+(?:♠️|♥️|♦️|♣️|♠|❤️|♦|♣))', text)
        return [self.normalize_card(c) for c in cards]

    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        normalized_content = content.replace("♥️", "❤️")
        return re.findall(r'(\d+|[AKQJ])(♠️|❤️|♦️|♣️)', normalized_content, re.IGNORECASE)

    def normalize_card(self, card_str: str) -> str:
        return card_str.replace("❤️", "♥️")

    def check_ef_reset(self):
        if self.ef_interval > 0:
            now = time.time()
            if now - self.last_ef_time >= (self.ef_interval * 60):
                self.predictions = {}
                self.inter_data = []
                self.smart_rules = []
                self.collected_games = set()
                self.sequential_history = {}
                self.last_ef_time = now
                self._save_all_data()
                logger.info(f"♻️ Reset automatique /ef ({self.ef_interval} min) effectué.")

    def collect_inter_data(self, game_number: int, message: str):
        info = self.get_first_card_info(message)
        if not info: return
        full_card, suit = info
        trigger_card_normalized = self.normalize_card(full_card)
        result_suit_normalized = suit.replace("❤️", "♥️")
        if game_number in self.collected_games:
            existing_data = self.sequential_history.get(game_number)
            if existing_data and existing_data.get('carte') == trigger_card_normalized: return
            self.inter_data = [e for e in self.inter_data if e.get('numero_resultat') != game_number]
        self.sequential_history[game_number] = {'carte': trigger_card_normalized, 'date': datetime.now().isoformat()}
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
        limit = game_number - 50
        self.sequential_history = {k:v for k,v in self.sequential_history.items() if k >= limit}
        self.collected_games = {g for g in self.collected_games if g >= limit}
        self._save_all_data()

    def get_first_card_info(self, message: str) -> Optional[Tuple[str, str]]:
        match = re.search(r'\(([^)]*)\)', message)
        content = match.group(1) if match else message
        details = self.extract_card_details(content)
        if details:
            v, c = details[0]
            return f"{v.upper()}{c}", c 
        return None

    def analyze_and_set_smart_rules(self, chat_id=None, force_activate=False):
        if len(self.inter_data) < 1: return
        trigger_patterns = defaultdict(Counter)
        for entry in self.inter_data:
            trigger_patterns[entry['declencheur']][entry['result_suit']] += 1
        new_rules = []
        for trigger, results in trigger_patterns.items():
            suit, count = results.most_common(1)[0]
            if count >= 1:
                new_rules.append({'trigger': trigger, 'predict': suit, 'count': count, 'total': sum(results.values())})
        new_rules.sort(key=lambda x: x['count'], reverse=True)
        self.smart_rules = new_rules
        if force_activate: self.is_inter_mode_active = True
        self._save_all_data()

    def should_predict(self, text: str):
        if not self.auto_prediction_enabled: return False, None, None, False
        game_num = self.extract_game_number(text)
        if not game_num: return False, None, None, False
        if self.last_predicted_game_number > 0:
            target_game = game_num + 2
            gap = target_game - self.last_predicted_game_number
            if gap < 3: return False, None, None, False
        for p in self.predictions.values():
            if p.get('status') == 'pending': return False, None, None, False
        
        first_group_match = re.search(r'\d+\(([^)]+)\)', text)
        if not first_group_match: return False, None, None, False
        cards_to_check = self.get_all_cards_in_first_group(first_group_match.group(1))
        if not cards_to_check: return False, None, None, False
        
        prediction, is_inter, trigger_used = None, False, None
        
        # Séparation stricte des modes
        if self.is_inter_mode_active:
            if self.smart_rules:
                rules_by_suit = defaultdict(list)
                for rule in self.smart_rules: rules_by_suit[rule['predict']].append(rule)
                # On regarde toutes les cartes du premier groupe
                found_rules = []
                for card in cards_to_check:
                    card_clean = card.replace("❤️", "♥️")
                    for suit, rules in rules_by_suit.items():
                        # On compare aux 8 meilleurs tops (règles intelligentes)
                        for rank, r in enumerate(rules[:8]):
                            if card_clean == r['trigger']:
                                found_rules.append({'rank': rank, 'suit': suit, 'trigger': card_clean})
                
                if found_rules:
                    # On prend la règle qui a le meilleur rang (plus proche du Top 1)
                    found_rules.sort(key=lambda x: x['rank'])
                    best = found_rules[0]
                    prediction, trigger_used, is_inter = best['suit'], best['trigger'], True
        else:
            # Mode statique uniquement si INTER est inactif
            # On prend la première carte du groupe qui a une règle statique
            for card in cards_to_check:
                card_name = card.replace("♥️", "❤️")
                if card_name in STATIC_RULES:
                    prediction, trigger_used, is_inter = STATIC_RULES[card_name], card, False
                    break
        
        if prediction:
            self._last_trigger_used = trigger_used
            return True, game_num + 2, prediction, is_inter
        return False, None, None, False

    def prepare_prediction_text(self, game_num: int, suit: str, ki: int = 0, show_ki: bool = False) -> str:
        # On utilise une entité invisible pour stocker le ki sans qu'il soit vu
        # Correction: On utilise un espace insécable (\u200b) au lieu des commentaires HTML
        invisible_ki = f"<a href='tg://user?id={ki}'>\u200b</a>"
        ki_display = f" {ki}" if show_ki else "\u200b"
        # On ajoute le ki au milieu en bas avec un sablier par défaut
        return f"🔵{game_num}🔵:{suit}statut :⏳\n\n          ⏳{ki_display}{invisible_ki}"

    def has_completion_indicators(self, text: str) -> bool:
        return '✅' in text or '❌' in text

    def _verify_prediction_common(self, text: str) -> Dict:
        game_num = self.extract_game_number(text)
        if not game_num: return {}
        first_group_match = re.search(r'\d+\(([^)]+)\)', text)
        if not first_group_match:
            cards = self.get_all_cards_in_first_group(text)
            first_group_cards = cards[:3] if cards else []
        else:
            first_group_cards = self.get_all_cards_in_first_group(first_group_match.group(1))
        target_game = None
        for offset in [0, 1, 2]:
            check_num = game_num - offset
            if str(check_num) in self.predictions:
                pred = self.predictions[str(check_num)]
                if pred.get('status') == 'pending':
                    target_game = str(check_num)
                    break
        if not target_game: return {}
        pred = self.predictions[target_game]
        predicted_suit = pred['predicted_costume']
        found_in_group = False
        for card in first_group_cards:
            suit = ""
            for s in ['♠️', '♥️', '♦️', '♣️', '♠', '❤️', '♦', '♣']:
                if s in card:
                    suit = s
                    break
            if not suit: suit = card[-1]
            if suit in ["❤️", "❤️️"]: suit = "♥️"
            if suit == predicted_suit:
                found_in_group = True
                break
        offset = game_num - int(target_game)
        
        status_emoji = "⏳"
        if found_in_group:
            status = 'won'
            if offset == 0: 
                symbol = "✅0️⃣"
                status_emoji = "🔥"
            elif offset == 1: 
                symbol = "✅1️⃣"
                status_emoji = "❤️"
            elif offset == 2: 
                symbol = "✅2️⃣"
                status_emoji = "👍🏻"
            else: 
                symbol = "✅"
                status_emoji = "🔥"
        else:
            if offset >= 2: 
                status, symbol = 'lost', "❌"
                status_emoji = "😎"
            else: return {}
            
        pred['status'] = status
        self._save_all_data()
        ki_base = pred.get('ki_base', 0)
        ki_final = ki_base + offset
        
        # Le ki final est stocké dans un caractère invisible à la fin du message
        invisible_ki = f"<a href='tg://user?id={ki_final}'>\u200b</a>"
        return {
            'type': 'edit_message', 
            'message_id_to_edit': pred['message_id'], 
            'new_message': f"🔵{target_game}🔵:{pred['predicted_costume']}statut :{symbol}\n\n          {status_emoji} {ki_final}{invisible_ki}",
            'offset': offset,
            'ki_final': ki_final
        }

    def get_session_report_preview(self) -> str:
        finished_preds = [p for p in self.predictions.values() if p.get('status') in ['won', 'lost']]
        total = len(finished_preds)
        won = sum(1 for p in finished_preds if p.get('status') == 'won')
        lost = sum(1 for p in finished_preds if p.get('status') == 'lost')
        rate = (won / total * 100) if total > 0 else 0
        return (f"📊 **BILAN 24h/24**\n\n📝 Total prédictions : {total}\n✅ Gagnés : {won}\n❌ Perdus : {lost}\n📈 Taux : {rate:.1f}%")

    def get_inter_status(self):
        is_active = self.is_inter_mode_active
        total_collected = len(self.inter_data)
        message = f"🧠 **MODE INTER - {'✅ ACTIF' if is_active else '❌ INACTIF'}**\n\n"
        message += f"📊 {len(self.smart_rules)} règles créées ({total_collected} jeux analysés):\n\n"
        rules_by_suit = defaultdict(list)
        for rule in self.smart_rules: rules_by_suit[rule['predict']].append(rule)
        for suit in ['♠️', '♥️', '♦️', '♣️']:
            suit_display = suit.replace("♥️", "❤️")
            message += f"Pour prédire {suit_display}:\n"
            actual_suit = suit if suit in rules_by_suit else suit.replace("❤️", "♥️")
            if actual_suit in rules_by_suit:
                for r in rules_by_suit[actual_suit][:8]:
                    trigger_display = r['trigger'].replace("♥️", "❤️")
                    message += f"  • {trigger_display} ({r['count']}x)\n"
            message += "\n"
        kb = {'inline_keyboard': [[{'text': '🔄 Actualiser Analyse', 'callback_data': 'inter_apply'}]]}
        return message, kb
