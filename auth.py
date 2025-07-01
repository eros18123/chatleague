# -- coding: utf-8 --
# auth.py - Módulo para gerenciar a autenticação e sessão do AnkiChat

import os
import json
import base64
import threading
import requests
from datetime import datetime, timedelta

from aqt import mw
from aqt.qt import (
    QDialog, QFormLayout, QComboBox, QLineEdit, QDialogButtonBox,
    QHBoxLayout, QPushButton, QInputDialog
)
from aqt.utils import tooltip

# --- Classe para Interagir com o Firebase ---
class FirebaseAPI:
    def __init__(self, base_url, api_key):
        if not base_url.endswith('/'): base_url += '/'
        self.base_url = base_url; self.api_key = api_key
        self.auth_url_signup = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={self.api_key}"
        self.auth_url_signin = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.api_key}"
        self.auth_url_reset = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={self.api_key}"
        self.auth_url_change = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={self.api_key}"
        self.auth_url_refresh = f"https://securetoken.googleapis.com/v1/token?key={self.api_key}"

    def _send_request(self, url, payload):
        try:
            r = requests.post(url, data=json.dumps(payload)); r.raise_for_status(); return r.json(), None
        except requests.exceptions.RequestException as e:
            try: error_data = e.response.json(); return None, error_data.get("error", {}).get("message", "UNKNOWN_ERROR")
            except: return None, str(e)
        except Exception as e: return None, str(e)
    def signup_user(self, email, password): return self._send_request(self.auth_url_signup, {"email": email, "password": password, "returnSecureToken": True})
    def signin_user(self, email, password): return self._send_request(self.auth_url_signin, {"email": email, "password": password, "returnSecureToken": True})
    def reset_password(self, email): return self._send_request(self.auth_url_reset, {"requestType": "PASSWORD_RESET", "email": email})
    def change_password(self, id_token, new_password): return self._send_request(self.auth_url_change, {"idToken": id_token, "password": new_password, "returnSecureToken": False})
    def refresh_token(self, refresh_token): return self._send_request(self.auth_url_refresh, {"grant_type": "refresh_token", "refresh_token": refresh_token})

    def get_data(self, path="", id_token=None, params=""):
        try:
            url = f"{self.base_url}{path}.json?auth={id_token}{'&' if params else ''}{params.lstrip('?')}"
            r = requests.get(url)
            r.raise_for_status()
            return r.json()
        except:
            return None

    def put_data(self, path, data, id_token=None):
        try:
            url = f"{self.base_url}{path}.json?auth={id_token}"
            requests.put(url, data=json.dumps(data)).raise_for_status()
        except Exception as e:
            print(f"AnkiChat: Erro ao enviar dados (PUT) para {path}. Erro: {e}")

    # <<< MÉTODO ADICIONADO >>>
    def patch_data(self, path, data, id_token=None):
        """Atualiza dados sem sobrescrever o nó inteiro (Usa PATCH)."""
        try:
            url = f"{self.base_url}{path}.json?auth={id_token}"
            requests.patch(url, data=json.dumps(data)).raise_for_status()
        except Exception as e:
            print(f"AnkiChat: Erro ao atualizar dados (PATCH) para {path}. Erro: {e}")

    def post_data(self, path, data, id_token=None):
        try:
            url = f"{self.base_url}{path}.json?auth={id_token}"
            requests.post(url, data=json.dumps(data)).raise_for_status()
        except Exception as e:
            print(f"AnkiChat: Erro ao postar dados para {path}. Erro: {e}")

    def delete_data(self, path, id_token=None):
        try:
            url = f"{self.base_url}{path}.json?auth={id_token}"
            requests.delete(url).raise_for_status()
        except: pass

# --- Serviço de Fundo para Atualizações em Tempo Real ---
class BackgroundUpdater:
    def __init__(self):
        self.is_connected = False
        self.nickname = None
        self.id_token = None
        self.uid = None
        self.firebase = None

    def initialize(self, firebase_api):
        self.firebase = firebase_api

    def update_state(self, is_connected, nickname, id_token, uid):
        self.is_connected = is_connected
        self.nickname = nickname
        self.id_token = id_token
        self.uid = uid

    def clear_state(self):
        self.is_connected = False
        self.nickname = None
        self.id_token = None
        self.uid = None

background_updater = BackgroundUpdater()

# --- Gerenciador de Autenticação ---
class AuthManager:
    def __init__(self, chat_window):
        self.cw = chat_window
        self.firebase = chat_window.firebase
        self.token_refresh_timer = None

    def _obfuscate(self, data: str) -> str:
        return base64.b64encode(data.encode('utf-8')).decode('utf-8')

    def _deobfuscate(self, data: str) -> str:
        try:
            return base64.b64decode(data.encode('utf-8')).decode('utf-8')
        except:
            return ""

    def load_login_history(self):
        if not os.path.exists(self.cw.login_history_file):
            return {}
        try:
            with open(self.cw.login_history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def save_login_history(self, history):
        try:
            with open(self.cw.login_history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=4)
        except IOError:
            tooltip("Não foi possível salvar o histórico de login.")

    def show_login_dialog(self):
        dialog = QDialog(self.cw)
        dialog.setWindowTitle("Login ou Registro")
        layout = QFormLayout(dialog)

        history = self.load_login_history()

        email_combo = QComboBox()
        email_combo.setEditable(True)
        email_combo.addItems(history.keys())
        email_combo.setPlaceholderText("seu.email@exemplo.com")

        pass_entry = QLineEdit()
        pass_entry.setEchoMode(QLineEdit.EchoMode.Password)
        pass_entry.setPlaceholderText("Mínimo 6 caracteres")

        def on_user_selected(email):
            if email in history:
                pass_entry.setText(self._deobfuscate(history[email]))
            else:
                pass_entry.clear()

        email_combo.currentTextChanged.connect(on_user_selected)
        if email_combo.currentText():
            on_user_selected(email_combo.currentText())

        layout.addRow("E-mail:", email_combo)
        layout.addRow("Senha:", pass_entry)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        extra_buttons_layout = QHBoxLayout()
        forget_button = QPushButton("Esquecer Usuário")
        extra_buttons_layout.addWidget(forget_button)
        extra_buttons_layout.addStretch()

        def on_forget_user():
            email_to_forget = email_combo.currentText()
            if email_to_forget in history:
                del history[email_to_forget]
                self.save_login_history(history)
                
                current_index = email_combo.findText(email_to_forget)
                if current_index >= 0:
                    email_combo.removeItem(current_index)
                
                tooltip(f"Usuário '{email_to_forget}' esquecido.")
                pass_entry.clear()

        forget_button.clicked.connect(on_forget_user)

        layout.addRow(extra_buttons_layout)
        layout.addWidget(buttons)

        if dialog.exec():
            email = email_combo.currentText().strip()
            password = pass_entry.text()
            if not email or not password:
                tooltip("E-mail e senha não podem estar em branco.")
                return
            self.cw.login_button.setEnabled(False)
            self.cw.login_button.setText("Verificando...")
            threading.Thread(target=self._login_thread_wrapper, args=(email, password), daemon=True).start()

    def _login_thread_wrapper(self, email, password):
        try:
            self.attempt_login_or_register(email, password)
        except Exception as e:
            self.cw.connection_failed.emit(f"Erro inesperado no login: {e}")

    def attempt_login_or_register(self, email, password):
        nickname_to_check = email.split('@')[0]
        
        if nickname_to_check == self.cw.admin_nick and email != self.cw.admin_email:
            self.cw.connection_failed.emit("Este nickname é reservado para o administrador.")
            return

        banned_users = self.firebase.get_data("banned_users") or {}
        if nickname_to_check in banned_users:
            self.cw.connection_failed.emit("Falha no login: Este usuário está banido.")
            return
        
        response, error = self.firebase.signin_user(email, password)
        if response:
            uid = response.get('localId')
            threading.Thread(target=self.firebase.put_data, args=(f"users/{uid}", {"nickname": nickname_to_check}, response.get('idToken')), daemon=True).start()
            self.cw.connection_succeeded.emit(response.get('email'), uid, response.get('idToken'), password, response.get('refreshToken'), response.get('expiresIn', '3600'))
            return
            
        if error == "EMAIL_NOT_FOUND" or error == "INVALID_LOGIN_CREDENTIALS":
            new_nick_to_check = email.split('@')[0]
            existing_uid = self.firebase.get_data(f"nick_to_uid/{new_nick_to_check}")
            if existing_uid:
                self.cw.connection_failed.emit("Falha no registro: Este nick já está em uso. Tente outro e-mail.")
                return

            signup_response, signup_error = self.firebase.signup_user(email, password)
            if signup_response:
                new_nick = signup_response.get('email').split('@')[0]
                uid = signup_response.get('localId')
                id_token = signup_response.get('idToken')
                def setup_new_user():
                    self.firebase.put_data(f"users/{uid}", {"nickname": new_nick}, id_token)
                    self.firebase.put_data(f"nick_to_uid/{new_nick}", uid, id_token)
                    self.firebase.put_data(f"goals/{uid}", {"division": "D"}, id_token)
                threading.Thread(target=setup_new_user, daemon=True).start()
                tooltip("Usuário registrado com sucesso! Conectando...")
                self.cw.connection_succeeded.emit(signup_response.get('email'), uid, id_token, password, signup_response.get('refreshToken'), signup_response.get('expiresIn', '3600'))
            else:
                if "WEAK_PASSWORD" in signup_error:
                    self.cw.connection_failed.emit("Falha no registro: A senha deve ter pelo menos 6 caracteres.")
                else:
                    self.cw.connection_failed.emit(f"Falha no registro/login: {signup_error}")
        else:
            self.cw.connection_failed.emit(f"Falha no login: {error}")

    def save_autologin_info(self):
        try:
            with open(self.cw.autologin_file, 'w') as f:
                json.dump({'email': self.cw.email, 'uid': self.cw.uid, 'refreshToken': self.cw.refresh_token}, f)
        except Exception as e:
            print(f"Erro ao salvar autologin: {e}")

    def clear_autologin_info(self):
        if os.path.exists(self.cw.autologin_file):
            try:
                os.remove(self.cw.autologin_file)
            except Exception as e:
                print(f"Erro ao limpar autologin: {e}")

    def attempt_autologin(self):
        if os.path.exists(self.cw.autologin_file):
            try:
                with open(self.cw.autologin_file, 'r') as f:
                    data = json.load(f)
                if 'email' in data and 'refreshToken' in data and 'uid' in data:
                    self.cw.login_button.setEnabled(False)
                    self.cw.login_button.setText("Logando...")
                    threading.Thread(target=self._autologin_with_refresh_token,
                                     args=(data['email'], data['uid'], data['refreshToken']),
                                     daemon=True).start()
            except Exception as e:
                print(f"AnkiChat: Autologin falhou na leitura do arquivo: {e}")
                self.clear_autologin_info()

    def _autologin_with_refresh_token(self, email, uid, refresh_token):
        response, error = self.firebase.refresh_token(refresh_token)
        if response:
            history = self.load_login_history()
            password = self._deobfuscate(history.get(email, ""))
            new_id_token = response.get('id_token')
            new_refresh_token = response.get('refresh_token')
            expires_in = response.get('expires_in', '3600')
            self.cw.connection_succeeded.emit(email, uid, new_id_token, password, new_refresh_token, expires_in)
        else:
            print(f"AnkiChat: Autologin com refresh token falhou: {error}. Limpando credenciais.")
            self.clear_autologin_info()
            self.cw.connection_failed.emit("Sua sessão expirou. Faça login novamente.")

    def start_token_refresh_timer(self):
        if self.token_refresh_timer:
            self.token_refresh_timer.cancel()
        refresh_in_seconds = (self.cw.token_expires_at - datetime.now()).total_seconds() - 300
        if refresh_in_seconds < 0:
            refresh_in_seconds = 1
        self.token_refresh_timer = threading.Timer(refresh_in_seconds, self._refresh_token_job)
        self.token_refresh_timer.daemon = True
        self.token_refresh_timer.start()

    def _refresh_token_job(self):
        if not self.cw.is_connected or not self.cw.refresh_token:
            return
        response, error = self.firebase.refresh_token(self.cw.refresh_token)
        if response:
            self.cw.id_token = response.get('id_token')
            self.cw.refresh_token = response.get('refresh_token')
            expires_in = response.get('expires_in', '3600')
            self.cw.token_expires_at = datetime.now() + timedelta(seconds=int(expires_in))
            background_updater.id_token = self.cw.id_token
            self.save_autologin_info()
            self.start_token_refresh_timer()
            print("AnkiChat: Token de autenticação renovado com sucesso.")
        else:
            print(f"AnkiChat: Falha ao renovar o token: {error}. Forçando logout.")
            self.cw.connection_lost_signal.emit()

    def show_forgot_password_dialog(self):
        email, ok = QInputDialog.getText(self.cw, "Recuperar Senha", "Digite seu e-mail de cadastro:")
        if ok and email:
            threading.Thread(target=self.firebase.reset_password, args=(email,)).start()
            tooltip("Se o e-mail estiver cadastrado, um link de recuperação foi enviado.")

    def show_change_password_dialog(self):
        new_pass, ok = QInputDialog.getText(self.cw, "Mudar Senha", "Digite a nova senha (mínimo 6 caracteres):", QLineEdit.EchoMode.Password)
        if ok and new_pass:
            if len(new_pass) < 6:
                tooltip("A senha deve ter pelo menos 6 caracteres.")
                return
            threading.Thread(target=self.firebase.change_password, args=(self.cw.id_token, new_pass)).start()
            tooltip("Senha alterada com sucesso!")