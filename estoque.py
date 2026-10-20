"""Cadastro próprio de estoque em SQLite."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

SITUACOES = ["Em uso", "Em estoque", "Em manutenção", "Emprestado", "Baixado"]
LOCAIS = ["RJ", "SP"]

_caminho = None


@contextmanager
def _conexao():
    conn = sqlite3.connect(_caminho)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def inicializar(caminho: str, popular_exemplo: bool = False):
    global _caminho
    _caminho = caminho
    with _conexao() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS equipamentos (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                service_tag   TEXT NOT NULL UNIQUE COLLATE NOCASE,
                modelo        TEXT NOT NULL DEFAULT '',
                situacao      TEXT NOT NULL,
                local         TEXT NOT NULL,
                observacao    TEXT NOT NULL DEFAULT '',
                atualizado_em TEXT NOT NULL
            )""")
        vazio = c.execute("SELECT COUNT(*) FROM equipamentos").fetchone()[0] == 0
    if popular_exemplo and vazio:
        for tag, modelo, situacao, local in [
            ("ABC1234", "Latitude 3540", "Em uso", "RJ"),
            ("ABC1235", "Latitude 3540", "Em uso", "RJ"),
            ("ABC1236", "Latitude 3540", "Em uso", "RJ"),
            ("DEF2001", "Latitude 3540", "Em uso", "SP"),
            ("DEF2002", "Latitude 3540", "Em uso", "SP"),
            ("DEF2003", "Latitude 3420", "Em estoque", "SP"),
            ("ABC1240", "Latitude 3420", "Em uso", "RJ"),
            ("ABC1241", "Latitude 5420", "Em uso", "RJ"),
            ("DEF2005", "Latitude 3540", "Em uso", "SP"),
            ("ABC1242", "Latitude 3540", "Em manutenção", "RJ"),
            ("XYZ9999", "Latitude 3420", "Em uso", "SP"),
            ("GHI3001", "Latitude 3540", "Em estoque", "RJ"),
        ]:
            salvar({"service_tag": tag, "modelo": modelo, "situacao": situacao, "local": local})


def listar() -> list[dict]:
    with _conexao() as c:
        return [dict(r) for r in c.execute("SELECT * FROM equipamentos ORDER BY local, modelo, service_tag")]


def obter(id_: int) -> dict | None:
    with _conexao() as c:
        r = c.execute("SELECT * FROM equipamentos WHERE id = ?", (id_,)).fetchone()
        return dict(r) if r else None


def salvar(dados: dict, id_: int | None = None):
    tag = (dados.get("service_tag") or "").strip().upper()
    modelo = (dados.get("modelo") or "").strip()
    situacao = dados.get("situacao")
    local = dados.get("local")
    obs = (dados.get("observacao") or "").strip()
    if not tag:
        raise ValueError("Informe a service tag.")
    if situacao not in SITUACOES:
        raise ValueError("Situação inválida.")
    if local not in LOCAIS:
        raise ValueError("Local inválido.")
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        with _conexao() as c:
            if id_ is None:
                c.execute("INSERT INTO equipamentos (service_tag, modelo, situacao, local, observacao, atualizado_em)"
                          " VALUES (?, ?, ?, ?, ?, ?)", (tag, modelo, situacao, local, obs, agora))
            else:
                c.execute("UPDATE equipamentos SET service_tag=?, modelo=?, situacao=?, local=?, observacao=?,"
                          " atualizado_em=? WHERE id=?", (tag, modelo, situacao, local, obs, agora, id_))
    except sqlite3.IntegrityError as e:
        raise ValueError(f"A service tag {tag} já está cadastrada.") from e


def excluir(id_: int):
    with _conexao() as c:
        c.execute("DELETE FROM equipamentos WHERE id = ?", (id_,))
