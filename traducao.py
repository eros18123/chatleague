# -- coding: utf-8 --
# traducao.py - Módulo para tradução em tempo real do AnkiChat (v1.1 - Bidirecional)

import threading
import html
import re

from aqt.qt import QObject, pyqtSignal

try:
    from googletrans import Translator
    GOOGLETRANS_AVAILABLE = True
except ImportError:
    GOOGLETRANS_AVAILABLE = False
    print("AnkiChat [AVISO]: Biblioteca 'googletrans' não encontrada. A função de tradução estará desabilitada. Para habilitar, instale-a: pip install googletrans==4.0.0-rc1")

class TranslationManager(QObject):
    """
    Gerencia a tradução de mensagens de chat usando a biblioteca googletrans.
    A tradução é feita em uma thread separada para não bloquear a UI.
    """
    translation_finished = pyqtSignal(object, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        if GOOGLETRANS_AVAILABLE:
            self.translator = Translator()
        else:
            self.translator = None

    def translate_text_async(self, list_widget, item, text_to_translate, ui_lang):
        """
        Inicia a tradução de um texto em uma thread de background.

        Args:
            list_widget (QListWidget): O widget que contém a mensagem.
            item (QListWidgetItem): O item da lista a ser atualizado.
            text_to_translate (str): O texto (pode conter HTML) a ser traduzido.
            ui_lang (str): O código do idioma da interface do usuário (ex: 'en', 'pt').
        """
        if not self.translator:
            self.translation_finished.emit(list_widget, item, "[Tradução indisponível: biblioteca não instalada]")
            return

        thread = threading.Thread(
            target=self._translation_worker,
            args=(list_widget, item, text_to_translate, ui_lang),
            daemon=True
        )
        thread.start()

    def _translation_worker(self, list_widget, item, text, ui_lang):
        """
        Executa a detecção e tradução na thread de background.
        """
        try:
            clean_text = re.sub('<[^<]+?>', '', text)
            
            if not clean_text.strip():
                self.translation_finished.emit(list_widget, item, "[Texto vazio]")
                return

            # 1. Detectar o idioma do texto de origem
            detected = self.translator.detect(clean_text)
            source_lang = detected.lang

            # 2. Determinar o idioma de destino
            target_lang = ''
            if source_lang == ui_lang:
                # Se o texto já está no idioma da UI, traduz para o outro idioma
                target_lang = 'en' if ui_lang == 'pt' else 'pt'
            else:
                # Se o texto está em outro idioma, traduz para o idioma da UI
                target_lang = ui_lang

            # 3. Traduzir
            translated = self.translator.translate(clean_text, dest=target_lang)
            
            safe_translation = html.escape(translated.text)
            self.translation_finished.emit(list_widget, item, safe_translation)
        except Exception as e:
            error_message = html.escape(str(e))
            self.translation_finished.emit(list_widget, item, f"[Erro na tradução: {error_message}]")