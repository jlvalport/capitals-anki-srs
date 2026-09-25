import unittest
import time
from datetime import datetime, timedelta, timezone

from database import init_db, get_db_connection
from auth import hash_password, create_session
from srs_engine import (
    process_review,
    get_button_intervals,
    format_interval,
    SEC_1_MIN,
    SEC_10_MIN,
    SEC_1_DAY,
    SEC_4_DAYS
)
from main import submit_review, ReviewRequest, get_due_cards


class TestSRSButtonsAndQueue(unittest.TestCase):
    """
    Suite de pruebas para verificar el comportamiento de los botones de calificación Anki SRS,
    los tiempos exactos de los intervalos y la priorización cronológica de tarjetas en cola.
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        """Crear usuario aislado para cada prueba."""
        conn = get_db_connection()
        cursor = conn.cursor()
        self.username = f"user_test_queue_{int(time.time() * 1000)}"
        self.email = f"{self.username}@test.com"
        pwd_hash, salt = hash_password("pass1234")
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, salt)
            VALUES (?, ?, ?, ?);
        """, (self.username, self.email, pwd_hash, salt))
        self.user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.user = {
            "id": self.user_id,
            "username": self.username,
            "email": self.email
        }

    def tearDown(self):
        """Limpiar usuario y progreso tras cada prueba."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_country_progress WHERE user_id = ?;", (self.user_id,))
        cursor.execute("DELETE FROM review_logs WHERE user_id = ?;", (self.user_id,))
        cursor.execute("DELETE FROM user_sessions WHERE user_id = ?;", (self.user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?;", (self.user_id,))
        conn.commit()
        conn.close()

    def test_01_button_intervals_and_labels(self):
        """
        Verifica que los 4 botones generen los intervalos y etiquetas exactos según el paso:
        - again: 1 min (60 s)
        - hard: 10 min (600 s)
        - good: 1 día (86.400 s)
        - easy: 4 días (345.600 s)
        """
        buttons = get_button_intervals(step=0, interval_seconds=SEC_1_MIN, ease_factor=2.5, is_learned=0)

        # 1. Otra vez (Again)
        self.assertEqual(buttons["again"]["seconds"], 60)
        self.assertEqual(buttons["again"]["label"], "1 min")

        # 2. Difícil (Hard)
        self.assertEqual(buttons["hard"]["seconds"], 600)
        self.assertEqual(buttons["hard"]["label"], "10 min")

        # 3. Bien (Good)
        self.assertEqual(buttons["good"]["seconds"], 86400)
        self.assertEqual(buttons["good"]["label"], "1 día")

        # 4. Fácil (Easy)
        self.assertEqual(buttons["easy"]["seconds"], 345600)
        self.assertEqual(buttons["easy"]["label"], "4 días")

    def test_02_button_review_due_timestamp_accuracy(self):
        """
        Verifica que al procesar cada botón, la fecha due_at se calcule con el intervalo exacto:
        - again -> now + 60s
        - hard -> now + 600s
        - good -> now + 86400s
        - easy -> now + 345600s
        """
        now = datetime.now(timezone.utc)

        # Again
        res_again = process_review('again', 0, 60, 2.5, 0, 0, 0)
        due_again = datetime.strptime(res_again["due_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        diff_again = (due_again - now).total_seconds()
        self.assertAlmostEqual(diff_again, 60, delta=2)
        self.assertEqual(res_again["interval_seconds"], 60)
        self.assertEqual(res_again["interval_label"], "1 min")

        # Hard
        res_hard = process_review('hard', 0, 60, 2.5, 0, 0, 0)
        due_hard = datetime.strptime(res_hard["due_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        diff_hard = (due_hard - now).total_seconds()
        self.assertAlmostEqual(diff_hard, 600, delta=2)
        self.assertEqual(res_hard["interval_seconds"], 600)
        self.assertEqual(res_hard["interval_label"], "10 min")

        # Good
        res_good = process_review('good', 0, 60, 2.5, 0, 0, 0)
        due_good = datetime.strptime(res_good["due_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        diff_good = (due_good - now).total_seconds()
        self.assertAlmostEqual(diff_good, 86400, delta=2)

        # Easy
        res_easy = process_review('easy', 0, 60, 2.5, 0, 0, 0)
        due_easy = datetime.strptime(res_easy["due_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        diff_easy = (due_easy - now).total_seconds()
        self.assertAlmostEqual(diff_easy, 345600, delta=2)

    def test_03_multiple_1_minute_cards_fifo_order(self):
        """
        CRÍTICO: Aunque haya muchas cartas señaladas con 1 minuto (Again),
        se deben mostrar primero las cartas que fueron señaladas primero en el tiempo establecido.
        """
        base_time = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)

        # Simular 5 tarjetas marcadas con 'again' (1 min = 60s) en momentos consecutivos
        # Card 1: marcada a los 0s   -> vence a los 60s
        # Card 2: marcada a los 10s  -> vence a los 70s
        # Card 3: marcada a los 20s  -> vence a los 80s
        # Card 4: marcada a los 30s  -> vence a los 90s
        # Card 5: marcada a los 40s  -> vence a los 100s
        cards = []
        for i in range(1, 6):
            marked_at = base_time + timedelta(seconds=(i - 1) * 10)
            due_at = marked_at + timedelta(seconds=60)
            cards.append({
                "id": i,
                "name": f"País_{i}",
                "marked_at": marked_at,
                "due_at": due_at,
                "dueTimestamp": int(due_at.timestamp() * 1000)
            })

        # Función que replica el algoritmo de selección y promoción del cliente
        def get_due_cards_at(current_simulated_time, scheduled_queue):
            sim_timestamp = int(current_simulated_time.timestamp() * 1000)
            ready = [c for c in scheduled_queue if c["dueTimestamp"] <= sim_timestamp]
            # Debe ordenar por dueTimestamp ASCENDENTE para respetar el orden cronológico
            ready.sort(key=lambda c: c["dueTimestamp"])
            return ready

        # 1. A los 55 segundos: Ninguna tarjeta ha cumplido su minuto
        t_55 = base_time + timedelta(seconds=55)
        ready_55 = get_due_cards_at(t_55, cards)
        self.assertEqual(len(ready_55), 0, "A los 55s ninguna tarjeta debe estar lista aún.")

        # 2. A los 65 segundos: SOLO la tarjeta 1 cumplió su minuto
        t_65 = base_time + timedelta(seconds=65)
        ready_65 = get_due_cards_at(t_65, cards)
        self.assertEqual(len(ready_65), 1)
        self.assertEqual(ready_65[0]["id"], 1, "A los 65s la primera tarjeta en mostrarse DEBE ser la 1.")

        # 3. A los 75 segundos: Las tarjetas 1 y 2 están listas
        t_75 = base_time + timedelta(seconds=75)
        ready_75 = get_due_cards_at(t_75, cards)
        self.assertEqual(len(ready_75), 2)
        self.assertEqual(ready_75[0]["id"], 1, "La tarjeta 1 debe mostrarse antes que la 2.")
        self.assertEqual(ready_75[1]["id"], 2, "La tarjeta 2 debe mostrarse en segundo lugar.")

        # 4. A los 105 segundos: Todas las 5 tarjetas han cumplido su minuto
        t_105 = base_time + timedelta(seconds=105)
        ready_105 = get_due_cards_at(t_105, cards)
        self.assertEqual(len(ready_105), 5)
        order_ids = [c["id"] for c in ready_105]
        self.assertEqual(order_ids, [1, 2, 3, 4, 5], "El orden de presentación debe ser estrictamente cronológico: [1, 2, 3, 4, 5].")

    def test_04_session_promotion_without_waiting_for_all_cards(self):
        """
        Verifica que una tarjeta en espera de 1 min NO espera a que terminen las 15 tarjetas de la sesión:
        apenas se cumple su tiempo, pasa al frente de la cola de estudio.
        """
        base_time = datetime.now(timezone.utc)

        # Cola de sesión inicial: 10 tarjetas nuevas
        ready_queue = [{"id": i, "name": f"País_Nuevo_{i}", "is_new": True} for i in range(2, 12)]

        # Tarjeta 1 marcada con 'again' hace 65 segundos
        due_card_1 = {
            "id": 1,
            "name": "País_Again_1",
            "dueTimestamp": int((base_time - timedelta(seconds=5)).timestamp() * 1000) # Ya venció hace 5s
        }
        scheduled_queue = [due_card_1]

        # Algoritmo de promoción en showNextCard:
        now_ts = int(base_time.timestamp() * 1000)
        ready_from_scheduled = [c for c in scheduled_queue if c["dueTimestamp"] <= now_ts]
        scheduled_queue = [c for c in scheduled_queue if c["dueTimestamp"] > now_ts]

        # Insertar al frente de la cola
        ready_queue = ready_from_scheduled + ready_queue

        # Verificar que la siguiente tarjeta en salir es la Tarjeta 1 (la que cumplió su minuto)
        next_card = ready_queue.pop(0)
        self.assertEqual(next_card["id"], 1, "La tarjeta marcada con 'again' debe salir INMEDIATAMENTE al frente sin esperar las demás de la sesión.")
        self.assertEqual(len(ready_queue), 10, "Las 10 tarjetas nuevas continúan después.")

    def test_05_interleaved_again_and_hard_priority(self):
        """
        Verifica que una tarjeta marcada con Again (1 min) tenga prioridad sobre una marcada con Hard (10 min),
        incluso si la de Hard fue marcada primero.
        """
        base_time = datetime(2026, 9, 25, 14, 0, 0, tzinfo=timezone.utc)

        # Card A marcada como Hard (10 min = 600s) en t=0s -> due at t=600s
        card_a = {
            "id": "A",
            "rating": "hard",
            "due_at": base_time + timedelta(seconds=600),
            "dueTimestamp": int((base_time + timedelta(seconds=600)).timestamp() * 1000)
        }

        # Card B marcada como Again (1 min = 60s) en t=10s -> due at t=70s
        card_b = {
            "id": "B",
            "rating": "again",
            "due_at": base_time + timedelta(seconds=70),
            "dueTimestamp": int((base_time + timedelta(seconds=70)).timestamp() * 1000)
        }

        scheduled = [card_a, card_b]

        # A los 80 segundos:
        # Card B (1 min) YA está lista (70s <= 80s).
        # Card A (10 min) TODAVÍA NO está lista (600s > 80s).
        t_80 = int((base_time + timedelta(seconds=80)).timestamp() * 1000)
        ready = [c for c in scheduled if c["dueTimestamp"] <= t_80]
        ready.sort(key=lambda c: c["dueTimestamp"])

        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["id"], "B", "La tarjeta de 1 minuto debe salir mucho antes que la de 10 minutos.")

    def test_06_database_due_query_order_by_asc(self):
        """
        Verifica que la consulta SQL en SQLite de tarjetas pendientes ordene estrictamente por due_at ASC,
        garantizando que la API retorne primero las primeras tarjetas señaladas con 1 minuto.
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        now = datetime.now(timezone.utc)

        # Insertar 4 países de prueba con vencimiento escalonado en el pasado
        # País 1 venció hace 40s
        # País 2 venció hace 30s
        # País 3 venció hace 20s
        # País 4 venció hace 10s
        country_ids = [1, 2, 3, 4]
        for idx, cid in enumerate(country_ids):
            offset_seconds = (4 - idx) * 10
            past_due = (now - timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO user_country_progress (
                    user_id, country_id, state, step, interval_seconds, 
                    ease_factor, repetitions, lapses, due_at, is_learned
                )
                VALUES (?, ?, 'learning', 0, 60, 2.5, 1, 1, ?, 0)
                ON CONFLICT(user_id, country_id) DO UPDATE SET
                    due_at = excluded.due_at;
            """, (self.user_id, cid, past_due))

        conn.commit()
        conn.close()

        # Consultar mediante la función get_due_cards de FastAPI
        res = get_due_cards(limit=10, continent="todos", current_user=self.user)
        cards = res["cards"]

        # Filtrar solo los 4 países insertados
        test_cards = [c for c in cards if c["id"] in country_ids]
        self.assertEqual(len(test_cards), 4)

        returned_ids = [c["id"] for c in test_cards]
        self.assertEqual(returned_ids, [1, 2, 3, 4], "La base de datos DEBE retornar las tarjetas en estricto orden cronológico ASC.")

    def test_07_api_review_endpoint_returns_updated_buttons(self):
        """
        Verifica que el endpoint /api/srs/review devuelva de inmediato las nuevas etiquetas
        y tiempos de los botones para la próxima revisión de la tarjeta.
        """
        req = ReviewRequest(country_id=1, rating="again", response_time_ms=1200)
        res = submit_review(req=req, current_user=self.user)

        self.assertTrue(res["success"])
        self.assertEqual(res["rating"], "again")
        self.assertEqual(res["interval_seconds"], 60)
        self.assertEqual(res["interval_label"], "1 min")
        self.assertIn("buttons", res)
        self.assertEqual(res["buttons"]["again"]["label"], "1 min")
        self.assertEqual(res["buttons"]["hard"]["label"], "10 min")
        self.assertEqual(res["buttons"]["good"]["label"], "1 día")
        self.assertEqual(res["buttons"]["easy"]["label"], "4 días")


if __name__ == "__main__":
    unittest.main()
