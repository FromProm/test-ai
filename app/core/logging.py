import logging
import sys
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

class StructuredLogger:
    """CloudWatch 친화적인 구조화된 JSON 로거"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.name = name
    
    def _format_log(
        self,
        level: str,
        message: str,
        request_id: Optional[str] = None,
        stage: Optional[str] = None,
        error_type: Optional[str] = None,
        retry_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "logger": self.name,
            "message": message
        }
        
        if request_id:
            log_entry["request_id"] = request_id
        if stage:
            log_entry["stage"] = stage
        if error_type:
            log_entry["error_type"] = error_type
        if retry_count > 0:
            log_entry["retry_count"] = retry_count
        if metadata:
            log_entry["metadata"] = metadata
        
        return json.dumps(log_entry, ensure_ascii=False)
    
    def info(self, message: str, **kwargs):
        self.logger.info(self._format_log("INFO", message, **kwargs))
    
    def warning(self, message: str, **kwargs):
        self.logger.warning(self._format_log("WARNING", message, **kwargs))
    
    def error(self, message: str, **kwargs):
        self.logger.error(self._format_log("ERROR", message, **kwargs))
    
    def debug(self, message: str, **kwargs):
        self.logger.debug(self._format_log("DEBUG", message, **kwargs))


class JsonFormatter(logging.Formatter):
    """JSON 포맷 로그 핸들러용 포매터"""
    
    def format(self, record):
        # 이미 JSON 형태면 그대로 반환
        if record.msg.startswith('{'):
            return record.msg
        
        # 일반 메시지는 JSON으로 변환
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging():
    """Setup logging configuration with JSON format for CloudWatch"""
    
    # JSON 포매터 생성
    json_formatter = JsonFormatter()
    
    # 콘솔 핸들러 (개발용 - 일반 포맷)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # 파일 핸들러 (CloudWatch용 - JSON 포맷)
    file_handler = logging.FileHandler('prompt_eval.log')
    file_handler.setFormatter(json_formatter)
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_structured_logger(name: str) -> StructuredLogger:
    """구조화된 로거 인스턴스 반환"""
    return StructuredLogger(name)


logger = logging.getLogger(__name__)