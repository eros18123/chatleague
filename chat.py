# chat.py

# -- coding: utf-8 --
# chat.py - Módulo para gerenciar o Chat Principal e Privado do AnkiChat (v2.6 - CORREÇÃO FINAL DE ALINHAMENTO)

import re
import time
import random
from datetime import datetime

from aqt.qt import (
    QListWidget, QListWidgetItem, QLabel, Qt, QColor, QMenu, QTextBrowser, QAbstractItemView, QFrame
)
from aqt.utils import tooltip
from aqt import mw

class ChatManager:
    def __init__(self, chat_window):
        self.cw = chat_window
        self.firebase = chat_window.firebase

        self.private_chats = {}
        self.private_chat_history = {}
        self.pending_messages = {}
        self.last_message_dates = {}
        self.unread_pms = set()
        self.unread_tabs = set()

    def clear_state(self):
        self.private_chats.clear()
        self.private_chat_history.clear()
        self.pending_messages.clear()
        self.last_message_dates.clear()
        self.unread_pms.clear()
        self.unread_tabs.clear()

    def _linkify_text(self, text):
        url_pattern = re.compile(r'((?:https?://|www\.)[^\s<]+)')
        def repl(match):
            url = match.group(1)
            href = url if url.startswith('http') else 'http://' + url
            return f'<a href="{href}">{url}</a>'
        return url_pattern.sub(repl, text)

    def display_message(self, msg_id, msg, is_history=False):
        try:
            local_id = msg.get('local_id')
            if local_id and local_id in self.pending_messages and msg_id:
                return

            nick, target = msg.get("nick"), msg.get("target")

            if target:
                is_for_me = (target == self.cw.nickname or nick == self.cw.nickname)
                if not is_for_me: return
                other_user = target if nick == self.cw.nickname else nick
                if other_user not in self.private_chat_history: self.private_chat_history[other_user] = []
                if not any(m[0] == msg_id for m in self.private_chat_history[other_user] if m[0] is not None):
                    self.private_chat_history[other_user].append((msg_id, msg))
                if other_user in self.private_chats:
                    chat_widget = self.private_chats[other_user]
                    self._display_message_in_widget(chat_widget, msg_id, msg)
                    message_tab_index = self.cw.tabs.indexOf(chat_widget)
                    if not is_history and message_tab_index != -1 and self.cw.tabs.currentIndex() != message_tab_index:
                        self.unread_tabs.add(message_tab_index)
                        self.cw.update_tab_colors()
                elif not is_history:
                    self.unread_pms.add(other_user)
                    self.cw.user_update_received.emit({'online_users': {}, 'all_users': {}})
                return

            # --- INÍCIO DA CORREÇÃO ---
            text = msg.get("text", "").strip()
            # Considera uma mensagem de quiz se for um evento, chat de quiz, ou uma tentativa de resposta numérica enquanto o quiz está ativo.
            is_answer_attempt = self.cw.quiz_manager.is_active and text.isdigit() and not msg.get("quiz_event")
            is_quiz_msg = msg.get("quiz_event") or msg.get("quiz_chat") or is_answer_attempt
            
            if is_quiz_msg:
                chat_widget = self.cw.quiz_chat_area
                message_tab_index = self.cw.tabs.indexOf(self.cw.tabs.findChild(object, "quiz_tab_widget"))
            else:
                chat_widget = self.cw.main_chat_area
                message_tab_index = 1
            # --- FIM DA CORREÇÃO ---

            self._display_message_in_widget(chat_widget, msg_id, msg)

            if not is_history and message_tab_index != -1 and self.cw.tabs.currentIndex() != message_tab_index:
                self.unread_tabs.add(message_tab_index)
                self.cw.update_tab_colors()

        except Exception as e:
            print(f"Erro ao exibir mensagem: {e}")



# Em chat.py, substitua a função send_message por esta:

    def send_message(self):
        text = self.cw.message_input.text().strip()
        if not text or not self.cw.is_connected:
            return
        
        current_widget = self.cw.tabs.currentWidget()
        is_quiz_tab = (current_widget == self.cw.tabs.findChild(object, "quiz_tab_widget"))
        
        # --- INÍCIO DA CORREÇÃO ---
        # Lógica simplificada para envio de mensagens do quiz
        if is_quiz_tab and self.cw.quiz_manager.is_active:
            # Se o quiz está ativo, qualquer texto digitado é enviado para o Firebase.
            # O host (seja o addon ou a web) irá processar a mensagem.
            # Se for um número, será uma resposta. Se não, será um chat.
            message_data = {
                "uid": self.cw.uid,
                "nick": self.cw.nickname,
                "text": text,
                "timestamp": {".sv": "timestamp"},
                "color": self.cw.message_color
            }
            # Adiciona a flag 'quiz_chat' se não for um número, para ajudar na exibição
            if not text.isdigit():
                message_data["quiz_chat"] = True

            self.firebase.post_data("messages", message_data, self.cw.id_token)
            self.cw.message_input.clear()
            self.cw.message_input.setFocus()
            return # Finaliza a função aqui
        # --- FIM DA CORREÇÃO ---

        # Lógica para chat privado e principal (continua a mesma)
        target_nick = None
        current_tab_index = self.cw.tabs.currentIndex()
        tab_title = self.cw.tabs.tabText(current_tab_index)
        
        non_pvt_widgets = [ self.cw.main_chat_area, self.cw.tabs.findChild(object, "quiz_tab_widget"), self.cw.hall_of_fame_widget, self.cw.legacy_tab, self.cw.tabs.widget(0) ]
        is_pvt = self.cw.tabs.widget(current_tab_index) not in non_pvt_widgets and tab_title.startswith("PVT: ")
        
        if is_pvt:
            target_nick = tab_title.replace("PVT: ", "")
        
        local_id = f"local_{time.time()}_{random.random()}"
        
        message_data = {
            "uid": self.cw.uid, "nick": self.cw.nickname, "text": text, 
            "timestamp": {".sv": "timestamp"},
            "color": self.cw.message_color, "local_id": local_id
        }
        if target_nick:
            message_data["target"] = target_nick
        
        self.display_message(None, message_data)
        
        self.firebase.post_data("messages", message_data, self.cw.id_token)
        self.cw.message_input.clear()
        self.cw.message_input.setFocus()




    def _display_message_in_widget(self, chat_widget, msg_id, msg):
        nick, text, target, timestamp = msg.get("nick"), msg.get("text"), msg.get("target"), msg.get("timestamp")
        
        if isinstance(chat_widget, QTextBrowser): chat_id = "quiz"
        elif target: chat_id = target if nick == self.cw.nickname else nick
        else: chat_id = "main"
        if timestamp:
            current_date = datetime.fromtimestamp(timestamp / 1000).date()
            last_date = self.last_message_dates.get(chat_id)
            if last_date is None or current_date > last_date:
                date_str = current_date.strftime("--- %A, %d de %B de %Y ---").title()
                if isinstance(chat_widget, QTextBrowser):
                    chat_widget.append(f'<div style="text-align: center; color: grey; font-style: italic; font-size: {self.cw.base_font_sizes["chat"] - 2 + self.cw.zoom_manager.ctrl_zoom_level}pt;">{date_str}</div>')
                    chat_widget.setAlignment(Qt.AlignmentFlag.AlignLeft)
                else:
                    separator_item = QListWidgetItem(chat_widget)
                    separator_label = QLabel(date_str)
                    separator_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    font = separator_label.font()
                    font.setPointSize(self.cw.base_font_sizes["chat"] - 2 + self.cw.zoom_manager.ctrl_zoom_level)
                    font.setItalic(True)
                    separator_label.setFont(font)
                    separator_label.setStyleSheet("color: grey;")
                    separator_item.setSizeHint(separator_label.sizeHint())
                    chat_widget.addItem(separator_item)
                    chat_widget.setItemWidget(separator_item, separator_label)
                self.last_message_dates[chat_id] = current_date
        
        is_quiz_bot_msg = (nick == "QuizBot" and msg.get("quiz_event"))
        
        if is_quiz_bot_msg:
            formatted_html = text
        else:
            text = self._linkify_text(text)
            nick_color = "blue"
            if nick == self.cw.admin_nick: nick_color = "#0000FF"
            flag_html = ""
            flag_filename = self.cw.user_flags_cache.get(nick)
            if flag_filename:
                flag_path = f"{self.cw.flags_path}/{flag_filename}"
                flag_html = f'<img src="{flag_path}" width="16" height="11"> '
            display_nick = f'{flag_html}<font color="{nick_color}">{nick}</font>'
            if target: display_nick = "Você" if nick == self.cw.nickname else display_nick
            color = msg.get("color")
            if color: formatted_html = f'<b>{display_nick}:</b> <font color="{color}">{text}</font>'
            else: formatted_html = f'<b>{display_nick}:</b> {text}'
        
        if isinstance(chat_widget, QTextBrowser):
            chat_widget.append(formatted_html)
        else:
            item = QListWidgetItem(chat_widget)
            local_id = msg.get('local_id')
            item.setData(Qt.ItemDataRole.UserRole, {'msg_id': msg_id, 'local_id': local_id})
            
            if local_id and not msg_id:
                self.pending_messages[local_id] = item
                formatted_html = f'<font color="grey">{formatted_html}</font>'

            label = QLabel(formatted_html)
            font = label.font()
            font.setPointSize(self.cw.base_font_sizes["chat"] + self.cw.zoom_manager.ctrl_zoom_level)
            label.setFont(font)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            label.setOpenExternalLinks(True)
            item.setSizeHint(label.sizeHint())
            chat_widget.addItem(item)
            chat_widget.setItemWidget(item, label)
            chat_widget.scrollToBottom()

    def get_or_create_pvt_tab(self, nick):
        if nick in self.private_chats:
            tab_widget = self.private_chats[nick]
            index = self.cw.tabs.indexOf(tab_widget)
            if index == -1: index = self.cw.tabs.addTab(tab_widget, f"PVT: {nick}")
            self.cw.tabs.setCurrentIndex(index)
            return tab_widget
        pvt_chat_box = QListWidget()
        pvt_chat_box.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        pvt_chat_box.setFrameShape(QFrame.Shape.NoFrame)
        pvt_chat_box.setWordWrap(True)
        pvt_chat_box.itemSelectionChanged.connect(self.on_message_selection_changed)
        if nick in self.private_chat_history:
            for msg_id, msg_data in self.private_chat_history[nick]:
                self._display_message_in_widget(pvt_chat_box, msg_id, msg_data)
        self.private_chats[nick] = pvt_chat_box
        self.cw.tabs.setTabsClosable(True)
        index = self.cw.tabs.addTab(pvt_chat_box, f"PVT: {nick}")
        self.cw.tabs.setCurrentIndex(index)
        return pvt_chat_box
    def close_pvt_tab(self, index):
        if index < 5: return
        self.cw.tabs.removeTab(index)
    def on_user_double_clicked(self, item: QListWidgetItem):
        nick = item.text()
        if nick == "QuizBot" or "Offline" in nick: return
        self.get_or_create_pvt_tab(nick)
        if nick in self.unread_pms:
            self.unread_pms.remove(nick)
            font = item.font(); font.setBold(False); item.setFont(font)
    def on_message_selection_changed(self):
        is_admin = self.cw.email == self.cw.admin_email
        current_widget = self.cw.tabs.currentWidget()
        if isinstance(current_widget, QListWidget):
            has_selection = bool(current_widget.selectedItems())
            self.cw.delete_msg_button.setEnabled(is_admin and has_selection)
            self.cw.translate_button.setEnabled(has_selection)
        else:
            self.cw.delete_msg_button.setEnabled(False)
            self.cw.translate_button.setEnabled(False)
    def on_delete_button_clicked(self):
        current_widget = self.cw.tabs.currentWidget()
        if not isinstance(current_widget, QListWidget): return
        selected_items = current_widget.selectedItems()
        if not selected_items: return
        item = selected_items[0]
        data = item.data(Qt.ItemDataRole.UserRole)
        msg_id = data.get('msg_id')
        if msg_id:
            current_widget.takeItem(current_widget.row(item))
            self.firebase.delete_data(f"messages/{msg_id}", self.cw.id_token)
            tooltip("Mensagem apagada.")
        else:
            tooltip("Não é possível apagar a mensagem antes de ser confirmada pelo servidor.")