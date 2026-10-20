"""Painel de inventário (memória por máquina, modelos, estoque x OCS)."""
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, send_file, url_for

import analise
import config
import estoque
import exportar
from ocs import OCSIndisponivel, carregar_maquinas

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY
estoque.inicializar(config.SQLITE_PATH, popular_exemplo=config.FONTE == "exemplo")

app.jinja_env.filters["gb"] = analise.fmt_gb
app.jinja_env.filters["upgrade"] = analise.fmt_upgrade


@app.context_processor
def _globais():
    return {"fonte": config.FONTE}


@app.errorhandler(OCSIndisponivel)
def _ocs_indisponivel(e):
    return render_template("erro.html", mensagem=str(e)), 503


def _analises():
    specs = analise.carregar_specs(config.MODELOS_JSON)
    return sorted((analise.analisar_maquina(m, specs) for m in carregar_maquinas()),
                  key=lambda a: (a["maquina"].modelo, a["maquina"].nome))


@app.route("/")
def maquinas():
    analises = _analises()
    modelos = sorted({a["maquina"].modelo for a in analises})
    modelo = request.args.get("modelo", "")
    busca = request.args.get("q", "").strip().lower()
    filtro = request.args.get("filtro", "")
    if modelo:
        analises = [a for a in analises if a["maquina"].modelo == modelo]
    if busca:
        analises = [a for a in analises
                    if busca in f"{a['maquina'].nome} {a['maquina'].service_tag} {a['maquina'].usuario}".lower()]
    if filtro == "upgrade":
        analises = [a for a in analises if a["upgrades"]]
    elif filtro == "livre":
        analises = [a for a in analises if a["livres"] > 0]
    return render_template("maquinas.html", analises=analises, modelos=modelos, modelo=modelo,
                           busca=request.args.get("q", ""), filtro=filtro)


@app.route("/modelos")
def modelos():
    analises = _analises()
    return render_template("modelos.html", grupos=analise.agrupar_por_modelo(analises),
                           configs=analise.resumo_configuracoes(analises))


def _dados_compras():
    analises = _analises()
    meta = request.args.get("meta", 16, type=int)
    categoria = request.args.get("categoria", "notebook")
    modelo = request.args.get("modelo", "")
    if categoria:
        analises = [a for a in analises if a["categoria"] == categoria]
    if modelo:
        analises = [a for a in analises if a["maquina"].modelo == modelo]
    return analises, {"meta": meta, "categoria": categoria, "modelo": modelo}


@app.route("/compras")
def compras():
    analises, filtros = _dados_compras()
    modelos = sorted({a["maquina"].modelo for a in _analises()})
    return render_template("compras.html", pentes=analise.contar_pentes(analises),
                           plano=analise.plano_compra(analises, filtros["meta"]), modelos=modelos,
                           metas=[8, 16, 24, 32, 64], qtd_maquinas=len(analises), **filtros)


@app.route("/compras/exportar")
def compras_exportar():
    analises, filtros = _dados_compras()
    arquivo = exportar.gerar_compras(analise.contar_pentes(analises),
                                     analise.plano_compra(analises, filtros["meta"]), filtros["meta"])
    nome = f"compras_memoria_{filtros['meta']}GB_{datetime.now():%Y-%m-%d}.xlsx"
    return send_file(arquivo, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/estoque")
def estoque_lista():
    editar = estoque.obter(request.args.get("editar", type=int)) if request.args.get("editar") else None
    return render_template("estoque.html", itens=estoque.listar(), editar=editar,
                           situacoes=estoque.SITUACOES, locais=estoque.LOCAIS)


@app.post("/estoque/salvar")
def estoque_salvar():
    id_ = request.form.get("id", type=int)
    try:
        estoque.salvar(request.form, id_)
        flash("Equipamento salvo.", "ok")
    except ValueError as e:
        flash(str(e), "erro")
        if id_:
            return redirect(url_for("estoque_lista", editar=id_))
    return redirect(url_for("estoque_lista"))


@app.post("/estoque/<int:id_>/excluir")
def estoque_excluir(id_):
    estoque.excluir(id_)
    flash("Equipamento excluído.", "ok")
    return redirect(url_for("estoque_lista"))


@app.route("/divergencias")
def divergencias():
    alertas = analise.divergencias(_analises(), estoque.listar(), config.DIAS_CONTATO_RECENTE)
    return render_template("divergencias.html", alertas=alertas)


@app.route("/exportar")
def exportar_excel():
    analises = _analises()
    itens = estoque.listar()
    arquivo = exportar.gerar(analises, analise.agrupar_por_modelo(analises), itens,
                             analise.divergencias(analises, itens, config.DIAS_CONTATO_RECENTE))
    nome = f"inventario_{datetime.now():%Y-%m-%d_%H%M}.xlsx"
    return send_file(arquivo, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=False)
