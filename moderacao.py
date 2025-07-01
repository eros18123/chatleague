# -- coding: utf-8 --
# moderacao.py - Módulo para as janelas de moderação do AnkiChat (v1.1 - Correção de Parent)

import threading

from aqt.qt import (
    QDialog, QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QPushButton, QLabel, pyqtSignal
)
from aqt.utils import tooltip

class BannedUsersDialog(QDialog):
    banned_users_loaded = pyqtSignal(list)
    def __init__(self, firebase_api, parent=None):
        super().__init__(parent)
        self.firebase = firebase_api
        self.parent_window = parent # Agora este será o ChatWindow
        self.setWindowTitle("Usuários Banidos")
        self.setMinimumSize(300, 400)
        self.setup_ui()
        self.banned_users_loaded.connect(self.populate_list)
        self.load_banned_users()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.list_widget)
        self.unban_button = QPushButton("Desbanir Usuário")
        self.unban_button.setEnabled(False)
        self.unban_button.clicked.connect(self.unban_user)
        layout.addWidget(self.unban_button)

    def load_banned_users(self):
        self.list_widget.clear()
        self.list_widget.addItem("Carregando...")
        threading.Thread(target=self._fetch_banned_users, daemon=True).start()

    def _fetch_banned_users(self):
        # Esta linha agora funciona, pois self.parent_window é o ChatWindow, que tem o id_token
        banned_data = self.firebase.get_data("banned_users", self.parent_window.id_token)
        nicks = sorted(list(banned_data.keys())) if banned_data else []
        self.banned_users_loaded.emit(nicks)

    def populate_list(self, nicks):
        self.list_widget.clear()
        if nicks:
            self.list_widget.addItems(nicks)
        else:
            self.list_widget.addItem("Nenhum usuário banido.")

    def on_selection_changed(self):
        self.unban_button.setEnabled(bool(self.list_widget.selectedItems()))

    def unban_user(self):
        selected_item = self.list_widget.currentItem()
        if not selected_item:
            return
        nick_to_unban = selected_item.text()
        threading.Thread(target=self._async_unban, args=(nick_to_unban,), daemon=True).start()
        self.list_widget.takeItem(self.list_widget.row(selected_item))
        tooltip(f"Usuário '{nick_to_unban}' foi desbanido.")

    def _async_unban(self, nickname):
        # Esta linha também funciona agora
        self.firebase.delete_data(f"banned_users/{nickname}", self.parent_window.id_token)

class ModerationDialog(QDialog):
    users_loaded = pyqtSignal(list)
    def __init__(self, firebase_api, parent_window):
        super().__init__(parent_window)
        self.firebase = firebase_api
        self.parent_window = parent_window # Este é o ChatWindow
        self.setWindowTitle("Painel de Moderação")
        self.setMinimumSize(500, 500)
        self.setup_ui()
        self.users_loaded.connect(self._update_user_list_gui)
        self.load_users()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel("Selecione um usuário para moderar:"))
        self.user_list = QListWidget()
        self.user_list.itemSelectionChanged.connect(self.on_user_selected)
        main_layout.addWidget(self.user_list)
        
        buttons_layout = QHBoxLayout()
        self.kick_button = QPushButton("Kickar")
        self.ban_button = QPushButton("Banir")
        self.delete_last_button = QPushButton("Apagar Última Msg")
        self.delete_all_button = QPushButton("Apagar Todas Msgs")
        buttons_layout.addWidget(self.kick_button)
        buttons_layout.addWidget(self.ban_button)
        buttons_layout.addWidget(self.delete_last_button)
        buttons_layout.addWidget(self.delete_all_button)
        main_layout.addLayout(buttons_layout)
        
        self.kick_button.clicked.connect(self.do_kick)
        self.ban_button.clicked.connect(self.do_ban)
        self.delete_last_button.clicked.connect(self.do_delete_last)
        self.delete_all_button.clicked.connect(self.do_delete_all)
        
        self.status_label = QLabel("Selecione um usuário da lista.")
        main_layout.addWidget(self.status_label)
        
        bottom_layout = QHBoxLayout()
        self.view_banned_button = QPushButton("Ver Banidos")
        self.view_banned_button.clicked.connect(self.show_banned_users)
        bottom_layout.addWidget(self.view_banned_button)
        bottom_layout.addStretch()
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(self.accept)
        bottom_layout.addWidget(close_button)
        main_layout.addLayout(bottom_layout)
        
        self.toggle_buttons(False)

    def show_banned_users(self):
        # <<< CORREÇÃO AQUI: Passamos self.parent_window (o ChatWindow) como o pai, não 'self' (o ModerationDialog) >>>
        dialog = BannedUsersDialog(self.firebase, self.parent_window)
        dialog.exec()

    def toggle_buttons(self, enabled):
        self.kick_button.setEnabled(enabled)
        self.ban_button.setEnabled(enabled)
        self.delete_last_button.setEnabled(enabled)
        self.delete_all_button.setEnabled(enabled)

    def on_user_selected(self):
        selected_items = self.user_list.selectedItems()
        if selected_items:
            nick = selected_items[0].text()
            is_self = (nick == self.parent_window.nickname)
            self.toggle_buttons(not is_self)
            if is_self:
                self.status_label.setText("Você não pode moderar a si mesmo.")
            else:
                self.status_label.setText(f"Usuário selecionado: {nick}")
        else:
            self.toggle_buttons(False)
            self.status_label.setText("Selecione um usuário da lista.")

    def get_selected_nick(self):
        selected_items = self.user_list.selectedItems()
        return selected_items[0].text() if selected_items else None

    def do_kick(self):
        nick = self.get_selected_nick()
        if nick:
            self.parent_window.kick_user(nick)
            self.status_label.setText(f"Comando 'Kickar' enviado para {nick}.")

    def do_ban(self):
        nick = self.get_selected_nick()
        if nick:
            self.parent_window.ban_user(nick)
            self.status_label.setText(f"Comando 'Banir' enviado para {nick}.")

    def do_delete_last(self):
        nick = self.get_selected_nick()
        if nick:
            self.parent_window.delete_last_message(nick)
            self.status_label.setText(f"Comando 'Apagar Última Msg' enviado para {nick}.")

    def do_delete_all(self):
        nick = self.get_selected_nick()
        if nick:
            self.parent_window.delete_all_messages(nick)
            self.status_label.setText(f"Comando 'Apagar Todas Msgs' enviado para {nick}.")

    def load_users(self):
        self.user_list.clear()
        self.user_list.addItem("Carregando usuários...")
        threading.Thread(target=self._fetch_and_populate_users, daemon=True).start()

    def _fetch_and_populate_users(self):
        all_users_data = self.firebase.get_data("users", self.parent_window.id_token) or {}
        nicks = sorted([ud.get("nickname", "Desconhecido") for ud in all_users_data.values()])
        self.users_loaded.emit(nicks)

    def _update_user_list_gui(self, nicks):
        self.user_list.clear()
        if nicks:
            self.user_list.addItems(nicks)
        else:
            self.user_list.addItem("Nenhum usuário registrado encontrado.")
        self.status_label.setText("Selecione um usuário da lista.")