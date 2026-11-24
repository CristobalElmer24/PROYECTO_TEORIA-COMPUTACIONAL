import sqlite3
import unittest

import analizador as A
import exportador as E
from app import app

LOTE = ["PED-045-M12-C03", "PED-102-D-B02+S01", "PED-007-L-C01+B02+S03",
        "PED-045-M5-B01",          # correlativo duplicado -> rechazado
        "PED-045-X12-C03",         # error sintáctico/léxico
        "PED-001-M1-C01'; DROP TABLE pedido;--"]   # intento de inyección


def _res(lineas=LOTE):
    return [A.analizar(l) for l in lineas]


class PruebasSQL(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(E.transpilar(_res(), "sqlite"))   # debe ejecutarse sin errores

    def test_pedidos_aceptados(self):
        filas = self.db.execute("SELECT correlativo, canal, mesa FROM pedido ORDER BY correlativo").fetchall()
        self.assertEqual(filas, [("007", "LLEVAR", None), ("045", "MESA", 12), ("102", "DELIVERY", None)])

    def test_items(self):
        n = self.db.execute("SELECT COUNT(*) FROM pedido_item").fetchone()[0]
        self.assertEqual(n, 1 + 2 + 3)
        fila = self.db.execute("SELECT codigo, categoria, numero FROM pedido_item "
                               "WHERE correlativo='102' AND linea=2").fetchone()
        self.assertEqual(fila, ("S01", "S", 1))

    def test_rechazados_e_inyeccion(self):
        filas = self.db.execute("SELECT entrada, motivo FROM pedido_rechazado ORDER BY id").fetchall()
        self.assertEqual(len(filas), 3)
        self.assertIn("duplicado", filas[0][1])
        self.assertTrue(any("DROP TABLE" in e for e, _ in filas))   # guardado como texto
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM pedido").fetchone()[0], 3)  # tabla intacta

    def test_claves_foraneas_activas(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO pedido_item VALUES ('999', 1, 'C01', 'C', 1)")


class PruebasDialectos(unittest.TestCase):
    def test_diferencias(self):
        r = _res(["PED-001-M1-C01"])
        self.assertIn("PRAGMA foreign_keys", E.transpilar(r, "sqlite"))
        pg = E.transpilar(r, "postgresql")
        self.assertIn("BEGIN;", pg)
        self.assertNotIn("PRAGMA", pg)
        self.assertIn("START TRANSACTION;", E.transpilar(r, "mysql"))

    def test_mysql_escapa_barra_invertida(self):
        self.assertEqual(E._lit("a\\b", "mysql"), "'a\\\\b'")
        self.assertEqual(E._lit("a\\b", "sqlite"), "'a\\b'")
        self.assertEqual(E._lit("it's", "postgresql"), "'it''s'")

    def test_dialecto_invalido(self):
        with self.assertRaises(ValueError):
            E.transpilar(_res(), "oracle")


class PruebasPDFyRutas(unittest.TestCase):
    def test_pdf(self):
        pdf = E.generar_pdf(_res(["PED-001-M1-C01", "PED→X", "PED-045-D-C03"]), "postgresql")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 2000)

    def test_rutas(self):
        c = app.test_client()
        cuerpo = {"texto": "PED-045-M12-C03\nPED-102-D-B02+S01", "dialecto": "postgresql"}
        r = c.post("/api/exportar/sql", json=cuerpo)
        self.assertIn("INSERT INTO pedido", r.get_json()["sql"])
        r = c.post("/descargar/sql", json=cuerpo)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertIn(b"BEGIN;", r.data)
        r = c.post("/descargar/pdf", json=cuerpo)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertEqual(c.post("/descargar/sql", json={"texto": ""}).status_code, 400)
        self.assertEqual(c.post("/descargar/sql", json={"texto": "PED-001-M1-C01", "dialecto": "x"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
