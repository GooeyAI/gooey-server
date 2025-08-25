"""
Function call status management for real-time updates during streaming responses.
"""

import threading
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FunctionCallStatus:
    """Represents the status of a function call."""
    id: str
    name: str
    status: str  # 'calling', 'called', 'failed'
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class FunctionStatusManager:
    """Manages function call statuses across a saved run."""
    
    def __init__(self):
        self._statuses: Dict[str, FunctionCallStatus] = {}
        self._lock = threading.Lock()
    
    def start_function_call(self, call_id: str, function_name: str) -> None:
        """Mark a function call as started."""
        with self._lock:
            self._statuses[call_id] = FunctionCallStatus(
                id=call_id,
                name=function_name,
                status='calling'
            )
    
    def complete_function_call(self, call_id: str, error: Optional[str] = None) -> None:
        """Mark a function call as completed."""
        with self._lock:
            if call_id in self._statuses:
                status = self._statuses[call_id]
                status.completed_at = datetime.now()
                status.status = 'failed' if error else 'called'
                status.error = error
    
    def get_status_dict(self) -> Dict[str, str]:
        """Get current status for all function calls."""
        with self._lock:
            return {call_id: status.status for call_id, status in self._statuses.items()}
    
    def get_active_calls(self) -> Dict[str, FunctionCallStatus]:
        """Get all currently active (calling) function calls."""
        with self._lock:
            return {
                call_id: status 
                for call_id, status in self._statuses.items() 
                if status.status == 'calling'
            }
    
    def clear(self) -> None:
        """Clear all statuses."""
        with self._lock:
            self._statuses.clear()


# Global manager instances per saved run
_managers: Dict[str, FunctionStatusManager] = {}
_managers_lock = threading.Lock()


def get_status_manager(saved_run_id: str) -> FunctionStatusManager:
    """Get or create a status manager for a saved run."""
    with _managers_lock:
        if saved_run_id not in _managers:
            _managers[saved_run_id] = FunctionStatusManager()
        return _managers[saved_run_id]


def cleanup_status_manager(saved_run_id: str) -> None:
    """Clean up status manager for a completed run."""
    with _managers_lock:
        _managers.pop(saved_run_id, None)


def render_function_status_text(call_id: str, function_name: str, status: str) -> str:
    """Render function status as markdown text for streaming updates."""
    if status == 'calling':
        return f"🧩 **Calling {function_name}** ⏳"
    elif status == 'called':
        return f"🧩 **Called {function_name}** ✅"
    elif status == 'failed':
        return f"🧩 **Failed {function_name}** ❌"
    else:
        return f"🧩 **{function_name}** ({status})"
