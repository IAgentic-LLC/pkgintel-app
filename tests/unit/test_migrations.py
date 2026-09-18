"""Chapter 17, unit tier: `pending_migrations`' own filtering logic,
pure, no I/O, no real Postgres, no real filesystem beyond a temp dir
this test creates itself.
"""

from pkgintel_app.migrations import pending_migrations


def test_already_applied_migrations_are_excluded(tmp_path):
    (tmp_path / "0001_baseline.sql").write_text("CREATE TABLE t (id INT)")
    (tmp_path / "0002_add_column.sql").write_text("ALTER TABLE t ADD COLUMN x INT")

    pending = pending_migrations(tmp_path, applied={"0001_baseline"})

    assert [p.stem for p in pending] == ["0002_add_column"]


def test_migrations_are_returned_in_filename_order(tmp_path):
    (tmp_path / "0003_third.sql").write_text("-- 3")
    (tmp_path / "0001_first.sql").write_text("-- 1")
    (tmp_path / "0002_second.sql").write_text("-- 2")

    pending = pending_migrations(tmp_path, applied=set())

    assert [p.stem for p in pending] == ["0001_first", "0002_second", "0003_third"]


def test_a_fully_applied_directory_has_nothing_pending(tmp_path):
    (tmp_path / "0001_baseline.sql").write_text("-- 1")

    pending = pending_migrations(tmp_path, applied={"0001_baseline"})

    assert pending == []
