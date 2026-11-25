FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    PORT=7860

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py cli.py captcha_solver.py ewaybill_source.py gst_source.py gstin_utils.py http_client.py lookup_service.py ./

EXPOSE 7860

# Single worker + 2 threads keeps RAM under 512 MB (Render/Koyeb) while sharing the RapidOCR model.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-7860} --workers 1 --threads 2 --timeout 180"]
