import hashlib
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets/cedardesk-v1.json"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(StrictModel):
    source: str
    quote: str = Field(min_length=1)


class Case(StrictModel):
    id: str = Field(pattern=r"^[a-z]+-\d{2}$")
    category: Literal["fact", "cross", "refusal", "multi", "adversarial"]
    question: str = Field(min_length=1, max_length=2000)
    expected_behavior: Literal["answer", "refuse"]
    reference_answer: str = Field(min_length=1)
    required_facts: list[str]
    forbidden_facts: list[str]
    expected_sources: list[str]
    evidence: list[Evidence]
    conversation_group: str | None = None
    turn: int | None = None


class Dataset(StrictModel):
    version: str
    documents: list[str]
    cases: list[Case]
    dataset_sha256: str = ""
    document_hashes: dict[str, str] = Field(default_factory=dict)
    fixtures_root: Path = ROOT / "fixtures"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset(path: Path, fixtures_root: Path = ROOT / "fixtures") -> Dataset:
    data = Dataset.model_validate_json(path.read_bytes())
    if not data.documents or len(set(data.documents)) != len(data.documents):
        raise ValueError("文档清单为空或重复")
    texts = {}
    root = fixtures_root.resolve()
    for name in data.documents:
        target = (root / name).resolve()
        if not target.is_relative_to(root) or not re.fullmatch(r"[a-zA-Z0-9_-]+\.md", name):
            raise ValueError("资料路径越界或文件名非法")
        texts[name] = target.read_text(encoding="utf-8")
        data.document_hashes[name] = digest(target)
    seen, groups = set(), {}
    for case in data.cases:
        if case.id in seen:
            raise ValueError("题号重复")
        seen.add(case.id)
        if len(set(case.expected_sources)) != len(case.expected_sources):
            raise ValueError("期望来源重复")
        if not set(case.expected_sources).issubset(texts):
            raise ValueError("期望来源不存在")
        if case.expected_behavior == "answer" and (
            not case.expected_sources
            or {e.source for e in case.evidence} != set(case.expected_sources)
        ):
            raise ValueError("可回答题必须为每个期望来源提供证据")
        if (case.category == "refusal") != (case.expected_behavior == "refuse"):
            raise ValueError("拒答类型冲突")
        for evidence in case.evidence:
            if evidence.source not in texts or evidence.quote not in texts[evidence.source]:
                raise ValueError("证据原文不存在")
        if case.category == "multi":
            if not case.conversation_group or type(case.turn) is not int:
                raise ValueError("多轮缺少分组与顺序")
            expected = groups.get(case.conversation_group, 0) + 1
            if case.turn != expected:
                raise ValueError("多轮顺序非法")
            groups[case.conversation_group] = expected
        elif case.conversation_group is not None or case.turn is not None:
            raise ValueError("非多轮题不能设置会话分组")
    if not data.cases or any(n < 2 for n in groups.values()):
        raise ValueError("题集为空或多轮分组不足两轮")
    data.dataset_sha256 = digest(path)
    data.fixtures_root = root
    return data


def select_cases(dataset: Dataset, ids: list[str] | None = None) -> list[Case]:
    if ids is None:
        return dataset.cases
    if not ids or len(set(ids)) != len(ids) or set(ids) - {c.id for c in dataset.cases}:
        raise ValueError("选择包含未知、空或重复题号")
    selected = [c for c in dataset.cases if c.id in ids]
    for case in selected:
        if case.conversation_group and any(
            c.id not in ids
            for c in dataset.cases
            if c.conversation_group == case.conversation_group and c.turn < case.turn
        ):
            raise ValueError("多轮选择缺少前置题")
    return selected
