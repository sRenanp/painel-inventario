"""Leitura das máquinas e pentes de memória: dados de exemplo, CSV do PowerShell ou MySQL do OCS."""
import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import config


class OCSIndisponivel(Exception):
    pass


@dataclass
class Pente:
    slot: str
    gb: float  # 0 = slot vazio
    tipo: str = ""
    velocidade: str = ""


@dataclass
class Maquina:
    nome: str
    modelo: str = ""
    fabricante: str = ""
    service_tag: str = ""
    usuario: str = ""
    ultimo_inventario: datetime | None = None
    pentes: list[Pente] = field(default_factory=list)
    slots_total: int | None = None  # None = usar o número de slots do modelos.json


def carregar_maquinas() -> list[Maquina]:
    if config.FONTE == "mysql":
        return _do_mysql()
    if config.FONTE == "csv":
        return _do_csv(config.CSV_MEMORIAS)
    return _exemplo()


# ---------------------------------------------------------------- exemplo

def _exemplo() -> list[Maquina]:
    agora = datetime.now()

    def m(nome, modelo, tag, usuario, dias, pentes_gb):
        pentes = [
            Pente(slot=f"DIMM {chr(65 + i)}", gb=gb, tipo="DDR4" if gb else "", velocidade="3200" if gb else "")
            for i, gb in enumerate(pentes_gb)
        ]
        return Maquina(nome=nome, modelo=modelo, fabricante="Dell Inc.", service_tag=tag, usuario=usuario,
                       ultimo_inventario=agora - timedelta(days=dias), pentes=pentes, slots_total=len(pentes))

    return [
        m("NB-RJ-001", "Latitude 3540", "ABC1234", "usuario01", 1, [8, 0]),
        m("NB-RJ-002", "Latitude 3540", "ABC1235", "usuario02", 2, [8, 8]),
        m("NB-RJ-003", "Latitude 3540", "ABC1236", "usuario03", 0, [16, 0]),
        m("NB-SP-001", "Latitude 3540", "DEF2001", "usuario04", 3, [8, 0]),
        m("NB-SP-002", "Latitude 3420", "DEF2002", "usuario05", 1, [8, 0]),
        m("NB-SP-003", "Latitude 3420", "DEF2003", "", 4, [4, 4]),
        m("NB-RJ-004", "Latitude 3420", "ABC1240", "usuario06", 45, [8, 8]),
        m("NB-RJ-005", "Latitude 5420", "ABC1241", "usuario07", 1, [16, 0]),
        m("DT-SP-001", "OptiPlex 3080", "DEF2004", "recepcao", 0, [8, 0]),
        m("NB-SP-004", "Latitude 3540", "DEF2005", "usuario08", 2, [32, 32]),
        m("NB-RJ-006", "Latitude 3420", "", "usuario09", 6, [8, 0]),
        m("NB-RJ-007", "Latitude 3540", "ABC1242", "usuario10", 1, [16, 16]),
    ]


# ---------------------------------------------------------------- MySQL do OCS

SQL_MAQUINAS = """
    SELECT h.ID, h.NAME, h.USERID, h.LASTDATE, b.SMANUFACTURER, b.SMODEL, b.SSN
    FROM hardware h
    LEFT JOIN bios b ON b.HARDWARE_ID = h.ID
"""

SQL_PENTES = """
    SELECT HARDWARE_ID, CAPTION, DESCRIPTION, CAPACITY, TYPE, SPEED, NUMSLOTS
    FROM memories
    ORDER BY HARDWARE_ID, ID
"""


def _do_mysql() -> list[Maquina]:
    try:
        import pymysql
        import pymysql.cursors
    except ImportError as e:
        raise OCSIndisponivel("O pacote pymysql não está instalado (pip install -r requirements.txt).") from e

    try:
        conn = pymysql.connect(**config.MYSQL, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                               connect_timeout=5, read_timeout=60)
    except pymysql.MySQLError as e:
        raise OCSIndisponivel(f"Não foi possível conectar ao MySQL do OCS em {config.MYSQL['host']}: {e}") from e

    try:
        with conn.cursor() as cur:
            cur.execute(SQL_MAQUINAS)
            linhas_maquinas = cur.fetchall()
            cur.execute(SQL_PENTES)
            linhas_pentes = cur.fetchall()
    except pymysql.MySQLError as e:
        raise OCSIndisponivel(f"Erro ao consultar o banco do OCS: {e}") from e
    finally:
        conn.close()

    pentes_por_id: dict[int, list[Pente]] = {}
    for r in linhas_pentes:
        mb = _numero(r["CAPACITY"])
        pentes_por_id.setdefault(r["HARDWARE_ID"], []).append(Pente(
            slot=(r["CAPTION"] or r["DESCRIPTION"] or "").strip(),
            gb=round(mb / 1024, 1) if mb else 0,
            tipo=(r["TYPE"] or "").strip(),
            velocidade=str(r["SPEED"] or "").strip(),
        ))

    maquinas = []
    for r in linhas_maquinas:
        pentes = pentes_por_id.get(r["ID"], [])
        # Se o agente reportou slots vazios (capacidade 0), a lista já representa todos os slots.
        # Senão, o total de slots vem do modelos.json.
        reporta_vazios = any(p.gb == 0 for p in pentes)
        maquinas.append(Maquina(
            nome=r["NAME"] or "",
            modelo=(r["SMODEL"] or "").strip(),
            fabricante=(r["SMANUFACTURER"] or "").strip(),
            service_tag=(r["SSN"] or "").strip(),
            usuario=r["USERID"] or "",
            ultimo_inventario=r["LASTDATE"] if isinstance(r["LASTDATE"], datetime) else None,
            pentes=pentes,
            slots_total=len(pentes) if reporta_vazios else None,
        ))
    return maquinas


# ---------------------------------------------------------------- CSV do PowerShell

# Nomes de coluna aceitos (comparação sem acento, sem espaço e em minúsculas)
COLUNAS = {
    "nome": ["computername", "pscomputername", "computador", "maquina", "hostname", "nome", "name"],
    "slot": ["devicelocator", "banklabel", "slot", "banco"],
    "gb": ["capacidadegb", "capacitygb", "tamanhogb", "gb", "capacidade", "capacity"],
    "tipo": ["smbiosmemorytype", "memorytype", "tipo", "type"],
    "velocidade": ["configuredclockspeed", "speed", "velocidade"],
    "modelo": ["modelo", "model"],
    "service_tag": ["servicetag", "service_tag", "ssn", "tag"],
}

TIPOS_SMBIOS = {"20": "DDR", "21": "DDR2", "24": "DDR3", "26": "DDR4", "34": "DDR5", "35": "LPDDR5"}


def _do_csv(caminho: str) -> list[Maquina]:
    try:
        texto = _ler_texto(caminho)
    except FileNotFoundError as e:
        raise OCSIndisponivel(f"Arquivo CSV não encontrado: {caminho}") from e

    linhas = [l for l in texto.splitlines() if l.strip() and not l.startswith("#TYPE")]
    if not linhas:
        raise OCSIndisponivel(f"O CSV {caminho} está vazio.")
    delimitador = ";" if linhas[0].count(";") > linhas[0].count(",") else ","
    leitor = csv.DictReader(linhas, delimiter=delimitador)

    mapa = {}
    normalizadas = {_chave(c): c for c in (leitor.fieldnames or [])}
    for campo, aliases in COLUNAS.items():
        mapa[campo] = next((normalizadas[a] for a in aliases if a in normalizadas), None)
    if not mapa["nome"] or not mapa["gb"]:
        raise OCSIndisponivel(
            f"Não reconheci as colunas do CSV. Encontrei: {', '.join(leitor.fieldnames or [])}. "
            "Preciso ao menos de uma coluna com o nome da máquina e outra com a capacidade.")
    coluna_em_gb = "gb" in _chave(mapa["gb"])

    maquinas: dict[str, Maquina] = {}
    for r in leitor:
        nome = (r.get(mapa["nome"]) or "").strip()
        if not nome:
            continue
        m = maquinas.setdefault(nome.upper(), Maquina(nome=nome))
        if mapa["modelo"] and not m.modelo:
            m.modelo = (r.get(mapa["modelo"]) or "").strip()
        if mapa["service_tag"] and not m.service_tag:
            m.service_tag = (r.get(mapa["service_tag"]) or "").strip()
        tipo = (r.get(mapa["tipo"]) or "").strip() if mapa["tipo"] else ""
        m.pentes.append(Pente(
            slot=(r.get(mapa["slot"]) or "").strip() if mapa["slot"] else f"Pente {len(m.pentes) + 1}",
            gb=_para_gb(r.get(mapa["gb"]), coluna_em_gb),
            tipo=TIPOS_SMBIOS.get(tipo, tipo),
            velocidade=(r.get(mapa["velocidade"]) or "").strip() if mapa["velocidade"] else "",
        ))
    return list(maquinas.values())


def _ler_texto(caminho: str) -> str:
    with open(caminho, "rb") as f:
        bruto = f.read()
    for codificacao in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            texto = bruto.decode(codificacao)
            if "\x00" not in texto:
                return texto
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1")


def _chave(nome: str) -> str:
    import unicodedata
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9_]", "", sem_acento.lower())


def _numero(valor) -> float:
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _para_gb(valor, coluna_em_gb: bool) -> float:
    n = _numero(valor)
    if coluna_em_gb or n <= 256:
        gb = n
    elif n > 1_000_000:  # bytes (Win32_PhysicalMemory.Capacity)
        gb = n / 1024 ** 3
    else:  # MB
        gb = n / 1024
    return round(gb, 1)
