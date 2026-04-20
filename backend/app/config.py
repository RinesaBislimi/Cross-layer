from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Vendos në .env sipas DB që përdor:
    # MySQL:   mysql+pymysql://USER:PASSWORD@HOST:3306/DATABASE
    # SQLite:  sqlite:///./crosslayer.db
    # Postgres: postgresql://user:password@localhost:5432/crosslayer
    DATABASE_URL: str = "sqlite:///./crosslayer.db"

    # Paths default për dataset-et (mund t'i ndryshosh nga .env)
    BGL_PATH: str = "data/bgl/bgl.csv"
    CICIDS_PATH: str = "data/cicids/cicids.csv"
    TDA_PATH: str = "data/tda/tda.csv"

    # ── LLM provider ─────────────────────────────────────────────────────────
    # Choose one: "anthropic" | "groq" | "ollama"
    # Groq  — free, no credit card: https://console.groq.com  → LLM_PROVIDER=groq
    # Ollama — fully local, no key:  https://ollama.ai        → LLM_PROVIDER=ollama
    LLM_PROVIDER: str = "anthropic"

    # Anthropic (paid)
    ANTHROPIC_API_KEY: str = ""

    # Groq (free tier) – get key at console.groq.com
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama3-70b-8192"

    # Ollama (local) – install from ollama.ai, then: ollama pull llama3
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # Google Gemini Flash (free) – get key at aistudio.google.com (no credit card)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # OpenAI / ChatGPT – get key at platform.openai.com
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"   # cheap & fast; change to gpt-4o for best quality

    # Local assistant – fully embedded, queries your own DB, zero external API
    # No keys needed. Just set LLM_PROVIDER=local

    # Direktoria ku ruhen modelet e trajnuara
    MODEL_DIR: str = "models"
    BGL_MODEL_PATH: str = "models/bgl_model.pkl"
    CICIDS_MODEL_PATH: str = "models/cicids_model.pkl"
    TDA_MODEL_PATH: str = "models/tda_model.pkl"
    CROSS_LAYER_MODEL_PATH: str = "models/cross_layer_model.pkl"

    # ── SMTP email settings ───────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = ""

    class Config:
        env_file = ".env"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
