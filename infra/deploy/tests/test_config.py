import pytest


def test_init_creates_isolated_config_without_printing_secrets(tmp_path, capsys):
    from infra.deploy.config import init_config

    path = tmp_path / ".env.rehearsal"
    assert init_config(path) == path
    fields = dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    assert fields["POSTGRES_USER"] == "devdocs_rehearsal"
    assert fields["POSTGRES_DB"] == "devdocs_rehearsal"
    assert fields["REHEARSAL_PORT"] == "3100"
    assert fields["SILICONFLOW_API_KEY"] == ""
    assert len(fields["POSTGRES_PASSWORD"]) >= 43
    assert not capsys.readouterr().out


def test_init_never_overwrites_existing_config(tmp_path):
    from infra.deploy.config import init_config

    path = tmp_path / ".env.rehearsal"
    path.write_bytes(b"existing-config")
    with pytest.raises(FileExistsError):
        init_config(path)
    assert path.read_bytes() == b"existing-config"


@pytest.mark.parametrize("port", [True, 80, 65536, "3100"])
def test_invalid_port_does_not_create_file(tmp_path, port):
    from infra.deploy.config import init_config

    path = tmp_path / ".env.rehearsal"
    with pytest.raises(ValueError):
        init_config(path, port=port)
    assert not path.exists()


def test_two_configs_have_different_generated_passwords(tmp_path):
    from infra.deploy.config import init_config

    first, second = (tmp_path / name for name in ("first", "second"))
    init_config(first)
    init_config(second)
    assert first.read_bytes() != second.read_bytes()
