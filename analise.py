"""Regras do painel: slots livres, sugestões de upgrade, agrupamento por modelo e divergências."""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime

TAMANHOS_PADRAO_GB = [4, 8, 16, 32, 48, 64]


def normalizar_modelo(modelo: str) -> str:
    s = (modelo or "").strip().lower()
    s = re.sub(r"^dell\s+(inc\.?\s+)?", "", s)
    return re.sub(r"\s+", " ", s)


def normalizar_tag(tag: str) -> str:
    return re.sub(r"\s+", "", tag or "").upper()


def fmt_gb(gb) -> str:
    if gb is None:
        return "—"
    return f"{int(gb)}GB" if float(gb).is_integer() else f"{gb:.1f}GB"


def fmt_config(pentes_gb: list) -> str:
    return " + ".join(fmt_gb(g) for g in sorted(pentes_gb, reverse=True)) or "—"


# ---------------------------------------------------------------- especificações

def carregar_specs(caminho: str) -> dict:
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    return {normalizar_modelo(k): v for k, v in dados.items() if not k.startswith("_")}


def spec_do_modelo(modelo: str, specs: dict) -> dict | None:
    n = normalizar_modelo(modelo)
    if not n:
        return None
    if n in specs:
        return specs[n]
    for chave in sorted(specs, key=len, reverse=True):
        if chave in n:
            return specs[chave]
    return None


# ---------------------------------------------------------------- memória por máquina

def analisar_maquina(m, specs: dict) -> dict:
    spec = spec_do_modelo(m.modelo, specs) or {}
    instalados = [p.gb for p in m.pentes if p.gb > 0]
    slots = m.slots_total or spec.get("slots") or len(m.pentes)
    slots = max(slots, len(instalados))
    livres = slots - len(instalados)
    max_gb = spec.get("max_gb")
    max_slot = spec.get("max_por_slot_gb") or (max_gb // slots if max_gb and slots else None)
    return {
        "maquina": m,
        "spec": spec,
        "pentes_gb": instalados,
        "config": fmt_config(instalados),
        "total_gb": sum(instalados),
        "slots": slots,
        "livres": livres,
        "max_gb": max_gb,
        "max_slot": max_slot,
        "categoria": spec.get("categoria", ""),
        "tipo": spec.get("tipo") or next((p.tipo for p in m.pentes if p.tipo), ""),
        "upgrades": sugerir_upgrades(instalados, slots, livres, max_gb, max_slot),
    }


def sugerir_upgrades(instalados, slots, livres, max_gb, max_slot) -> list[dict]:
    """Lista de opções {acao, pentes, total_final, obs}. Vazia se já está no máximo ou sem spec."""
    if not max_gb or not slots or not max_slot:
        return []
    total = sum(instalados)
    if total >= max_gb:
        return []
    maior = max(instalados) if instalados else 0
    opcoes = []

    if livres:
        cabem = [t for t in TAMANHOS_PADRAO_GB if t <= max_slot and total + t <= max_gb]
        candidatos = []
        if maior in cabem:
            candidatos.append(maior)
        if cabem and cabem[-1] not in candidatos:
            candidatos.append(cabem[-1])
        for t in candidatos:
            obs = "mesmo tamanho do atual, dual channel" if t == maior else ""
            opcoes.append({"acao": "Adicionar", "pentes": f"1x {t}GB", "total_final": total + t, "obs": obs})
            if livres > 1 and total + t * livres <= max_gb:
                opcoes.append({"acao": "Adicionar", "pentes": f"{livres}x {t}GB",
                               "total_final": total + t * livres, "obs": obs})

    for t in TAMANHOS_PADRAO_GB:
        if maior < t <= max_slot and total < t * slots <= max_gb:
            sobra = f"sobra(m) {fmt_config(instalados)}" if instalados else ""
            opcoes.append({"acao": "Substituir todos", "pentes": f"{slots}x {t}GB",
                           "total_final": t * slots, "obs": sobra})
    return opcoes


def fmt_upgrade(u: dict) -> str:
    txt = f"{u['acao']} {u['pentes']} → {fmt_gb(u['total_final'])}"
    return f"{txt} ({u['obs']})" if u["obs"] else txt


def fmt_qtd(pentes_gb: list) -> str:
    """[8, 8] -> '2x 8GB'; [16, 8] -> '1x 16GB + 1x 8GB'."""
    c = Counter(pentes_gb)
    return " + ".join(f"{n}x {fmt_gb(gb)}" for gb, n in sorted(c.items(), reverse=True)) or "sem pente"


def resumo_configuracoes(analises: list[dict]) -> list[dict]:
    """Quantas máquinas de cada modelo têm cada combinação de pentes (ex.: 16GB = 2x 8GB ou 1x 16GB)."""
    c = Counter((a["maquina"].modelo or "(sem modelo)", a["total_gb"], fmt_qtd(a["pentes_gb"]),
                 a["livres"]) for a in analises)
    linhas = [{"modelo": m, "total_gb": t, "config": cfg, "livres": l, "qtd": n}
              for (m, t, cfg, l), n in c.items()]
    return sorted(linhas, key=lambda x: (x["modelo"], -x["total_gb"], -x["qtd"]))


# ---------------------------------------------------------------- por modelo

def agrupar_por_modelo(analises: list[dict]) -> list[dict]:
    grupos = defaultdict(list)
    for a in analises:
        grupos[a["maquina"].modelo or "(sem modelo)"].append(a)

    resultado = []
    for modelo, itens in sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        resultado.append({
            "modelo": modelo,
            "qtd": len(itens),
            "configs": Counter(a["config"] for a in itens).most_common(),
            "media_gb": sum(a["total_gb"] for a in itens) / len(itens),
            "com_slot_livre": sum(1 for a in itens if a["livres"] > 0),
            "com_upgrade": sum(1 for a in itens if a["upgrades"]),
            "spec": itens[0]["spec"],
            "maquinas": sorted(itens, key=lambda a: a["maquina"].nome),
        })
    return resultado


# ---------------------------------------------------------------- compras

def contar_pentes(analises: list[dict]) -> dict:
    """Pentes instalados: totais por (tipo, GB) e grade modelo x GB."""
    por_tipo = Counter()
    por_modelo = defaultdict(Counter)
    for a in analises:
        for gb in a["pentes_gb"]:
            por_tipo[(a["tipo"] or "tipo desconhecido", gb)] += 1
            por_modelo[a["maquina"].modelo or "(sem modelo)"][gb] += 1
    tamanhos = sorted({gb for c in por_modelo.values() for gb in c})
    return {
        "por_tipo": sorted(por_tipo.items()),
        "tamanhos": tamanhos,
        "por_modelo": sorted(por_modelo.items()),
        "total": sum(por_tipo.values()),
    }


def _tamanho_padrao(gb, max_slot) -> int | None:
    if gb and float(gb).is_integer() and int(gb) in TAMANHOS_PADRAO_GB and gb <= max_slot:
        return int(gb)
    return None


def _plano_maquina(a: dict, meta_gb: int) -> dict | None:
    total = a["total_gb"]
    base = {"analise": a, "comprar": [], "liberados": [], "obs": "", "alvo": meta_gb}
    if not a["spec"]:
        return None if total >= meta_gb else {**base, "obs": "Modelo sem especificação em modelos.json"}

    alvo = min(meta_gb, a["max_gb"])
    if a["max_gb"] < meta_gb:
        base["obs"] = f"Máximo do modelo é {fmt_gb(a['max_gb'])}"
    base["alvo"] = alvo
    if total >= alvo:
        return None

    # 1º tenta só completar os slots livres (não sobra pente)
    falta = alvo - total
    for n in range(1, a["livres"] + 1):
        t = _tamanho_padrao(falta / n, a["max_slot"])
        if t:
            return {**base, "comprar": [t] * n}
    # 2º troca todos os pentes; os antigos ficam livres para reaproveitar
    t = _tamanho_padrao(alvo / a["slots"], a["max_slot"])
    if t:
        return {**base, "comprar": [t] * a["slots"], "liberados": list(a["pentes_gb"])}
    return {**base, "obs": (base["obs"] + "; " if base["obs"] else "") + "Sem combinação padrão, avaliar manualmente"}


def plano_compra(analises: list[dict], meta_gb: int) -> dict:
    maquinas = [p for p in (_plano_maquina(a, meta_gb) for a in analises) if p]
    resumo = defaultdict(lambda: {"necessarios": 0, "liberados": 0})
    for p in maquinas:
        tipo = p["analise"]["tipo"] or "tipo desconhecido"
        for gb in p["comprar"]:
            resumo[(tipo, gb)]["necessarios"] += 1
        for gb in p["liberados"]:
            resumo[(tipo, gb)]["liberados"] += 1
    linhas = []
    for (tipo, gb), v in sorted(resumo.items()):
        linhas.append({"tipo": tipo, "gb": gb, **v,
                       "comprar": max(0, v["necessarios"] - v["liberados"]),
                       "sobram": max(0, v["liberados"] - v["necessarios"])})
    return {
        "maquinas": sorted(maquinas, key=lambda p: (p["analise"]["maquina"].modelo, p["analise"]["maquina"].nome)),
        "resumo": linhas,
        "total_comprar": sum(l["comprar"] for l in linhas),
        "sem_plano": sum(1 for p in maquinas if not p["comprar"]),
    }


# ---------------------------------------------------------------- divergências OCS x estoque

def divergencias(analises: list[dict], itens_estoque: list[dict], dias_contato: int) -> list[dict]:
    alertas = []

    def alerta(gravidade, tipo, tag, maquina, detalhe):
        alertas.append({"gravidade": gravidade, "tipo": tipo, "service_tag": tag,
                        "maquina": maquina, "detalhe": detalhe})

    ocs_por_tag = defaultdict(list)
    for a in analises:
        m = a["maquina"]
        tag = normalizar_tag(m.service_tag)
        if tag:
            ocs_por_tag[tag].append(m)
        else:
            alerta("média", "Sem service tag no OCS", "", m.nome,
                   "O OCS não reportou o SSN da BIOS; não dá para cruzar com o estoque.")

    for tag, ms in ocs_por_tag.items():
        if len(ms) > 1:
            alerta("média", "Service tag duplicada no OCS", tag, ", ".join(m.nome for m in ms),
                   "Mais de uma máquina no OCS com a mesma service tag (renomeada ou reinstalada?).")

    agora = datetime.now()
    tags_estoque = set()
    for item in itens_estoque:
        tag = normalizar_tag(item["service_tag"])
        tags_estoque.add(tag)
        ms = ocs_por_tag.get(tag)
        if not ms:
            if item["situacao"] == "Em uso":
                alerta("alta", "Em uso, mas ausente do OCS", tag, "",
                       f"Cadastrada como 'Em uso' em {item['local']}, mas não aparece no OCS (agente não instalado?).")
            continue
        m = max(ms, key=lambda x: x.ultimo_inventario or datetime.min)
        mod_est, mod_ocs = normalizar_modelo(item["modelo"]), normalizar_modelo(m.modelo)
        if mod_est and mod_ocs and mod_est not in mod_ocs and mod_ocs not in mod_est:
            alerta("alta", "Modelo divergente", tag, m.nome,
                   f"Estoque diz '{item['modelo']}', OCS diz '{m.modelo}'.")
        if item["situacao"] in ("Em estoque", "Baixado") and m.ultimo_inventario:
            dias = (agora - m.ultimo_inventario).days
            if dias <= dias_contato:
                alerta("alta", "Situação divergente", tag, m.nome,
                       f"Cadastrada como '{item['situacao']}', mas comunicou com o OCS há {dias} dia(s).")

    for tag, ms in ocs_por_tag.items():
        if tag not in tags_estoque:
            m = ms[0]
            alerta("média", "Não cadastrada no estoque", tag, m.nome,
                   f"Está no OCS ({m.modelo or 'modelo desconhecido'}) mas não no cadastro de estoque.")

    ordem = {"alta": 0, "média": 1, "baixa": 2}
    return sorted(alertas, key=lambda a: (ordem[a["gravidade"]], a["tipo"], a["service_tag"]))
