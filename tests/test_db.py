from pipeline.db import connect


def test_schema_and_fts5_match():
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO articles (source_id, url, title, body, fetched_at, content_hash) "
        "VALUES (?, ?, ?, ?, datetime('now'), ?)",
        ("shabla_sabitiya", "https://shabla.bg/example", "Koncert v Shabla",
         "Zapovyadayte na kontsert v gradskiya park.", "deadbeef"),
    )
    conn.commit()

    rows = conn.execute(
        "SELECT a.id, a.title FROM articles a "
        "JOIN articles_fts f ON f.rowid = a.id "
        "WHERE articles_fts MATCH ?",
        ("koncert",),
    ).fetchall()

    assert len(rows) == 1
    assert rows[0]["title"] == "Koncert v Shabla"


def test_schema_is_idempotent():
    conn = connect(":memory:")
    # Re-running the schema script against the same connection must not raise.
    from pipeline.db import SCHEMA
    conn.executescript(SCHEMA)
