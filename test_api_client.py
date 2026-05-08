import httpx
import numpy as np
import logging
from datetime import datetime, timedelta
import subprocess
import os
import sys
from dotenv import load_dotenv

# Configurazione logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Carica .env locale se presente
load_dotenv()

# Recupera il token:
# 1. Da TEST_TOKEN env var
# 2. O estraendo il primo da API_TOKENS
# 3. O fallback hardcoded
TEST_TOKEN = os.getenv("TEST_TOKEN")
if not TEST_TOKEN:
    api_tokens = os.getenv("API_TOKENS", "").split(",")
    TEST_TOKEN = api_tokens[0] if api_tokens[0] else "test_token_secret"


def run_test():
    url = "http://127.0.0.1:8000/api/v1/chart"
    output_file = "chart_test.png"

    logger.info("Generazione dati di test...")
    base = datetime.now()
    data = []
    price = 50000.0
    for i in range(300):
        dt = base - timedelta(minutes=15 * (300 - i))
        price += np.random.normal(0, 50)
        data.append(
            {
                "date": dt.isoformat(),
                "open": price - 10,
                "high": price + 25,
                "low": price - 30,
                "close": price,
                "volume": np.random.uniform(1, 10),
            }
        )

    payload = {"symbol": "BTC/USDT", "data": data, "bb_k": 2.0, "max_ohlcv_points": 180}

    # Header di Autenticazione
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    logger.info("Invio richiesta a %s...", url)
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            logger.error("Errore API (%d): %s", response.status_code, response.text)
            if response.status_code == 401:
                logger.error(
                    "Assicurati di aver avviato il server con --env-file e che API_TOKENS contenga il token di test."
                )
            return

        with open(output_file, "wb") as f:
            f.write(response.content)

        logger.info("Grafico salvato in: %s", output_file)

        if sys.platform == "darwin":
            subprocess.run(["open", output_file])
        elif sys.platform == "win32":
            os.startfile(output_file)
        else:
            subprocess.run(["xdg-open", output_file])

    except Exception as e:
        logger.critical(
            "Connessione fallita: %s. Assicurati che l'API sia attiva su :8000", e
        )


if __name__ == "__main__":
    run_test()
