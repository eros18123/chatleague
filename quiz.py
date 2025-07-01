# quiz.py

import random
import threading
import time
from aqt import mw

class QuizManager:
    def __init__(self, firebase_api, chat_window, addon_path):
        self.firebase = firebase_api
        self.chat_window = chat_window
        self.addon_path = addon_path
        
        self.is_active = False
        self.questions = []
        self.unasked_questions = []
        
        self.current_question_data = None
        self.correct_answer_index = -1
        
        self.question_timer = None
        self.question_resolved = threading.Event()
        
        self.current_category_name = None

    def _load_questions_from_firebase(self, category_name):
        """Carrega as perguntas do Firebase para a memória."""
        self.questions = []
        try:
            questions_data = self.firebase.get_data(f"quiz_questions/{category_name}", self.chat_window.id_token)
            if not questions_data:
                self._post_system_message(f"<b>ERRO: Nenhuma pergunta encontrada para a categoria '{category_name}' no Firebase.</b>")
                return False

            for key, value in questions_data.items():
                if 'question' in value and 'answers' in value and isinstance(value['answers'], list):
                    self.questions.append(value)

            if self.questions:
                print(f"AnkiChat [INFO QUIZ]: Sucesso! {len(self.questions)} perguntas carregadas do Firebase para a categoria '{category_name}'.")
                return True
            else:
                self._post_system_message(f"<b>ERRO: Formato de perguntas inválido para a categoria '{category_name}' no Firebase.</b>")
                return False
        except Exception as e:
            self._post_system_message(f"<b>ERRO ao carregar o quiz do Firebase: {e}</b>")
            return False

    def _post_system_message(self, text):
        if not self.chat_window.is_connected: return
        # --- INÍCIO DA CORREÇÃO ---
        # Adiciona o UID do anfitrião à mensagem para satisfazer a regra de validação do Firebase.
        message_data = { 
            "uid": self.chat_window.uid,
            "nick": "QuizBot", 
            "text": text, 
            "timestamp": {".sv": "timestamp"}, 
            "quiz_event": True 
        }
        # --- FIM DA CORREÇÃO ---
        threading.Thread(target=self.firebase.post_data, args=("messages", message_data, self.chat_window.id_token), daemon=True).start()
        local_display_msg = message_data.copy()
        local_display_msg["timestamp"] = int(time.time() * 1000)
        self.chat_window.chat_manager.display_message(None, local_display_msg)

    def start_quiz(self, category_name, starter_nick):
        if not self._load_questions_from_firebase(category_name):
            self.is_active = False
            if self.chat_window.current_quiz_data and self.chat_window.uid == self.chat_window.current_quiz_data.get("host_uid"):
                self.firebase.delete_data("league_status/current_quiz", self.chat_window.id_token)
            return

        self.is_active = True
        self.current_category_name = category_name
        self.unasked_questions = self.questions.copy()
        random.shuffle(self.unasked_questions)
        self._post_system_message(f"<b>--- O Quiz de {category_name} começou, iniciado por {starter_nick}! ---</b>")
        threading.Thread(target=self.game_loop, daemon=True).start()

    def stop_quiz(self):
        if not self.is_active: return
        self.is_active = False
        self.current_category_name = None
        self.question_resolved.set()
        if self.question_timer: self.question_timer.cancel()
        self.chat_window.timer_updated.emit("Tempo restante: --")

    def game_loop(self):
        while self.is_active:
            if not self.unasked_questions:
                self._post_system_message("<b>Fim de jogo! Todas as perguntas foram feitas. Reiniciando...</b>")
                time.sleep(3)
                self.unasked_questions = self.questions.copy()
                random.shuffle(self.unasked_questions)
            self.ask_next_question()
            self.question_resolved.wait()
            if not self.is_active: break
            time.sleep(1.5) 
            if self.unasked_questions: self._post_system_message('<div style="border-bottom: 1px solid black; margin: 8px 0;"></div>')
            time.sleep(3.5)

    def ask_next_question(self):
        self.question_resolved.clear()
        self.current_question_data = self.unasked_questions.pop(0)
        correct_answer = self.current_question_data["answers"][0]
        shuffled_answers = self.current_question_data["answers"].copy()
        random.shuffle(shuffled_answers)
        self.correct_answer_index = shuffled_answers.index(correct_answer) + 1
        question_html = f"<b>❓ {self.current_question_data['question']}</b>"
        options_html = "<br>" + "<br>".join([f"  <b>{i+1})</b> {ans}" for i, ans in enumerate(shuffled_answers)])
        self._post_system_message(f"{question_html}{options_html}")
        self.start_countdown_timer(60)

    def start_countdown_timer(self, duration):
        if self.question_timer: self.question_timer.cancel()
        def countdown(seconds_left):
            if not self.is_active or self.question_resolved.is_set(): return
            if seconds_left > 0:
                timer_text = f"Tempo restante: {seconds_left}s"
                self.chat_window.timer_updated.emit(timer_text)
                self.firebase.put_data("quiz_timer", timer_text, self.chat_window.id_token)
                self.question_timer = threading.Timer(1.0, countdown, [seconds_left - 1])
                self.question_timer.daemon = True
                self.question_timer.start()
            else: self._on_timeout()
        countdown(duration)

    def _on_timeout(self):
        if self.question_resolved.is_set(): return
        correct_text = self.current_question_data['answers'][0]
        msg = f"<font color='orange'>⏰ Tempo esgotado! A resposta era <b>{self.correct_answer_index}) {correct_text}</b></font>"
        self._post_system_message(msg)
        self.chat_window.timer_updated.emit("Tempo restante: 0s")
        self.firebase.delete_data("quiz_timer", self.chat_window.id_token)
        self.question_resolved.set()



# Em quiz.py

    def handle_answer(self, nickname, uid, answer_text):
        if not self.is_active or self.question_resolved.is_set(): return
        try: answer_num = int(answer_text)
        except ValueError: return
        if answer_num == self.correct_answer_index:
            if self.question_timer: self.question_timer.cancel()
            msg = f"<font color='green'>🏆 <b>{nickname} acertou!</b></font>"
            self._post_system_message(msg)
            self.chat_window.timer_updated.emit(f"Acertou: {nickname}!")
            self.firebase.delete_data("quiz_timer", self.chat_window.id_token)
            self._update_user_quiz_score(uid, nickname)
            self._update_user_pr_points(uid)
            self.chat_window.quiz_score_updated.emit(nickname)
            # Emite o sinal para forçar a atualização do ranking principal
            self.chat_window.main_ranking_update_signal.emit()
            self.question_resolved.set()
        else:
            msg = f"<font color='red'>❌ {nickname} errou.</font>"
            self._post_system_message(msg)



    def _update_user_quiz_score(self, uid, nickname):
        threading.Thread(target=self._task_update_quiz_score, args=(uid, nickname, self.chat_window), daemon=True).start()

    def _task_update_quiz_score(self, uid, nickname, cw):
        if not cw.is_connected or not self.current_category_name: return
        path = f"quiz_scores/{self.current_category_name}/{uid}"
        score_data = self.firebase.get_data(path, cw.id_token) or {"score": 0}
        score_data["score"] = score_data.get("score", 0) + 1
        score_data["nickname"] = nickname
        self.firebase.put_data(path, score_data, cw.id_token)

    def _update_user_pr_points(self, uid):
        threading.Thread(target=self._task_update_pr_points, args=(uid, self.chat_window), daemon=True).start()

    def _task_update_pr_points(self, uid, cw):
        if not cw.is_connected: return
        goal_data = self.firebase.get_data(f"goals/{uid}", cw.id_token) or {}
        goal_data["retention_points"] = goal_data.get("retention_points", 0) + 1
        self.firebase.put_data(f"goals/{uid}", goal_data, cw.id_token)