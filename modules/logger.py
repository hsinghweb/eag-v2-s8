# modules/logger.py

"""
File-based logging system for tracking tool calls and LLM interactions
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import threading

# Create logs directory if it doesn't exist
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Thread lock for file writing
_file_lock = threading.Lock()


class AgentLogger:
    """File-based logger for agent operations"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Log files
        self.tools_log = LOGS_DIR / f"tools_{self.timestamp}_{session_id[:8]}.log"
        self.llm_log = LOGS_DIR / f"llm_{self.timestamp}_{session_id[:8]}.log"
        self.workflow_log = LOGS_DIR / f"workflow_{self.timestamp}_{session_id[:8]}.log"
        self.errors_log = LOGS_DIR / f"errors_{self.timestamp}_{session_id[:8]}.log"
        
        # Initialize log files with headers
        self._init_log_file(self.tools_log, "TOOL CALLS LOG")
        self._init_log_file(self.llm_log, "LLM CALLS LOG")
        self._init_log_file(self.workflow_log, "WORKFLOW LOG")
        self._init_log_file(self.errors_log, "ERRORS LOG")
    
    def _init_log_file(self, log_file: Path, header: str):
        """Initialize log file with header"""
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"{'='*80}\n")
            f.write(f"{header}\n")
            f.write(f"Session ID: {self.session_id}\n")
            f.write(f"Started: {datetime.now().isoformat()}\n")
            f.write(f"{'='*80}\n\n")
    
    def _write_log(self, log_file: Path, entry: Dict[str, Any]):
        """Thread-safe log file writing"""
        with _file_lock:
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().isoformat()
                entry['timestamp'] = timestamp
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                f.flush()
    
    def log_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any, 
                     duration_ms: Optional[float] = None, error: Optional[str] = None):
        """Log a tool call"""
        entry = {
            'type': 'tool_call',
            'tool_name': tool_name,
            'arguments': arguments,
            'result': str(result)[:1000] if result else None,  # Truncate long results
            'duration_ms': duration_ms,
            'error': error,
            'session_id': self.session_id
        }
        self._write_log(self.tools_log, entry)
    
    def log_llm_call(self, model_name: str, prompt_type: str, prompt: str, 
                    response: str, duration_ms: Optional[float] = None, 
                    error: Optional[str] = None):
        """Log an LLM call"""
        entry = {
            'type': 'llm_call',
            'model_name': model_name,
            'prompt_type': prompt_type,  # 'perception', 'decision', 'other'
            'prompt_length': len(prompt),
            'response_length': len(response),
            'prompt_preview': prompt[:500],  # First 500 chars
            'response_preview': response[:500],  # First 500 chars
            'duration_ms': duration_ms,
            'error': error,
            'session_id': self.session_id
        }
        self._write_log(self.llm_log, entry)
    
    def log_workflow_step(self, step_number: int, phase: str, status: str, 
                         details: Optional[str] = None):
        """Log workflow step"""
        entry = {
            'type': 'workflow_step',
            'step_number': step_number,
            'phase': phase,  # 'perception', 'memory', 'decision', 'execution', 'completion'
            'status': status,  # 'started', 'completed', 'failed', 'skipped'
            'details': details,
            'session_id': self.session_id
        }
        self._write_log(self.workflow_log, entry)
    
    def log_verification(self, step_name: str, verified: bool, details: str):
        """Log step verification"""
        entry = {
            'type': 'verification',
            'step_name': step_name,
            'verified': verified,
            'details': details,
            'session_id': self.session_id
        }
        self._write_log(self.workflow_log, entry)
    
    def log_error(self, error_type: str, error_message: str, traceback: Optional[str] = None):
        """Log an error"""
        entry = {
            'type': 'error',
            'error_type': error_type,
            'error_message': error_message,
            'traceback': traceback,
            'session_id': self.session_id
        }
        self._write_log(self.errors_log, entry)
    
    def log_step_completion(self, step_name: str, verified: bool, next_step: Optional[str] = None):
        """Log completion of a workflow step"""
        entry = {
            'type': 'step_completion',
            'step_name': step_name,
            'verified': verified,
            'next_step': next_step,
            'session_id': self.session_id
        }
        self._write_log(self.workflow_log, entry)


# Global logger instance (will be set per session)
_logger_instance: Optional[AgentLogger] = None


def get_logger() -> Optional[AgentLogger]:
    """Get the current logger instance"""
    return _logger_instance


def set_logger(logger: AgentLogger):
    """Set the global logger instance"""
    global _logger_instance
    _logger_instance = logger


def log_tool_call(tool_name: str, arguments: Dict[str, Any], result: Any, 
                 duration_ms: Optional[float] = None, error: Optional[str] = None):
    """Convenience function to log tool call"""
    logger = get_logger()
    if logger:
        logger.log_tool_call(tool_name, arguments, result, duration_ms, error)


def log_llm_call(model_name: str, prompt_type: str, prompt: str, response: str,
                duration_ms: Optional[float] = None, error: Optional[str] = None):
    """Convenience function to log LLM call"""
    logger = get_logger()
    if logger:
        logger.log_llm_call(model_name, prompt_type, prompt, response, duration_ms, error)

