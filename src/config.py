"""Application configuration. All env-driven knobs live here."""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


class Config:
    # ── Application ────────────────────────────────────────────────────────
    SERVICE_NAME = os.getenv("SERVICE_NAME", "tickora")
    API_PORT     = int(os.getenv("API_PORT", "5100"))
    DEV_MODE     = _bool("DEV_MODE", True)
    LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO")
    ROLE         = os.getenv("ROLE", "api")  # api | worker | sla_checker

    ALLOWED_ORIGINS = [
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ]

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    DATABASE_URL    = os.getenv("DATABASE_URL", "postgresql://tickora:tickora@localhost:5432/tickora")
    DB_POOL_SIZE    = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL  = os.getenv("REDIS_URL",  "redis://localhost:6379/0")
    # QF framework compat — framework.etl reads these directly from Config
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = os.getenv("REDIS_PORT", "6379")
    REDIS_DB   = os.getenv("REDIS_DB",   "0")

    # ── Keycloak ───────────────────────────────────────────────────────────
    KEYCLOAK_SERVER_URL        = os.getenv("KEYCLOAK_SERVER_URL", "http://localhost:8080")
    KEYCLOAK_REALM             = os.getenv("KEYCLOAK_REALM", "tickora")
    KEYCLOAK_API_CLIENT_ID     = os.getenv("KEYCLOAK_API_CLIENT_ID", "tickora-api")
    KEYCLOAK_API_CLIENT_SECRET = os.getenv("KEYCLOAK_API_CLIENT_SECRET", "")
    KEYCLOAK_SPA_CLIENT_ID     = os.getenv("KEYCLOAK_SPA_CLIENT_ID", "tickora-spa")
    KEYCLOAK_ISSUER            = os.getenv(
        "KEYCLOAK_ISSUER",
        f"{os.getenv('KEYCLOAK_SERVER_URL', 'http://localhost:8080')}/realms/{os.getenv('KEYCLOAK_REALM', 'tickora')}",
    )
    KEYCLOAK_AUDIENCE          = os.getenv("KEYCLOAK_AUDIENCE", "tickora-api")
    KEYCLOAK_ADMIN_USER        = os.getenv("KEYCLOAK_ADMIN_USER", "admin")
    KEYCLOAK_ADMIN_PASSWORD    = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin")

    JWKS_CACHE_TTL      = int(os.getenv("JWKS_CACHE_TTL", "3600"))
    PRINCIPAL_CACHE_TTL = int(os.getenv("PRINCIPAL_CACHE_TTL", "60"))

    # ── Kafka / tasking ────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
    KAFKA_TOPIC_FAST        = os.getenv("KAFKA_TOPIC_FAST", "tickora_fast")
    KAFKA_TOPIC_SLOW        = os.getenv("KAFKA_TOPIC_SLOW", "tickora_slow")
    WORKER_NAME             = os.getenv("WORKER_NAME", "tickora")
    # QF framework legacy keys (consumer doesn't run for the API role)
    KAFKA_POLL_TIMEOUT_MS         = int(os.getenv("KAFKA_POLL_TIMEOUT_MS", "100"))
    KAFKA_POLL_MAX_RECORDS        = int(os.getenv("KAFKA_POLL_MAX_RECORDS", "200"))
    KAFKA_IDLE_SLEEP_SEC          = float(os.getenv("KAFKA_IDLE_SLEEP_SEC", "0"))
    KAFKA_COMMIT_TICK_SEC         = float(os.getenv("KAFKA_COMMIT_TICK_SEC", "0.2"))
    KAFKA_MAX_JOBS_PER_TP_PER_TICK = int(os.getenv("KAFKA_MAX_JOBS_PER_TP_PER_TICK", "20"))

    # ── MinIO / S3 ─────────────────────────────────────────────────────────
    S3_ENDPOINT_URL   = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
    S3_REGION         = os.getenv("S3_REGION", "us-east-1")
    S3_ACCESS_KEY     = os.getenv("S3_ACCESS_KEY", "minio")
    S3_SECRET_KEY     = os.getenv("S3_SECRET_KEY", "minio12345")
    S3_BUCKET_ATTACHMENTS    = os.getenv("S3_BUCKET_ATTACHMENTS", "tickora-attachments")
    ATTACHMENT_MAX_SIZE_BYTES = int(os.getenv("ATTACHMENT_MAX_SIZE_BYTES", str(25 * 1024 * 1024)))
    ATTACHMENT_PRESIGNED_TTL  = int(os.getenv("ATTACHMENT_PRESIGNED_TTL", "60"))

    # ── Tracing ────────────────────────────────────────────────────────────
    ENABLE_TRACING = _bool("ENABLE_TRACING", False)
    OTLP_ENDPOINT  = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")

    # ── Rate limiting (Redis-backed) ───────────────────────────────────────
    RATE_LIMIT_COMMENTS_PER_MIN    = int(os.getenv("RATE_LIMIT_COMMENTS_PER_MIN", "30"))
    RATE_LIMIT_ATTACHMENTS_PER_MIN = int(os.getenv("RATE_LIMIT_ATTACHMENTS_PER_MIN", "10"))

    # ── Email ──────────────────────────────────────────────────────────────
    SMTP_HOST     = os.getenv("SMTP_HOST", "")
    SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER     = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM     = os.getenv("SMTP_FROM", "tickora@example.com")
