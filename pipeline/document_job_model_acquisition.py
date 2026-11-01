"""Explicit fixed-path loopback metadata transport; disconnected by default.

Declarations do not establish artifact bytes, execution locality, cloud policy,
consent or readiness. Trusted fake factories are not hostile-plugin isolation.
"""
from dataclasses import dataclass, field
from http.client import HTTPConnection
import math
import sys
import time
from urllib.parse import urlsplit

from pipeline.document_job_model import MAX_LOCAL_MODEL_LISTING_BYTES, inspect_ollama_local_model_listing
from pipeline.document_job_model_request import ModelListingRequest


MODEL_LISTING_TIMEOUT_SECONDS = 10


class ModelListingAcquisitionError(RuntimeError):
    """Content-free acquisition or cleanup failure."""


@dataclass(frozen=True, init=False, repr=False, eq=False)
class ModelListingAcquirer:
    _request: ModelListingRequest = field(repr=False)
    _factory: object = field(repr=False)
    _clock: object = field(repr=False)

    def __init__(self, request, *, _connection_factory=None, _clock=None):
        factory = HTTPConnection if _connection_factory is None else _connection_factory
        clock = time.monotonic if _clock is None else _clock
        if type(request) is not ModelListingRequest or not callable(factory) or not callable(clock):
            raise ModelListingAcquisitionError("model listing acquisition is unavailable")
        for key, value in (("_request", request), ("_factory", factory), ("_clock", clock)):
            object.__setattr__(self, key, value)

    def inspect(self):
        connection = response = None
        try:
            started = self._clock()
            if type(started) not in (int, float) or not math.isfinite(started):
                raise ValueError
            previous = started

            def remaining():
                nonlocal previous
                now = self._clock()
                if (type(now) not in (int, float) or not math.isfinite(now)
                        or now < previous or now - started >= MODEL_LISTING_TIMEOUT_SECONDS):
                    raise TimeoutError
                previous = now
                return MODEL_LISTING_TIMEOUT_SECONDS - (now - started)

            endpoint = urlsplit(self._request.target.endpoint)
            connection = self._factory(endpoint.hostname, endpoint.port, timeout=remaining())
            connection.timeout = remaining()
            connection.connect()
            wire = connection.sock
            wire.settimeout(remaining())
            connection.request("GET", "/api/tags", headers={"Accept": "application/json",
                               "Accept-Encoding": "identity", "Connection": "close"})
            wire.settimeout(remaining())
            response = connection.getresponse()
            if (response.status != 200
                    or response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json"
                    or response.getheader("Content-Encoding", "identity").strip().lower() != "identity"):
                raise ValueError
            parts, size = [], 0
            while True:
                wire.settimeout(remaining())
                part = response.read1(min(16384, MAX_LOCAL_MODEL_LISTING_BYTES + 1 - size))
                if type(part) is not bytes:
                    raise ValueError
                if not part:
                    break
                size += len(part)
                if size > MAX_LOCAL_MODEL_LISTING_BYTES:
                    raise ValueError
                parts.append(part)
            remaining()
            result = inspect_ollama_local_model_listing(b"".join(parts), self._request.model)
            remaining()
            return result
        except Exception:
            raise ModelListingAcquisitionError("model listing acquisition failed safely") from None
        finally:
            pending = sys.exc_info()[0] is not None
            failed = False
            for resource in (response, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        failed = True
            if failed and not pending:
                raise ModelListingAcquisitionError("model listing cleanup failed safely") from None
