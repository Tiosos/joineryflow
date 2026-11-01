"""Process metadata: which image is running and which schema it expects.

The readiness probe and GET /version both read from here. The schema head is
derived from the alembic scripts themselves — the repository is the source of
truth, not an env var that can drift out of sync with the code.

The ini path is probed rather than configured because the layout differs by
environment: /db/alembic.ini in the containers (compose mounts ./db:/db),
<repo>/db/alembic.ini from a source checkout.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session


def _alembic_ini() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        Path("/db/alembic.ini"),
        Path("db/alembic.ini"),
        here.parents[3] / "db" / "alembic.ini",  # <repo>/db from apps/api/app
    ]
    return next((p for p in candidates if p.is_file()), None)


@lru_cache(maxsize=1)
def expected_schema_head() -> str | None:
    """The alembic head this build was shipped with.

    None means the migration scripts are not reachable from this process —
    treat that as "schema check cannot run", not as "schema is wrong".
    """
    ini = _alembic_ini()
    if ini is None:
        return None
    cfg = Config(str(ini))
    # script_location in the ini is relative; make it absolute so the lookup
    # does not depend on the process cwd.
    cfg.set_main_option("script_location", str(ini.parent / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def current_schema_version(db: Session) -> list[str]:
    """The revision(s) the database says it is on. A list because alembic
    supports branch points; today the chain is linear so it has one entry."""
    return sorted(
        db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    )
