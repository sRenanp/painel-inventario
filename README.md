# Painel de Inventário

Painel em Flask para inventário de memória RAM, lendo dados do [OCS Inventory](https://ocsinventory-ng.org/).

> **Projeto de teste.** Todas as máquinas, service tags, usuários e hosts do repositório são fictícios.

Funcionalidades:

- **Memória por máquina**: pentes, GB por pente, slots livres e upgrades possíveis.
- **Por modelo**: quantas máquinas de cada modelo têm cada combinação de pentes (ex.: 16GB = 2x 8GB ou 1x 16GB).
- **Compras**: quantos pentes comprar para levar as máquinas a uma meta de memória.
- **Estoque**: cadastro próprio em SQLite (service tag, modelo, situação, local RJ/SP).
- **Divergências**: cruzamento estoque x OCS pela service tag.
- **Exportar Excel**: uma aba para cada visão.

## Rodar no PC

```powershell
cd painel-inventario
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.exemplo .env      # ajuste PAINEL_FONTE etc.
.\.venv\Scripts\python app.py
```

Depois abra http://127.0.0.1:5000

## Fontes de dados (`PAINEL_FONTE` no .env)

| Valor     | O que usa                                                               |
|-----------|-------------------------------------------------------------------------|
| `exemplo` | Máquinas fictícias + estoque fictício em `estoque_exemplo.db`           |
| `csv`     | `PAINEL_CSV` (padrão `C:\temp\memorias.csv`), gerado pelo PowerShell. Para testar: `PAINEL_CSV=exemplos\memorias_exemplo.csv` |
| `mysql`   | Banco `ocsweb` do OCS (tabelas `hardware`, `bios`, `memories`)          |

No modo `csv` e no `mysql`, o estoque fica em `estoque.db`, separado do banco de exemplo.

### CSV
As colunas são reconhecidas pelo nome. Ele aceita, por exemplo, a saída de
`Get-CimInstance Win32_PhysicalMemory | Select PSComputerName, DeviceLocator, Capacity, Speed, SMBIOSMemoryType | Export-Csv`.
A capacidade pode vir em bytes, MB ou GB. O separador pode ser `,` ou `;`.
Para cruzar com o estoque, inclua também as colunas `Modelo` e `ServiceTag`.

### MySQL do OCS
Crie um usuário **somente leitura**:

```sql
CREATE USER 'painel_leitura'@'%' IDENTIFIED BY '...';
GRANT SELECT ON ocsweb.hardware TO 'painel_leitura'@'%';
GRANT SELECT ON ocsweb.bios     TO 'painel_leitura'@'%';
GRANT SELECT ON ocsweb.memories TO 'painel_leitura'@'%';
```

Quando o painel estiver no próprio servidor do OCS, use `'painel_leitura'@'localhost'` e `OCS_DB_HOST=localhost`.
Assim a porta 3306 não precisa ficar aberta na rede.

Na primeira carga real, confira se o agente reporta os slots vazios (linhas com `CAPACITY` 0/"No").
Se reportar, o total de slots vem do OCS. Se não, vem do `modelos.json`.

## modelos.json
Tem o número de slots, o máximo suportado e o tipo de memória de cada modelo. É a base das sugestões de upgrade.
**Os valores atuais (`"conferido": false`) são estimativas.** Confirme cada um no manual/spec sheet da Dell
e troque para `true` (o aviso ⚠ some do painel). Modelo sem entrada aparece como "sem especificação".

## Mover para o servidor do OCS
1. Copie a pasta (sem `.venv` e sem `*.db`, a não ser que queira levar o estoque, que fica em `estoque.db`).
2. Crie o venv, instale os requirements e ajuste o `.env` (`PAINEL_FONTE=mysql`, `PAINEL_SECRET_KEY` fixo).
3. Para servir na rede, use um servidor WSGI (ex.: `pip install waitress` e
   `waitress-serve --listen=0.0.0.0:5000 app:app`) ou gunicorn atrás do Apache que já serve o OCS.
   O painel **não tem login**. Exponha só na rede interna ou proteja com autenticação no Apache.
