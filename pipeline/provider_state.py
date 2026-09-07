"""Bounded provider/model lifecycle state for shared diagnostics."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any

class ProviderLifecycleState(str, Enum):
    DISCONNECTED="disconnected"; CONNECTING="connecting"; LOADING="loading"; READY="ready"; IDLE="idle"; GENERATING="generating"; STREAMING="streaming"; COOLING="cooling"; UNLOADING="unloading"; ERROR="error"

@dataclass(frozen=True)
class ProviderLifecycleSnapshot:
    provider: str
    model: str
    state: str
    previous_state: str | None
    error: str | None
    transition_count: int

class ProviderLifecycle:
    _allowed={
      ProviderLifecycleState.DISCONNECTED:{ProviderLifecycleState.CONNECTING,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.CONNECTING:{ProviderLifecycleState.LOADING,ProviderLifecycleState.READY,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.LOADING:{ProviderLifecycleState.READY,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.READY:{ProviderLifecycleState.IDLE,ProviderLifecycleState.GENERATING,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.IDLE:{ProviderLifecycleState.GENERATING,ProviderLifecycleState.COOLING,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.GENERATING:{ProviderLifecycleState.STREAMING,ProviderLifecycleState.IDLE,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.STREAMING:{ProviderLifecycleState.IDLE,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.COOLING:{ProviderLifecycleState.UNLOADING,ProviderLifecycleState.IDLE,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.UNLOADING:{ProviderLifecycleState.DISCONNECTED,ProviderLifecycleState.IDLE,ProviderLifecycleState.ERROR},
      ProviderLifecycleState.ERROR:{ProviderLifecycleState.CONNECTING,ProviderLifecycleState.IDLE,ProviderLifecycleState.DISCONNECTED},
    }
    def __init__(self, provider: str, model: str):
        self._lock=RLock(); self._provider=str(provider or "unknown"); self._model=str(model or "unknown"); self._state=ProviderLifecycleState.DISCONNECTED; self._previous=None; self._error=None; self._count=0
    def transition(self,state: ProviderLifecycleState | str, *, error: str | None=None):
        target=state if isinstance(state,ProviderLifecycleState) else ProviderLifecycleState(state)
        with self._lock:
            if target != self._state and target not in self._allowed[self._state]: raise ValueError(f"Invalid provider lifecycle transition: {self._state.value} -> {target.value}")
            self._previous=self._state if target != self._state else self._previous; self._state=target; self._error=str(error)[:300] if error else None; self._count+=1
            return self.snapshot()
    def begin_generation(self, *, stream: bool, model: str | None=None, provider: str | None=None):
        with self._lock:
            if provider:
                self._provider=str(provider)
            if model: self._model=str(model)
            if self._state in {ProviderLifecycleState.DISCONNECTED,ProviderLifecycleState.ERROR}:
                self.transition(ProviderLifecycleState.CONNECTING); self.transition(ProviderLifecycleState.READY)
            elif self._state == ProviderLifecycleState.CONNECTING: self.transition(ProviderLifecycleState.READY)
            elif self._state == ProviderLifecycleState.LOADING: self.transition(ProviderLifecycleState.READY)
            elif self._state not in {ProviderLifecycleState.READY,ProviderLifecycleState.IDLE}: self._state=ProviderLifecycleState.IDLE
            self.transition(ProviderLifecycleState.GENERATING)
            return self.transition(ProviderLifecycleState.STREAMING) if stream else self.snapshot()
    def finish(self):
        with self._lock:
            return self.transition(ProviderLifecycleState.IDLE) if self._state in {ProviderLifecycleState.GENERATING,ProviderLifecycleState.STREAMING} else self.snapshot()
    def fail(self,error: Any):
        with self._lock:
            if self._state != ProviderLifecycleState.ERROR:
                if ProviderLifecycleState.ERROR not in self._allowed.get(self._state,set()): self._state=ProviderLifecycleState.IDLE
                self.transition(ProviderLifecycleState.ERROR,error=str(error))
            return self.snapshot()
    def snapshot(self): return ProviderLifecycleSnapshot(self._provider,self._model,self._state.value,self._previous.value if self._previous else None,self._error,self._count)
    def public_dict(self):
        s=self.snapshot(); return {"provider":s.provider,"model":s.model,"state":s.state,"previous_state":s.previous_state,"error":s.error,"transition_count":s.transition_count}

__all__=["ProviderLifecycle","ProviderLifecycleSnapshot","ProviderLifecycleState"]
