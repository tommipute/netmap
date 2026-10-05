from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "NetMap"
    database_url: str = "postgresql+psycopg://netmap:netmap@localhost:5433/netmap"
    # Origini ammesse per il frontend (fase 2)
    cors_origins: list[str] = ["http://localhost:5173"]

    # Chiave Fernet per cifrare community e chiavi SNMP. Vuota = generata al primo uso nel file qui sotto
    secrets_key: str = ""
    secrets_key_file: str = ".secrets_key"
    # Scansione: host interrogati in parallelo, massimo host per job, ogni quanti secondi il worker guarda la coda
    discovery_concurrency: int = 50
    discovery_max_hosts: int = 4096
    worker_poll_seconds: float = 3.0


settings = Settings()
