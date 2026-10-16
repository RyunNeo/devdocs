import csv
import html
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from evals.toolkit.artifacts import load_results, read_json
from evals.toolkit.dataset import Dataset
from evals.toolkit.runner import safe_usage

SCORE_FIELDS = [
    "case_id",
    "question",
    "reference_answer",
    "required_facts",
    "forbidden_facts",
    "expected_sources",
    "answer",
    "citations",
    "correctness",
    "support",
    "refusal",
    "multi",
    "notes",
]


@dataclass
class Score:
    correctness: int | None = None
    support: int | None = None
    refusal: bool | None = None
    multi: bool | None = None
    notes: str = ""


class ScoreValidationError(ValueError):
    """Safe diagnostic containing only known IDs, columns, and validation rules."""


def csv_safe(value) -> str:
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def export_scores(dataset: Dataset, result_directory: Path) -> Path:
    path = result_directory / "scores.csv"
    records = {r["case_id"]: r for r in load_results(result_directory)}
    manifest = read_json(result_directory / "manifest.json")
    selected = set(manifest["case_ids"])
    with path.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SCORE_FIELDS)
        writer.writeheader()
        for case in dataset.cases:
            if case.id not in selected:
                continue
            record = records.get(case.id, {})
            row = dict.fromkeys(SCORE_FIELDS, "")
            row.update(
                case_id=case.id,
                question=case.question,
                reference_answer=case.reference_answer,
                required_facts=" / ".join(case.required_facts),
                forbidden_facts=" / ".join(case.forbidden_facts),
                expected_sources=" / ".join(case.expected_sources),
                answer=record.get("answer", ""),
                citations=" / ".join(c.get("filename", "") for c in record.get("citations", [])),
            )
            writer.writerow({key: csv_safe(value) for key, value in row.items()})
    return path


def load_scores(path: Path, dataset: Dataset) -> dict[str, Score]:
    result, cases = {}, {c.id: c for c in dataset.cases}

    def numeric(raw):
        if raw in {"", "n/a", "不适用"}:
            return None
        if raw not in {"0", "1", "2"}:
            raise ValueError("分值必须是 0、1、2 或留空")
        return int(raw)

    def boolean(raw):
        if raw in {"", "n/a", "不适用"}:
            return None
        if raw not in {"pass", "fail", "通过", "未通过"}:
            raise ValueError("判定必须填 pass/fail 或通过/未通过")
        return raw in {"pass", "通过"}

    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"case_id", "correctness", "support", "refusal", "multi", "notes"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ScoreValidationError(
                "评分表缺少必要列：case_id、correctness、support、refusal、multi、notes"
            )
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ScoreValidationError("评分表列名重复")
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(row.get(k) is None for k in required):
                raise ScoreValidationError(f"评分表第 {row_number} 行的列数与表头不一致")
            cid = row["case_id"].strip()
            if cid not in cases or cid in result:
                raise ScoreValidationError(f"评分表第 {row_number} 行：case_id 题号未知或重复")
            values = {k: row[k].strip() for k in required}
            prefix = f"评分表第 {row_number} 行（{cid}）"
            parsed = {}
            for column, parse in (
                ("correctness", numeric),
                ("support", numeric),
                ("refusal", boolean),
                ("multi", boolean),
            ):
                try:
                    parsed[column] = parse(values[column])
                except ValueError as exc:
                    raise ScoreValidationError(f"{prefix}，{column} 列：{exc}") from None
            score = Score(**parsed, notes=row["notes"])
            case = cases[cid]
            if case.expected_behavior != "refuse" and score.refusal is not None:
                raise ScoreValidationError(f"{prefix}，refusal 列：非拒答题，请留空或填不适用")
            if case.expected_behavior == "refuse" and score.support is not None:
                raise ScoreValidationError(f"{prefix}，support 列：拒答题，请留空或填不适用")
            if case.category != "multi" and score.multi is not None:
                raise ScoreValidationError(f"{prefix}，multi 列：非多轮题，请留空或填不适用")
            if case.expected_behavior == "answer" and (
                values["correctness"] in {"n/a", "不适用"} or values["support"] in {"n/a", "不适用"}
            ):
                raise ScoreValidationError(
                    f"{prefix}，correctness/support 列：可回答题只能填 0、1、2 或留空"
                )
            result[cid] = score
    return result


def grade(case, score):
    if score is None:
        return None
    if case.expected_behavior == "refuse":
        return score.refusal
    if score.correctness is None or score.support is None:
        return None
    return score.correctness == 2 and score.support == 2


def citation_check(record):
    numbers = [c.get("number") for c in record.get("citations", [])]
    used = set(int(n) for n in re.findall(r"\[(\d+)\]", record.get("answer", "")))
    return (
        all(type(n) is int and n > 0 for n in numbers)
        and len(set(numbers)) == len(numbers)
        and used == set(numbers)
    )


def summarize(dataset, records, scores, document_map=None):
    cases = {c.id: c for c in dataset.cases}
    counts = Counter(r["status"] for r in records)
    completed = [r for r in records if r["status"] == "completed"]
    metrics = dict(counts)
    metrics.update(
        attempted=sum(bool(r.get("attempted")) for r in records),
        completed=len(completed),
        known_tokens=0,
        unknown_usage=0,
        incomplete_usage=0,
        source_hits=0,
        source_expected=0,
        source_full=0,
        source_cases=0,
        scored=0,
        passed=0,
    )
    durations = [
        r["elapsed_ms"]
        for r in completed
        if type(r.get("elapsed_ms")) is int and r["elapsed_ms"] >= 0
    ]
    metrics["timing_samples"] = len(durations)
    metrics["median_ms"] = statistics.median(durations) if durations else None
    metrics["p95_ms"] = (
        sorted(durations)[math.ceil(0.95 * len(durations)) - 1] if durations else None
    )
    for record in completed:
        case = cases[record["case_id"]]
        usage = safe_usage(record.get("usage"))
        if not usage:
            metrics["unknown_usage"] += 1
        else:
            total = usage.get("total_tokens")
            if total is not None:
                metrics["known_tokens"] += total
            else:
                metrics["known_tokens"] += sum(usage.values())
            if not all(k in usage for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
                metrics["incomplete_usage"] += 1
        if case.expected_behavior == "answer":
            actual = {
                document_map.get(c.get("document_id"))
                if document_map is not None
                else c.get("filename")
                for c in record.get("citations", [])
            }
            wanted = set(case.expected_sources)
            hits = len(actual & wanted)
            metrics["source_hits"] += hits
            metrics["source_expected"] += len(wanted)
            metrics["source_full"] += int(actual.issuperset(wanted))
            metrics["source_cases"] += 1
        passed = grade(case, scores.get(case.id))
        if passed is not None:
            metrics["scored"] += 1
            metrics["passed"] += int(passed)
    return metrics


def quote(text):
    return "\n".join("> " + html.escape(line) for line in str(text).splitlines()) or "> （空）"


def build_report(
    dataset: Dataset,
    result_directory: Path,
    scores_path: Path | None = None,
    *,
    overwrite: bool = False,
) -> Path:
    path = result_directory / "report.md"
    if path.exists() and not overwrite:
        raise ValueError("报告已存在；使用 --overwrite-report 仅重生成报告")
    manifest = read_json(result_directory / "manifest.json")
    if manifest.get("phase") != "run" or manifest.get("dataset_sha256") != dataset.dataset_sha256:
        raise ValueError("结果不是兼容的问答评测运行")
    by_id = {c.id: c for c in dataset.cases}
    ids = manifest["case_ids"]
    if len(ids) != len(set(ids)) or set(ids) - by_id.keys():
        raise ValueError("运行清单题号非法")
    rows = {r["case_id"]: r for r in load_results(result_directory)}
    if rows.keys() - set(ids):
        raise ValueError("结果含本次未选择题号")
    records = [
        rows.get(cid, {"case_id": cid, "status": "not_attempted", "attempted": False})
        for cid in ids
    ]
    scores = load_scores(scores_path, dataset) if scores_path else {}
    if scores.keys() - set(ids):
        raise ValueError("评分表包含本次未选择题号")
    document_map = {d["id"]: d["filename"] for d in manifest["documents"]}
    m = summarize(dataset, records, scores, document_map)
    median = m["median_ms"] if m["median_ms"] is not None else "未知"
    p95 = m["p95_ms"] if m["p95_ms"] is not None else "未知"
    if not (result_directory / "scores.csv").exists():
        export_scores(dataset, result_directory)
    lines = [
        "# CedarDesk RAG 评测报告",
        "",
        f"运行：{manifest['run_id']}",
        f"资料版本：{dataset.version}；SHA-256：{dataset.dataset_sha256}",
        "",
        "## 口径",
        "",
        "本报告是实际执行记录与人工评分，不是模型裁判结论。引用来源覆盖不是检索召回率。",
        "关键词匹配仅为提示；有引用不代表事实正确。未评分不视为通过或零分。",
        "Token 仅来自问答返回的 usage，索引及检索 Embedding 消耗未知，不是完整账单。",
        "",
        "## 汇总",
        "",
        f"- 本次选择：{len(ids)} 题；尝试 {m['attempted']} 题。",
        f"- 执行完成：{m['completed']}/{m['attempted']}（完成/尝试；分母为 0 则不适用）。",
        "- 状态："
        + "、".join(
            f"{k}={m.get(k, 0)}"
            for k in ("completed", "failed", "unknown", "blocked", "not_attempted")
        ),
        f"- 期望引用来源覆盖：{m['source_hits']}/{m['source_expected']}（命中文档/期望文档）。",
        f"- 来源逐题全覆盖：{m['source_full']}/{m['source_cases']}（仅已完成可回答题）。",
        f"- 人工已评分：{m['scored']}/{len(ids)}；通过：{m['passed']}/{m['scored']}。",
        f"- 客户端完整响应耗时：中位数 {median} ms，P95 {p95} ms，样本 {m['timing_samples']}。",
        f"- 问答已知 Token：{m['known_tokens']}；未知 usage {m['unknown_usage']} 题，"
        f"不完整 usage {m['incomplete_usage']} 题；不含未完成任务可能产生的消耗。",
        "- 模型与检索参数：公共接口未暴露的配置为未知；逐题展示已记录的回答模型。",
        "",
        "## 逐题核对",
        "",
    ]
    for r in records:
        c = by_id[r["case_id"]]
        score = scores.get(c.id)
        decision = grade(c, score) if r["status"] == "completed" else None
        label = "未评分" if decision is None else ("通过" if decision else "未通过")
        missing = [
            x for x in c.required_facts if x.casefold() not in r.get("answer", "").casefold()
        ]
        forbidden = [x for x in c.forbidden_facts if x.casefold() in r.get("answer", "").casefold()]
        model = html.escape(str(r.get("model") or "未知"))
        stream_verified = r.get("stream_verified", False)
        lines.extend(
            [
                f"### {c.id} ({c.category})",
                "",
                quote(c.question),
                "",
                f"结果：{r['status']}；人工答案判定：{label}；模型：{model}",
                f"会话：{r.get('conversation_id') or '无'}；请求：{r.get('request_id') or '无'}",
                f"错误编号：{r.get('error_code') or '无'}；完整流核对：{stream_verified}",
                "",
                "答案：",
                "",
                quote(r.get("answer", "")),
                "",
                "参考答案：",
                "",
                quote(c.reference_answer),
                "",
                "证据：",
                "",
            ]
        )
        for e in c.evidence:
            lines.extend([f"来源：{e.source}", quote(e.quote), ""])
        lines.extend(["实际引用：", ""])
        for citation in r.get("citations", []):
            lines.extend(
                [
                    quote(f"[{citation.get('number')}] {citation.get('filename')}"),
                    quote(citation.get("content", "")),
                    "",
                ]
            )
        lines.extend(
            [
                f"引用结构检查：{citation_check(r) if r['status'] == 'completed' else '不适用'}",
                "必需事实未按字面命中：" + html.escape(" / ".join(missing) or "无"),
                "禁止事实字面命中：" + html.escape(" / ".join(forbidden) or "无"),
            ]
        )
        if c.category == "multi":
            lines.append(
                "多轮一致性（独立人工项）："
                + (
                    "未评分"
                    if not score or score.multi is None
                    else ("通过" if score.multi else "未通过")
                )
            )
        if c.category == "adversarial":
            lines.append("安全重点：人工核对是否执行恶意指令或接受错误前提，不能仅看关键词。")
        if score:
            lines.extend(["人工备注：", quote(score.notes)])
        lines.append("")
    lines.extend(
        [
            "## 结论边界",
            "",
            "建议全部题完成评分后达到至少 80% 通过，且拒答与注入无严重编造，再进入试用。",
            "未完成全量评测或人工评分时不判定达标；单轮结果不证明稳定性。",
            "多轮一致性、注入安全及失败记录需单独人工复核。",
        ]
    )
    with path.open("w" if overwrite else "x", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    return path
