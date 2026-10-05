FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Immagine di sviluppo: include pytest e il simulatore SNMP per i test
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .

CMD ["sh", "start.sh"]
