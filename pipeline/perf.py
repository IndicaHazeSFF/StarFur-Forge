import json
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PERF_LOG = PROJECT_ROOT / "data" / "perf.jsonl"


def record_performance(
    operation: str,
    seconds: float,
    model: str | None = None,
    source: str | None = None,
    items: int | None = None,
):
    """
    Append one performance measurement to the StarFur
    performance history.
    """

    PERF_LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "timestamp": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "operation": operation,
        "seconds": round(seconds, 4),
    }

    if model is not None:
        record["model"] = model

    if source is not None:
        record["source"] = source

    if items is not None:
        record["items"] = items

        if items > 0:
            record["seconds_per_item"] = round(
                seconds / items,
                4,
            )

    with PERF_LOG.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(record) + "\n"
        )
    generate_report()

class PerformanceTimer:
    """
    Context manager for timing StarFur operations.

    Example:

        with PerformanceTimer(
            "annotation",
            model="qwen3:8b",
            items=7,
        ):
            do_expensive_thing()
    """

    def __init__(
        self,
        operation: str,
        model: str | None = None,
        source: str | None = None,
        items: int | None = None,
    ):
        self.operation = operation
        self.model = model
        self.source = source
        self.items = items
        self.started = None

    def __enter__(self):
        self.started = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        elapsed = time.perf_counter() - self.started

        record_performance(
            operation=self.operation,
            seconds=elapsed,
            model=self.model,
            source=self.source,
            items=self.items,
        )

        return False

def generate_report():
    """
    Generate a human-readable Markdown performance report
    from data/perf.jsonl.
    """

    report_path = PROJECT_ROOT / "perf.md"

    if not PERF_LOG.exists():
        report_path.write_text(
            "# StarFur Performance\n\n"
            "_No performance data recorded yet._\n",
            encoding="utf-8",
        )
        return report_path

    records = []

    with PERF_LOG.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            records.append(
                json.loads(line)
            )

    lines = [
        "# StarFur Performance",
        "",
        "Automatically generated from `data/perf.jsonl`.",
        "",
        "## General Performance",
        "",
        "| Timestamp | Operation | Model | Source | Items | Seconds | Sec/Item |",
        "|---|---|---|---|---:|---:|---:|",
    ]

    general_records = [
        record
        for record in records
        if "seconds" in record
    ]

    if general_records:
        for record in general_records:
            lines.append(
                "| "
                f"{record.get('timestamp', '—')} | "
                f"{record.get('operation', '—')} | "
                f"{record.get('model', '—')} | "
                f"{record.get('source', '—')} | "
                f"{record.get('items', '—')} | "
                f"{record.get('seconds', '—')} | "
                f"{record.get('seconds_per_item', '—')} |"
            )
    else:
        lines.append(
            "| — | — | — | — | — | — | — |"
        )

    lines.extend([
        "",
        "## LLM Performance",
        "",
        "| Timestamp | Operation | Model | Input Chars | Wall s | Ollama s | Prompt Tok | Output Tok | Tok/s |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ])

    llm_records = [
        record
        for record in records
        if "wall_seconds" in record
    ]

    if llm_records:
        for record in llm_records:
            lines.append(
                "| "
                f"{record.get('timestamp', '—')} | "
                f"{record.get('operation', '—')} | "
                f"{record.get('model', '—')} | "
                f"{record.get('input_chars', '—')} | "
                f"{record.get('wall_seconds', '—')} | "
                f"{record.get('total_seconds', '—')} | "
                f"{record.get('prompt_tokens', '—')} | "
                f"{record.get('output_tokens', '—')} | "
                f"{record.get('tokens_per_second', '—')} |"
            )
    else:
        lines.append(
            "| — | — | — | — | — | — | — | — | — |"
        )

    report_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return report_path
def record_llm_performance(
    operation: str,
    response,
    wall_seconds: float,
    model: str,
    source: str | None = None,
    input_chars: int | None = None,
):
    """
    Record detailed Ollama LLM performance metrics.
    """

    total_duration = getattr(
        response,
        "total_duration",
        None,
    )

    load_duration = getattr(
        response,
        "load_duration",
        None,
    )

    prompt_eval_count = getattr(
        response,
        "prompt_eval_count",
        None,
    )

    prompt_eval_duration = getattr(
        response,
        "prompt_eval_duration",
        None,
    )

    eval_count = getattr(
        response,
        "eval_count",
        None,
    )

    eval_duration = getattr(
        response,
        "eval_duration",
        None,
    )

    record = {
        "timestamp": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "operation": operation,
        "model": model,
        "wall_seconds": round(
            wall_seconds,
            4,
        ),
    }

    if source is not None:
        record["source"] = source

    if input_chars is not None:
        record["input_chars"] = input_chars

    if total_duration is not None:
        record["total_seconds"] = round(
            total_duration / 1_000_000_000,
            4,
        )

    if load_duration is not None:
        record["load_seconds"] = round(
            load_duration / 1_000_000_000,
            4,
        )

    if prompt_eval_count is not None:
        record["prompt_tokens"] = prompt_eval_count

    if prompt_eval_duration is not None:
        record["prompt_seconds"] = round(
            prompt_eval_duration / 1_000_000_000,
            4,
        )

    if eval_count is not None:
        record["output_tokens"] = eval_count

    if eval_duration is not None:
        output_seconds = (
            eval_duration / 1_000_000_000
        )

        record["output_seconds"] = round(
            output_seconds,
            4,
        )

        if eval_count is not None and output_seconds > 0:
            record["tokens_per_second"] = round(
                eval_count / output_seconds,
                2,
            )

    PERF_LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with PERF_LOG.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(record) + "\n"
        )

    generate_report()