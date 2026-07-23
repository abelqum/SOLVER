from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    SettingsConfigDict,
)


def parse_cors_origins(value: object) -> list[str]:
    if isinstance(value, list):
        return [
            str(origin).strip()
            for origin in value
            if str(origin).strip()
        ]

    if isinstance(value, str):
        return [
            origin.strip()
            for origin in value.split(",")
            if origin.strip()
        ]

    raise ValueError(
        "CORS_ORIGINS debe ser una lista o una cadena separada por comas."
    )


class Settings(BaseSettings):
    app_name: str = "Horarium Solver"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    solver_api_key: str

    cors_origins: Annotated[
        list[str],
        NoDecode,
        BeforeValidator(parse_cors_origins),
    ] = ["http://localhost:3000"]

    solver_max_time_seconds: float = 30.0
    solver_num_workers: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("solver_api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        normalized_value = value.strip()

        if len(normalized_value) < 12:
            raise ValueError(
                "SOLVER_API_KEY debe contener al menos 12 caracteres."
            )

        return normalized_value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(
        cls,
        value: list[str],
    ) -> list[str]:
        if not value:
            raise ValueError(
                "CORS_ORIGINS debe contener al menos un origen."
            )

        for origin in value:
            if not origin.startswith(
                ("http://", "https://")
            ):
                raise ValueError(
                    f"Origen CORS inválido: {origin}"
                )

        return value

    @field_validator("solver_max_time_seconds")
    @classmethod
    def validate_max_time(
        cls,
        value: float,
    ) -> float:
        if value <= 0:
            raise ValueError(
                "SOLVER_MAX_TIME_SECONDS debe ser mayor que cero."
            )

        return value

    @field_validator("solver_num_workers")
    @classmethod
    def validate_workers(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "SOLVER_NUM_WORKERS debe ser igual o mayor que uno."
            )

        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()