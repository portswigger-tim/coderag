"""Configuration, loaded from the environment and an optional .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Directories and file patterns that never carry useful source signal. Kept
# deliberately blunt: a false skip costs one missing file, a false include
# costs minutes of embedding time on vendored code.
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "dist", "build", "target", "out", ".next", ".nuxt", ".cache",
        "vendor", "third_party", "site-packages", ".tox", ".gradle",
        ".idea", ".vscode", "coverage", "htmlcov",
    }
)

DEFAULT_IGNORE_GLOBS: tuple[str, ...] = (
    "*.min.js", "*.min.css", "*.map", "*.lock", "*.sum",
    "package-lock.json", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock",
    "*.pb.go", "*_pb2.py", "*.generated.*", "*.g.dart",
)


class Settings(BaseSettings):
    """Runtime configuration: where Neo4j is, and nothing else.

    One field, with an explicit environment-variable alias. Without the
    alias pydantic derives the name from the field, so neo4j_uri would
    answer to NEO4J_URI by luck rather than intent.

    There is no user or password because the database runs with
    authentication disabled, bound to loopback -- see docker-compose.yml.
    Values that were once settings -- embedding model, batch sizes,
    response budgets, co-change thresholds -- are constants next to the
    code that uses them, because each was chosen by measurement and
    exposing it mostly invites someone to make it worse. Response budgets
    remain adjustable per call, via the MCP tools' budget_tokens argument.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    neo4j_uri: str = Field("bolt://localhost:7687", alias="NEO4J_URI")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
