from functools import lru_cache

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./crosslayer.db"

    BGL_PATH: str = "data/bgl/bgl.csv"
    CICIDS_PATH: str = "data/cicids/cicids.csv"
    TDA_PATH: str = "data/tda/tda.csv"

    LLM_PROVIDER: str = "anthropic"

    ANTHROPIC_API_KEY: str = ""

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama3-70b-8192"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    MODEL_DIR: str = "models"
    BGL_MODEL_PATH: str = "models/bgl_model.pkl"
    CICIDS_MODEL_PATH: str = "models/cicids_model.pkl"
    TDA_MODEL_PATH: str = "models/tda_model.pkl"
    CROSS_LAYER_MODEL_PATH: str = "models/cross_layer_model.pkl"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = ""

    JWT_SECRET: str = "change-me-in-production-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    class Config:
        env_file = ".env"

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
