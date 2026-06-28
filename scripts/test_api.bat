@echo off
:: Test Candle Graph API — POST /api/v1/chart
:: Usage: test_api.bat "<token>" [port]
:: NOTE: quote the token if it contains commas or spaces

set TOKEN=%~1
set PORT=%~2
if "%TOKEN%"=="" (
    echo Usage: scripts\test_api.bat "^<token^>" [port]
    echo Example: scripts\test_api.bat "my-secret-token" 8000
    echo Example: scripts\test_api.bat "tok1,tok2,tok3" 8000
    exit /b 1
)
if "%PORT%"=="" set PORT=8000

set OUTFILE=chart_test.png
set TMPJSON=%TEMP%\cg_payload_%RANDOM%.json

echo Generating payload...
powershell -NoProfile -Command ^
    "$rows = 1..50 | ForEach-Object { $d = ([datetime]'2024-01-01').AddDays($_ - 1); $p = 50000 + $_ * 100; [ordered]@{ date = $d.ToString('yyyy-MM-ddTHH:mm:ss'); open = [double]$p; high = [double]($p + 500); low = [double]($p - 500); close = [double]($p + 200); volume = 1000.0 } }; @{ symbol = 'BTCUSDT'; data = $rows; bb_k = 2.0; max_ohlcv_points = 180; response_format = 'png' } | ConvertTo-Json -Depth 3 -Compress" ^
    > "%TMPJSON%"

echo Calling http://localhost:%PORT%/api/v1/chart ...
for /f "delims=" %%C in ('curl -s -X POST "http://localhost:%PORT%/api/v1/chart" ^
    -H "Authorization: Bearer %TOKEN%" ^
    -H "Content-Type: application/json" ^
    -d "@%TMPJSON%" ^
    --output "%OUTFILE%" ^
    -w "%%{http_code}"') do set HTTP_CODE=%%C

del "%TMPJSON%" 2>nul

echo HTTP %HTTP_CODE%
if "%HTTP_CODE%"=="200" (
    for %%A in ("%OUTFILE%") do echo Saved: %OUTFILE% ^(%%~zA bytes^)
) else (
    echo ERROR: server returned %HTTP_CODE%
    type "%OUTFILE%"
    del "%OUTFILE%" 2>nul
    exit /b 1
)
