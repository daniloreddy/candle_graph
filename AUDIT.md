# 🛡️ Software Audit Report: Candle Graph API

## 1. Security Audit

### ⚠️ High Severity: Potential Timing Attack in Token Verification
* **Location**: `main.py:52` (`if credentials.credentials not in VALID_TOKENS:`)
* **Issue**: The token comparison uses a standard set lookup (`in`). While Python's set lookup is highly optimized, it does not use constant-time comparison. In a high-precision environment, an attacker could theoretically use timing attacks to guess valid tokens.
* **Mitigation**: Use `secrets.compare_digest` for comparing the provided token against known valid tokens.

### 🟡 Medium Severity: Information Disclosure via Error Messages
* **Location**: `main.py:119` (`raise HTTPException(status_code=400, detail=str(e))`)
* **Issue**: The API returns the raw string representation of exceptions (`str(e)`) to the client. While mostly harmless for `ValueError`, if an unexpected exception occurs that is caught by a generic handler, it could leak internal logic, library versions, or database-like error structures.
* **Mitigation**: Implement custom error messages for different exception types. Avoid returning raw exception strings to the client in production.

### 🟢 Low Severity: Input Payload Size
* **Location**: `main.py:77` (`data: List[OHLCVData] = Field(..., max_length=5000)`)
* **Observation**: The limit of 5,000 data points is a good first defense against DoS. However, 5,000 `OHLCVData` objects in a single JSON payload could still result in a large memory footprint during Pydantic parsing.
* **Mitigation**: Monitor memory usage during peak load and consider lowering this limit if the API is intended for purely technical analysis (where 500-1000 points are usually sufficient).

---

## 2. Stability & Resource Management Audit

### 🟡 Medium Severity: Memory Pressure under High Concurrency
* **Location**: `main.py:91` (Semaphore) and `libs/plotting.py:154` (Figure creation)
* **Issue**: The `chart_semaphore` limits *concurrent* processing to 4. However, each process creates a large Matplotlib `Figure` (`figsize=(13, 11), dpi=140`). If 4 requests are processed simultaneously, they will consume significant RAM. If a user sends many requests quickly, the *queue* of pending tasks in `asyncio` could grow, leading to high memory overhead before they even hit the semaphore.
* **Mitigation**: Ensure the server environment has sufficient RAM to handle `MAX_CONCURRENT_CHARTS * [Estimated RAM per Figure]`.

### 🟢 Low Severity: Redundant Data Copying
* **Location**: `main.py:95` (`df = df.tail(...).copy()`) and `libs/plotting.py:150` (`plot_df = df.copy()`)
* **Issue**: The code performs multiple deep copies of the DataFrame during a single request lifecycle. While this ensures thread safety and prevents side effects, it increases CPU and memory usage for large datasets.
* **Mitigation**: Evaluate if `copy()` is strictly necessary at every step, or if some operations can be performed on slices/views safely.

---

## 3. Robustness & Numerical Stability Audit

### 🟡 Medium Severity: Indicator Calculation Sensitivity
* **Location**: `libs/indicators.py:31` and `libs/indicators.py:77`
* **Issue**: 
    1.  **Insufficient Data**: The code correctly warns if there are fewer than 26 bars, but it returns an empty DataFrame. If the calling code doesn't check for `.empty` (though `main.py` does), it could cause downstream crashes.
    2.  **NaN Propagation**: The code uses `dropna(subset=cols_to_check, how="any")`. If a single indicator (like MACD) fails to calculate for the entire dataset due to one `NaN` or insufficient window, the *entire* dataset is dropped, resulting in an empty response.
* **Mitigation**: Use more granular error handling in `indicators.py`. Instead of dropping the whole DataFrame, consider returning the data with `NaN`s for the failed indicators so the user gets *some* chart.

### 🟢 Low Severity: Plotting Edge Cases
* **Location**: `libs/plotting.py:146` (`if df is None or df.empty or len(df) < 2:`)
* **Observation**: The check for `len(df) < 2` is good, but it might still be too low for some indicators. Since `add_indicators` requires at least 26 points, `get_plot_bytes` will likely receive a DataFrame with 0 rows if indicators failed.
* **Mitigation**: Ensure the relationship between "minimum data for indicators" and "minimum data for plotting" is explicitly synchronized.

---

## Summary Table

| Category | Severity | Issue | Impact |
| :--- | :--- | :--- | :--- |
| **Security** | 🔴 High | Timing Attack | Token guessing |
| **Security** | 🟡 Med | Info Disclosure | Leaking internal details |
| **Stability** | 🟡 Med | RAM Pressure | OOM under load |
| **Robustness**| 🟡 Med | Aggressive `dropna` | All-or-nothing chart rendering |
| **Robustness**| 🟢 Low | Redundant Copies | Increased latency/CPU |
