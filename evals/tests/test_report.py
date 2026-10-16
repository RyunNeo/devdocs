import csv

import pytest

from evals.tests.test_runner import setup_run
from evals.toolkit.artifacts import append_result


def trial(tmp_path):
    from evals.toolkit.runner import run_cases

    client, dataset, manifest = setup_run(tmp_path)
    directory = run_cases(
        client, dataset, manifest, tmp_path, "trial", ["fact-01", "cross-01", "refusal-01"]
    )
    return dataset, directory


def test_report_counts_and_unscored(tmp_path):
    from evals.toolkit.report import build_report

    dataset, directory = trial(tmp_path)
    report = build_report(dataset, directory)
    text = report.read_text(encoding="utf-8")
    assert "3/3" in text and "2/3" in text
    assert "0/3" in text and "未知" in text
    assert "不是检索召回率" in text and "12" in text
    assert (directory / "scores.csv").exists()
    with pytest.raises(ValueError, match="已存在"):
        build_report(dataset, directory)


def edit_scores(path, mutate):
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fields, rows = reader.fieldnames, list(reader)
    mutate(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_manual_scores_and_validation(tmp_path):
    from evals.toolkit.report import build_report, load_scores

    dataset, directory = trial(tmp_path)
    build_report(dataset, directory)
    path = directory / "scores.csv"

    def fill(rows):
        for row in rows:
            if row["case_id"] == "refusal-01":
                row["refusal"] = "通过"
            else:
                row["correctness"] = "2"
                row["support"] = "2"

    edit_scores(path, fill)
    text = build_report(dataset, directory, path, overwrite=True).read_text(encoding="utf-8")
    assert "3/3" in text
    scores = load_scores(path, dataset)
    assert scores["fact-01"].correctness == 2
    edit_scores(path, lambda rows: rows[0].update(correctness="3"))
    with pytest.raises(ValueError):
        load_scores(path, dataset)


@pytest.mark.parametrize("change", ["duplicate", "unknown", "inapplicable"])
def test_score_bad_ids_and_types(tmp_path, change):
    from evals.toolkit.report import build_report, load_scores

    dataset, directory = trial(tmp_path)
    build_report(dataset, directory)

    def mutate(rows):
        if change == "duplicate":
            rows[1]["case_id"] = rows[0]["case_id"]
        elif change == "unknown":
            rows[0]["case_id"] = "unknown"
        else:
            rows[0]["refusal"] = "通过"

    edit_scores(directory / "scores.csv", mutate)
    with pytest.raises(ValueError):
        load_scores(directory / "scores.csv", dataset)


def test_no_samples_and_formula_safe(tmp_path):
    from evals.toolkit.report import build_report

    dataset, directory = trial(tmp_path)
    dataset.cases[0].reference_answer = "=FORMULA()"
    for case_id in ("fact-01", "cross-01", "refusal-01"):
        append_result(
            directory,
            {
                "case_id": case_id,
                "status": "not_attempted",
                "attempted": False,
                "usage": None,
                "elapsed_ms": None,
            },
        )
    text = build_report(dataset, directory).read_text(encoding="utf-8")
    assert "0/0" in text and "NaN" not in text
    assert "'=FORMULA()" in (directory / "scores.csv").read_text(encoding="utf-8-sig")


def test_metric_partial_tokens_and_citations(tmp_path):
    from evals.toolkit.artifacts import load_results
    from evals.toolkit.report import summarize

    dataset, directory = trial(tmp_path)
    rows = load_results(directory)
    rows[0]["usage"] = {"total_tokens": 30}
    rows[1]["status"] = "failed"
    metric = summarize(dataset, rows, {})
    assert metric["completed"] == 2 and metric["attempted"] == 3
    assert metric["known_tokens"] == 30 and metric["unknown_usage"] == 1
    assert metric["p95_ms"] == 12


def test_source_coverage_uses_owned_document_id(tmp_path):
    from evals.toolkit.artifacts import load_results
    from evals.toolkit.report import build_report

    dataset, directory = trial(tmp_path)
    row = load_results(directory)[0]
    row["citations"][0]["document_id"] = "foreign-id"
    append_result(directory, row)
    text = build_report(dataset, directory).read_text(encoding="utf-8")
    assert "期望引用来源覆盖：1/3" in text


@pytest.mark.parametrize(
    "case_id,column,value",
    [
        ("fact-01", "refusal", "pass"),
        ("cross-01", "multi", "通过"),
        ("refusal-01", "support", "1"),
        ("fact-01", "correctness", "secret-invalid-score"),
    ],
)
def test_score_error_identifies_case_and_column(tmp_path, case_id, column, value):
    from evals.toolkit.report import build_report, load_scores

    dataset, directory = trial(tmp_path)
    build_report(dataset, directory)

    def mutate(rows):
        next(row for row in rows if row["case_id"] == case_id)[column] = value

    edit_scores(directory / "scores.csv", mutate)
    with pytest.raises(ValueError) as exc:
        load_scores(directory / "scores.csv", dataset)
    assert case_id in str(exc.value) and column in str(exc.value)
    assert "secret-invalid-score" not in str(exc.value)
