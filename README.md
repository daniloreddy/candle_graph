# Candle Graph API

API REST ad alte prestazioni per la generazione di grafici di Analisi Tecnica (OHLCV) per criptovalute. Include una web dashboard NiceGUI per il monitoraggio delle richieste, protetta da autenticazione cookie JWT.

## Caratteristiche

- **FastAPI Core**: Endpoint asincroni e performanti.
- **Analisi Tecnica**: Calcolo automatico di Bande di Bollinger (20), RSI (14) e MACD (12/26/9).
- **Produzione Immagini in RAM**: Generazione di grafici PNG direttamente in memoria (zero scritture su disco).
- **Thread-Safe**: Utilizza l'API Object-Oriented di Matplotlib per gestire richieste concorrenti senza corruzione dei dati.
- **Gestione Carico**: Semaforo asincrono per limitare la saturazione della CPU (max 4 render concorrenti).
- **Sicurezza**: Validazione rigorosa degli input tramite Pydantic e protezione tramite **Bearer Token**.
- **Dashboard**: Interfaccia web NiceGUI su `/ui` con metriche e storico richieste, protetta da password.

## Avvio Rapido con Docker

> Requisito: **Docker** con il plugin Compose installato. Non serve clonare il progetto.

**1. Scarica solo il file Compose**

```bash
curl -O https://raw.githubusercontent.com/daniloreddy/candle_graph/main/docker-compose.yml
```

**2. Crea il file `.env`** nella stessa cartella:

```env
API_TOKENS=token_segreto_1,token_segreto_2

# Facoltativi
PORT=8000
HOST=0.0.0.0
DEV=false
AUTH_SECURE_COOKIE=1   # impostare a 1 se dietro proxy HTTPS (es. Cloudflare Tunnel)
RATE_LIMIT=20/minute   # limite per IP su /api/v1/chart
TRUSTED_PROXIES=127.0.0.1   # IP dei proxy fidati a cui viene concesso di impostare CF-Connecting-IP/X-Forwarded-For
```

**3. Avvia il container**

```bash
docker compose up -d
```

**4. Imposta la password della dashboard** (primo avvio)

```bash
docker compose exec candle-graph python scripts/set_password.py
```

L'API sarà disponibile su `http://localhost:8000`, la dashboard su `http://localhost:8000/ui`.

**Aggiornamento immagine**

```bash
docker compose pull && docker compose up -d
```

**Stop**

```bash
docker compose down
```

---

## Sviluppo Locale

> Solo per chi vuole modificare il codice sorgente.

**Requisiti**: Python 3.12+

```bash
git clone https://github.com/daniloreddy/candle_graph.git
cd candle_graph
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt -r requirements.dev.txt
```

**Imposta la password della dashboard (primo avvio)**

```bash
python scripts/set_password.py
```

**Esecuzione**:

```bash
scripts\run.bat --port 8000 --env-file .env      # Windows
scripts/run.sh  --port 8000 --env-file .env       # Linux/macOS
scripts\run.bat --dev                              # Windows con auto-reload
```

## Dashboard

La dashboard di monitoraggio è accessibile su `/ui`. Mostra:
- Metriche aggregate delle ultime 24h (richieste totali, OK, errori, timeout, durata media)
- Storico degli ultimi 50 record con status colorato

**Autenticazione**: Cookie JWT. Impostare la password con `python scripts/set_password.py` prima del primo avvio. Senza password configurata il server avvierà ma tutti i login falliranno.

**Configurazione** (`/ui/config`): intervallo di auto-refresh della dashboard (15 / 30 / 60 / 120s). Il valore è condiviso tra tutti gli utenti e si applica alla prossima apertura della Dashboard. Default: 30s.

## Autenticazione API

L'API è protetta tramite **Bearer Token**.

### Configurazione

File `.env`:

```env
API_TOKENS=token_segreto_1,token_segreto_2,test_token_secret
PORT=8000
HOST=0.0.0.0
DEV=false
AUTH_SECURE_COOKIE=1   # 1 se dietro HTTPS proxy
RATE_LIMIT=20/minute   # limite per IP su /api/v1/chart
TRUSTED_PROXIES=127.0.0.1   # IP dei proxy fidati per CF-Connecting-IP/X-Forwarded-For
```

### Utilizzo

Tutte le richieste devono includere l'header:

```
Authorization: Bearer <tuo_token>
```

## Utilizzo API

### Endpoint: `POST /api/v1/chart`

Genera un grafico PNG (o base64) partendo da una serie storica OHLCV.

#### Formato della Richiesta (JSON)

| Campo | Tipo | Obbligatorio | Descrizione |
| :--- | :--- | :---: | :--- |
| `symbol` | `string` | Sì | Identificativo della coin (es. "BTC/USDT"). Max 50 caratteri. |
| `data` | `array` | Sì | Lista di oggetti OHLCV (max 5000 elementi). |
| `bb_k` | `float` | No | Moltiplicatore dev. std. per Bollinger. Default: `2.0`. Range: `(0, 10]`. |
| `max_ohlcv_points` | `integer` | No | Numero di candele recenti da mostrare. Default: `180`. Range: `10–1000`. |
| `response_format` | `string` | No | `"png"` (default) o `"b64"` (immagine base64 in JSON). |

##### Struttura oggetto OHLCV in `data`:

| Campo | Tipo | Descrizione |
| :--- | :--- | :--- |
| `date` | `string` | Data in formato ISO8601 (es. "2024-05-08T10:00:00"). |
| `open` | `float` | Prezzo di apertura. |
| `high` | `float` | Prezzo massimo. |
| `low` | `float` | Prezzo minimo. |
| `close` | `float` | Prezzo di chiusura. |
| `volume` | `float` | Volume di scambio. |

**Esempio Payload:**

```json
{
  "symbol": "BTC/USDT",
  "bb_k": 2.0,
  "max_ohlcv_points": 180,
  "response_format": "png",
  "data": [
    {
      "date": "2024-05-08T10:00:00",
      "open": 62500.0,
      "high": 62800.0,
      "low": 62400.0,
      "close": 62700.0,
      "volume": 120.5
    }
  ]
}
```

#### Risposta

| Status | Descrizione |
| :--- | :--- |
| `200 OK` | PNG binario (`image/png`) oppure `{"image_b64": "..."}` se `response_format=b64` |
| `400 Bad Request` | Dati insufficienti (`< 26` punti OHLCV), parametri fuori range, o lista vuota |
| `401 Unauthorized` | Token mancante o non valido |
| `429 Too Many Requests` | Rate limit superato |
| `503 Service Unavailable` | Timeout generazione grafico (> 30s) |
| `500 Internal Server Error` | Errore imprevisto del server |

---

## Qualità del Codice

```bash
scripts\check.bat    # Windows: Ruff format, Ruff check, MyPy, pytest
scripts/check.sh     # Linux/macOS: same
```

## Test

```bash
scripts\test_api.bat "<token>" [port]    # Windows
scripts/test_api.sh  "<token>" [port]    # Linux/macOS
```

*(Assicurarsi che l'app sia avviata su un altro terminale con il token di test configurato)*
