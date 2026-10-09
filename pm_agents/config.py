"""Configuración leída desde variables de entorno o `.env`."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: str = ""
    # Los IDs de modelo no tienen valor por defecto en el código: vienen siempre del entorno.
    # Vacío significa "no configurado"; llm.py lo valida al crear el modelo.
    model_orchestrator: str = ""
    model_specialist: str = ""
    model_fallback: str = ""
    db_path: str = "data/proyecto.db"
    max_requests_per_run: int = 15


settings = Settings()
