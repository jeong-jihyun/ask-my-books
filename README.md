# ask-my-books: 내 서재 AI 검색

PDF/EPUB 책을 PC에서 검색 가능하게 만들고, 질문하면 관련 내용을 찾아 AI가 답해줍니다.
책 내용은 밖으로 나가지 않습니다 (Ollama 로컬 실행).

## 파일 구성

| 파일 | 하는 일 |
|---|---|
| `config.py` | 폴더 경로, 모델 이름 등 설정 (여기만 고치면 됨) |
| `ingest.py` | 책 → 글자 뽑기 → (스캔본이면 OCR) → 조각내기 → 검색 DB 저장 |
| `ask.py` | 질문 → 관련 조각 찾기 → AI 답변 |
| `common.py` | 위 두 프로그램이 같이 쓰는 도구 |

## 빠른 시작 (Windows)

1. Python 3.11/3.12 설치 ("Add python.exe to PATH" 체크), Ollama 설치
2. `setup.bat` 더블클릭 (패키지 설치 + 모델 받기)
3. `config.py` 에서 `BOOKS_DIR`, `DATA_DIR` 수정
4. `run_ingest.bat --limit 50` 으로 시험 → `run_ask.bat` 으로 질문

자세한 설명은 `TUTORIAL.md` 를 보세요. 아래는 수동 설치 방법입니다.

## 1. 처음 한 번만 설치

```
pip install -r requirements.txt
ollama pull bge-m3
```

- `bge-m3`는 한국어 책 검색에 좋은 모델입니다. (용량 약 1.2GB)
- **스캔본(글자 복사가 안 되는 PDF)이 있을 때만** Tesseract가 추가로 필요합니다.
  - Windows: https://github.com/UB-Mannheim/tesseract/wiki 에서 설치
  - 설치 중 **Additional language data → Korean** 을 꼭 체크하세요.
  - 설치 후 `tesseract` 명령이 안 먹으면 `config.py`의 `TESSERACT_CMD`에 경로를 적으세요.

## 2. 설정

`config.py`를 열어 아래 두 곳만 바꾸세요.

- `BOOKS_DIR` : 책 파일이 있는 폴더
- `DATA_DIR` : 결과물을 저장할 폴더 (여유 공간 있는 드라이브)
- `CHAT_MODEL` : 답변에 쓸 Ollama 모델 이름 (`ollama list`에 보이는 그대로)

## 3. 책 등록

```
python ingest.py --limit 50
```

- **처음엔 50권만** 해보세요. 검색이 쓸 만한지 먼저 확인하는 게 좋습니다.
- 다시 실행하면 이미 처리한 책은 건너뛰고 이어서 합니다. 중간에 Ctrl+C로 멈춰도 괜찮아요.
- 실패한 책은 `DATA_DIR/failed.log`에 이유와 함께 기록됩니다.

## 4. 질문하기

```
python ask.py "자동화로 수익 만든 사례 알려줘"
python ask.py "블로그 자동화" --ideas          # 아이디어 5개 뽑기
python ask.py "수익화" --search-only          # AI 없이 관련 발췌만 보기
python ask.py                                  # 대화 모드
```

## 용량이 부족할 때: 나눠서 처리하기

마이박스에서 한 번에 다 받지 않고 이렇게 반복하세요.

1. 마이박스에서 책 5~10GB를 `BOOKS_DIR`로 내려받기
2. `python ingest.py --delete-original`
3. 끝나면 PC의 원본이 자동 삭제됩니다 (마이박스 원본은 그대로)
4. 다음 묶음으로 1번부터 반복

PC에 남는 것은 텍스트와 검색 DB뿐이라 훨씬 적은 공간으로 충분합니다.
`--delete-original`은 **PC에 내려받은 파일만** 지웁니다. 처음엔 옵션 없이 소량으로 먼저 확인하세요.

## 알아둘 점

- 스캔본은 OCR 때문에 오래 걸립니다 (한 권에 수 분~수십 분).
- DRM이 걸린 전자책은 글자를 뽑을 수 없어 실패로 기록됩니다.
- 책 문장을 블로그나 상품에 그대로 옮기지 말고, 아이디어와 구조만 참고해 내 말로 쓰세요.
- 검색 품질이 아쉬우면 `config.py`의 `CHUNK_SIZE`(조각 크기)를 조절한 뒤, `DATA_DIR/db`와 `done.json`을 지우고 다시 등록하세요.
