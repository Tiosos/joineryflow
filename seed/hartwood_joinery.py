"""Idempotent dev seed for the Hartwood Joinery workspace.

Run inside the api container:

    docker compose exec api python -m seed.hartwood_joinery

Inserts (or upserts) one workspace `hartwood-joinery` and 8 staff users with
the dev password `hartwood-dev`. Mina Klee is the procurement officer
(auth_role=purchase_officer).
"""
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal

DEV_PASSWORD = "hartwood-dev"

USERS: list[tuple[str, str, str, str]] = [
    ("aria.voss@hartwood.test", "Aria Voss", "admin", "CEO"),
    ("rin.park@hartwood.test", "Rin Park", "manager", "PM"),
    ("theo.blake@hartwood.test", "Theo Blake", "manager", "PM"),
    ("noa.lindqvist@hartwood.test", "Noa Lindqvist", "drafter", "Drafter"),
    ("juno.okafor@hartwood.test", "Juno Okafor", "editor", "Foreman"),
    ("kai.matthews@hartwood.test", "Kai Matthews", "editor", "Machine"),
    ("mina.klee@hartwood.test", "Mina Klee", "purchase_officer", "Procurement"),
    ("sam.ito@hartwood.test", "Sam Ito", "viewer", "Observer"),
]


def main() -> None:
    db = SessionLocal()
    try:
        wid = db.execute(
            text(
                """
                INSERT INTO workspace(slug, name)
                VALUES ('hartwood-joinery', 'Hartwood Joinery')
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """
            )
        ).scalar()
        pw = hash_password(DEV_PASSWORD)
        for email, name, role, jtbd in USERS:
            db.execute(
                text(
                    """
                    INSERT INTO app_user(workspace_id, email, full_name,
                                         password_hash, auth_role, jtbd_role)
                    VALUES (:w, :e, :n, :p, :r, :j)
                    ON CONFLICT (workspace_id, email) DO NOTHING
                    """
                ),
                {"w": wid, "e": email, "n": name, "p": pw, "r": role, "j": jtbd},
            )
        db.execute(text("""
  UPDATE app_user SET auth_role='drafter'
  WHERE workspace_id=:w AND email='noa.lindqvist@hartwood.test'
"""), {"w": wid})
        db.commit()
        print(f"seeded workspace {wid} with {len(USERS)} users")
    finally:
        db.close()


if __name__ == "__main__":
    main()
