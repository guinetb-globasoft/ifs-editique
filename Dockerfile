# L'image de Playwright 1.58 : Python 3.12 et le Chromium de cette version, avec ses dépendances système.
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

# Calibri et Arial n'existent pas sous Linux : Carlito et Liberation Sans ont les mêmes métriques (spec § 7).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-crosextra-carlito fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY ressources ressources

ENV PORT=8000 PYTHONUNBUFFERED=1
# --proxy-headers : derrière le proxy de l'hébergeur, l'URL vue par l'application reste en https.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
