from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://lanvexa:lanvexa@localhost:5432/lanvexa"
    jwt_secret: str = "lanvexa_change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    public_domain: str = "localhost"

    relay_public_host: str = "localhost"
    relay_public_port: int = 7000

    port: int = 8000

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator("relay_public_port", "port", mode="before")
    @classmethod
    def parse_int(cls, value, info):
        defaults = {"relay_public_port": 7000, "port": 8000}
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
