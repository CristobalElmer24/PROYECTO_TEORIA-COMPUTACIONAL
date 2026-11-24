"""Etapa 3 - Exportación de pedidos

1. Transpilador: convierte los pedidos analizados (salida de analizador.analizar)
   en un script SQL ejecutable. Solo se insertan los pedidos aceptados por el
   analizador léxico/sintáctico; los rechazados se guardan en una tabla de
   auditoría con el motivo del error.
2. Reporte PDF: resumen, resultado por pedido y el script SQL generado.

Dialectos soportados: SQLite, PostgreSQL y MySQL/MariaDB.
"""
import io
import textwrap
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

DIALECTOS = {"sqlite": "SQLite", "postgresql": "PostgreSQL", "mysql": "MySQL / MariaDB"}

# Significado de la letra inicial del ítem y de la ubicación (editable).
CATEGORIAS = [("C", "Comida"), ("B", "Bebida"), ("S", "Snack")]
CANALES = {"M": ("MESA", "Mesa"), "D": ("DELIVERY", "Delivery"), "L": ("LLEVAR", "Para llevar")}


# ------------------------------------------------------------ utilidades SQL
def _lit(valor, dialecto):
    """Literal SQL seguro (escapa comillas; en MySQL también la barra invertida)."""
    if valor is None:
        return "NULL"
    if isinstance(valor, int):
        return str(valor)
    s = str(valor).replace("\x00", "")
    if dialecto == "mysql":
        s = s.replace("\\", "\\\\")
    return "'" + s.replace("'", "''") + "'"


def clasificar(resultados):
    """Separa los resultados en (aceptados, rechazados).

    Un correlativo repetido dentro del mismo lote se rechaza, porque el
    correlativo es la clave primaria del pedido.
    """
    aceptados, rechazados, vistos = [], [], set()
    for r in resultados:
        if r["valido"]:
            p = dict(r["pedido"], entrada=r["entrada"])
            if p["correlativo"] in vistos:
                rechazados.append({"entrada": r["entrada"], "pos": None,
                                   "motivo": "Correlativo duplicado en el lote: PED-%s ya fue registrado"
                                             % p["correlativo"]})
                continue
            vistos.add(p["correlativo"])
            aceptados.append(p)
        else:
            rechazados.append({"entrada": r["entrada"], "pos": r["pos"], "motivo": r["mensaje"]})
    return aceptados, rechazados


# ------------------------------------------------------------ transpilador
def _ddl():
    return """\
CREATE TABLE IF NOT EXISTS categoria_item (
    codigo  VARCHAR(1)  PRIMARY KEY,
    nombre  VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS canal (
    codigo  VARCHAR(10) PRIMARY KEY,
    nombre  VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS pedido (
    correlativo VARCHAR(3)  PRIMARY KEY,
    canal       VARCHAR(10) NOT NULL REFERENCES canal (codigo),
    ubicacion   VARCHAR(3)  NOT NULL,
    mesa        INTEGER,
    estado      VARCHAR(20) NOT NULL DEFAULT 'EN_COCINA',
    creado_en   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    CHECK (canal <> 'MESA' OR mesa IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS pedido_item (
    correlativo VARCHAR(3) NOT NULL REFERENCES pedido (correlativo),
    linea       INTEGER    NOT NULL,
    codigo      VARCHAR(3) NOT NULL,
    categoria   VARCHAR(1) NOT NULL REFERENCES categoria_item (codigo),
    numero      INTEGER    NOT NULL,
    PRIMARY KEY (correlativo, linea)
);

CREATE TABLE IF NOT EXISTS pedido_rechazado (
    id       INTEGER PRIMARY KEY,
    entrada  TEXT    NOT NULL,
    motivo   TEXT    NOT NULL,
    posicion INTEGER
);"""


def transpilar(resultados, dialecto="sqlite", ahora=None):
    """Convierte los pedidos analizados en un script SQL ejecutable (str)."""
    if dialecto not in DIALECTOS:
        raise ValueError("Dialecto no soportado: %s" % dialecto)
    L = lambda v: _lit(v, dialecto)  # noqa: E731
    aceptados, rechazados = clasificar(resultados)
    ahora = ahora or datetime.now()
    inicio = {"sqlite": "BEGIN TRANSACTION;", "postgresql": "BEGIN;",
              "mysql": "START TRANSACTION;"}[dialecto]

    o = ["-- ============================================================",
         "-- Script generado por el transpilador de pedidos (Etapa 3)",
         "-- Dialecto : %s" % DIALECTOS[dialecto],
         "-- Generado : %s" % ahora.strftime("%Y-%m-%d %H:%M:%S"),
         "-- Pedidos  : %d aceptados, %d rechazados" % (len(aceptados), len(rechazados)),
         "-- Uso      : ejecutar sobre una base de datos nueva (las claves",
         "--            primarias impiden insertar dos veces el mismo lote).",
         "-- ============================================================", ""]
    if dialecto == "sqlite":
        o += ["PRAGMA foreign_keys = ON;", ""]
    o += ["-- 1. Esquema", _ddl(), "", "-- 2. Datos", inicio, ""]

    o.append("-- Catálogos")
    for cod, nom in CATEGORIAS:
        o.append("INSERT INTO categoria_item (codigo, nombre) VALUES (%s, %s);" % (L(cod), L(nom)))
    for cod, nom in CANALES.values():
        o.append("INSERT INTO canal (codigo, nombre) VALUES (%s, %s);" % (L(cod), L(nom)))

    o += ["", "-- Pedidos aceptados (%d)" % len(aceptados)]
    for p in aceptados:
        ub = p["ubicacion"]
        canal = CANALES[ub[0]][0]
        mesa = int(ub[1:]) if ub[0] == "M" else None
        o.append("-- %s" % p["entrada"].replace("\n", " "))
        o.append("INSERT INTO pedido (correlativo, canal, ubicacion, mesa) VALUES (%s, %s, %s, %s);"
                 % (L(p["correlativo"]), L(canal), L(ub), L(mesa)))
        for n, it in enumerate(p["items"], 1):
            o.append("INSERT INTO pedido_item (correlativo, linea, codigo, categoria, numero) "
                     "VALUES (%s, %d, %s, %s, %d);"
                     % (L(p["correlativo"]), n, L(it), L(it[0]), int(it[1:])))

    o += ["", "-- Pedidos rechazados (%d): auditoría de errores" % len(rechazados)]
    for n, r in enumerate(rechazados, 1):
        o.append("INSERT INTO pedido_rechazado (id, entrada, motivo, posicion) VALUES (%d, %s, %s, %s);"
                 % (n, L(r["entrada"]), L(r["motivo"]), L(r["pos"])))

    o += ["", "COMMIT;", "",
          "-- 3. Consultas de ejemplo",
          "-- SELECT p.correlativo, c.nombre AS canal, p.mesa, COUNT(i.linea) AS items",
          "--   FROM pedido p JOIN canal c ON c.codigo = p.canal",
          "--   LEFT JOIN pedido_item i ON i.correlativo = p.correlativo",
          "--  GROUP BY p.correlativo, c.nombre, p.mesa;",
          "-- SELECT * FROM pedido_rechazado;", ""]
    return "\n".join(o)


# --------------------------------------------------------------- reporte PDF
def _t(s):
    """Texto compatible con las fuentes base del PDF (Latin-1/cp1252)."""
    return str(s).encode("cp1252", "replace").decode("cp1252")


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(18 * mm, 10 * mm, "Analizador de pedidos - Teoría de Computación (USIL)")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, "Página %d" % doc.page)
    canvas.restoreState()


def generar_pdf(resultados, dialecto="sqlite", ahora=None):
    """Devuelve los bytes de un PDF con resumen, resultados y script SQL."""
    ahora = ahora or datetime.now()
    aceptados, rechazados = clasificar(resultados)
    sql = transpilar(resultados, dialecto, ahora)

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Title"], fontSize=18, textColor=colors.HexColor("#1f4e9c"))
    h2 = ParagraphStyle("h2", parent=base["Heading2"], fontSize=13, textColor=colors.HexColor("#1f4e9c"),
                        spaceBefore=14)
    txt = ParagraphStyle("txt", parent=base["BodyText"], fontSize=9, leading=11)
    cel = ParagraphStyle("cel", parent=txt, fontSize=8, leading=10)
    cod = ParagraphStyle("cod", fontName="Courier", fontSize=7.5, leading=9,
                         backColor=colors.HexColor("#f4f6fa"), borderPadding=4)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title="Reporte de pedidos", author="Analizador de pedidos")
    S = [Paragraph("Reporte de pedidos", h1),
         Paragraph("Generado el %s &middot; Dialecto SQL: %s"
                   % (ahora.strftime("%d/%m/%Y %H:%M"), escape(_t(DIALECTOS[dialecto]))), txt),
         Paragraph("1. Resumen", h2)]

    resumen = Table([["Pedidos analizados", len(resultados)],
                     ["Aceptados (se insertan en pedido / pedido_item)", len(aceptados)],
                     ["Rechazados (se guardan en pedido_rechazado)", len(rechazados)]],
                    colWidths=[110 * mm, 30 * mm])
    resumen.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#d9dfea")),
                                 ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f9")),
                                 ("FONTSIZE", (0, 0), (-1, -1), 9),
                                 ("ALIGN", (1, 0), (1, -1), "CENTER")]))
    S += [resumen, Paragraph("2. Resultado por pedido", h2)]

    filas = [[Paragraph("<b>%s</b>" % h, cel) for h in ("#", "Entrada", "Estado", "Detalle")]]
    for n, r in enumerate(resultados, 1):
        if r["valido"]:
            p = r["pedido"]
            estado = '<font color="#1b8a4b"><b>Válido</b></font>'
            detalle = "%s &middot; ítems: %s" % (escape(_t(p["canal"])), escape(", ".join(p["items"])))
        else:
            estado = '<font color="#c0392b"><b>Rechazado</b></font>'
            detalle = escape(_t(r["mensaje"]))
        filas.append([Paragraph(str(n), cel), Paragraph(escape(_t(r["entrada"])), cel),
                      Paragraph(estado, cel), Paragraph(detalle, cel)])
    tabla = Table(filas, colWidths=[9 * mm, 52 * mm, 20 * mm, 93 * mm], repeatRows=1)
    tabla.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#d9dfea")),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f9")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    S += [tabla, Paragraph("3. Script SQL ejecutable", h2),
          Paragraph("Copiar y ejecutar sobre una base de datos nueva. También puede descargarse "
                    "como archivo .sql desde la aplicación.", txt), Spacer(1, 4)]

    lineas = []
    for linea in _t(sql).splitlines():
        lineas += textwrap.wrap(linea, 105, subsequent_indent="    ",
                                replace_whitespace=False, drop_whitespace=False) or [""]
    S.append(Preformatted("\n".join(lineas), cod))

    doc.build(S, onFirstPage=_pie, onLaterPages=_pie)
    return buf.getvalue()
