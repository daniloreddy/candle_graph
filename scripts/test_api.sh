#!/bin/bash
# Test Candle Graph API — POST /api/v1/chart
# Usage: scripts/test_api.sh <token> [port]

TOKEN="${1}"
PORT="${2:-8000}"
OUTFILE="chart_test.png"

if [ -z "$TOKEN" ]; then
    echo "Usage: scripts/test_api.sh <token> [port]"
    echo "Example: scripts/test_api.sh my-secret-token 8000"
    exit 1
fi

echo "Generating payload..."
PAYLOAD=$(python3 - <<'EOF'
import json, datetime

rows = []
for i in range(50):
    d = datetime.date(2024, 1, 1) + datetime.timedelta(days=i)
    p = 50000 + i * 100
    rows.append({
        "date": d.isoformat() + "T00:00:00",
        "open":   float(p),
        "high":   float(p + 500),
        "low":    float(p - 500),
        "close":  float(p + 200),
        "volume": 1000.0,
    })

print(json.dumps({
    "symbol": "BTCUSDT",
    "data": rows,
    "bb_k": 2.0,
    "max_ohlcv_points": 180,
    "response_format": "png",
}))
EOF
)

echo "Calling http://localhost:${PORT}/api/v1/chart ..."
HTTP_CODE=$(curl -s -X POST "http://localhost:${PORT}/api/v1/chart" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" \
    --output "${OUTFILE}" \
    -w "%{http_code}")

echo "HTTP ${HTTP_CODE} — $(wc -c < "${OUTFILE}") bytes"

if [ "${HTTP_CODE}" = "200" ]; then
    echo "Saved: ${OUTFILE}"
else
    echo "ERROR: server returned ${HTTP_CODE}"
    cat "${OUTFILE}"
    rm -f "${OUTFILE}"
    exit 1
fi
