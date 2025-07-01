# -- coding: utf-8 --
# zoom.py - Módulo para gerenciar o zoom da interface do AnkiChat

from aqt.qt import QFont, QTextBrowser, QListWidget
from aqt.utils import tooltip
from aqt import mw

class ZoomManager:
    def __init__(self, chat_window):
        self.cw = chat_window
        self.config = chat_window.config
        self.ctrl_zoom_level = self.config.get("ctrl_zoom_level", 0)
        self.base_font_sizes = chat_window.base_font_sizes

    def apply_and_save_zoom(self):
        """Aplica o zoom e salva a configuração."""
        self.apply_zoom()
        self.config["ctrl_zoom_level"] = self.ctrl_zoom_level
        mw.addonManager.writeConfig(__name__, self.config)

    def zoom_in(self):
        """Aumenta o nível de zoom."""
        if self.ctrl_zoom_level < 20:
            self.ctrl_zoom_level += 1
            self.apply_and_save_zoom()
        else:
            tooltip("Zoom máximo atingido")

    def zoom_out(self):
        """Diminui o nível de zoom."""
        if (self.base_font_sizes["chat"] + self.ctrl_zoom_level - 1) >= 6:
            self.ctrl_zoom_level -= 1
            self.apply_and_save_zoom()
        else:
            tooltip("Zoom mínimo atingido")

    def apply_zoom(self):
        """Aplica o nível de zoom atual a todos os componentes da UI."""
        tooltip(f"Zoom: {self.ctrl_zoom_level}")
        cw = self.cw
        
        # Aplica zoom aos widgets
        cw.user_list.setFont(QFont("Arial", self.base_font_sizes["user_list"] + self.ctrl_zoom_level))
        cw.goals_area.setFont(QFont("Courier New", self.base_font_sizes["goals"] + self.ctrl_zoom_level))
        cw.hall_of_fame_widget.user_list.setFont(QFont("Arial", self.base_font_sizes["hall_of_fame_list"] + self.ctrl_zoom_level))
        cw.hall_of_fame_widget.achievements_area.setFont(QFont("Arial", self.base_font_sizes["hall_of_fame_ach"] + self.ctrl_zoom_level))
        cw.legacy_tab.legacy_area.setFont(QFont("Arial", self.base_font_sizes["legacy"] + self.ctrl_zoom_level))
        cw.message_input.setFont(QFont("Arial", self.base_font_sizes["input"] + self.ctrl_zoom_level))

        # Lista de todos os widgets de chat para aplicar o zoom
        chat_widgets = [cw.main_chat_area, cw.quiz_chat_area, cw.quiz_ranking_area] + list(cw.chat_manager.private_chats.values())
        
        for chat_widget in chat_widgets:
            if isinstance(chat_widget, QTextBrowser):
                font = chat_widget.font()
                font.setPointSize(self.base_font_sizes["chat"] + self.ctrl_zoom_level)
                chat_widget.setFont(font)
            elif isinstance(chat_widget, QListWidget):
                for i in range(chat_widget.count()):
                    item = chat_widget.item(i)
                    label = chat_widget.itemWidget(item)
                    if label:
                        font = label.font()
                        # Ajusta o tamanho da fonte para separadores de data
                        if "---" in label.text():
                            font.setPointSize(self.base_font_sizes["chat"] - 2 + self.ctrl_zoom_level)
                        else:
                            font.setPointSize(self.base_font_sizes["chat"] + self.ctrl_zoom_level)
                        label.setFont(font)
                        item.setSizeHint(label.sizeHint())