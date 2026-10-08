from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://lanvexa:lanvexa@localhost:5432/lanvexa"
    jwt_secret: str = "lanvexa_change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    public_domain: str = "localhost"
    relay_host: str = "0.0.0.0"
    relay_control_port: int = 7001
    relay_public_host: str = "localhost"
    relay_public_port: int = 7001
    relay_enabled: bool = True

    port_range_start: int = 40000
    port_range_end: int = 50000

    port: int = 8000

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator(
        "relay_public_port",
        "relay_control_port",
        "port",
        "port_range_start",
        "port_range_end",
        mode="before",
    )
    @classmethod
    def parse_int_with_default(cls, value, info):
        defaults = {
            "relay_public_port": 7001,
            "relay_control_port": 7001,
            "port": 8000,
            "port_range_start": 40000,
            "port_range_end": 50000,
        }
        if value is None or value == "":
            return defaults[info.field_name]
        try:
            return int(value)
        except (TypeError, ValueError):
            return defaults[info.field_name]

    @field_validator("relay_enabled", mode="before")
    @classmethod
    def parse_bool(cls, value):
        if value is None or value == "":
            return True
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def model_post_init(self, __context):
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql://", 1)
        if "?" in self.database_url:
            self.database_url = self.database_url.partition("?")[0]


settings = Settings()
