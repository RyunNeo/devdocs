import json
from collections import Counter
from pathlib import Path

import pytest

from evals.toolkit.dataset import load_dataset, select_cases

ROOT = Path(__file__).resolve().parents[1]


def test_default_dataset():
    data = load_dataset(ROOT / "datasets/cedardesk-v1.json", ROOT / "fixtures")
    assert len(data.documents) == 4
    assert Counter(c.category for c in data.cases) == {
        "fact": 8,
        "cross": 4,
        "refusal": 4,
        "multi": 6,
        "adversarial": 2,
    }
    assert len(select_cases(data, ["fact-01", "refusal-01", "cross-01"])) == 3
    for ids in (["multi-02"], ["unknown"], ["fact-01", "fact-01"]):
        with pytest.raises(ValueError):
            select_cases(data, ids)


@pytest.mark.parametrize("mutation", ["duplicate", "escape", "evidence", "turn", "extra"])
def test_invalid_dataset(tmp_path, mutation):
    raw = json.loads((ROOT / "datasets/cedardesk-v1.json").read_text(encoding="utf-8"))
    if mutation == "duplicate":
        raw["cases"][1]["id"] = raw["cases"][0]["id"]
    elif mutation == "escape":
        raw["documents"][0] = "../README.md"
    elif mutation == "evidence":
        raw["cases"][0]["evidence"][0]["quote"] = "not present anywhere"
    elif mutation == "turn":
        next(c for c in raw["cases"] if c["category"] == "multi")["turn"] = 2
    else:
        raw["unexpected"] = True
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(path, ROOT / "fixtures")
