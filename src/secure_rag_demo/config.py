from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://rag:local-demo-password@127.0.0.1:5432/rag"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "llama3.1"

    # EDUCATIONAL ONLY: static demo tokens, not production authentication.
    demo_token_public: str = "demo-public-token-change-me"
    demo_token_restricted: str = "demo-restricted-token-change-me"

    # Tracing is opt-in; content hiding is on by default.
    langsmith_tracing: bool = False
    langsmith_hide_inputs: bool = True
    langsmith_hide_outputs: bool = True


def get_settings() -> Settings:
    return Settings()
