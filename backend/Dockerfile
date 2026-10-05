FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ping per il monitor dello stato live (fase 4)
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Immagine di sviluppo: include pytest e il simulatore SNMP per i test
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .

CMD ["sh", "start.sh"]
