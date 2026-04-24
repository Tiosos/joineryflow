from app.auth.passwords import hash_password, verify_password


def test_hash_then_verify():
    h = hash_password("hartwood-dev")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "hartwood-dev")
    assert not verify_password(h, "wrong")
