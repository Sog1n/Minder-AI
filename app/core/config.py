from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True
    llm_mode: str = "demo"  # demo | openai

    openai_api_key: str | None = None
    openai_extraction_model: str = "gpt-4o"
    openai_judge_model: str = "gpt-4o-mini"
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "secret"
    mysql_database: str = "minder_ai"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_knowledge: str = "tribal_knowledge"
    qdrant_collection_sop: str = "sop_documents"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
