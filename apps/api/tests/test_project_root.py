"""Конфиги репозитория находятся независимо от рабочего каталога запуска."""

import yaml


def test_root_config_resolves_from_foreign_cwd(monkeypatch, tmp_path):
    """Ложный репозиторий в cwd не должен перехватывать разрешение конфигов."""
    decoy = tmp_path
    (decoy / "config").mkdir()
    (decoy / "data").mkdir()
    (decoy / "pyproject.toml").write_text('[project]\nname = "cwd-decoy"\n')
    (decoy / "config" / "constraints.yaml").write_text(
        yaml.safe_dump({"pressure_limits": {"cwd_decoy": True}})
    )

    from ppd_audit.config import load_constraints, project_root

    project_root.cache_clear()
    load_constraints.cache_clear()
    monkeypatch.chdir(decoy)
    try:
        root = project_root()
        assert root != decoy
        assert (root / "config" / "constraints.yaml").is_file()
        assert "cwd_decoy" not in load_constraints().pressure_limits
    finally:
        load_constraints.cache_clear()
        project_root.cache_clear()
