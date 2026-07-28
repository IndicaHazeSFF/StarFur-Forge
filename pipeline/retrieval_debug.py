from dataclasses import dataclass, field
import json
import time

DEBUG_LEVELS = ("off", "summary", "verbose", "trace")


@dataclass
class RetrievalTrace:
    level: str = "off"
    events: list = field(default_factory=list)
    started_at: float = field(default_factory=time.perf_counter)

    def __post_init__(self):
        if self.level not in DEBUG_LEVELS:
            raise ValueError(f"Invalid debug level: {self.level!r}")

    def record(self, event, **data):
        if self.level == "off":
            return
        item = {"event": event, **data}
        if self.level == "trace":
            item["elapsed_ms"] = round((time.perf_counter() - self.started_at) * 1000, 2)
        self.events.append(item)

    def render(self):
        if self.level == "off" or not self.events:
            return ""
        lines = ["=== RETRIEVAL DEBUG ==="]
        for item in self.events:
            event = item["event"]
            data = {key: value for key, value in item.items() if key != "event"}
            if self.level == "summary":
                data = {
                    key: value for key, value in data.items()
                    if key in {"domain", "count", "selected_count", "message_count", "model", "status", "command"}
                }
            elif self.level == "verbose":
                data.pop("elapsed_ms", None)
            lines.append(f"{event}: {json.dumps(data, ensure_ascii=False, default=str)}")
        lines.append("=== END RETRIEVAL DEBUG ===")
        return "\n".join(lines)

    def emit(self, output):
        rendered = self.render()
        if rendered:
            output(rendered)


def normalize_debug_level(level):
    if level not in DEBUG_LEVELS:
        raise ValueError(f"Invalid debug level: {level!r}")
    return level
