import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.config import settings
from app.core import logbuffer

# Log dell'app (accessi, errori) con data e ora, accanto a quelli di uvicorn: docker compose logs api
_logger = logging.getLogger("netmap")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(logbuffer.FORMAT))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
# Le stesse righe, più errori e avvii di uvicorn, restano in memoria per il pacchetto diagnostico
logbuffer.attach("netmap", "uvicorn.error")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Documentazione di rete: device, interfacce, cavi, VLAN, IPAM e topologia.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
