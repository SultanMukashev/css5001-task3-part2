"""D2.6 Config-driven pipelines with a plugin registry."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from d2_2_sources_sinks import solution as io_
from d2_3_transforms import solution as tf
from d2_4_quality_checks import solution as dq


class ConfigError(Exception):
    """Bad pipeline config. The message starts with the exact config path."""


class ParamError(ValueError):
    """Raised by a plugin constructor to blame one specific parameter."""

    def __init__(self, param: str, message: str):
        super().__init__(message)
        self.param = param


class Registered:
    registry: ClassVar[dict[str, dict[str, type]]] = {}

    def __init_subclass__(cls, *, kind: str | None = None, name: str | None = None, **kw):
        super().__init_subclass__(**kw)
        if kind and name:
            kinds = Registered.registry.setdefault(kind, {})
            if name in kinds:
                raise TypeError(f"{kind} plugin {name!r} already registered by {kinds[name].__name__}")
            kinds[name] = cls


def to_decimal(value) -> Decimal:
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f"not a number: {value!r}") from None
    if not d.is_finite():
        raise ValueError(f"not finite: {value!r}")
    return d


def to_int(value) -> int:
    return int(str(value).strip())


SCHEMAS: dict[str, dict] = {
    "orders": {"order_id": to_int, "amount": to_decimal},
    "clicks": {},
}

# ---- plugins: thin subclasses that only add a short name ----


class CsvSource(io_.CsvSource, Registered, kind="source", name="csv"): pass
class JsonLinesSource(io_.JsonLinesSource, Registered, kind="source", name="jsonl"): pass
class CsvSink(io_.CsvSink, Registered, kind="sink", name="csv"): pass
class JsonLinesSink(io_.JsonLinesSink, Registered, kind="sink", name="jsonl"): pass
class Deduplicate(tf.Deduplicate, Registered, kind="transform", name="dedupe"): pass
class Rename(tf.Rename, Registered, kind="transform", name="rename"): pass


class Cast(tf.Cast, Registered, kind="transform", name="cast"):
    def __init__(self, schema: str):
        if schema not in SCHEMAS:
            raise ParamError("schema", f"unknown schema {schema!r}; known: {sorted(SCHEMAS)}")
        super().__init__(SCHEMAS[schema])


class Filter(tf.Filter, Registered, kind="transform", name="filter"):
    def __init__(self, column: str, equals):
        super().__init__(lambda r: r.get(column) == equals)


class NotNull(dq.NotNull, Registered, kind="check", name="not_null"): pass
class Unique(dq.Unique, Registered, kind="check", name="unique"): pass
class InRange(dq.InRange, Registered, kind="check", name="in_range"): pass
class MatchesPattern(dq.MatchesPattern, Registered, kind="check", name="matches_pattern"): pass


class Freshness(dq.Freshness, Registered, kind="check", name="freshness"):
    def __init__(self, column: str, max_age_hours: float, severity: str = "error"):
        super().__init__(column, timedelta(hours=max_age_hours), severity)


# ---- builder ----

def instantiate(kind: str, spec, path: str):
    if not isinstance(spec, dict):
        raise ConfigError(f"{path}: expected an object")
    type_ = spec.get("type")
    if not isinstance(type_, str):
        raise ConfigError(f"{path}.type: missing or not a string")
    cls = Registered.registry.get(kind, {}).get(type_)
    if cls is None:
        known = sorted(Registered.registry.get(kind, {}))
        raise ConfigError(f"{path}.type: unknown {kind} type {type_!r}; known: {known}")
    params = {k: v for k, v in spec.items() if k != "type"}
    sig = inspect.signature(cls)
    for pname, p in sig.parameters.items():
        if p.default is p.empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) \
                and pname not in params:
            raise ConfigError(f"{path}.{pname}: missing required parameter")
    for pname in params:
        if pname not in sig.parameters:
            raise ConfigError(f"{path}.{pname}: unknown parameter for {kind} {type_!r}")
    try:
        return cls(**params)
    except ParamError as exc:
        raise ConfigError(f"{path}.{exc.param}: {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def _list(config: dict, key: str) -> list:
    value = config.get(key, [])
    if not isinstance(value, list):
        raise ConfigError(f"{key}: expected a list")
    return value


class _Tap(tf.Transform):
    """Keeps a copy of every record that reaches the sink, for the quality suite."""

    def __init__(self, store: list):
        self.store = store

    def apply(self, record):
        self.store.append(record)
        return record


@dataclass
class BuiltPipeline:
    pipeline: tf.Pipeline
    suite: dq.QualitySuite
    sink: io_.Sink

    def run(self) -> tuple[tf.RunStats, dq.SuiteReport]:
        loaded: list[dict] = []  # shortcut: output kept in memory for checks; sample in a stream for huge runs
        stats = (self.pipeline | _Tap(loaded)).into(self.sink)
        stats.steps.pop()  # hide the internal tap from the step stats
        return stats, self.suite.run(loaded)


def build(config) -> BuiltPipeline:
    if not isinstance(config, dict):
        raise ConfigError("<root>: expected a JSON object")
    for key in ("source", "sink"):
        if key not in config:
            raise ConfigError(f"{key}: missing")
    source = instantiate("source", config["source"], "source")
    transforms = [instantiate("transform", t, f"transforms[{i}]")
                  for i, t in enumerate(_list(config, "transforms"))]
    checks = [instantiate("check", c, f"checks[{i}]") for i, c in enumerate(_list(config, "checks"))]
    sink = instantiate("sink", config["sink"], "sink")
    return BuiltPipeline(tf.Pipeline(source, transforms), dq.QualitySuite(checks), sink)


def load_config(path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON at line {exc.lineno}: {exc.msg}") from exc
