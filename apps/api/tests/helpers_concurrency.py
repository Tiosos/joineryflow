"""Exercise PostgreSQL lock waits without mocking application queries."""
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import time
from sqlalchemy import text
from app.db import SessionLocal


def finish_after_waiting(first, operation):
    started = Queue()

    def run():
        with SessionLocal() as second:
            second.execute(text("SET statement_timeout = '10s'"))
            started.put(second.execute(text('SELECT pg_backend_pid()')).scalar_one())
            result = operation(second)
            second.commit()
            return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        try:
            pid = started.get(timeout=5)
            deadline = time.monotonic() + 5
            with SessionLocal() as observer:
                while not future.done():
                    if observer.execute(text('SELECT cardinality(pg_blocking_pids(:p))'), {'p': pid}).scalar_one():
                        break
                    assert time.monotonic() < deadline, 'worker neither blocked nor completed'
                    time.sleep(.01)
        finally:
            first.commit()
        return future.result(timeout=12)
