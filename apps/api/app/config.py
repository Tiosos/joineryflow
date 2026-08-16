from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    session_cookie_name: str = "jf_session"
    session_sliding_days: int = 14
    session_hard_cap_days: int = 30
    cookie_secure: bool = False
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
