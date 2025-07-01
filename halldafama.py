# -- coding: utf-8 --
# halldafama.py - Módulo para a aba Hall da Fama do AnkiChat (v1.4 - Layout em Tabela)

from datetime import datetime
from aqt.qt import (
    QWidget, QHBoxLayout, QVBoxLayout, QTextBrowser, Qt, QLabel, QFont,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView
)

class HallOfFameTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_achievements = {}
        self.setup_ui()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        
        ranking_layout = QVBoxLayout()
        
        title_label = QLabel("🏆 Ranking de Medalhas 🏆")
        font = title_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        title_label.setFont(font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # --- INÍCIO DA CORREÇÃO: Troca QListWidget por QTableWidget ---
        self.user_list = QTableWidget()
        self.user_list.setColumnCount(5)
        self.user_list.setHorizontalHeaderLabels(["#", "Nome", "🥇", "🥈", "🥉"])
        self.user_list.itemSelectionChanged.connect(self.on_user_selected)
        
        # Configurações de aparência da tabela
        self.user_list.verticalHeader().setVisible(False)
        self.user_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.user_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.user_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        # Ajusta o tamanho das colunas
        header = self.user_list.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Rank #
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)         # Nome
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Ouro
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Prata
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Bronze
        # --- FIM DA CORREÇÃO ---
        
        ranking_layout.addWidget(title_label)
        ranking_layout.addWidget(self.user_list)
        
        ranking_widget = QWidget()
        ranking_widget.setLayout(ranking_layout)

        self.achievements_area = QTextBrowser()
        self.achievements_area.setReadOnly(True)
        self.achievements_area.setOpenExternalLinks(True)
        
        main_layout.addWidget(ranking_widget, 1)
        main_layout.addWidget(self.achievements_area, 2)

    def populate_users(self, data):
        self.all_achievements = data.get("achievements", {})
        users_data = data.get("users", {})
        
        ranked_users = []
        all_nicks = {ud.get("nickname") for ud in users_data.values() if ud.get("nickname")}

        for nick in all_nicks:
            achievements = self.all_achievements.get(nick, {})
            counts = {"gold": 0, "silver": 0, "bronze": 0}
            for ach_data in achievements.values():
                medal = ach_data.get("medal")
                if medal in counts:
                    counts[medal] += 1
            
            ranked_users.append({
                "nick": nick,
                "gold": counts["gold"],
                "silver": counts["silver"],
                "bronze": counts["bronze"]
            })

        ranked_users.sort(key=lambda u: (-u['gold'], -u['silver'], -u['bronze'], u['nick']))

        # --- INÍCIO DA CORREÇÃO: Popula a tabela em vez da lista ---
        self.user_list.setRowCount(len(ranked_users))
        for i, user_data in enumerate(ranked_users):
            rank_item = QTableWidgetItem(str(i + 1))
            name_item = QTableWidgetItem(user_data['nick'])
            gold_item = QTableWidgetItem(str(user_data['gold']))
            silver_item = QTableWidgetItem(str(user_data['silver']))
            bronze_item = QTableWidgetItem(str(user_data['bronze']))

            # Centraliza o texto nas colunas numéricas
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            gold_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            silver_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            bronze_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Armazena o nick puro no item do nome para referência
            name_item.setData(Qt.ItemDataRole.UserRole, user_data['nick'])

            self.user_list.setItem(i, 0, rank_item)
            self.user_list.setItem(i, 1, name_item)
            self.user_list.setItem(i, 2, gold_item)
            self.user_list.setItem(i, 3, silver_item)
            self.user_list.setItem(i, 4, bronze_item)
        # --- FIM DA CORREÇÃO ---

    def on_user_selected(self):
        selected_items = self.user_list.selectedItems()
        if not selected_items:
            return
        
        # --- CORREÇÃO: Pega o nick a partir da linha selecionada ---
        current_row = self.user_list.currentRow()
        if current_row < 0:
            return
        
        name_item = self.user_list.item(current_row, 1) # Coluna 1 é a do nome
        if not name_item:
            return
            
        nick = name_item.data(Qt.ItemDataRole.UserRole)
        # --- FIM DA CORREÇÃO ---
        
        self.achievements_area.clear()
        user_achievements_dict = self.all_achievements.get(nick, {})
        user_achievements = list(user_achievements_dict.values())

        if not user_achievements:
            self.achievements_area.setText(f"Nenhuma conquista para {nick}.")
            return
            
        medals = {"gold": 0, "silver": 0, "bronze": 0}
        for ach in user_achievements:
            if ach.get("medal") in medals:
                medals[ach["medal"]] += 1
        summary = (f'<b>Conquistas de {nick}:</b><br>'
                   f'🥇({medals["gold"]}) 🥈({medals["silver"]}) 🥉({medals["bronze"]})<hr>')
        self.achievements_area.append(summary)
        
        sorted_achievements = sorted(user_achievements, key=lambda x: int(str(x.get('season_key', '0_0')).split('_')[0]), reverse=True)

        for ach in sorted_achievements:
            season_str = "Temporada Desconhecida"
            try:
                key_parts = str(ach.get('season_key', '0_0')).split('_')
                season_number = key_parts[0]
                
                if len(key_parts) > 1:
                    year_or_ts = key_parts[1]
                    if len(year_or_ts) > 4:
                        year = datetime.fromtimestamp(int(year_or_ts)).year
                    else:
                        year = year_or_ts
                    season_str = f"Temporada {season_number} ({year})"
                else:
                    season_str = f"Temporada {season_number}"

            except (ValueError, IndexError, TypeError):
                season_str = f"Temporada {ach.get('season_key', 'N/A')}"

            position_text = ach.get('position', 'N/A')
            position_str = f"{position_text}º" if isinstance(position_text, int) else position_text

            line = (f"<b>{season_str}:</b><br>"
                    f"  Divisão: {ach.get('division', 'N/A')} | Posição na Divisão: {position_str}<br>"
                    f"  Pontos de Retenção: {ach.get('retention_points', 0)} | Pontos de Meta: {ach.get('meta_points', 0)}")
            self.achievements_area.append(line)