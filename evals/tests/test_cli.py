import pytest


def test_report_displays_specific_score_error(tmp_path, capsys):
    from evals import run
    from evals.tests.test_report import edit_scores, trial
    from evals.toolkit.report import build_report

    dataset, directory = trial(tmp_path)
    report = build_report(dataset, directory)
    before = report.read_bytes()
    edit_scores(directory / "scores.csv", lambda rows: rows[0].update(refusal="pass"))
    code = run.main(
        [
            "report",
            "--results",
            str(directory),
            "--scores",
            str(directory / "scores.csv"),
            "--overwrite-report",
        ]
    )
    assert code == 1
    output = capsys.readouterr().out
    assert "fact-01" in output and "refusal" in output
    assert report.read_bytes() == before


def test_validate_offline(monkeypatch, capsys):
    from evals import run

    monkeypatch.setattr(run, "EvaluationClient", lambda *a, **kw: pytest.fail("network"))
    assert run.main(["validate"]) == 0
    assert "24" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["prepare", "run"])
def test_paid_gate_before_login(monkeypatch, command, tmp_path):
    from evals import run

    monkeypatch.setattr(run, "EvaluationClient", lambda *a, **kw: pytest.fail("network"))
    monkeypatch.setattr(run.getpass, "getpass", lambda *a: pytest.fail("password"))
    args = [command, "--email", "test@example.com", "--run-id", "trial"]
    if command == "run":
        args += ["--manifest", str(tmp_path / "missing.json")]
    assert run.main(args) == 1


def test_help_and_bad_arguments():
    from evals import run

    with pytest.raises(SystemExit) as help_exit:
        run.main(["--help"])
    assert help_exit.value.code == 0
    with pytest.raises(SystemExit) as bad_exit:
        run.main(["bad-command"])
    assert bad_exit.value.code == 2


def test_report_offline(monkeypatch, tmp_path):
    from evals import run
    from evals.tests.test_report import trial

    _, directory = trial(tmp_path)
    monkeypatch.setattr(run, "EvaluationClient", lambda *a, **kw: pytest.fail("network"))
    assert run.main(["report", "--results", str(directory)]) == 0
    assert run.main(["report", "--results", str(directory)]) == 1


def test_login_error_never_prints_secrets(monkeypatch, capsys):
    from evals import run
    from evals.toolkit.client import EvaluationError

    class BadClient:
        def __init__(self, *args, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def login(self, *args):
            raise EvaluationError("login_required", 401)

    monkeypatch.setattr(run, "EvaluationClient", BadClient)
    monkeypatch.setattr(run.getpass, "getpass", lambda *a: "secret-sentinel")
    assert (
        run.main(
            ["prepare", "--email", "test@example.com", "--run-id", "trial", "--allow-paid-calls"]
        )
        == 1
    )
    assert "secret-sentinel" not in capsys.readouterr().out


def test_failed_batch_exit_nonzero(monkeypatch, tmp_path):
    from evals import run
    from evals.tests.test_report import trial
    from evals.toolkit.artifacts import append_result

    _, directory = trial(tmp_path)
    append_result(directory, {"case_id": "fact-01", "status": "failed", "attempted": True})

    class Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def login(self, *a):
            pass

    monkeypatch.setattr(run, "EvaluationClient", Client)
    monkeypatch.setattr(run.getpass, "getpass", lambda *a: "test-only")
    monkeypatch.setattr(run, "run_cases", lambda *a: directory)
    assert (
        run.main(
            [
                "run",
                "--manifest",
                str(directory / "manifest.json"),
                "--email",
                "test@example.com",
                "--run-id",
                "new-id",
                "--allow-paid-calls",
            ]
        )
        == 1
    )
