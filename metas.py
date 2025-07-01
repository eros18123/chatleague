# -- coding: utf-8 --
# metas.py - Módulo para gerenciar Metas, Ranking e Legado do AnkiChat (v3.4 - Retorno para Temporada Semanal)

import random
from datetime import datetime, timedelta
import os
import re

from aqt.qt import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox
)
from aqt.utils import tooltip
from aqt import mw

class GoalsManager:
    def __init__(self, chat_window):
        self.chat_window = chat_window
        self.firebase = chat_window.firebase
        self.addon_path = chat_window.addon_path

    def _format_seconds(self, seconds):
        minutes, sec = divmod(seconds, 60)
        return f"{int(minutes)}m {int(sec)}s"

    def render_goals_list(self, data, search_term=""):
        users_data = data.get('users', {})
        goals_data = data.get('goals', {})
        cw = self.chat_window

        if cw.is_connected:
            my_goal_data = goals_data.get(cw.uid, {})
            my_flag = my_goal_data.get("flag", "")
            cw.update_my_flag_display(my_flag)

        cw.goals_area.clear()

        now = datetime.now()
        # --- MUDANÇA: Retorna a contagem regressiva para o fim da semana ---
        end_of_week = (now - timedelta(days=now.weekday()) + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=0)
        time_left = end_of_week - now
        days = time_left.days
        hours, rem = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        countdown_str = f"{days}d, {hours}h e {minutes}m"
        # --- FIM DA MUDANÇA ---
        
        league_status = self.firebase.get_data("league_status", cw.id_token) or {}
        season_number = league_status.get("season_counter", 1)
        season_header = f"<b>{season_number}ª Temporada - {cw._('season_ends_in')} {countdown_str}</b><br>"
        cw.goals_area.append(season_header)

        is_night_mode = mw.pm.night_mode

        divisions = {"A": [], "B": [], "C": [], "D": []}
        for uid, goal_data in goals_data.items():
            nick = users_data.get(uid, {}).get("nickname")
            if not nick: continue
            if search_term and not nick.lower().startswith(search_term.lower()):
                continue
            divisions.setdefault(goal_data.get("division", "D"), []).append((nick, goal_data))
        
        for div_name in sorted(divisions.keys()):
            div_users = divisions[div_name]
            header = f"--- SÉRIE {div_name} ---"
            cw.goals_area.append(f"<b>{header}</b>")
            if not div_users:
                cw.goals_area.append(f"<i>{cw._('no_user_in_division')}</i><br>")
                continue

            def sort_key(item):
                user, data = item
                return (data.get("retention_points", 0), data.get("meta_points", 0), data.get("study_time_week", 0), data.get("new_cards_week", 0), random.random())
            
            div_users.sort(key=sort_key, reverse=True)
            
            num_users_in_div = len(div_users)
            num_to_promote = 2 if div_name != "A" else 0
            
            if num_users_in_div <= 2: num_to_relegate = 0
            elif num_users_in_div == 3: num_to_relegate = 1
            else: num_to_relegate = 2
            if div_name == "D": num_to_relegate = 0

            for i, (user, data) in enumerate(div_users):
                flag_html = ""
                flag_filename = data.get("flag")
                if flag_filename:
                    flag_path = os.path.join(self.addon_path, 'bandeiras', flag_filename)
                    if os.path.exists(flag_path):
                        flag_html = f'<img src="{flag_path}" width="16" height="11"> '

                pos = i + 1; points = data.get("retention_points", 0); materia = data.get("materia", "N/A")
                reviews_today = data.get("reviews_today", 0); goal_daily = data.get("goal_daily", 100)
                reviews_week = data.get("reviews_week", 0)
                time_today_str = self._format_seconds(data.get("study_time_today", 0))
                time_week_str = self._format_seconds(data.get("study_time_week", 0))
                
                total_reviews = data.get("reviews_week", 0); total_retention_pts = data.get("retention_points", 0)
                max_possible_pts = total_reviews * 5
                aproveitamento = (total_retention_pts / max_possible_pts * 100) if max_possible_pts > 0 else 0
                
                line = (f"{pos}. {flag_html}{user} ({materia}) - {points} PR ({aproveitamento:.0f}%) | "
                        f"{cw._('today')}: {reviews_today}/{goal_daily} ({time_today_str}) | "
                        f"{cw._('week')}: {reviews_week} ({time_week_str})")
                
                bg_color = None
                if cw.is_connected and user == cw.nickname:
                    bg_color = "#4a4a2a" if is_night_mode else "#ffffbb"
                elif pos <= num_to_promote:
                    bg_color = "#2E4E2E" if is_night_mode else "#aaffaa"
                elif pos > num_users_in_div - num_to_relegate:
                    bg_color = "#5A2A2A" if is_night_mode else "#ffaaaa"
                
                if bg_color:
                    cw.goals_area.append(f'<p style="background-color:{bg_color}; margin:0; padding: 2px;">{line}</p>')
                else:
                    cw.goals_area.append(line)
            cw.goals_area.append("")

    def edit_my_goal(self):
        cw = self.chat_window
        if not cw.is_connected:
            tooltip("Você precisa estar conectado para editar sua meta.")
            return
        dialog = QDialog(cw)
        dialog.setWindowTitle("Definir Metas e Matéria")
        layout = QFormLayout(dialog)
        current_goals = self.firebase.get_data(f"goals/{cw.uid}", cw.id_token) or {}
        materia_entry = QLineEdit()
        materia_entry.setText(current_goals.get("materia", ""))
        daily_goal_entry = QLineEdit()
        daily_goal_entry.setText(str(current_goals.get("goal_daily", "100")))
        weekly_goal_entry = QLineEdit()
        weekly_goal_entry.setText(str(current_goals.get("goal_weekly", "700")))
        layout.addRow("Matéria Principal:", materia_entry)
        layout.addRow("Meta Diária de Cards:", daily_goal_entry)
        layout.addRow("Meta Semanal de Cards:", weekly_goal_entry)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            materia = materia_entry.text().strip()
            try:
                goal_daily = int(daily_goal_entry.text().strip())
                goal_weekly = int(weekly_goal_entry.text().strip())
            except ValueError:
                tooltip("Valores de meta inválidos. Use apenas números.")
                return
            updates = {
                "materia": materia,
                "goal_daily": goal_daily,
                "goal_weekly": goal_weekly
            }
            self.firebase.patch_data(f"goals/{cw.uid}", updates, cw.id_token)
            tooltip("Metas atualizadas!")

    def check_and_process_season_end(self):
        cw = self.chat_window
        
        try:
            league_status = self.firebase.get_data("league_status", cw.id_token) or {}
            
            # --- MUDANÇA: Retorna a lógica de verificação para a semana do calendário ---
            last_processed_str = str(league_status.get("last_processed_week", "0_0"))

            now = datetime.now()
            current_week = now.isocalendar()[1]
            current_year = now.year
            current_week_str = f"{current_week}_{current_year}"

            if last_processed_str == current_week_str:
                return
            # --- FIM DA MUDANÇA ---

            print(f"AnkiChat: Detectado fim de temporada. Processando Semana {last_processed_str} -> {current_week_str}...")
            
            all_goals = self.firebase.get_data("goals", cw.id_token) or {}
            all_users = self.firebase.get_data("users", cw.id_token) or {}
            if not all_goals or not all_users:
                return

            season_number = league_status.get("season_counter", 1)
            season_key = f"{season_number}_{current_year}"

            def sort_key(item):
                _uid, data = item
                return (data.get("retention_points", 0), data.get("meta_points", 0), data.get("study_time_week", 0), data.get("new_cards_week", 0), random.random())

            divisions_data = {"A": [], "B": [], "C": [], "D": []}
            for user_uid, data in all_goals.items():
                divisions_data.setdefault(data.get("division", "D"), []).append((user_uid, data))

            for div_users in divisions_data.values():
                div_users.sort(key=sort_key, reverse=True)

            for div_name, div_users in divisions_data.items():
                for i, (user_uid, data) in enumerate(div_users):
                    position = i + 1
                    nick = all_users.get(user_uid, {}).get("nickname")
                    if not nick or re.search(r'[.#$\[\]]', nick): continue

                    legacy_entry = {
                        "season_key": season_key, "division": div_name, "position": position,
                        "retention_points": data.get("retention_points", 0),
                        "meta_points": data.get("meta_points", 0), "medal": None
                    }
                    if position == 1: legacy_entry["medal"] = "gold"
                    elif position == 2: legacy_entry["medal"] = "silver"
                    elif position == 3: legacy_entry["medal"] = "bronze"
                    
                    self.firebase.put_data(f"legacy/{user_uid}/{season_key}", legacy_entry, cw.id_token)
                    if legacy_entry["medal"]:
                        self.firebase.put_data(f"achievements/{nick}/{season_key}", legacy_entry, cw.id_token)

            new_assignments = {}
            PROMOTION_COUNT = 2
            for uid, _ in divisions_data.get("D", [])[:PROMOTION_COUNT]: new_assignments[uid] = "C"
            for uid, _ in divisions_data.get("C", [])[:PROMOTION_COUNT]: new_assignments[uid] = "B"
            for uid, _ in divisions_data.get("B", [])[:PROMOTION_COUNT]: new_assignments[uid] = "A"

            def get_relegation_count(division_size):
                if division_size <= 2: return 0
                if division_size == 3: return 1
                return 2

            rele_count_A = get_relegation_count(len(divisions_data.get("A", [])))
            if rele_count_A > 0:
                for uid, _ in divisions_data["A"][-rele_count_A:]: new_assignments[uid] = "B"
            rele_count_B = get_relegation_count(len(divisions_data.get("B", [])))
            if rele_count_B > 0:
                for uid, _ in divisions_data["B"][-rele_count_B:]: new_assignments[uid] = "C"
            rele_count_C = get_relegation_count(len(divisions_data.get("C", [])))
            if rele_count_C > 0:
                for uid, _ in divisions_data["C"][-rele_count_C:]: new_assignments[uid] = "D"
            
            final_goals_payload = {}
            for user_uid, data in all_goals.items():
                new_data = data.copy()
                new_data.update({
                    "retention_points": 0, "meta_points": 0, "reviews_week": 0,
                    "reviews_today": 0, "study_time_week": 0, "study_time_today": 0,
                    "new_cards_week": 0, "last_update_day": 0
                })
                if user_uid in new_assignments:
                    new_data["division"] = new_assignments[user_uid]
                else:
                    new_data["division"] = data.get("division", "D")
                if data.get("reviews_week", 0) == 0:
                    new_data["division"] = "D"
                final_goals_payload[user_uid] = new_data

            self.firebase.put_data("goals", final_goals_payload, cw.id_token)
            
            # --- MUDANÇA: Atualiza o status da liga com a semana processada ---
            # Remove o timestamp antigo para manter o banco de dados limpo.
            self.firebase.put_data("league_status", {
                "season_counter": season_number + 1,
                "last_processed_week": current_week_str,
                "season_start_timestamp": None 
            }, cw.id_token)
            # --- FIM DA MUDANÇA ---
            
            cw.force_refresh_signal.emit()
            print(f"AnkiChat: Processamento da Temporada {season_number} concluído.")

        except Exception as e:
            print(f"AnkiChat [ERRO CRÍTICO] em check_and_process_season_end: {e}")