# 저장소 조사 (2026-10-18)

- 시작 브랜치: `codex/checkpoint-memory-chat-20261018`.
- 작업 브랜치: `codex/selective-memory-capture`. 현재 HEAD에서 생성했으며 미커밋 변경을 유지했다.
- 시작 시 `pma/chat/api.py` 수정, `tests/`, `evaluation/conversation_modes_results.rst` 미추적 상태였다. 이를 삭제하거나 덮어쓰지 않았다.
- Python 3.14.8, FastAPI/Pydantic, SQLite, NumPy, requests. 기존 `.venv`를 사용했다.
- 적용되는 AGENTS.md는 조사한 저장소와 상위 경로에서 발견되지 않았다.
- 검색: `pma/service.py`, `pma/store.py`, `pma/facts.py`, `pma/grounding.py`, `pma/answer_review.py`.
- 대화: `pma/chat/engine.py`, `automatic.py`, `store.py`, `schema.py`, `schemas.py`, `api.py`.
- 웹: `pma/web.py`, `pma/static/{index.html,app.js,chat.js,style.css}`.
- Qwen3-8B/BGE-M3는 기존 `LocalModels`와 공유 모델 슬롯을 재사용한다. 새 모델 서버나 유료 API를 추가하지 않았다.
- `evaluation/`에는 평가 저장소와 기존 결과가 있었으나, 현재 체크아웃의 테스트 파일은 `tests/test_chat_mode_api.py` 한 개였다. 과거 보고서의 606개 테스트를 현재 실행 가능한 것으로 간주하지 않았다.
- Python 3.14는 `except TypeError, ValueError:` 문법을 지원한다. `compileall`로 실제 문법 검사를 수행했다.

운영 DB, `.local`, `.venv`, 기존 평가 결과는 직접 변경하지 않았다. 기능 검증에는 새 임시 DB와 합성 대화만 사용했다.
