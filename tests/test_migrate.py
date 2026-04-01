from pathlib import Path

from tastebuds.db import migrate


def test_get_migration_files_sorted(monkeypatch, tmp_path: Path):
    (tmp_path / "003_c.sql").write_text("-- c", encoding="utf-8")
    (tmp_path / "001_a.sql").write_text("-- a", encoding="utf-8")
    (tmp_path / "002_b.sql").write_text("-- b", encoding="utf-8")

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", tmp_path)

    migration_names = [path.name for path in migrate.get_migration_files()]

    assert migration_names == ["001_a.sql", "002_b.sql", "003_c.sql"]
