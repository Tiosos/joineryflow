from sqlalchemy import text
from app.db import engine

def test_engine_connects():
    with engine.connect() as c:
        assert c.execute(text("select 1")).scalar() == 1
