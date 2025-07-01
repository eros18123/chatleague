# -- coding: utf-8 --
# mudaridioma.py - Módulo para gerenciar a troca de idioma do AnkiChat

import locale
from aqt import mw
from aqt.utils import tooltip

class LanguageManager:
    def __init__(self, chat_window):
        self.cw = chat_window  # Referência à janela principal
        self.config = chat_window.config
        self.lang = self.config.get("language", "pt")
        self._setup_translations()
        self.set_locale()

    def _setup_translations(self):
        """Define o dicionário com todas as traduções."""
        self.i18n = {
            "login_register": {"pt": "Login / Registrar", "en": "Login / Register"},
            "forgot_password": {"pt": "Esqueceu a senha?", "en": "Forgot password?"},
            "change_password": {"pt": "Mudar Senha", "en": "Change Password"},
            "change_color": {"pt": "Mudar Cor do Texto", "en": "Change Text Color"},
            "logout": {"pt": "Logout", "en": "Logout"},
            "moderate_users": {"pt": "Moderar Usuários (Admin)", "en": "Moderate Users (Admin)"},
            "online_users": {"pt": "Usuários Online", "en": "Online Users"},
            "goals_ranking": {"pt": "Metas e Ranking", "en": "Goals & Ranking"},
            "chat_main": {"pt": "Chat Principal", "en": "Main Chat"},
            "live_quiz": {"pt": "Quiz ao Vivo", "en": "Live Quiz"},
            "hall_of_fame": {"pt": "Hall da Fama", "en": "Hall of Fame"},
            "my_legacy": {"pt": "Meu Legado", "en": "My Legacy"},
            "set_goals": {"pt": "Definir Metas e Matéria", "en": "Set Goals & Subject"},
            "about_game": {"pt": "Sobre o Jogo", "en": "About the Game"},
            "send": {"pt": "Enviar", "en": "Send"},
            "delete_selected": {"pt": "Apagar Selecionado", "en": "Delete Selected"},
            "translate_selected": {"pt": "Traduzir Selecionado", "en": "Translate Selected"}, # <<< NOVA TRADUÇÃO
            "choose_flag": {"pt": "Escolha uma bandeira...", "en": "Choose a flag..."},
            "season_ends_in": {"pt": "A temporada termina em:", "en": "Season ends in:"},
            "no_user_in_division": {"pt": "Nenhum usuário nesta divisão.", "en": "No users in this division."},
            "today": {"pt": "Hoje", "en": "Today"},
            "week": {"pt": "Semana", "en": "Week"},
            "search_user": {"pt": "Pesquisar usuário:", "en": "Search user:"},
            "start_quiz": {"pt": "Iniciar Quiz", "en": "Start Quiz"},
            "stop_quiz": {"pt": "Parar Quiz", "en": "Stop Quiz"},
        }

    def _(self, key):
        """Função auxiliar para buscar a tradução correta."""
        return self.i18n.get(key, {}).get(self.lang, key)

    def set_locale(self):
        """Configura o locale do sistema para formatação de datas."""
        try:
            locale_str = 'pt_BR.UTF-8' if self.lang == 'pt' else 'en_US.UTF-8'
            locale.setlocale(locale.LC_TIME, locale_str)
        except locale.Error:
            locale.setlocale(locale.LC_TIME, '')

    def toggle_language(self):
        """Alterna o idioma, salva a configuração e atualiza a UI."""
        self.lang = "en" if self.lang == "pt" else "pt"
        self.config["language"] = self.lang
        mw.addonManager.writeConfig(__name__, self.config)
        self.set_locale()
        self.update_ui_language()
        tooltip(f"Idioma alterado para {'Inglês' if self.lang == 'en' else 'Português'}")

    def update_ui_language(self):
        """Atualiza o texto de todos os componentes da UI."""
        cw = self.cw
        cw.login_button.setText(self._("login_register"))
        cw.forgot_button.setText(self._("forgot_password"))
        cw.change_pass_button.setText(self._("change_password"))
        cw.change_color_button.setText(self._("change_color"))
        cw.logout_button.setText(self._("logout"))
        cw.moderation_button.setText(self._("moderate_users"))
        cw.quiz_button.setText(self._("start_quiz") if not cw.quiz_manager.is_active else self._("stop_quiz"))
        cw.users_label.setText(self._("online_users"))
        cw.tabs.setTabText(0, self._("goals_ranking"))
        cw.tabs.setTabText(1, self._("chat_main"))
        cw.tabs.setTabText(2, self._("live_quiz"))
        cw.tabs.setTabText(3, self._("hall_of_fame"))
        cw.tabs.setTabText(4, self._("my_legacy"))
        cw.edit_goal_button.setText(self._("set_goals"))
        cw.about_game_button.setText(self._("about_game"))
        cw.send_button.setText(self._("send"))
        cw.delete_msg_button.setText(self._("delete_selected"))
        cw.translate_button.setText(self._("translate_selected")) # <<< NOVA LINHA
        cw.search_label.setText(self._("search_user"))
        cw.populate_flag_combobox() # Precisa ser chamado para atualizar o texto do placeholder
        if cw.is_connected and cw.cached_goals_data:
            cw.update_goals_list(cw.cached_goals_data)