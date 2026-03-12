#!/bin/bash
set -e

echo "==> Inicializando banco de dados..."
python init_db.py

echo "==> Iniciando Streamlit..."
exec streamlit run app.py \
  --server.port "${PORT:-8501}" \
  --server.address "0.0.0.0" \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection true
