"""Configuração do painel. Tudo vem de variáveis de ambiente (ou do arquivo .env)."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

# De onde vêm os dados das máquinas: "exemplo", "csv" ou "mysql"
FONTE = os.environ.get("PAINEL_FONTE", "exemplo").strip().lower()

CSV_MEMORIAS = os.environ.get("PAINEL_CSV", r"C:\temp\memorias.csv")

MYSQL = {
    "host": os.environ.get("OCS_DB_HOST", "ocs.empresa.local"),
    "port": int(os.environ.get("OCS_DB_PORT", "3306")),
    "user": os.environ.get("OCS_DB_USER", "painel_leitura"),
    "password": os.environ.get("OCS_DB_PASS", ""),
    "database": os.environ.get("OCS_DB_NAME", "ocsweb"),
}

# Os dados de exemplo usam um banco separado para não sujar o cadastro real
SQLITE_PATH = os.environ.get(
    "PAINEL_SQLITE",
    os.path.join(BASE_DIR, "estoque_exemplo.db" if FONTE == "exemplo" else "estoque.db"),
)

MODELOS_JSON = os.path.join(BASE_DIR, "modelos.json")

# Máquina marcada como "Em estoque"/"Baixado" que conversou com o OCS há menos que isso gera alerta
DIAS_CONTATO_RECENTE = int(os.environ.get("PAINEL_DIAS_CONTATO", "30"))

SECRET_KEY = os.environ.get("PAINEL_SECRET_KEY") or os.urandom(32).hex()
HOST = os.environ.get("PAINEL_HOST", "127.0.0.1")
PORT = int(os.environ.get("PAINEL_PORT", "5000"))
