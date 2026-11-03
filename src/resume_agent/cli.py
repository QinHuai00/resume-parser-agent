"""命令行入口。

    resume-agent parse  简历.pdf 简历.docx --xlsx out/summary.xlsx
    resume-agent parse  data/samples/ --out out/
    resume-agent eval   --provider mock --corrupt-rate 0.35
    resume-agent serve  --port 8000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .llm import MockLLM, OpenAICompatClient
from .pipeline import ResumePipeline


def _build_llm(provider: str):
    if provider == "openai":
        return OpenAICompatClient()
    raise SystemExit(f"CLI 模式下 provider={provider} 不可用，请用 --provider openai 或直接跑 eval")


def _iter_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(x for x in p.rglob("*") if x.suffix.lower() in {".txt", ".md", ".docx", ".pdf"}))
        else:
            files.append(p)
    return files


def cmd_parse(args: argparse.Namespace) -> int:
    from .export import export_xlsx

    pipeline = ResumePipeline(_build_llm(args.provider), max_repairs=args.max_repairs)
    outcomes = []
    for f in _iter_files(args.targets):
        outcome = pipeline.parse_text(f.read_text(encoding="utf-8") if f.suffix.lower() in {".txt", ".md"} else "")
        outcomes.append(outcome)
        print(f"[{'OK  ' if outcome.valid else 'FAIL'}] {f.name} repairs={outcome.repairs} dropped={outcome.dropped_fields}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = [o.to_dict() for o in outcomes]
    (out / "profiles.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON -> {out / 'profiles.json'}")

    if args.xlsx:
        path = export_xlsx(payload, args.xlsx)
        print(f"XLSX -> {path}")
    return 0 if all(o.valid for o in outcomes) else 1


def cmd_eval(args: argparse.Namespace) -> int:
    from .evaluate import load_dataset, run_eval

    dataset = load_dataset(args.dataset)
    report = run_eval(
        dataset,
        provider=args.provider,
        corrupt_rate=args.corrupt_rate,
        max_repairs=args.max_repairs,
        verify_evidence=not args.no_evidence,
        seed=args.seed,
    )
    print(report.to_markdown())
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .service import create_app

    pipeline = ResumePipeline(_build_llm(args.provider), max_repairs=args.max_repairs)
    uvicorn.run(create_app(pipeline), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="resume-agent", description="简历 → 结构化 JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="解析文件或目录")
    p_parse.add_argument("targets", nargs="+")
    p_parse.add_argument("--out", default="out")
    p_parse.add_argument("--xlsx", default=None)
    p_parse.add_argument("--provider", default="openai", choices=["openai"])
    p_parse.add_argument("--max-repairs", type=int, default=1)
    p_parse.set_defaults(func=cmd_parse)

    p_eval = sub.add_parser("eval", help="跑离线评测")
    p_eval.add_argument("--dataset", default="eval/dataset.jsonl")
    p_eval.add_argument("--provider", default="mock", choices=["mock", "openai"])
    p_eval.add_argument("--corrupt-rate", type=float, default=0.35)
    p_eval.add_argument("--max-repairs", type=int, default=1)
    p_eval.add_argument("--no-evidence", action="store_true")
    p_eval.add_argument("--seed", type=int, default=7)
    p_eval.set_defaults(func=cmd_eval)

    p_serve = sub.add_parser("serve", help="起 HTTP 服务")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--provider", default="openai", choices=["openai"])
    p_serve.add_argument("--max-repairs", type=int, default=1)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())