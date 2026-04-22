from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    session_cookie_name: str = "jf_session"
    session_sliding_days: int = 14
    session_hard_cap_days: int = 30
    class Config: env_file = ".env"

settings = Settings()
