# base/logger.py
# -*- coding:utf-8 -*-
import logging
import os
import re
import json
import time
import threading
from datetime import datetime, timezone

from .config import Config
# 获取当前文件的绝对路径
current_file_path = os.path.abspath(__file__)
# print(f'current_file_path--》{current_file_path}')
# 获取当前文件所在目录的绝对路径
current_dir_path = os.path.dirname(current_file_path)
# print(f'current_dir_path--》{current_dir_path}')
# 获取项目根目录的绝对路径
project_root = os.path.dirname(current_dir_path)

log_file_path = os.path.join(project_root, Config().LOG_FILE)


class SensitiveDataFilter(logging.Filter):
    """Mask common sensitive values before emitting logs."""

    def __init__(self):
        super().__init__()
        self._patterns = [
            (re.compile(r'(api[_-]?key\s*[=:]\s*)([^\s,;]+)', re.IGNORECASE), r'\1***'),
            (re.compile(r'(password\s*[=:]\s*)([^\s,;]+)', re.IGNORECASE), r'\1***'),
            (re.compile(r'(token\s*[=:]\s*)([^\s,;]+)', re.IGNORECASE), r'\1***'),
            (re.compile(r'(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)', re.IGNORECASE), r'\1***'),
            (re.compile(r'(sk-[A-Za-z0-9\-_]{8,})'), '***'),
        ]

    def filter(self, record):
        message = record.getMessage()
        masked = message
        for pattern, replacement in self._patterns:
            masked = pattern.sub(replacement, masked)

        if masked != message:
            record.msg = masked
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """Structured JSON formatter for machine-friendly logs."""

    def format(self, record):
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "event") and record.event:
            payload["event"] = record.event
        if hasattr(record, "request_id") and record.request_id:
            payload["request_id"] = record.request_id
        if hasattr(record, "fields") and isinstance(record.fields, dict):
            payload.update(record.fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ErrorAlertMonitor:
    """Simple in-process alerting when 5xx error rate spikes."""

    def __init__(self, threshold: int = 20, window_sec: int = 300):
        self.threshold = max(1, int(threshold or 1))
        self.window_sec = max(30, int(window_sec or 30))
        self._events = []
        self._last_alert_ts = 0.0
        self._lock = threading.Lock()

    def record_error(self):
        now = time.time()
        with self._lock:
            cutoff = now - self.window_sec
            self._events = [ts for ts in self._events if ts >= cutoff]
            self._events.append(now)

            # Avoid duplicate alert storms: at most one alert per window.
            if len(self._events) >= self.threshold and (now - self._last_alert_ts) >= self.window_sec:
                self._last_alert_ts = now
                return {
                    "error_count": len(self._events),
                    "window_sec": self.window_sec,
                    "threshold": self.threshold,
                }
        return None


def setup_logging(log_file=log_file_path):
    # 创建日志目录
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    # 获取日志器
    logger = logging.getLogger("EduRAG")
    # 设置日志级别
    logger.setLevel(logging.INFO)
    # print(f'logger.handlers-->{logger.handlers}')
    # 避免重复添加处理器
    if not logger.handlers:
        conf = Config()
        # 创建文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        # 设置文件处理器级别
        file_handler.setLevel(logging.INFO)
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        # 设置控制台处理器级别
        console_handler.setLevel(logging.INFO)
        # 设置日志格式
        if conf.LOG_STRUCTURED:
            formatter = JsonFormatter()
        else:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # 为文件处理器设置格式
        file_handler.setFormatter(formatter)
        # 为控制台处理器设置格式
        console_handler.setFormatter(formatter)
        # 添加文件处理器
        logger.addHandler(file_handler)
        # 添加控制台处理器
        logger.addHandler(console_handler)
        logger.addFilter(SensitiveDataFilter())
    # 返回日志器
    return logger


def log_event(level: str, event: str, **fields):
    """Helper for consistent structured log events."""
    level_name = (level or "info").lower()
    log_func = getattr(logger, level_name, logger.info)
    log_func(event, extra={"event": event, "fields": fields})

# 初始化日志器
logger = setup_logging()
