# Candle Graph API

API REST ad alte prestazioni per la generazione di grafici di Analisi Tecnica (OHLCV) per criptovalute.

## Caratteristiche

- **FastAPI Core**: Endpoint asincroni e performanti.
- **Analisi Tecnica**: Calcolo automatico di Bande di Bollinger, RSI (14) e MACD.
- **Produzione Immagini in RAM**: Generazione di grafici PNG direttamente in memoria (zero scritture su disco).
- **Thread-Safe**: Utilizza l'API Object-Oriented di Matplotlib per gestire richieste concorrenti senza corruzione dei dati.
- **Gestione Carico**: Implementa un sistema di semafori asincroni per limitare la saturazione della CPU durante la generazione dei grafici.
- **Sicurezza**: Validazione rigorosa degli input tramite Pydantic e protezione tramite **Bearer Token**.

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
```

**3. Avvia il container**

```bash
docker compose up -d
```

L'API sarà disponibile su `http://localhost:8000`.

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

**Requisiti**: Python 3.9+

```bash
git clone https://github.com/daniloreddy/candle_graph.git
cd candle_graph
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows
pip install -r requirements.txt -r requirements.dev.txt
```

Esecuzione:
```bash
./scripts/run.sh --port 8000 --env-file .env      # Linux/macOS
scripts\run.bat --port 8000 --env-file .env        # Windows
```

## Autenticazione

L'API è protetta tramite **Bearer Token**.

### Configurazione
Crea un file `.env` (può essere ovunque nel sistema) per definire i token e i parametri del server:
```env
# Sicurezza
API_TOKENS=token_segreto_1,token_segreto_2,test_token_secret

# Server (facoltativi)
PORT=8000
HOST=0.0.0.0
DEV=false
```

### Utilizzo
Tutte le richieste devono includere l'header di autorizzazione:
`Authorization: Bearer <tuo_token>`

## Utilizzo API

### Endpoint: `POST /api/v1/chart`

Genera un grafico PNG partendo da una serie storica OHLCV.

#### Formato della Richiesta (JSON)

La richiesta deve essere un oggetto JSON con la seguente struttura:

| Campo | Tipo | Obbligatorio | Descrizione |
| :--- | :--- | :---: | :--- |
| `symbol` | `string` | Sì | Identificativo della coin (es. "BTC/USDT"). Max 50 caratteri. |
| `bb_k` | `float` | No | Moltiplicatore deviazione standard per Bollinger. Default: `2.0`. Deve essere `> 0`. |
| `max_ohlcv_points` | `integer` | No | Numero di candele recenti da mostrare. Default: `180`. Range: `10-1000`. |
| `data` | `array` | Sì | Lista di oggetti OHLCV (max 5000 elementi). |

##### Struttura oggetto OHLCV in `data`:

Ogni elemento dell'array `data` deve contenere:

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

- **Successo (200 OK)**: Contenuto binario dell'immagine PNG (`Content-Type: image/png`).
- **Errore Validazione (400 Bad Request)**: JSON con dettaglio dell'errore (es. dati insufficienti o parametri fuori range).
- **Errore Autenticazione (401 Unauthorized)**: Token mancante o non valido.
- **Errore Server (500 Internal Server Error)**: JSON generico per errori imprevisti.

## Qualità del Codice

Il progetto segue standard rigorosi di formattazione e tipizzazione:
- **Ruff**: Formattazione e Linting.
- **MyPy**: Type-checking statico.

Esegui i controlli con:
```bash
./check.sh
```

## Test

È incluso uno script per testare l'API con dati generati casualmente:
```bash
./venv/bin/python test_api_client.py
```
*(Assicurarsi che l'app sia avviata su un altro terminale con il token di test configurato)*
