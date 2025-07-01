# __init__.py

import sys
import os
import re
import base64
import webbrowser

addon_path = os.path.dirname(os.path.abspath(__file__))

vendor_path = os.path.join(addon_path, "vendor")
if os.path.isdir(vendor_path):
    sys.path.insert(0, vendor_path)

sys.path.insert(0, addon_path)

import threading
import json
import time
from datetime import datetime, timedelta
import random
import locale

import requests

from aqt import mw
from aqt.qt import (
    QAction, QDialog, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QTabWidget, QTextEdit, QLineEdit, QPushButton, QLabel, pyqtSignal, QColor,
    QDialogButtonBox, QFormLayout, Qt, QMenu, QInputDialog, QFont, QColorDialog,
    QTextBrowser, QAbstractItemView, QFrame, QComboBox, QIcon, QSize, QStyle
)
from aqt.utils import tooltip
from aqt import gui_hooks

from .quiz import QuizManager
from .metas import GoalsManager
from .moderacao import ModerationDialog
from .chat import ChatManager
from .halldafama import HallOfFameTab
from .meulegado import LegacyTab
from .mudaridioma import LanguageManager
from .zoom import ZoomManager
from .auth import AuthManager, FirebaseAPI, background_updater
from .traducao import TranslationManager

class ChatWindow(QDialog):
    new_messages_polled = pyqtSignal(dict)
    user_update_received = pyqtSignal(dict)
    goals_update_received = pyqtSignal(dict)
    hall_of_fame_update_received = pyqtSignal(dict)
    connection_succeeded = pyqtSignal(str, str, str, str, str, str)
    connection_failed = pyqtSignal(str)
    connection_lost_signal = pyqtSignal()
    legacy_update_received = pyqtSignal(dict)
    force_refresh_signal = pyqtSignal()
    timer_updated = pyqtSignal(str)
    quiz_ranking_data_fetched = pyqtSignal(dict, dict)
    quiz_score_updated = pyqtSignal(str) 
    history_loaded = pyqtSignal(list)
    
    quiz_start_command_received = pyqtSignal(dict)
    quiz_stop_command_received = pyqtSignal()
    main_ranking_update_signal = pyqtSignal() # <<< 1. SINAL DEFINIDO AQUI

    def __init__(self, parent=None):
        super().__init__(parent)
        self.firebase = background_updater.firebase
        self.admin_email = "eros18123@gmail.com"; self.admin_nick = self.admin_email.split('@')[0]
        
        self.addon_path = os.path.dirname(os.path.abspath(__file__))
        
        self.autologin_file = os.path.join(self.addon_path, 'autologin.json')
        self.login_history_file = os.path.join(self.addon_path, 'login_history.json')
        self.flags_path = os.path.join(self.addon_path, 'bandeiras')
        os.makedirs(self.flags_path, exist_ok=True)
        self.user_flags_cache = {}
        self.current_flag_filename = None

        self.nickname = "Convidado"; self.email = None; self.id_token = None
        self.uid = None; self.refresh_token = None; self.token_expires_at = None
        self.is_connected = False
        
        self.message_color = "#000000"
        self.displayed_message_ids = set()
        
        self.config = mw.addonManager.getConfig(__name__) or {}
        self.base_font_sizes = {
            "user_list": 11, "goals": 11, "hall_of_fame_list": 11,
            "hall_of_fame_ach": 11, "legacy": 11, "chat": 12, "input": 11
        }

        self.cached_goals_data = None
        self.current_quiz_category = None
        self.cached_quiz_scores = {}
        self.cached_quiz_users = {}
        self.current_quiz_data = None
        
        self.last_selected_quiz_category = self.config.get("last_quiz_category", "Geral")

        self.setWindowTitle("AnkiChat - Firebase")
        
        self.auth_manager = AuthManager(self)
        self.lang_manager = LanguageManager(self)
        self.zoom_manager = ZoomManager(self)
        self.chat_manager = ChatManager(self)
        self.quiz_manager = QuizManager(self.firebase, self, self.addon_path)
        self.goals_manager = GoalsManager(self)
        self.translation_manager = TranslationManager(self)
        
        self._ = self.lang_manager._

        self.setup_ui()
        
        self.new_messages_polled.connect(self.handle_polled_messages)
        self.user_update_received.connect(self.update_user_list)
        self.connection_succeeded.connect(self.on_connection_success)
        self.connection_failed.connect(self.on_connection_failure)
        self.connection_lost_signal.connect(self.handle_connection_lost)
        self.force_refresh_signal.connect(self.force_full_refresh)
        self.timer_updated.connect(self.update_timer_display)
        self.quiz_ranking_data_fetched.connect(self._render_quiz_ranking_gui)
        self.quiz_score_updated.connect(self._optimistically_update_ranking)
        self.history_loaded.connect(self._on_history_loaded)

        self.goals_update_received.connect(self.update_goals_list)
        self.hall_of_fame_update_received.connect(self.hall_of_fame_widget.populate_users)
        self.legacy_update_received.connect(self.legacy_tab.update_display)
        self.translation_manager.translation_finished.connect(self.update_message_with_translation)

        self.quiz_start_command_received.connect(self.start_quiz_from_command)
        self.quiz_stop_command_received.connect(self.stop_quiz_from_command)
        self.main_ranking_update_signal.connect(self.schedule_goals_refresh) # <<< 2. SINAL CONECTADO AQUI

        self.auth_manager.attempt_autologin()
        self.ensure_game_rules_file()
        
        self._load_persistent_quiz_ranking()

    def setup_ui(self):
        self.resize(800, 600); self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        main_layout = QHBoxLayout(self); left_panel = QWidget(); left_layout = QVBoxLayout(left_panel); left_panel.setFixedWidth(220)
        
        font = QFont(); font.setPointSize(10)
        self.login_button = QPushButton(); self.login_button.setFont(font); self.login_button.clicked.connect(self.auth_manager.show_login_dialog)
        self.forgot_button = QPushButton(); self.forgot_button.setFont(font); self.forgot_button.clicked.connect(self.auth_manager.show_forgot_password_dialog)
        self.change_pass_button = QPushButton(); self.change_pass_button.setFont(font); self.change_pass_button.clicked.connect(self.auth_manager.show_change_password_dialog); self.change_pass_button.hide()
        
        self.flag_combo = QComboBox(); self.flag_combo.setFont(font); self.flag_combo.hide()
        self.flag_combo.setMaxVisibleItems(10)
        
        self.populate_flag_combobox()
        self.flag_combo.currentIndexChanged.connect(self.on_flag_selected)

        self.change_color_button = QPushButton(); self.change_color_button.setFont(font); self.change_color_button.clicked.connect(self.show_color_dialog); self.change_color_button.hide()
        self.logout_button = QPushButton(); self.logout_button.setFont(font); self.logout_button.clicked.connect(self.logout); self.logout_button.hide()
        
        self.quiz_button = QPushButton(); self.quiz_button.setFont(font); self.quiz_button.clicked.connect(self.toggle_quiz)
        self.quiz_button.setAutoDefault(False)
        self.quiz_button.hide()

        self.admin_buttons_widget = QWidget()
        admin_layout = QVBoxLayout(self.admin_buttons_widget)
        admin_layout.setContentsMargins(0,0,0,0)
        self.moderation_button = QPushButton(); self.moderation_button.setFont(font); self.moderation_button.clicked.connect(self.show_moderation_dialog)
        admin_layout.addWidget(self.moderation_button)
        self.admin_buttons_widget.hide()

        self.users_label = QLabel(); self.users_label.setFont(font)
        self.user_list = QListWidget()
        self.user_list.itemDoubleClicked.connect(self.chat_manager.on_user_double_clicked)
        self.user_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.user_list.customContextMenuRequested.connect(self.show_user_context_menu)
        
        left_layout.addWidget(self.login_button); left_layout.addWidget(self.forgot_button); left_layout.addWidget(self.change_pass_button)
        left_layout.addWidget(self.flag_combo)
        left_layout.addWidget(self.change_color_button); left_layout.addWidget(self.logout_button)
        left_layout.addWidget(self.quiz_button)
        left_layout.addWidget(self.admin_buttons_widget)
        left_layout.addWidget(self.users_label); left_layout.addWidget(self.user_list)
        
        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel)
        
        top_right_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.setToolTip("Atualizar Chat e Ranking (forçado)")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.force_full_refresh)
        self.refresh_button.hide()
        top_right_layout.addWidget(self.refresh_button)
        
        self.lang_button = QPushButton("EN/PT"); self.lang_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lang_button.clicked.connect(self.lang_manager.toggle_language)
        top_right_layout.addWidget(self.lang_button)
        
        top_right_layout.addStretch()

        zoom_layout = QHBoxLayout()
        zoom_out_button = QPushButton(" - ")
        zoom_out_button.setCursor(Qt.CursorShape.PointingHandCursor)
        zoom_out_button.setFixedWidth(30)
        zoom_out_button.clicked.connect(self.zoom_manager.zoom_out)
        
        zoom_in_button = QPushButton(" + ")
        zoom_in_button.setCursor(Qt.CursorShape.PointingHandCursor)
        zoom_in_button.setFixedWidth(30)
        zoom_in_button.clicked.connect(self.zoom_manager.zoom_in)
        
        zoom_layout.addWidget(zoom_out_button)
        zoom_layout.addWidget(zoom_in_button)
        top_right_layout.addLayout(zoom_layout)
        
        self.ranking_button = QPushButton("AnkiAppx")
        self.ranking_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ranking_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff; color: white; border: none;
                padding: 5px 15px; border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #0056b3; }
        """)
        self.ranking_button.clicked.connect(self.open_ranking_page)
        top_right_layout.addWidget(self.ranking_button)
        
        self.tabs = QTabWidget(); self.tabs.setFont(font)
        self.tabs.tabCloseRequested.connect(self.chat_manager.close_pvt_tab)
        
        goals_tab_widget = QWidget(); goals_layout = QVBoxLayout(goals_tab_widget)
        
        search_layout = QHBoxLayout()
        self.search_label = QLabel(self._("search_user"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Digite o nick para filtrar...")
        self.search_input.textChanged.connect(self.on_search_text_changed)
        search_layout.addWidget(self.search_label)
        search_layout.addWidget(self.search_input)
        goals_layout.addLayout(search_layout)

        self.goals_area = QTextBrowser(); self.goals_area.setReadOnly(True)
        self.goals_area.setOpenExternalLinks(True)
        bottom_goals_layout = QHBoxLayout()
        self.edit_goal_button = QPushButton(); self.edit_goal_button.setFont(font)
        self.edit_goal_button.clicked.connect(lambda: self.goals_manager.edit_my_goal())
        self.about_game_button = QPushButton(); self.about_game_button.setFont(font); self.about_game_button.clicked.connect(self.show_about_game)
        bottom_goals_layout.addWidget(self.edit_goal_button); bottom_goals_layout.addWidget(self.about_game_button)
        goals_layout.addWidget(self.goals_area); goals_layout.addLayout(bottom_goals_layout)
        
        self.main_chat_area = QListWidget()
        self.main_chat_area.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.main_chat_area.setFrameShape(QFrame.Shape.NoFrame)
        self.main_chat_area.setWordWrap(True)
        self.main_chat_area.itemSelectionChanged.connect(self.chat_manager.on_message_selection_changed)
        
        quiz_tab_widget = QWidget()
        quiz_tab_widget.setObjectName("quiz_tab_widget")
        quiz_layout = QHBoxLayout(quiz_tab_widget)
        self.quiz_chat_area = QTextBrowser()
        self.quiz_chat_area.setReadOnly(True)
        
        self.quiz_chat_area.setStyleSheet("background-color: #FFFFE0; color: black;")
        self.quiz_chat_area.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.quiz_ranking_area = QTextBrowser()
        self.quiz_ranking_area.setReadOnly(True)
        self.quiz_ranking_area.setFixedWidth(200)
        quiz_layout.addWidget(self.quiz_chat_area, 3)
        quiz_layout.addWidget(self.quiz_ranking_area, 1)
        
        self.hall_of_fame_widget = HallOfFameTab(self)
        self.legacy_tab = LegacyTab(self)
        
        self.tabs.addTab(goals_tab_widget, "")
        self.tabs.addTab(self.main_chat_area, "")
        self.tabs.addTab(quiz_tab_widget, "")
        self.tabs.addTab(self.hall_of_fame_widget, "")
        self.tabs.addTab(self.legacy_tab, "")
        
        self.timer_label = QLineEdit("Tempo restante: --")
        self.timer_label.setReadOnly(True)
        self.timer_label.setStyleSheet("background-color: #f0f0f0; border: none;")
        
        self.input_widget = QWidget(); input_layout = QHBoxLayout(self.input_widget); input_layout.setContentsMargins(0,0,0,0)
        self.message_input = QLineEdit(); self.message_input.setEnabled(False)
        self.send_button = QPushButton(); self.send_button.setFont(font); self.send_button.setEnabled(False)
        self.send_button.setDefault(True)
        
        self.translate_button = QPushButton()
        self.translate_button.setFont(font)
        self.translate_button.setEnabled(False)
        self.translate_button.clicked.connect(self.on_translate_button_clicked)

        self.delete_msg_button = QPushButton()
        self.delete_msg_button.setFont(font)
        self.delete_msg_button.setEnabled(False)
        self.delete_msg_button.clicked.connect(self.chat_manager.on_delete_button_clicked)

        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        input_layout.addWidget(self.translate_button)
        input_layout.addWidget(self.delete_msg_button)

        right_layout.addLayout(top_right_layout)
        right_layout.addWidget(self.tabs)
        right_layout.addWidget(self.timer_label)
        right_layout.addWidget(self.input_widget)
        main_layout.addWidget(left_panel); main_layout.addWidget(right_panel)
        
        self.tabs.currentChanged.connect(self.on_tab_switched)
        self.send_button.clicked.connect(self.chat_manager.send_message)
        self.message_input.returnPressed.connect(self.chat_manager.send_message)
        
        self.lang_manager.update_ui_language()
        self.on_tab_switched(0)
        self.zoom_manager.apply_zoom()

    def on_connection_success(self, email, uid, id_token, password, refresh_token, expires_in):
        self.email = email
        self.uid = uid
        self.id_token = id_token
        self.nickname = email.split('@')[0]
        self.is_connected = True
        self.refresh_token = refresh_token
        self.token_expires_at = datetime.now() + timedelta(seconds=int(expires_in))
        
        background_updater.update_state(True, self.nickname, self.id_token, self.uid)
        
        history = self.auth_manager.load_login_history()
        history[email] = self.auth_manager._obfuscate(password)
        self.auth_manager.save_login_history(history)

        banned_users = self.firebase.get_data("banned_users", self.id_token) or {}
        if self.nickname in banned_users:
            self.connection_failed.emit("Falha no login: Este usuário está banido.")
            self.logout()
            return
            
        self.auth_manager.save_autologin_info()
        self.setWindowTitle(f"AnkiChat - {self.nickname}")
        self.message_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.message_input.setPlaceholderText("Digite sua mensagem aqui...")
        self.login_button.hide()
        self.forgot_button.hide()
        self.change_pass_button.show()
        self.flag_combo.show()
        self.change_color_button.show()
        self.logout_button.show()
        self.quiz_button.show()
        self.refresh_button.show()
        if self.email == self.admin_email:
            self.admin_buttons_widget.show()
            threading.Thread(target=self.goals_manager.check_and_process_season_end, daemon=True).start()
        
        threading.Thread(target=self._ensure_user_data_exists, daemon=True).start()
        self.force_full_refresh()
        
        threading.Thread(target=self.poll_for_updates, daemon=True).start()
        
        self.auth_manager.start_token_refresh_timer()
        
        self._load_persistent_quiz_ranking()

    def on_connection_failure(self, error_message):
        tooltip(error_message)
        self.login_button.setEnabled(True)
        self.login_button.setText(self._("login_register"))

    def handle_connection_lost(self):
        tooltip("Sua sessão expirou ou a conexão foi perdida. Por favor, faça login novamente.")
        self.logout()

    def logout(self):
        if self.auth_manager.token_refresh_timer:
            self.auth_manager.token_refresh_timer.cancel()
            self.auth_manager.token_refresh_timer = None
        
        if self.quiz_manager.is_active:
            self.toggle_quiz()

        self.is_connected = False
        if self.nickname != "Convidado":
            self.firebase.delete_data(f"online/{self.uid}", self.id_token)
        
        time.sleep(0.1)
        self.nickname = "Convidado"
        self.email = None
        self.id_token = None
        self.uid = None
        self.refresh_token = None
        self.token_expires_at = None
        
        background_updater.clear_state()
        self.auth_manager.clear_autologin_info()
        self.setWindowTitle("AnkiChat - Firebase")
        self.login_button.show()
        self.forgot_button.show()
        self.change_pass_button.hide()
        self.flag_combo.hide()
        self.change_color_button.hide()
        self.logout_button.hide()
        self.quiz_button.hide()
        self.admin_buttons_widget.hide()
        self.delete_msg_button.hide()
        self.translate_button.hide()
        self.refresh_button.hide()
        self.message_input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.message_input.setPlaceholderText("Faça login para enviar mensagens...")
        self.user_list.clear()
        self.main_chat_area.clear()
        self.quiz_chat_area.clear()
        self.chat_manager.clear_state()
        self.current_flag_filename = None
        self.cached_goals_data = None
        self.search_input.clear()
        
        for i in range(self.tabs.count() - 1, 4, -1):
            self.tabs.removeTab(i)
        self.tabs.setTabsClosable(False)
        
        self.login_button.setText(self._("login_register"))
        self.login_button.setEnabled(True)

    def open_ranking_page(self):
        webbrowser.open("https://ankichatapp.web.app")

    def populate_flag_combobox(self):
        self.flag_combo.blockSignals(True)
        current_data = self.flag_combo.currentData()
        self.flag_combo.clear()
        self.flag_combo.addItem(self._("choose_flag"))
        self.flag_combo.setItemData(0, "", Qt.ItemDataRole.UserRole)
        
        try:
            flag_files = sorted([f for f in os.listdir(self.flags_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))])
            for filename in flag_files:
                country_name = os.path.splitext(filename)[0].replace("_", " ").title()
                icon_path = os.path.join(self.flags_path, filename)
                self.flag_combo.addItem(QIcon(icon_path), country_name)
                self.flag_combo.setItemData(self.flag_combo.count() - 1, filename, Qt.ItemDataRole.UserRole)
        except FileNotFoundError:
            pass
        
        index = self.flag_combo.findData(current_data)
        if index != -1:
            self.flag_combo.setCurrentIndex(index)

        self.flag_combo.blockSignals(False)

    def on_flag_selected(self, index):
        if not self.is_connected or index < 0:
            return
        flag_filename = self.flag_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if flag_filename != self.current_flag_filename:
            threading.Thread(target=self._async_save_flag, args=(flag_filename,), daemon=True).start()

    def update_my_flag_display(self, my_flag_filename):
        if my_flag_filename == self.current_flag_filename:
            return
        
        self.current_flag_filename = my_flag_filename
        self.flag_combo.blockSignals(True)
        index = self.flag_combo.findData(my_flag_filename)
        if index != -1:
            self.flag_combo.setCurrentIndex(index)
        else:
            self.flag_combo.setCurrentIndex(0)
        self.flag_combo.blockSignals(False)

    def _async_save_flag(self, flag_filename):
        if not self.is_connected: return
        goal_data = self.firebase.get_data(f"goals/{self.uid}", self.id_token) or {}
        goal_data['flag'] = flag_filename
        self.firebase.put_data(f"goals/{self.uid}", goal_data, self.id_token)
        tooltip("Bandeira atualizada!")
        self.current_flag_filename = flag_filename

    def showEvent(self, event):
        super().showEvent(event)
        if not self.is_connected and not hasattr(self, 'centered'): self.center_on_screen(); self.centered = True
        self.tabs.setCurrentIndex(0)

    def center_on_screen(self):
        try:
            screen_geometry = mw.screen().geometry()
            self.move(screen_geometry.center().x() - self.width() / 2, screen_geometry.center().y() - self.height() / 2)
        except: pass

    def _ensure_user_data_exists(self):
        if not self.is_connected: return
        self.firebase.put_data(f"users/{self.uid}", {"nickname": self.nickname}, self.id_token)
        self.firebase.put_data(f"nick_to_uid/{self.nickname}", self.uid, self.id_token)
        
        goal_data = self.firebase.get_data(f"goals/{self.uid}", self.id_token)
        if goal_data is None:
            print(f"AnkiChat: Criando entrada de 'goals' para o usuário {self.nickname}")
            self.firebase.put_data(f"goals/{self.uid}", {"division": "D"}, self.id_token)

    def poll_for_updates(self):
        while self.is_connected:
            try:
                presence_data = {"nickname": self.nickname, "state": "online"}
                self.firebase.put_data(f"online/{self.uid}", presence_data, self.id_token)

                all_messages = self.firebase.get_data("messages", self.id_token)
                if all_messages:
                    self.new_messages_polled.emit(all_messages)

                online_users_data = self.firebase.get_data("online", self.id_token) or {}
                all_users_data = self.firebase.get_data("users", self.id_token) or {}
                goals_data = self.firebase.get_data("goals", self.id_token) or {}
                all_achievements = self.firebase.get_data("achievements", self.id_token) or {}
                my_legacy_data = self.firebase.get_data(f"legacy/{self.uid}", self.id_token) or {}
                
                self.user_update_received.emit({
                    'online_users': online_users_data,
                    'all_users': all_users_data,
                    'goals': goals_data
                })
                self.goals_update_received.emit({'users': all_users_data, 'goals': goals_data})
                self.hall_of_fame_update_received.emit({"users": all_users_data, "achievements": all_achievements})
                self.legacy_update_received.emit(my_legacy_data)

                quiz_command = self.firebase.get_data("league_status/current_quiz", self.id_token)
                self.current_quiz_data = quiz_command

                if quiz_command and not self.quiz_manager.is_active:
                    self.quiz_start_command_received.emit(quiz_command)
                elif not quiz_command and self.quiz_manager.is_active:
                    self.quiz_stop_command_received.emit()

            except Exception as e:
                print(f"AnkiChat: Erro no loop de polling: {e}")
            
            time.sleep(2.0)

    def handle_polled_messages(self, messages):
        if not messages:
            return
            
        sorted_messages = sorted(messages.items(), key=lambda item: item[1].get('timestamp', 0))

        for msg_id, msg_data in sorted_messages:
            local_id = msg_data.get('local_id')

            if local_id and local_id in self.chat_manager.pending_messages:
                item_to_update = self.chat_manager.pending_messages.pop(local_id)
                if item_to_update:
                    item_data = item_to_update.data(Qt.ItemDataRole.UserRole)
                    item_data['msg_id'] = msg_id
                    item_to_update.setData(Qt.ItemDataRole.UserRole, item_data)
                    
                    widget = item_to_update.listWidget()
                    if widget:
                        label = widget.itemWidget(item_to_update)
                        if label:
                            original_html = label.text()
                            clean_html = re.sub(r'^<font color="grey">(.*)</font>$', r'\1', original_html)
                            label.setText(clean_html)
                self.displayed_message_ids.add(msg_id)

            elif msg_id not in self.displayed_message_ids:
                text = msg_data.get('text', '').strip()
                
                is_this_client_host = (
                    self.quiz_manager.is_active and 
                    self.current_quiz_data and 
                    self.uid == self.current_quiz_data.get("host_uid")
                )

                if is_this_client_host and text.isdigit() and not msg_data.get('quiz_event'):
                    self.quiz_manager.handle_answer(msg_data.get('nick'), msg_data.get('uid'), text)
                
                # <<< 3. LÓGICA DE ATUALIZAÇÃO CORRIGIDA >>>
                if msg_data.get("quiz_event") and "acertou!" in text:
                    self.main_ranking_update_signal.emit()

                self.chat_manager.display_message(msg_id, msg_data)
                self.displayed_message_ids.add(msg_id)

    def schedule_goals_refresh(self):
        """Agenda uma atualização dos dados de metas para daqui a 0.5 segundos.
        Isso dá tempo para o Firebase processar a atualização dos pontos antes de buscá-los.
        """
        if not self.is_connected:
            return
        
        def task():
            users_data = self.firebase.get_data("users", self.id_token) or {}
            goals_data = self.firebase.get_data("goals", self.id_token) or {}
            self.goals_update_received.emit({'users': users_data, 'goals': goals_data})

        threading.Timer(0.5, task).start()

    def update_user_list(self, data):
        online_users_data = data.get('online_users', {})
        all_users_data = data.get('all_users', {})
        goals_data = data.get('goals', {})

        online_uids = {uid for uid, udata in online_users_data.items() if udata and udata.get('state') == 'online'}
        
        uid_to_flag = {uid: gdata.get('flag') for uid, gdata in goals_data.items() if gdata.get('flag')}
        
        online_to_display = []
        offline_to_display = []

        for uid, user_data in all_users_data.items():
            nick = user_data.get("nickname")
            if not nick:
                continue
            
            user_info = {'nick': nick, 'uid': uid}
            if uid in online_uids:
                online_to_display.append(user_info)
            else:
                offline_to_display.append(user_info)

        online_to_display.sort(key=lambda x: x['nick'].lower())
        offline_to_display.sort(key=lambda x: x['nick'].lower())

        self.users_label.setText(f"{self._('online_users')} ({len(online_to_display)})")
        
        current_selection = self.user_list.currentItem().text() if self.user_list.currentItem() else None
        self.user_list.clear()

        def create_user_item(user_info, is_online=True):
            item = QListWidgetItem(user_info['nick'])
            
            flag_filename = uid_to_flag.get(user_info['uid'])
            if flag_filename:
                flag_path = os.path.join(self.flags_path, flag_filename)
                if os.path.exists(flag_path):
                    item.setIcon(QIcon(flag_path))

            if not is_online:
                item.setForeground(QColor("grey"))
            elif user_info['nick'] == self.admin_nick:
                item.setForeground(QColor("blue"))
            elif user_info['nick'] == self.nickname:
                item.setForeground(QColor("green"))
            return item

        for user in online_to_display:
            self.user_list.addItem(create_user_item(user, is_online=True))

        if offline_to_display:
            separator = QListWidgetItem("------ Offline ------")
            separator.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = separator.font(); font.setItalic(True); separator.setFont(font)
            separator.setFlags(Qt.ItemFlag.NoItemFlags); separator.setForeground(QColor("grey"))
            self.user_list.addItem(separator)

            for user in offline_to_display:
                self.user_list.addItem(create_user_item(user, is_online=False))

        if current_selection:
            items = self.user_list.findItems(current_selection, Qt.MatchFlag.MatchExactly)
            if items:
                self.user_list.setCurrentItem(items[0])

    def force_full_refresh(self):
        self.displayed_message_ids.clear()
        self.main_chat_area.clear()
        self.quiz_chat_area.clear()
        self.chat_manager.clear_state()
        for i in range(self.tabs.count() - 1, 4, -1):
            self.tabs.removeTab(i)
        tooltip("Atualizando o chat e carregando histórico...")
        threading.Thread(target=self._load_all_history_async, daemon=True).start()
        self._load_persistent_quiz_ranking()

    def _load_all_history_async(self):
        if not self.is_connected: return
        all_messages = self.firebase.get_data("messages", self.id_token) or {}
        sorted_messages = sorted(all_messages.items(), key=lambda item: item[1].get('timestamp', 0))
        self.history_loaded.emit(sorted_messages)

    def _on_history_loaded(self, messages):
        for msg_id, msg_data in messages:
            self.chat_manager.display_message(msg_id, msg_data, is_history=True)
            self.displayed_message_ids.add(msg_id)
        tooltip("Histórico carregado.")

    def toggle_quiz(self):
        if not self.is_connected: return

        if not self.quiz_manager.is_active:
            categories = ["Geral", "Matemática", "Português"]
            category_name, ok = QInputDialog.getItem(self, "Escolha um Quiz", "Selecione a categoria:", categories, 0, False)
            if ok and category_name:
                self.config["last_quiz_category"] = category_name
                mw.addonManager.writeConfig(__name__, self.config)
                self.last_selected_quiz_category = category_name
                
                quiz_command = { "category": category_name, "host_uid": self.uid, "host_nick": self.nickname }
                self.firebase.put_data("league_status/current_quiz", quiz_command, self.id_token)
        else:
            if self.current_quiz_data:
                is_host = self.current_quiz_data.get("host_uid") == self.uid
                is_admin = self.email == self.admin_email
                if is_host or is_admin:
                    self.quiz_manager._post_system_message(f"<hr><b>--- O Quiz foi parado por {self.nickname}. ---</b>")
                    self.firebase.delete_data("league_status/current_quiz", self.id_token)
                else:
                    host_nick = self.current_quiz_data.get("host_nick", "o anfitrião")
                    tooltip(f"Apenas {host_nick} ou um administrador pode parar o quiz.")
            else:
                tooltip("Aguarde... Sincronizando dados do quiz para parar.")

    def start_quiz_from_command(self, command_data):
        category_name = command_data.get("category")
        host_uid = command_data.get("host_uid")
        starter_nick = command_data.get("host_nick")

        if not category_name:
            print(f"Comando de quiz inválido recebido: sem categoria")
            if host_uid == self.uid: self.firebase.delete_data("league_status/current_quiz", self.id_token)
            return
        
        self.quiz_chat_area.clear()
        self.current_quiz_category = category_name
        self._fetch_quiz_ranking_data_async()
        
        if host_uid == self.uid:
            threading.Thread(target=self.quiz_manager.start_quiz, args=(category_name, starter_nick), daemon=True).start()
        else:
            self.quiz_manager.is_active = True
            print(f"AnkiChat: Entrando no quiz como espectador. Host: {starter_nick}")

        self.quiz_button.setText(self._("stop_quiz"))

    def stop_quiz_from_command(self):
        threading.Thread(target=self.quiz_manager.stop_quiz, daemon=True).start()
        self.quiz_button.setText(self._("start_quiz"))
        self.current_quiz_category = None
        self.current_quiz_data = None

    def _render_quiz_ranking_gui(self, scores_data, users_data):
        self.cached_quiz_scores = scores_data
        self.cached_quiz_users.update(users_data)
        
        category_to_display = self.current_quiz_category or self.last_selected_quiz_category
        if not category_to_display: return

        self.quiz_ranking_area.clear()
        self.quiz_ranking_area.append(f"<b>🏆 Ranking: {category_to_display} 🏆</b><hr>")

        if not self.cached_quiz_scores:
            self.quiz_ranking_area.append("<i>Ninguém pontuou ainda.</i>")
            return
        
        uid_to_nick = {uid: u_data.get("nickname", "Desconhecido") for uid, u_data in self.cached_quiz_users.items()}
        player_scores = []
        for uid, score_data in self.cached_quiz_scores.items():
            nickname = uid_to_nick.get(uid, score_data.get("nickname", f"User-{uid[:4]}"))
            score = score_data.get("score", 0)
            player_scores.append((nickname, score))

        sorted_scores = sorted(player_scores, key=lambda item: item[1], reverse=True)
        
        for i, (nick, score) in enumerate(sorted_scores):
            self.quiz_ranking_area.append(f"<b>{i+1}º</b> - {nick}: {score} pts")

    def _optimistically_update_ranking(self, winner_nickname):
        if not self.cached_quiz_users or not self.is_connected:
            self._fetch_quiz_ranking_data_async()
            return

        winner_uid = None
        for uid, user_data in self.cached_quiz_users.items():
            if user_data.get("nickname") == winner_nickname:
                winner_uid = uid
                break
        
        if not winner_uid:
            self._fetch_quiz_ranking_data_async()
            return

        if winner_uid in self.cached_quiz_scores:
            self.cached_quiz_scores[winner_uid]["score"] += 1
        else:
            self.cached_quiz_scores[winner_uid] = {"score": 1, "nickname": winner_nickname}

        self._render_quiz_ranking_gui(self.cached_quiz_scores, self.cached_quiz_users)

    def update_timer_display(self, text):
        self.timer_label.setText(text)
        bg_color = "#333" if mw.pm.night_mode else "#f0f0f0"
        text_color = "black" if mw.pm.night_mode else "black"
        
        if "restante" in text and "0s" not in text and "Acertou" not in text:
            self.timer_label.setStyleSheet(f"background-color: {bg_color}; border: none; color: white; font-weight: bold;")
        else:
            self.timer_label.setStyleSheet(f"background-color: {bg_color}; border: none; color: {text_color};")

    def on_search_text_changed(self, text):
        if self.cached_goals_data: self.goals_manager.render_goals_list(self.cached_goals_data, text)
    def update_goals_list(self, data):
        self.cached_goals_data = data; self.goals_manager.render_goals_list(data, self.search_input.text())
    def show_user_context_menu(self, pos):
        item = self.user_list.itemAt(pos)
        if not item or "Offline" in item.text() or "------" in item.text(): return
        target_nick = item.text(); menu = QMenu()
        if target_nick == self.nickname:
            menu.addAction("Apagar minha última mensagem").triggered.connect(self.delete_my_last_message)
        elif self.email == self.admin_email:
            menu.addAction("Kickar Usuário").triggered.connect(lambda: self.kick_user(target_nick))
            menu.addAction("Banir Usuário").triggered.connect(lambda: self.ban_user(target_nick))
            menu.addSeparator()
            menu.addAction("Apagar Última Mensagem").triggered.connect(lambda: self.delete_last_message(target_nick))
            menu.addAction("Apagar TODAS as Mensagens").triggered.connect(lambda: self.delete_all_messages(target_nick))
        menu.exec(self.user_list.mapToGlobal(pos))
    def show_moderation_dialog(self):
        dialog = ModerationDialog(self.firebase, self); dialog.exec()
    def kick_user(self, nickname):
        uid_to_kick = self.firebase.get_data(f"nick_to_uid/{nickname}", self.id_token)
        if uid_to_kick:
            threading.Thread(target=self._async_kick_user, args=(uid_to_kick,), daemon=True).start()
            tooltip(f"Usuário {nickname} kickado.")
        else: tooltip(f"Não foi possível encontrar o usuário {nickname}.")
    def _async_kick_user(self, uid): self.firebase.delete_data(f"online/{uid}", self.id_token)
    def ban_user(self, nickname): threading.Thread(target=self._async_ban_user, args=(nickname,), daemon=True).start()
    def _async_ban_user(self, nickname):
        uid_to_kick = self.firebase.get_data(f"nick_to_uid/{nickname}", self.id_token)
        if uid_to_kick: self.firebase.delete_data(f"online/{uid_to_kick}", self.id_token)
        self.firebase.put_data(f"banned_users/{nickname}", True, self.id_token)
    def delete_last_message(self, nickname): threading.Thread(target=self._async_delete_message, args=(nickname, False), daemon=True).start()
    def delete_all_messages(self, nickname): threading.Thread(target=self._async_delete_message, args=(nickname, True), daemon=True).start()
    def delete_my_last_message(self): threading.Thread(target=self._async_delete_message, args=(self.nickname, False), daemon=True).start()
    def _async_delete_message(self, nickname, delete_all):
        all_messages = self.firebase.get_data("messages", self.id_token)
        if not all_messages: return
        user_messages = [(msg_id, data) for msg_id, data in all_messages.items() if data.get("nick") == nickname]
        if not user_messages: tooltip(f"Nenhuma mensagem encontrada para {nickname}."); return
        if delete_all: ids_to_delete = [msg_id for msg_id, data in user_messages]
        else: user_messages.sort(key=lambda item: item[1].get("timestamp", 0), reverse=True); ids_to_delete = [user_messages[0][0]]
        for msg_id in ids_to_delete: self.firebase.delete_data(f"messages/{msg_id}", self.id_token)
        self.force_refresh_signal.emit()
    def on_translate_button_clicked(self):
        current_widget = self.tabs.currentWidget()
        if not isinstance(current_widget, QListWidget): return
        selected_items = current_widget.selectedItems()
        if not selected_items: return
        item = selected_items[0]; label = current_widget.itemWidget(item)
        if not label: return
        original_html = label.text()
        if 'id="translation_span"' in original_html: tooltip("Esta mensagem já foi traduzida."); return
        text_part = original_html.split('</b>', 1)[-1].strip()
        if not text_part: tooltip("Não foi possível extrair o texto para tradução."); return
        ui_lang = self.lang_manager.lang; tooltip("Traduzindo mensagem...")
        self.translation_manager.translate_text_async(current_widget, item, text_part, ui_lang)
    def update_message_with_translation(self, list_widget, item, translated_text):
        if not list_widget or not item or not list_widget.itemWidget(item): return
        label = list_widget.itemWidget(item); original_html = label.text()
        if 'id="translation_span"' in original_html: return
        translation_html = (f'<br><span id="translation_span" style="background-color: #FFFF00; color: #000000; padding: 1px 3px; border-radius: 3px;">'
                            f'<i>Trad.: {translated_text}</i></span>')
        new_html = original_html + translation_html
        label.setText(new_html); item.setSizeHint(label.sizeHint())
    def show_color_dialog(self):
        color = QColorDialog.getColor(QColor(self.message_color), self)
        if color.isValid():
            self.message_color = color.name(); self.message_input.setStyleSheet(f"color: {self.message_color};")
            tooltip(f"Cor do texto atualizada para {self.message_color}")
    def on_tab_switched(self, index):
        if index in self.chat_manager.unread_tabs:
            self.chat_manager.unread_tabs.discard(index); self.update_tab_colors()
        current_widget = self.tabs.widget(index)
        is_chat_tab = current_widget in [self.main_chat_area, self.tabs.findChild(QWidget, "quiz_tab_widget")] or current_widget in self.chat_manager.private_chats.values()
        self.input_widget.setVisible(is_chat_tab)
        self.timer_label.setVisible(current_widget == self.tabs.findChild(QWidget, "quiz_tab_widget"))
        is_list_widget_tab = isinstance(current_widget, QListWidget)
        self.translate_button.setVisible(is_list_widget_tab)
        self.delete_msg_button.setVisible(is_list_widget_tab and self.is_connected and self.email == self.admin_email)
        if is_chat_tab: self.chat_manager.on_message_selection_changed()
    def update_tab_colors(self):
        is_night_mode = mw.pm.night_mode
        notification_color = QColor("darkgreen") if not is_night_mode else QColor("lightgreen")
        for i in range(self.tabs.count()):
            self.tabs.tabBar().setTabTextColor(i, notification_color if i in self.chat_manager.unread_tabs else QColor())
    def go_offline(self):
        if self.is_connected: self.firebase.delete_data(f"online/{self.uid}", self.id_token)
    def closeEvent(self, event):
        for i in range(self.tabs.count() - 1, 4, -1): self.chat_manager.close_pvt_tab(i)
        self.hide(); event.ignore()
    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal): self.zoom_manager.zoom_in()
            elif event.key() in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore): self.zoom_manager.zoom_out()
        super().keyPressEvent(event)
    def ensure_game_rules_file(self):
        rules_path = os.path.join(self.addon_path, "jogo.txt")
        if not os.path.exists(rules_path):
            with open(rules_path, "w", encoding="utf-8") as f: f.write("As regras do jogo são definidas no arquivo 'jogo.txt' na pasta do addon.")
    def show_about_game(self):
        rules_path = os.path.join(self.addon_path, "jogo.txt")
        try:
            with open(rules_path, "r", encoding="utf-8") as f: rules = f.read()
            dialog = QDialog(self); dialog.setWindowTitle("Sobre o Jogo"); layout = QVBoxLayout(dialog)
            text_area = QTextBrowser(); text_area.setReadOnly(True); text_area.setText(rules); text_area.setOpenExternalLinks(True)
            layout.addWidget(text_area); dialog.resize(500, 400); dialog.exec()
        except FileNotFoundError:
            tooltip("Arquivo 'jogo.txt' não encontrado. Criando um novo."); self.ensure_game_rules_file(); self.show_about_game()
    
    def _fetch_quiz_ranking_data_async(self):
        category_to_fetch = self.current_quiz_category or self.last_selected_quiz_category
        if not self.is_connected or not category_to_fetch: return
        
        def task():
            scores = self.firebase.get_data(f"quiz_scores/{category_to_fetch}", self.id_token) or {}
            users = self.firebase.get_data("users", self.id_token) or {}
            self.quiz_ranking_data_fetched.emit(scores, users)
        threading.Thread(target=task, daemon=True).start()

    def _load_persistent_quiz_ranking(self):
        if self.is_connected:
            self._fetch_quiz_ranking_data_async()
        else:
            self.quiz_ranking_area.clear()
            self.quiz_ranking_area.append(f"<b>🏆 Ranking: {self.last_selected_quiz_category} 🏆</b><hr>")
            self.quiz_ranking_area.append("<i>Faça login para ver as pontuações.</i>")

window_instance = None
def launch_window():
    global window_instance
    if window_instance is None:
        try: window_instance = ChatWindow(mw)
        except Exception as e: print(f"Falha ao criar a janela do AnkiChat: {e}"); tooltip(f"Erro ao iniciar o AnkiChat: {e}"); return
    window_instance.show(); window_instance.activateWindow()
def on_card_reviewed(reviewer, card, ease):
    if not background_updater.is_connected: return
    threading.Thread(target=_update_stats_after_review, args=(ease, card.ivl == 0), daemon=True).start()
def _update_stats_after_review(ease, is_new):
    if not background_updater.is_connected: return
    uid = background_updater.uid; firebase = background_updater.firebase; id_token = background_updater.id_token
    goal_data = firebase.get_data(f"goals/{uid}", id_token) or {}
    now = datetime.now(); current_week = now.isocalendar()[1]; today_ordinal = now.toordinal()
    goal_data.setdefault("goal_daily", 100); goal_data.setdefault("goal_weekly", 700); goal_data.setdefault("division", "D")
    goal_data.setdefault("retention_points", 0); goal_data.setdefault("meta_points", 0); goal_data.setdefault("reviews_week", 0)
    goal_data.setdefault("reviews_today", 0); goal_data.setdefault("study_time_week", 0); goal_data.setdefault("study_time_today", 0)
    goal_data.setdefault("new_cards_week", 0); goal_data.setdefault("season_week", 0); goal_data.setdefault("last_update_day", 0)
    if today_ordinal != goal_data.get("last_update_day", 0):
        goal_data["reviews_today"] = 0; goal_data["study_time_today"] = 0; goal_data["last_update_day"] = today_ordinal
    if current_week != goal_data.get("season_week", 0):
        for key in ["retention_points", "meta_points", "reviews_week", "study_time_week", "new_cards_week"]: goal_data[key] = 0
        goal_data["season_week"] = current_week
    points_map = {1: -2, 2: 1, 3: 3, 4: 5}
    goal_data["retention_points"] += points_map.get(ease, 0); goal_data["reviews_today"] += 1; goal_data["reviews_week"] += 1
    goal_data["study_time_today"] += 5; goal_data["study_time_week"] += 5
    if is_new: goal_data["new_cards_week"] += 1
    if goal_data["goal_daily"] > 0 and goal_data["reviews_today"] == goal_data["goal_daily"]: goal_data["meta_points"] += 3
    firebase.put_data(f"goals/{uid}", goal_data, id_token)
def clean_up_on_exit():
    if window_instance and window_instance.is_connected: window_instance.go_offline()
    elif background_updater.is_connected:
        background_updater.firebase.delete_data(f"online/{background_updater.uid}", background_updater.id_token)
def initialize_background_service():
    FIREBASE_URL = "https://ankichatapp-default-rtdb.firebaseio.com/"
    API_KEY = "AIzaSyDNSI7R6GX9B5PCGIwvAoKM_5uen7BU_C0"
    firebase_api = FirebaseAPI(FIREBASE_URL, API_KEY)
    background_updater.initialize(firebase_api)
def add_main_menu():
    open_action = QAction("AnkiChat", mw)
    open_action.triggered.connect(launch_window)
    mw.form.menubar.addAction(open_action)
gui_hooks.profile_will_close.append(clean_up_on_exit)
gui_hooks.reviewer_did_answer_card.append(on_card_reviewed)
gui_hooks.main_window_did_init.append(add_main_menu)
gui_hooks.main_window_did_init.append(initialize_background_service)