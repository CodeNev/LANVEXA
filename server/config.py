from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://lanvexa:lanvexa@localhost:5432/lanvexa"
    jwt_secret: str = "lanvexa_change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    public_domain: str = "localhost"
    relay_host: str = "0.0.0.0"
    relay_control_port: int = 7000
    relay_public_host: str = "localhost"
    relay_public_port: int = 7000

    port_range_start: int = 40000
    port_range_end: int = 50000

    port: int = 8000

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()