"""Database engine helpers.

Database URLs are intentionally read from environment variables so credentials
do not live in source control.
"""

import os
from functools import lru_cache

import sqlalchemy


DATABASE_URL_ENV_VARS = {
    "jy": "BETA_MMT_JY_DATABASE_URL",
    "finance": "BETA_MMT_FINANCE_DATABASE_URL",
    "market": "BETA_MMT_MARKET_DATABASE_URL",
    "basic": "BETA_MMT_BASIC_DATABASE_URL",
    "index": "BETA_MMT_INDEX_DATABASE_URL",
}


def get_database_url(env_var):
    """Return a database URL from an environment variable."""
    url = os.getenv(env_var)
    if not url:
        raise RuntimeError(
            f"Missing database URL environment variable: {env_var}. "
            "Set it locally before running scripts that query MySQL."
        )
    return url


@lru_cache(maxsize=None)
def get_database_engine(env_var):
    """Create and cache a SQLAlchemy engine for a database URL env var."""
    return sqlalchemy.create_engine(get_database_url(env_var))


def get_jy_engine():
    return get_database_engine(DATABASE_URL_ENV_VARS["jy"])


def get_finance_engine():
    return get_database_engine(DATABASE_URL_ENV_VARS["finance"])


def get_market_engine():
    return get_database_engine(DATABASE_URL_ENV_VARS["market"])


def get_basic_engine():
    return get_database_engine(DATABASE_URL_ENV_VARS["basic"])


def get_index_engine():
    return get_database_engine(DATABASE_URL_ENV_VARS["index"])
