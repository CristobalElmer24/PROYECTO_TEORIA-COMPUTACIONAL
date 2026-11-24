# Analizador léxico y sintáctico de pedidos (Teoría de Computación – USIL)

Valida códigos de pedido con el formato `PED-NNN-UBICACIÓN-ÍTEM(+ÍTEM)*`
(mesa, para llevar y delivery) con expresiones regulares, AFND/AFD y análisis LR (SLR(1)).

## Etapa 1
Interfaz web (`templates/index.html`), servidor Flask (`app.py`), ingreso de pedidos
escritos o por archivo `.txt`, generación de tokens y lexemas.

## Etapa 2
Sección 7 de la interfaz y archivo `automatas.py`. Para cada lexema/token se genera con código:
1. ER (expresión regular)
2. AFND con transiciones ε (Thompson) — gráfico SVG dibujado por código, no es imagen
3. AFD (construcción de subconjuntos)
4. Tabla de transiciones
5. Transiciones δ
6. Quíntupla (Q, Σ, δ, q0, F)

Ruta de la API: `GET /api/automatas`.

## Etapa 3 – Exportación (transpilador a SQL y PDF)
Sección 8 de la interfaz y archivo `exportador.py`.
- **Transpilador**: los pedidos *válidos* se convierten en un script SQL ejecutable
  (esquema + `INSERT` en `pedido` y `pedido_item`); los *rechazados* se guardan en
  `pedido_rechazado` con el motivo del error. Un correlativo repetido en el lote se rechaza.
- Dialectos: SQLite, PostgreSQL y MySQL/MariaDB. Los valores se escapan para evitar inyección SQL.
- **PDF**: resumen, resultado por pedido y el script SQL completo.
- Significado de las letras de ítem (`C`, `B`, `S`) editable en `CATEGORIAS` de `exportador.py`.

Rutas: `POST /api/exportar/sql` (vista previa), `POST /descargar/sql`, `POST /descargar/pdf`
con JSON `{"texto": "...", "dialecto": "sqlite|postgresql|mysql"}`.

## Ejecutar
    pip install -r requirements.txt
    python app.py          # http://localhost:5000
    python -m unittest     # pruebas (AFND y AFD verificados contra re.fullmatch)

## Archivos
- `app.py` – rutas Flask (`/`, `/api/analizar`, `/api/archivo`, `/api/automatas`, `/api/exportar/sql`, `/descargar/sql`, `/descargar/pdf`)
- `analizador.py` – ER, AFD, AFND, gramática, tabla LR, analizador léxico y sintáctico
- `automatas.py` – Etapa 2: ER → AFND → AFD, tabla, transiciones, quíntupla y gráficos SVG
- `exportador.py` – Etapa 3: transpilador a SQL y reporte PDF
- `templates/index.html` – interfaz
- `test_analizador.py`, `test_automatas.py`, `test_exportador.py` – pruebas
