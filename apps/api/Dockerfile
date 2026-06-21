FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# libpq5 : client PostgreSQL ; le reste = dépendances natives de WeasyPrint (PDF).
# Sans elles, `import weasyprint` plante au démarrage (cannot load library
# 'libgobject-2.0-0') → l'app entière tombe et le schéma n'est jamais créé.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpq5 \
       libglib2.0-0 libpango-1.0-0 libpangocairo-1.0-0 libcairo2 \
       libgdk-pixbuf-2.0-0 libharfbuzz0b libffi8 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
