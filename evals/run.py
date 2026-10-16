"""Run from the repository root with the backend virtual environment."""

import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path

from pydantic import ValidationError

from evals.toolkit.artifacts import load_results, read_json
from evals.toolkit.client import EvaluationClient, EvaluationError
from evals.toolkit.dataset import DEFAULT_DATASET, ROOT, Dataset, load_dataset, select_cases
from evals.toolkit.report import ScoreValidationError, build_report
from evals.toolkit.runner import prepare, reconcile, run_cases


def parser():
    root = argparse.ArgumentParser(description="DevDocs AI 独立资料 RAG 质量评测")
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="离线校验资料与题集")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    for name in ("prepare", "run"):
        cmd = commands.add_parser(name, help="准备资料并索引" if name == "prepare" else "运行问答")
        cmd.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
        cmd.add_argument("--output-root", type=Path, default=ROOT / "results")
        cmd.add_argument("--email", required=True)
        cmd.add_argument("--run-id", required=True)
        cmd.add_argument("--allow-paid-calls", action="store_true")
        cmd.add_argument("--allow-remote", action="store_true")
        if name == "prepare":
            cmd.add_argument("--base-url", default="http://127.0.0.1:8000")
        else:
            cmd.add_argument("--manifest", type=Path, required=True)
            cmd.add_argument("--cases", help="逗号分隔题号；多轮题须包含前置题")
    cmd = commands.add_parser("reconcile", help="只读核对未知结果，不重新提问")
    cmd.add_argument("--results", type=Path, required=True)
    cmd.add_argument("--email", required=True)
    cmd.add_argument("--allow-remote", action="store_true")
    cmd = commands.add_parser("report", help="离线生成评分模板和 Markdown 报告")
    cmd.add_argument("--results", type=Path, required=True)
    cmd.add_argument("--scores", type=Path)
    cmd.add_argument("--overwrite-report", action="store_true")
    return root


def hidden_password():
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass("测试账号密码（隐藏输入）：")


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in {"prepare", "run"} and not args.allow_paid_calls:
            print("未执行：真实调用会消耗配额与供应商费用，需要 --allow-paid-calls。")
            return 1
        if args.command == "validate":
            dataset = load_dataset(args.dataset)
            print(f"校验通过：{len(dataset.documents)} 份文档，{len(dataset.cases)} 题。")
            return 0
        if args.command == "report":
            manifest = read_json(args.results / "manifest.json")
            dataset = Dataset.model_validate_json(json.dumps(manifest["dataset"]))
            path = build_report(dataset, args.results, args.scores, overwrite=args.overwrite_report)
            print(f"已生成：{path}\n评分模板：{args.results / 'scores.csv'}")
            return 0
        if args.command == "prepare":
            dataset = load_dataset(args.dataset)
            base_url = args.base_url
            print(
                f"准备：{base_url}；{dataset.version}；最多索引 {len(dataset.documents)} 份资料。"
            )
        else:
            manifest_path = (
                args.manifest if args.command == "run" else args.results / "manifest.json"
            )
            manifest = read_json(manifest_path)
            base_url = manifest["base_url"]
            if args.command == "run":
                dataset = load_dataset(args.dataset)
                case_ids = [s.strip() for s in args.cases.split(",")] if args.cases else None
                selected = select_cases(dataset, case_ids)
                print(
                    f"问答：{base_url}；{dataset.version}；最多受理 {len(selected)} 次，"
                    "包括无依据回复；不自动重试。"
                )
            else:
                print("只读核对现有会话，不重新提问。")
        with EvaluationClient(base_url, allow_remote=args.allow_remote) as client:
            password = hidden_password()
            try:
                client.login(args.email, password)
            finally:
                del password
            if args.command == "prepare":
                result = prepare(client, dataset, args.output_root, args.run_id)
            elif args.command == "run":
                result = run_cases(
                    client, dataset, args.manifest, args.output_root, args.run_id, case_ids
                )
            else:
                reconcile(client, args.results)
                result = args.results
        print(f"已保存：{result}")
        if args.command == "run":
            print("运行记录不代表质量达标；请生成报告并人工评分。")
            if any(r["status"] != "completed" for r in load_results(result)):
                print("本批存在失败、未知或未执行题，请查看结果；不会自动重新提交。")
                return 1
        return 0
    except ScoreValidationError as exc:
        print(f"未完成：{exc}。修改评分表后执行原命令即可，无需重跑问答。")
    except EvaluationError as exc:
        print(f"未完成：{exc}。已有目录中的清单和结果会保留，请核对后再操作。")
    except getpass.GetPassWarning:
        print("未执行：当前终端无法隐藏密码输入，请在本机交互终端运行。")
    except KeyboardInterrupt:
        print("已中断；不要直接重发。先检查结果目录，必要时使用 reconcile 只读核对。")
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        # Never echo raw API content, file content, credentials, or a traceback.
        print(
            "未完成：文件、资料、评分或参数不符合要求；检查路径、题号、评分及运行编号。"
            "报告已存在时需 --overwrite-report，运行编号必须使用新的名称。"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
