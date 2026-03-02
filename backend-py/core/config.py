"""
Ved.io Backend — pydantic BaseSettings configuration.
Maps 1:1 to the Go Viper config structure (configs/config.yaml).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    name: str = "Huobao Drama API"
    version: str = "1.0.0"
    debug: bool = True
    language: str = "zh"  # zh or en

    model_config = SettingsConfigDict(env_prefix="APP_")


class ServerConfig(BaseSettings):
    port: int = 5678
    host: str = "0.0.0.0"
    cors_origins: list[str] = ["http://localhost:3012", "http://localhost:5678"]
    read_timeout: int = 600
    write_timeout: int = 600

    model_config = SettingsConfigDict(env_prefix="SERVER_")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [s.strip() for s in v.split(",")]
        return v


class DatabaseConfig(BaseSettings):
    type: str = "sqlite"
    path: str = "./data/drama_generator.db"
    host: str = "localhost"
    port: int = 5432
    user: str = "veduser"
    password: str = "vedpassword"
    name: str = "veddb"
    charset: str = "utf8mb4"
    max_idle: int = 10
    max_open: int = 100

    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    def async_url(self) -> str:
        if self.type == "sqlite":
            return f"sqlite+aiosqlite:///{self.path}"
        elif self.type == "postgres":
            return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        elif self.type == "mysql":
            return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}?charset={self.charset}"
        raise ValueError(f"Unsupported database type: {self.type}")

    def sync_url(self) -> str:
        """Sync URL for Alembic migrations."""
        if self.type == "sqlite":
            return f"sqlite:///{self.path}"
        elif self.type == "postgres":
            return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        elif self.type == "mysql":
            return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}?charset={self.charset}"
        raise ValueError(f"Unsupported database type: {self.type}")


class StorageConfig(BaseSettings):
    type: str = "local"
    local_path: str = "./data/storage"
    base_url: str = "http://localhost:5678/static"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "vedio"
    minio_secure: bool = False

    model_config = SettingsConfigDict(env_prefix="STORAGE_")


class AIConfig(BaseSettings):
    default_text_provider: str = "openai"
    default_image_provider: str = "openai"
    default_video_provider: str = "doubao"

    model_config = SettingsConfigDict(env_prefix="AI_")


class CriticConfig(BaseSettings):
    score_threshold: float = 7.5
    max_iterations: int = 3

    model_config = SettingsConfigDict(env_prefix="CRITIC_")


class Settings(BaseSettings):
    """Top-level settings — merges YAML config with env vars."""

    app: AppConfig = AppConfig()
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    storage: StorageConfig = StorageConfig()
    ai: AIConfig = AIConfig()
    critic: CriticConfig = CriticConfig()

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def _load_yaml_config(path: str = "./configs/config.yaml") -> dict[str, Any]:
    """Load YAML config file if it exists."""
    p = Path(path)
    if not p.exists():
        p = Path("../configs/config.yaml")
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_settings() -> Settings:
    """Load settings, applying YAML file overrides over pydantic defaults."""
    yaml_data = _load_yaml_config()

    # Build sub-configs from YAML, falling back to env-based defaults
    app_data = yaml_data.get("app", {})
    server_data = yaml_data.get("server", {})
    db_data = yaml_data.get("database", {})
    storage_data = yaml_data.get("storage", {})
    ai_data = yaml_data.get("ai", {})

    return Settings(
        app=AppConfig(**app_data) if app_data else AppConfig(),
        server=ServerConfig(**server_data) if server_data else ServerConfig(),
        database=DatabaseConfig(**db_data) if db_data else DatabaseConfig(),
        storage=StorageConfig(**storage_data) if storage_data else StorageConfig(),
        ai=AIConfig(**{k.replace("default_", ""): v for k, v in ai_data.items()} if ai_data else {})
        if ai_data
        else AIConfig(),
        critic=CriticConfig(),
    )


# Singleton instance
_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings
