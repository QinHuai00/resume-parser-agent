# resume-parser-agent

Turn PDF / DOCX / TXT resumes into a **validated, traceable JSON profile**:
Pydantic contract → validation-error feedback repair → field-level evidence
grounding → async batch → offline evaluation harness.

> Not "call an LLM once and hope for JSON" — a pipeline that can *explain* a
> failure, *prevent* fabrication, and be *measured*.

## Pipeline

```
extract (docx/pdf/txt + OCR hook)
  → prompt = resume text + JSON Schema
  → LLM
  → Pydantic validation (email/phone/years, extra=forbid)
  → on error: send ValidationError back to the model once (targeted repair)
  → evidence filter: every field needs a verbatim quote from the source,
    otherwise it is set to null and reported in `dropped_fields`
```

## Measured (offline, reproducible)

Simulated model injecting 35% dirty outputs over 12 synthetic resumes:

| metric | no repair | 1 repair round |
| --- | --- | --- |
| structurally valid output | 91.7% | **100%** |
| avg repair rounds | 0 | 0.08 |
| skills set F1 | 0.917 | **1.000** |

With 100% dirty outputs, structural validity still reaches 100%.
Full tables: [`eval/results.md`](eval/results.md).

## Quickstart

```bash
pip install -e ".[dev]"
pytest -q                       # 36 offline tests
python eval/make_dataset.py
python -m resume_agent.cli eval --provider mock --corrupt-rate 0.35 --max-repairs 1

export LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export LLM_API_KEY=sk-xxx
export LLM_MODEL=qwen-plus
python -m resume_agent.cli serve --port 8000
```

Any OpenAI-compatible `/chat/completions` endpoint works — switching vendors is a
single environment variable.

## HTTP API

```bash
curl -X POST localhost:8000/api/v1/parse -F "file=@cv.pdf"
curl -X POST localhost:8000/api/v1/batch -F "files=@a.docx" -F "files=@b.pdf"
curl localhost:8000/api/v1/tasks/<task_id>
```

## Design notes

- **JSON Schema + repair loop instead of function calling** — portable across
  vendors and the error message itself becomes part of the prompt.
- **One repair round by default** — round 1 fixes every repairable failure;
  round 2 adds latency for little gain.
- **Evidence grounding trades recall for precision** — a fabricated phone number
  poisons downstream filtering, a null does not. The tradeoff is observable via
  `dropped_fields`.
- **Batch is async by design** — return `task_id` immediately, run in background,
  isolate per-file failures.

## Limitations

OCR is a hook only; no multi-model voting; task state is in-memory; no auth/rate
limiting; the eval set is synthetic and should be treated as a regression
baseline, not a benchmark.

MIT © [QinHuai00](https://github.com/QinHuai00)