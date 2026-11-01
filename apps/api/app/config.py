from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    session_cookie_name: str = "jf_session"
    session_sliding_days: int = 14
    session_hard_cap_days: int = 30
    cookie_secure: bool = False
    meili_url: str = "http://meili:7700"
    meili_api_key: str = ""
    search_index: str = "jf_search"
    # Image tag baked in at build/publish time (CI sets APP_VERSION); surfaced
    # by GET /version. "dev" marks a source checkout, not a release.
    app_version: str = "dev"
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
