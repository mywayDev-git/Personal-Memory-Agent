"""Safe explanations for worker failures, without raw exception/model contents."""

import sqlite3

from scripts.memory_agent.diagnostics import failure

PHASES = {
    "health": "AI 서버 연결 확인", "maintenance": "휴지통 만료 기록 정리",
    "model_wait": "AI 사용 순서 대기", "rebuild": "검색 자료 재구축",
    "claim": "대기 기록 조회", "failure_save": "처리 실패 상태 저장",
    "extract": "기억 추출·검증", "embed": "검색 벡터 생성", "save": "기억 저장",
}
HELP = {
    "MODEL_UNAVAILABLE": ("로컬 AI 서버에 연결하지 못했습니다.",
                          "모델 서버가 실행 중인지 확인하세요. 서버 복구 후 실패 기록을 재시도하세요."),
    "MODEL_TIMEOUT": ("AI 응답 대기 시간을 초과했습니다.",
                      "모델 로딩·PC 자원 사용량을 확인하고 실패 기록을 재시도하세요."),
    "MODEL_HTTP_ERROR": ("AI 서버가 오류 응답을 반환했습니다.",
                         "모델 서버 상태와 모델 설정을 확인한 뒤 재시도하세요."),
    "DB_BUSY": ("다른 작업이 데이터베이스를 사용 중입니다.",
                "다른 DB 편집·가져오기 작업이 끝나면 자동 재시도합니다."),
    "DB_ERROR": ("데이터베이스 작업이 실패했습니다.",
                 "저장 폴더 권한과 디스크 여유 공간을 확인하세요. 계속되면 앱을 종료하고 DB를 백업한 뒤 점검하세요."),
    "FILE_PERMISSION": ("파일 접근 권한이 부족합니다.",
                        "저장 폴더·백업 파일의 쓰기 권한과 보안 프로그램 차단 여부를 확인하세요."),
    "DISK_FULL": ("저장 공간이 부족합니다.", "저장 드라이브의 여유 공간을 확보한 뒤 재시도하세요."),
    "FILE_ERROR": ("파일 작업이 실패했습니다.",
                   "저장 경로가 존재하는지, 드라이브 연결과 쓰기 권한을 확인하세요."),
}
VALIDATION_CODES = {
    "MODEL_TRUNCATED", "MODEL_INVALID_JSON", "MODEL_INVALID_RESPONSE", "MODEL_EMPTY_RESPONSE",
    "INVALID_EXTRACTION_SCHEMA", "INVALID_EXTRACTION_EVIDENCE_OR_SCHEMA", "INVALID_EVIDENCE",
    "EXTRACTION_INVALID", "INVALID_SOURCE_CONTEXT",
}
VECTOR_CODES = {"INVALID_EMBEDDING", "INVALID_EMBEDDING_RESPONSE", "VECTOR_COUNT_MISMATCH"}


def describe_failure(exc, phase):
    code, _ = failure(exc, phase)
    if isinstance(exc, sqlite3.Error):
        number = getattr(exc, "sqlite_errorcode", 0) or 0
        base = number & 255
        code = "DB_BUSY" if base in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else "DB_ERROR"
        if base == sqlite3.SQLITE_FULL:
            code = "DISK_FULL"
    elif isinstance(exc, PermissionError):
        code = "FILE_PERMISSION"
    elif isinstance(exc, OSError) and not code.startswith("MODEL_"):
        code = "DISK_FULL" if exc.errno == 28 else "FILE_ERROR"
    if code in VALIDATION_CODES:
        reason, remedy = ("AI가 반환한 기억이 형식·원문 근거 검증을 통과하지 못했습니다.",
                          "실패 기록을 재시도하세요. 반복되면 원문과 모델 설정을 확인하세요.")
    elif code in VECTOR_CODES:
        reason, remedy = ("검색 벡터의 개수·형식·차원이 설정과 맞지 않습니다.",
                          "임베딩 모델과 차원 설정이 실행 중인 서버와 같은지 확인한 뒤 재시도하세요.")
    else:
        reason, remedy = HELP.get(code, (
            "예상하지 못한 내부 오류입니다. 현재 정보만으로 정확한 원인은 확정할 수 없습니다.",
            "반복되면 아래 단계·오류 코드·오류 종류를 전달해 주세요. 원문이나 DB를 삭제하지 마세요.",
        ))
    # Never echo arbitrary exception codes/messages, which may contain personal text.
    if code not in HELP and code not in VALIDATION_CODES and code not in VECTOR_CODES:
        code = "INTERNAL_PROCESSING_ERROR"
    return dict(code=code, phase=PHASES.get(phase, "기록 처리"),
                exception_type=type(exc).__name__, reason=reason, remedy=remedy)
