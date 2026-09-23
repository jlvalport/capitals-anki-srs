import unittest
import os
import sqlite3
from datetime import datetime, timedelta, timezone

# Importar módulos de la aplicación
from database import init_db, get_db_connection, DB_PATH
from auth import hash_password, verify_password, create_session, get_current_user
from srs_engine import (
    process_review, 
    get_button_intervals, 
    format_interval,
    SEC_1_MIN, 
    SEC_10_MIN, 
    SEC_1_DAY, 
    SEC_4_DAYS
)

class TestCapitalsApp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Inicializar base de datos de prueba."""
        init_db()

    def test_01_countries_catalog_seeded(self):
        """Verificar que el catálogo contenga al menos 190 países."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM countries;")
        total = cursor.fetchone()["total"]
        conn.close()
        self.assertGreaterEqual(total, 190, f"Debe haber al menos 190 países en la BD, hay {total}")

    def test_02_password_hashing(self):
        """Verificar hashing seguro con PBKDF2 y salting."""
        pwd = "MiSuperPassword123"
        hash1, salt1 = hash_password(pwd)
        hash2, salt2 = hash_password(pwd)

        # Dos hashes con salts diferentes deben ser distintos
        self.assertNotEqual(hash1, hash2)
        self.assertNotEqual(salt1, salt2)

        # La verificación debe ser exitosa con el salt correcto
        self.assertTrue(verify_password(pwd, hash1, salt1))
        self.assertFalse(verify_password("PasswordErroneo", hash1, salt1))

    def test_03_session_management(self):
        """Verificar creación y persistencia de tokens de sesión."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Crear usuario de prueba
        test_user = f"test_user_{int(datetime.now(timezone.utc).timestamp())}"
        pwd_hash, salt = hash_password("pass123")
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, salt)
            VALUES (?, ?, ?, ?);
        """, (test_user, f"{test_user}@test.com", pwd_hash, salt))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Crear sesión
        token = create_session(user_id)
        self.assertIsNotNone(token)
        self.assertEqual(len(token), 64)

        # Validar usuario con la función get_current_user
        user_data = get_current_user(f"Bearer {token}")
        self.assertEqual(user_data["id"], user_id)
        self.assertEqual(user_data["username"], test_user)

    def test_04_anki_srs_flow(self):
        """Verificar la secuencia exacta de intervalos Anki: 1m, 10m, 1d, 4d."""
        # 1. Tarjeta nueva: Paso 0 con Hard (10 min)
        res_hard = process_review(
            rating='hard',
            current_step=0,
            current_interval=SEC_1_MIN,
            current_ease=2.5,
            current_repetitions=0,
            current_lapses=0,
            current_is_learned=0
        )
        self.assertEqual(res_hard["step"], 1)
        self.assertEqual(res_hard["interval_seconds"], SEC_10_MIN)
        self.assertEqual(res_hard["is_learned"], 0)

        # 2. Paso 0 (o 1) con Good -> Paso 2 (1 día) [Graduación]
        res_good = process_review(
            rating='good',
            current_step=0,
            current_interval=SEC_1_MIN,
            current_ease=2.5,
            current_repetitions=0,
            current_lapses=0,
            current_is_learned=0
        )
        self.assertEqual(res_good["step"], 2)
        self.assertEqual(res_good["interval_seconds"], SEC_1_DAY)
        self.assertEqual(res_good["is_learned"], 1, "Al llegar a 1 día debe quedar marcado como aprendido (is_learned = 1)")

        # 3. Paso 2 (1 día) -> Good -> Paso 3 (4 días)
        res3 = process_review(
            rating='good',
            current_step=2,
            current_interval=SEC_1_DAY,
            current_ease=2.5,
            current_repetitions=1,
            current_lapses=0,
            current_is_learned=1
        )
        self.assertEqual(res3["step"], 3)
        self.assertEqual(res3["interval_seconds"], SEC_4_DAYS)
        self.assertEqual(res3["is_learned"], 1)

        # 4. Olvido (Again): Vuelve a Paso 0 (1 min)
        res_again = process_review(
            rating='again',
            current_step=3,
            current_interval=SEC_4_DAYS,
            current_ease=2.5,
            current_repetitions=2,
            current_lapses=0,
            current_is_learned=1
        )
        self.assertEqual(res_again["step"], 0)
        self.assertEqual(res_again["interval_seconds"], SEC_1_MIN)
        self.assertEqual(res_again["lapses"], 1)

    def test_05_anki_easy_jump(self):
        """Verificar salto acelerado con botón Fácil."""
        res_easy = process_review(
            rating='easy',
            current_step=0,
            current_interval=SEC_1_MIN,
            current_ease=2.5,
            current_repetitions=0,
            current_lapses=0,
            current_is_learned=0
        )
        # Fácil desde el paso 0 salta directamente a 4 días (graduado)
        self.assertEqual(res_easy["step"], 3)
        self.assertEqual(res_easy["interval_seconds"], SEC_4_DAYS)
        self.assertEqual(res_easy["is_learned"], 1)
        self.assertGreater(res_easy["ease_factor"], 2.5)

    def test_06_button_intervals(self):
        """Verificar que los botones generen los textos de intervalos exactos: 1 min, 10 min, 1 día, 4 días."""
        buttons = get_button_intervals(step=0, interval_seconds=60, ease_factor=2.5, is_learned=0)
        self.assertEqual(buttons["again"]["label"], "1 min")
        self.assertEqual(buttons["hard"]["label"], "10 min")
        self.assertEqual(buttons["good"]["label"], "1 día")
        self.assertEqual(buttons["easy"]["label"], "4 días")

if __name__ == "__main__":
    unittest.main()
