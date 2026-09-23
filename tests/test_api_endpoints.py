"""
Suite de Pruebas de Integración para la API REST de Capitales del Mundo.
Ejecución ASGI directa sin dependencias externas (100% compatible con Python 3.10+ y 3.14).
"""

import unittest
import asyncio
import json
import urllib.parse
from datetime import datetime, timezone

from main import app
from database import init_db, get_db_connection
from auth import hash_password, create_session


class ASGIClient:
    """Cliente ASGI liviano en memoria para probar endpoints de FastAPI de forma rápida y reproducible."""
    
    def __init__(self, asgi_app):
        self.app = asgi_app

    def request(self, method: str, path: str, headers: dict = None, body = None, query_params: dict = None):
        return asyncio.run(self._async_request(method, path, headers, body, query_params))

    async def _async_request(self, method: str, path: str, headers: dict = None, body = None, query_params: dict = None):
        headers = headers or {}
        raw_headers = [(k.lower().encode('latin1'), v.encode('latin1')) for k, v in headers.items()]
        
        # Procesar query parameters
        query_string = ""
        if query_params:
            query_string = urllib.parse.urlencode(query_params)

        body_bytes = b""
        if body is not None:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode('utf-8')
                raw_headers.append((b'content-type', b'application/json'))
            elif isinstance(body, str):
                body_bytes = body.encode('utf-8')
            elif isinstance(body, bytes):
                body_bytes = body

        raw_headers.append((b'content-length', str(len(body_bytes)).encode('latin1')))
        raw_headers.append((b'host', b'testserver'))

        response_headers = {}
        response_body = []
        status_code = None

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "raw_path": path.encode('latin1'),
            "query_string": query_string.encode('latin1'),
            "headers": raw_headers,
            "client": ("127.0.0.1", 54321),
            "server": ("127.0.0.1", 80),
        }

        body_sent = False
        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            nonlocal status_code, response_headers
            if message["type"] == "http.response.start":
                status_code = message["status"]
                for k, v in message.get("headers", []):
                    response_headers[k.decode('latin1').lower()] = v.decode('latin1')
            elif message["type"] == "http.response.body":
                response_body.append(message.get("body", b""))

        await self.app(scope, receive, send)

        class Response:
            def __init__(self, status, hdrs, b):
                self.status_code = status
                self.headers = hdrs
                self.content = b
                self.text = b.decode('utf-8', errors='replace')
            def json(self):
                return json.loads(self.text)

        return Response(status_code, response_headers, b"".join(response_body))

    def get(self, path: str, headers: dict = None, query_params: dict = None):
        return self.request("GET", path, headers=headers, query_params=query_params)

    def post(self, path: str, headers: dict = None, body = None, query_params: dict = None):
        return self.request("POST", path, headers=headers, body=body, query_params=query_params)


class TestAPIEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = ASGIClient(app)
        
        # Crear usuario exclusivo de prueba para la suite de integración
        cls.timestamp = int(datetime.now(timezone.utc).timestamp())
        cls.username = f"api_tester_{cls.timestamp}"
        cls.email = f"api_tester_{cls.timestamp}@test.org"
        cls.password = "ValidSecret123"

        # Registrar usuario vía API
        reg_resp = cls.client.post("/api/auth/register", body={
            "username": cls.username,
            "email": cls.email,
            "password": cls.password
        })
        assert reg_resp.status_code == 200, f"Error creando usuario de prueba: {reg_resp.text}"
        data = reg_resp.json()
        cls.token = data["token"]
        cls.user_id = data["user"]["id"]
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

    def test_01_auth_register_validation(self):
        """Verificar que el registro valide campos requeridos con errores descriptivos."""
        # 1. Contraseña muy corta (< 6 caracteres)
        res = self.client.post("/api/auth/register", body={
            "username": "short_user",
            "email": "short@test.com",
            "password": "123"
        })
        self.assertEqual(res.status_code, 422)
        self.assertIn("al menos 6 caracteres", res.json()["detail"])

        # 2. Correo duplicado
        res_dup = self.client.post("/api/auth/register", body={
            "username": f"another_{self.timestamp}",
            "email": self.email,
            "password": "PasswordValido123"
        })
        self.assertEqual(res_dup.status_code, 400)
        self.assertIn("correo electrónico ya está registrado", res_dup.json()["detail"])

    def test_02_auth_login_and_me(self):
        """Verificar login exitoso, credenciales inválidas y endpoint /api/auth/me."""
        # Login exitoso
        res = self.client.post("/api/auth/login", body={
            "login": self.username,
            "password": self.password
        })
        self.assertEqual(res.status_code, 200)
        token = res.json()["token"]

        # Endpoint /api/auth/me con token
        res_me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_me.status_code, 200)
        self.assertEqual(res_me.json()["user"]["username"], self.username)

        # Endpoint /api/auth/me sin token -> 401
        res_anon = self.client.get("/api/auth/me")
        self.assertEqual(res_anon.status_code, 401)

    def test_03_countries_catalog(self):
        """Verificar catálogo de países con filtros de continente y búsqueda."""
        # Catálogo general
        res = self.client.get("/api/countries", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total"], 190)

        # Filtro por continente Europa
        res_eu = self.client.get("/api/countries", headers=self.auth_headers, query_params={"continent": "Europa"})
        self.assertEqual(res_eu.status_code, 200)
        eu_data = res_eu.json()
        for c in eu_data["countries"]:
            self.assertEqual(c["continent"], "Europa")

        # Búsqueda por texto (Francia)
        res_fr = self.client.get("/api/countries", headers=self.auth_headers, query_params={"search": "Francia"})
        self.assertEqual(res_fr.status_code, 200)
        fr_data = res_fr.json()
        self.assertTrue(any(c["name_es"] == "Francia" for c in fr_data["countries"]))

    def test_04_srs_due_cards_and_intervals(self):
        """Verificar que la cola de tarjetas SRS devuelva tarjetas listas con los 4 botones configurados."""
        res = self.client.get("/api/srs/due", headers=self.auth_headers, query_params={"limit": 5})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        
        self.assertIn("cards", data)
        self.assertIn("due_count", data)
        self.assertIn("new_count", data)
        self.assertGreater(len(data["cards"]), 0)

        # Verificar botones en una tarjeta nueva
        first_card = data["cards"][0]
        buttons = first_card["buttons"]
        self.assertEqual(buttons["again"]["label"], "1 min")
        self.assertEqual(buttons["hard"]["label"], "10 min")
        self.assertEqual(buttons["good"]["label"], "1 día")
        self.assertEqual(buttons["easy"]["label"], "4 días")

    def test_05_srs_review_submission_and_live_counters(self):
        """Verificar que el repaso actualice la base de datos y retorne los conteos totales inmediatamente."""
        # Obtener un país para repasar
        due_res = self.client.get("/api/srs/due", headers=self.auth_headers, query_params={"limit": 1})
        card = due_res.json()["cards"][0]
        country_id = card["id"]

        # Calificar con 'good' (1 día -> graduación)
        review_res = self.client.post("/api/srs/review", headers=self.auth_headers, body={
            "country_id": country_id,
            "rating": "good",
            "response_time_ms": 1500
        })
        self.assertEqual(review_res.status_code, 200)
        data = review_res.json()
        
        self.assertTrue(data["success"])
        self.assertTrue(data["is_learned"], "Con 'good' la tarjeta pasa a estar aprendida")
        self.assertEqual(data["interval_label"], "1 día")
        self.assertGreaterEqual(data["total_learned"], 1, "total_learned debe incluir al menos 1 país aprendido")

        # Verificar persistencia en base de datos SQLite
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT is_learned, step, interval_seconds 
            FROM user_country_progress 
            WHERE user_id = ? AND country_id = ?;
        """, (self.user_id, country_id))
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["is_learned"], 1)
        self.assertEqual(row["step"], 2)
        self.assertEqual(row["interval_seconds"], 86400)

    def test_06_srs_stats_endpoint(self):
        """Verificar cálculo global de estadísticas y desglose por continente."""
        res = self.client.get("/api/srs/stats", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("total_countries", data)
        self.assertIn("learned_count", data)
        self.assertIn("learning_count", data)
        self.assertIn("mastery_percentage", data)
        self.assertIn("continents", data)
        self.assertGreaterEqual(data["total_countries"], 190)
        self.assertGreaterEqual(len(data["continents"]), 5)

    def test_07_quiz_question_generator(self):
        """Verificar que el modo Quiz genere preguntas válidas con 4 opciones únicas."""
        res = self.client.get("/api/quiz/question", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("target_country", data)
        self.assertIn("options", data)
        self.assertEqual(len(data["options"]), 4, "Debe haber exactamente 4 opciones")
        
        correct_opts = [o for o in data["options"] if o.get("is_correct")]
        self.assertEqual(len(correct_opts), 1, "Debe haber exactamente 1 opción correcta")
        
        capital_names = [o["capital"] for o in data["options"]]
        self.assertEqual(len(set(capital_names)), 4, "Las 4 opciones deben ser capitales distintas")

    def test_08_static_files_served(self):
        """Verificar que los archivos estáticos de la SPA se sirvan correctamente."""
        res_html = self.client.get("/")
        self.assertEqual(res_html.status_code, 200)
        self.assertIn("Capitales del Mundo", res_html.text)

        res_css = self.client.get("/static/css/styles.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn(".flashcard-3d", res_css.text)

        res_js = self.client.get("/static/js/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("updateSessionIndicators", res_js.text)


if __name__ == "__main__":
    unittest.main()
