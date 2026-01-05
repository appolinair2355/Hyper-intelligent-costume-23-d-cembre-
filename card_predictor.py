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
        self.deleted_tops = [] # Liste des 10 derniers tops supprimés
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
            if os.path.exists('deleted_tops.json'):
                with open('deleted_tops.json', 'r') as f: self.deleted_tops = json.load(f)
            if os.path.exists('sequential_history.json'):
                with open('sequential_history.json', 'r') as f: self.sequential_history = {int(k): v for k, v in json.load(f).items()}
            if os.path.exists('inter_mode_status.json'):
                with open('inter_mode_status.json', 'r') as f: self.is_inter_mode_active = json.load(f).get('active', True)
        except Exception as e:
            logger.error(f"Error loading data: {e}")

    def _save_all_data(self):
        try:
            with open('predictions.json', 'w') as f: json.dump(self.predictions, f)
            with open('inter_data.json', 'w') as f: json.dump(self.inter_data, f)
            with open('smart_rules.json', 'w') as f: json.dump(self.smart_rules, f)
            with open('deleted_tops.json', 'w') as f: json.dump(self.deleted_tops, f)
            with open('sequential_history.json', 'w') as f: json.dump(self.sequential_history, f)
            with open('inter_mode_status.json', 'w') as f: json.dump({'active': self.is_inter_mode_active}, f)
            with open('config_ids.json', 'w') as f:
                json.dump({
                    'target_channel_id': self.target_channel_id,
                    'prediction_channel_id': self.prediction_channel_id
                }, f)
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def extract_game_number(self, text: str) -> Optional[int]:
        # Nettoyage pour ignorer la casse
        text = text.upper()
        # Recherche précise du numéro de jeu avec préfixe N suivi de chiffres, supporte #N, N, #n, n
        m = re.search(r'(?:#|N|#N)(\d+)', text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        # Recherche précise du numéro de jeu entre cercles bleus
        m = re.search(r'🔵(\d+)🔵', text)
        if m:
            return int(m.group(1))
        return None

    def get_all_cards_in_first_group(self, text: str) -> List[str]:
        # Nettoie le texte pour uniformiser les cœurs et supprimer les espaces parasites
        # On remplace aussi les cœurs sans variation selector pour la détection
        text = text.replace("❤️", "♥️").replace("❤️️", "♥️").replace(" ", "")
        # Recherche toutes les cartes (Valeur + Enseigne)
        # Amélioration du regex pour capturer les variantes d'enseignes
        cards = re.findall(r'([AJQK\d]+(?:♠️|♥️|♦️|♣️|♠|❤️|♦|♣))', text)
        # Normalisation immédiate des cartes extraites
        return [self.normalize_card(c) for c in cards]

    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        """Extrait les cartes au format (Valeur, Enseigne)."""
        normalized_content = content.replace("♥️", "❤️")
        return re.findall(r'(\d+|[AKQJ])(♠️|❤️|♦️|♣️)', normalized_content, re.IGNORECASE)

    def normalize_card(self, card_str: str) -> str:
        """Normalise une carte pour le stockage (cœurs uniformisés)."""
        return card_str.replace("❤️", "♥️")

    def collect_inter_data(self, game_number: int, message: str):
        """Collecte les données (N-2 -> N) même sur messages temporaires (⏰)."""
        info = self.get_first_card_info(message)
        if not info: return
        
        full_card, suit = info
        # Normaliser le déclencheur stocké
        trigger_card_normalized = self.normalize_card(full_card)
        result_suit_normalized = suit.replace("❤️", "♥️")
        
        # Vérifier si déjà dans collected_games
        if game_number in self.collected_games:
            existing_data = self.sequential_history.get(game_number)
            if existing_data and existing_data.get('carte') == trigger_card_normalized:
                logger.debug(f"🧠 Jeu {game_number} déjà collecté, ignoré.")
                return
            else:
                # Mise à jour de la carte (cas rare mais possible)
                logger.info(f"🧠 Jeu {game_number} mis à jour: {existing_data.get('carte') if existing_data else 'N/A'} -> {trigger_card_normalized}")
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
            logger.info(f"🧠 Jeu {game_number} collecté pour INTER: {trigger_card} -> {result_suit_normalized}")

        # Nettoyage des anciennes données (garde les 50 derniers)
        limit = game_number - 50
        self.sequential_history = {k:v for k,v in self.sequential_history.items() if k >= limit}
        self.collected_games = {g for g in self.collected_games if g >= limit}
        
        self._save_all_data()

    def get_first_card_info(self, message: str) -> Optional[Tuple[str, str]]:
        """Retourne la PREMIÈRE carte du PREMIER groupe (déclencheur)."""
        # On cherche d'abord dans les parenthèses
        match = re.search(r'\(([^)]*)\)', message)
        content = match.group(1) if match else message
        
        details = self.extract_card_details(content)
        if details:
            v, c = details[0]
            return f"{v.upper()}{c}", c 
        return None

    def analyze_and_set_smart_rules(self, chat_id=None, force_activate=False):
        if len(self.inter_data) < 1: # Réduit le minimum pour tester et s'assurer que ça tourne
            logger.warning("⚠️ Pas assez de données pour l'analyse INTER.")
            return
        
        # On regroupe les résultats par déclencheur pour voir ce qui sort le plus souvent après une carte
        trigger_patterns = defaultdict(Counter)
        for entry in self.inter_data:
            # On utilise 'declencheur' et 'result_suit' de inter_data
            trigger_patterns[entry['declencheur']][entry['result_suit']] += 1
            
        new_rules = []
        for trigger, results in trigger_patterns.items():
            # Pour chaque déclencheur, on prend le résultat le plus fréquent
            suit, count = results.most_common(1)[0]
            # On ne garde que si le déclencheur a été vu au moins 1 fois
            if count >= 1:
                new_rules.append({
                    'trigger': trigger, 
                    'predict': suit, 
                    'count': count,
                    'total': sum(results.values())
                })
        
        # Trier par fiabilité (nombre d'occurrences)
        new_rules.sort(key=lambda x: x['count'], reverse=True)
        
        self.smart_rules = new_rules
        if force_activate: self.is_inter_mode_active = True
        self._save_all_data()
        logger.info(f"✨ Mise à jour des règles INTER effectuée ({len(new_rules)} règles)")

    def should_predict(self, text: str) -> Tuple[bool, Optional[int], Optional[str], bool]:
        if not self.auto_prediction_enabled: return False, None, None, False
        game_num = self.extract_game_number(text)
        if not game_num: return False, None, None, False
        
        # RÈGLE STRICTE : Écart de exactement 3 par rapport au dernier numéro prédit
        if self.last_predicted_game_number > 0:
            target_game = game_num + 2
            gap = target_game - self.last_predicted_game_number
            if gap != 3:
                logger.info(f"🚫 Prédiction bloquée: Écart {gap} != 3 (Dernier: {self.last_predicted_game_number}, Actuel: {target_game})")
                return False, None, None, False
        
        # Vérifier si une prédiction est déjà en attente (pending) pour éviter d'en lancer deux
        for p in self.predictions.values():
            if p.get('status') == 'pending':
                logger.info("🚫 Prédiction bloquée: Une prédiction est déjà en attente.")
                return False, None, None, False
        # Extraction du groupe entre parenthèses (le premier groupe uniquement pour la prédiction rapide)
        first_group_match = re.search(r'\d+\(([^)]+)\)', text)
        if first_group_match:
            group_content = first_group_match.group(1)
            cards_to_check = self.get_all_cards_in_first_group(group_content)
        else:
            # Fallback sur les premières cartes trouvées si format différent
            all_cards = self.get_all_cards_in_first_group(text)
            cards_to_check = all_cards[:3] if all_cards else []
            
        if not cards_to_check: return False, None, None, False
        
        # LOGIQUE D'EXCLUSION MUTUELLE
        prediction, is_inter, trigger_used = None, False, None
        
        # 1. SI LE MODE INTER EST ACTIF -> ON N'UTILISE QUE INTER
        if self.is_inter_mode_active:
            if self.smart_rules:
                # Regrouper les règles par enseigne prédite
                rules_by_suit = defaultdict(list)
                for rule in self.smart_rules:
                    rules_by_suit[rule['predict']].append(rule)
                
                # Obtenir les Tops 7 pour chaque enseigne
                top7_by_suit = {}
                for suit, rules in rules_by_suit.items():
                    top7_by_suit[suit] = [r['trigger'] for r in rules[:7]]
                
                # Chercher si une carte du message est dans le Top 7 d'une enseigne
                best_rank = 99
                rule_to_remove = -1
                for card in cards_to_check:
                    card_clean = card.replace("❤️", "♥️")
                    for suit, top7 in top7_by_suit.items():
                        if card_clean in top7:
                            rank = top7.index(card_clean)
                            if rank < best_rank:
                                best_rank = rank
                                prediction = suit
                                trigger_used = card_clean
                                is_inter = True
                
                # Supprimer le top utilisé et l'ajouter à la liste des supprimés
                if prediction:
                    # Ne jamais utiliser deux fois même top pour prédire
                    # On le retire des règles et on réinitialise ses collectes
                            for i, rule in enumerate(self.smart_rules):
                                if rule['trigger'] == trigger_used and rule['predict'] == prediction:
                                    # Ajouter aux supprimés avec timestamp pour expiration (1h)
                                    self.deleted_tops.insert(0, {
                                        'text': f"{trigger_used} avait prédit {prediction}",
                                        'time': time.time()
                                    })
                                    self.deleted_tops = self.deleted_tops[:10]
                                    
                                    # Supprimer toutes les données liées à ce déclencheur pour repartir à zéro
                                    self.inter_data = [d for d in self.inter_data if d['declencheur'] != trigger_used]
                                    
                                    # Nettoyer aussi l'historique séquentiel pour ce déclencheur
                                    self.sequential_history = {k: v for k, v in self.sequential_history.items() if v.get('carte') != trigger_used}
                                    
                                    # Retirer de la liste des règles intelligentes
                                    self.smart_rules.pop(i)
                                    logger.info(f"🗑️ Top utilisé et remis à zéro (expirera dans 1h) : {trigger_used} -> {prediction}")
                                    self._save_all_data()
                                    break
        
        # 2. SI LE MODE INTER EST INACTIF -> ON N'UTILISE QUE LE STATIQUE
        else:
            info = self.get_first_card_info(text)
            if info:
                card_name = info[0].replace("♥️", "❤️")
                if card_name in STATIC_RULES:
                    prediction, trigger_used, is_inter = STATIC_RULES[card_name], info[0], False
        
        if prediction:
            self._last_trigger_used = trigger_used
            return True, game_num + 2, prediction, is_inter
            
        return False, None, None, False

    def prepare_prediction_text(self, game_num: int, suit: str) -> str:
        return f"🔵{game_num}🔵:{suit}statut :⏳"

    def has_completion_indicators(self, text: str) -> bool:
        return '✅' in text or '❌' in text

    def _verify_prediction_common(self, text: str) -> Dict:
        game_num = self.extract_game_number(text)
        if not game_num: return {}
        
        # Extraction du premier groupe de cartes entre parenthèses
        # Exemple: #N930. 0(J♥️10♥️J♠️) -> le groupe est J♥️10♥️J♠️
        first_group_match = re.search(r'\d+\(([^)]+)\)', text)
        if not first_group_match:
            # Fallback si le format est différent mais qu'on a des cartes
            cards = self.get_all_cards_in_first_group(text)
            first_group_cards = cards[:3] if cards else []
        else:
            group_content = first_group_match.group(1)
            first_group_cards = self.get_all_cards_in_first_group(group_content)

        # On vérifie si ce numéro de jeu correspond à une prédiction en attente (jusqu'à +2)
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
        
        # Vérification si le costume prédit est présent dans le premier groupe
        found_in_group = False
        for card in first_group_cards:
            # Extraction de l'enseigne de la carte du groupe
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
        
        # Calcul de l'offset pour l'affichage ✅0️⃣, ✅1️⃣, ✅2️⃣
        offset = game_num - int(target_game)
        
        if found_in_group:
            status = 'won'
            # symbol = f"✅{chr(0x30 + offset)}️⃣" # Génère ✅0️⃣, ✅1️⃣, ✅2️⃣
            if offset == 0: symbol = "✅0️⃣"
            elif offset == 1: symbol = "✅1️⃣"
            elif offset == 2: symbol = "✅2️⃣"
            else: symbol = "✅"
        else:
            # Si on est au dernier essai (offset 2) et que c'est toujours pas bon
            if offset >= 2:
                status = 'lost'
                symbol = "❌"
            else:
                # Sinon on attend encore le prochain numéro (n+1 ou n+2)
                return {}

        pred['status'] = status
        self._save_all_data()
        
        return {
            'type': 'edit_message', 
            'message_id_to_edit': pred['message_id'], 
            'new_message': f"🔵{target_game}🔵:{pred['predicted_costume']}statut :{symbol}",
            'offset': offset # Retourner l'offset pour la réaction
        }

    def get_session_report_preview(self) -> str:
        # On ne compte que les prédictions terminées (won ou lost)
        finished_preds = [p for p in self.predictions.values() if p.get('status') in ['won', 'lost']]
        total = len(finished_preds)
        won = sum(1 for p in finished_preds if p.get('status') == 'won')
        lost = sum(1 for p in finished_preds if p.get('status') == 'lost')
        
        # Calcul du taux basé sur les prédictions terminées
        rate = (won / total * 100) if total > 0 else 0
        
        return (f"📊 **BILAN 24h/24**\n\n"
                f"📝 Total prédictions : {total}\n"
                f"✅ Gagnés : {won}\n"
                f"❌ Perdus : {lost}\n"
                f"📈 Taux : {rate:.1f}%")

    def get_inter_status(self) -> Tuple[str, Dict]:
        is_active = self.is_inter_mode_active
        total_collected = len(self.inter_data)
        
        # Nettoyage des tops supprimés de plus de 1h (3600 secondes)
        now_ts = time.time()
        self.deleted_tops = [dt for dt in self.deleted_tops if isinstance(dt, dict) and now_ts - dt.get('time', 0) < 3600]
        self._save_all_data()
        
        message = f"🧠 **MODE INTER - {'✅ ACTIF' if is_active else '❌ INACTIF'}**\n\n"
        
        if self.deleted_tops:
            message += "Les 10 dernier tops supprimer (Expirent après 1h)\n"
            for dt in self.deleted_tops:
                if isinstance(dt, dict):
                    message += f"{dt.get('text')}\n"
                else:
                    message += f"{dt}\n"
            message += "\n"
            
            message += f"📊 {len(self.smart_rules)} règles créées ({total_collected} jeux analysés):\n\n"
        
        # Regrouper par enseigne de prédiction
        rules_by_suit = defaultdict(list)
        for rule in self.smart_rules:
            rules_by_suit[rule['predict']].append(rule)
            
        for suit in ['♠️', '♥️', '♦️', '♣️']:
            suit_display = suit.replace("♥️", "❤️")
            message += f"Pour prédire {suit_display}:\n"
            if suit in rules_by_suit or suit.replace("❤️", "♥️") in rules_by_suit:
                actual_suit = suit if suit in rules_by_suit else suit.replace("❤️", "♥️")
                # On affiche les 7 meilleures règles par enseigne
                for r in rules_by_suit[actual_suit][:7]:
                    trigger_display = r['trigger'].replace("♥️", "❤️")
                    message += f"  • {trigger_display} ({r['count']}x)\n"
            message += "\n"
        
        kb = {'inline_keyboard': [[{'text': '🔄 Actualiser Analyse', 'callback_data': 'inter_apply'}]]}
        return message, kb
