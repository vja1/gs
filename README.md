# GSTIN Lookup API

A self-hosted HTTP API and CLI that returns public GST taxpayer details for a GSTIN by querying the government portals directly — no paid GSP required.

Two upstream sources are supported:

| Source     | Upstream page                                             | Notes |
|------------|-----------------------------------------------------------|-------|
| `ewaybill` | `ewaybillgst.gov.in/Others/TaxPayerSearch.aspx`            | Primary source. ASP.NET postback + 6-char CAPTCHA. |
| `gst`      | `services.gst.gov.in/services/searchtp`                    | JSON API + 6-digit CAPTCHA. Used as fallback. |
| `auto`     | (default) tries `ewaybill`, then falls back to `gst`       | |

## Install

```powershell
python -m pip install -r requirements.txt
```

## Run the API

```powershell
python app.py                 # http://127.0.0.1:8000
```

Or with Gunicorn on Linux/containers:

```bash
gunicorn app:app --bind 0.0.0.0:8000 --workers 1 --threads 2 --timeout 180
```

Endpoints:

```
GET /health
GET /lookup/<GSTIN>?source=auto&attempts=8&refresh=0&raw=0
```

Example:

```powershell
curl "http://127.0.0.1:8000/lookup/27AAACT2727Q1ZW"
```

```json
{
  "success": true,
  "gstin": "27AAACT2727Q1ZW",
  "state": "Maharashtra",
  "source": "gst",
  "attempts": 9,
  "cached": false,
  "data": {
    "gstin": "27AAACT2727Q1ZW",
    "legal_name": "TATA MOTORS PASSENGER VEHICLES LIMITED",
    "trade_name": "TATA MOTORS PASSENGER VEHICLES LIMITED",
    "status": "Active",
    "registration_date": "01/07/2017",
    "constitution": "Public Limited Company",
    "dealer_type": "Regular",
    "taxpayer_type": null,
    "nature_of_business": ["Factory / Manufacturing", "Wholesale Business"],
    "principal_place": { "address": "Pune, Maharashtra", "lat": null, "lng": null },
    "centre_jurisdiction": "...",
    "state_jurisdiction": "...",
    "einvoice_status": null
  }
}
```

Errors:

| Status | `error`            | Meaning |
|--------|--------------------|---------|
| 400    | `invalid_gstin`    | Format/checksum/state code failed locally |
| 400    | `bad_request`      | Unknown source or non-numeric `attempts` |
| 401    | `unauthorized`     | Missing or invalid `API_KEY` (when `API_KEY` is configured) |
| 404    | `unknown-gstin`    | Portal reports the GSTIN does not exist |
| 429    | `rate_limited`     | Per-IP request limit exceeded |
| 503    | `failed`           | Attempt budget exhausted / both portals unavailable |

## Command line

```powershell
python cli.py 27AAACT2727Q1ZW
python cli.py 27AAACT2727Q1ZW --source gst --attempts 12 --quiet
```

## Environment Variables

| Variable             | Default     | Purpose |
|----------------------|-------------|---------|
| `HOST`               | `127.0.0.1` | Bind address (dev server) |
| `PORT`               | `8000`      | Bind port |
| `DEBUG`              | off         | Flask debug reloader |
| `LOG_LEVEL`          | `INFO`      | Logging verbosity |
| `API_KEY`            | *(unset)*   | Optional secret checked via `X-API-Key`, `Authorization: Bearer`, or `?api_key=` |
| `CACHE_TTL`          | `3600`      | In-memory cache TTL in seconds (`0` disables caching) |
| `RATE_LIMIT_PER_MIN` | `30`        | Per-IP `/lookup` requests per minute (`0` disables) |
| `ENABLE_CORS`        | `true`      | Set `false` to disable wildcard CORS headers |
| `GSTIN_TLS_VERIFY`   | `false`     | Set `true` or a CA bundle path to enforce TLS verification |

## Free Hosting Guide (No Credit Card Required)

Because this project uses `opencv-python-headless` and `rapidocr-onnxruntime` (native ONNX binaries + ~300 MB footprint) and makes outbound HTTPS calls to Indian government portals, serverless hosts (Vercel, Cloudflare Workers) and outbound-restricted hosts (PythonAnywhere Free) are not suitable.

1. **Render — Free Native Python Web Service (Recommended, No Card)**
   - **Specs**: **512 MB RAM**, 750 free hours/month, **Singapore** region available (closer to NIC servers), sleeps after 15 min inactivity (~50s cold start).
   - **Setup**:
     1. Push this folder to a GitHub repository.
     2. Sign up at `render.com` with GitHub (no credit card required).
     3. Click **New → Blueprint** and select your repo — Render reads `render.yaml` automatically (`pip install -r requirements.txt` + `gunicorn app:app --workers 1 --threads 2`).
     4. *(Or use **New → Web Service** manually with Build Command `pip install -r requirements.txt` and Start Command `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 180`, Instance Type **Free**, Region **Singapore**.)*

2. **SnapDeploy — Free Docker Container (No Card)**
   - **Specs**: **512 MB RAM**, 0.25 vCPU, 100 free running-hours/month (sleeps after 15 min idle), deploys directly from `Dockerfile`.

*(Note: Hugging Face Spaces now requires a paid PRO plan for Docker/Gradio compute Spaces; only Static Spaces remain free there.)*

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Notes & limitations

* Public portals are rate sensitive — keep concurrency low and rely on `CACHE_TTL` to avoid repeated upstream calls.
* TLS verification defaults to `false` because NIC hosts are known to serve incomplete certificate chains. Set `GSTIN_TLS_VERIFY=/path/to/ca.pem` or `true` when your environment has the required intermediate CA.
