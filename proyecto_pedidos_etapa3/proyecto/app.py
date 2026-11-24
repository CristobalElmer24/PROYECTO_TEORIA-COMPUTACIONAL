from flask import Flask, render_template, request, jsonify, Response
import analizador as A
import automatas as AU
import exportador as E

app = Flask(__name__)


def arbol_json(n):
    return {"etq": n.etq, "lexema": n.lexema,
            "hijos": [arbol_json(h) for h in n.hijos]}


def a_json(r):
    return {"entrada": r["entrada"], "valido": r["valido"],
            "mensaje": r["mensaje"], "pos": r["pos"], "pedido": r["pedido"],
            "tokens": [{"token": t, "lexema": l, "pos": p} for t, l, p in r["tokens"]],
            "traza": [{"pila": p, "entrada": e, "accion": a} for p, e, a in r["traza"]],
            "arbol": arbol_json(r["arbol"]) if r["arbol"] else None}


def analizar_texto(texto):
    """Analiza un pedido por línea (ignora líneas vacías)."""
    return [A.analizar(l) for l in str(texto).splitlines() if l.strip()]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analizar", methods=["POST"])
def analizar():
    datos = request.get_json(silent=True) or {}
    return jsonify([a_json(r) for r in analizar_texto(datos.get("texto", ""))])


@app.route("/api/automatas")
def automatas():
    """Etapa 2: ER, AFND, AFD, tabla, transiciones y quíntupla de cada token."""
    return jsonify(AU.datos())


@app.route("/api/archivo", methods=["POST"])
def archivo():
    f = request.files.get("archivo")
    if not f:
        return jsonify({"error": "No se recibió archivo"}), 400
    texto = f.read().decode("utf-8", errors="ignore")
    return jsonify([a_json(r) for r in analizar_texto(texto)])


# ------------------------------------------------ Etapa 3: exportación
def _para_exportar():
    """Lee texto y dialecto del JSON. Devuelve (resultados, dialecto, error)."""
    datos = request.get_json(silent=True) or {}
    dialecto = datos.get("dialecto", "sqlite")
    if dialecto not in E.DIALECTOS:
        return None, None, (jsonify({"error": "Dialecto no soportado: %s" % dialecto}), 400)
    resultados = analizar_texto(datos.get("texto", ""))
    if not resultados:
        return None, None, (jsonify({"error": "No hay pedidos para exportar"}), 400)
    return resultados, dialecto, None


@app.route("/api/exportar/sql", methods=["POST"])
def vista_sql():
    """Vista previa del script SQL (JSON)."""
    res, dial, err = _para_exportar()
    if err:
        return err
    return jsonify({"sql": E.transpilar(res, dial)})


@app.route("/descargar/sql", methods=["POST"])
def descargar_sql():
    res, dial, err = _para_exportar()
    if err:
        return err
    return Response(E.transpilar(res, dial), mimetype="application/sql; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="pedidos_%s.sql"' % dial})


@app.route("/descargar/pdf", methods=["POST"])
def descargar_pdf():
    res, dial, err = _para_exportar()
    if err:
        return err
    return Response(E.generar_pdf(res, dial), mimetype="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="reporte_pedidos.pdf"'})


if __name__ == "__main__":
    app.run(debug=True)
