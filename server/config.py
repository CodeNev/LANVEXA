from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://lanvexa:lanvexa@localhost:5432/lanvexa"
    jwt_secret: str = "lanvexa_change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    public_domain: str = "localhost"

    relay_host: str = "0.0.0.0"
    relay_control_port: int = 7000
    relay_public_host: str = "127.0.0.1"
    relay_public_port: int = 7000

    port_range_start: int = 40000
    port_range_end: int = 50000

    port: int = 8000

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator(
        "relay_control_port",
        "relay_public_port",
        "port",
        "port_range_start",
        "port_range_end",
        mode="before",
    )
    @classmethod
    def parse_int(cls, value, info):
        defaults = {
            "relay_control_port": 7000,
            "relay_public_port": 7000,
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

    def model_post_init(self, __context):
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql://", 1)
        if "?" in self.database_url:
            self.database_url = self.database_url.partition("?")[0]


settings = Settings()
