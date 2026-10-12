"""공통 도구: Ollama로 '의미 숫자' 만들기 + 검색 DB 열기"""
import sys

import chromadb
import requests

import config


def setup_console():
    """Windows 콘솔에서 한글이 깨지지 않게"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def ollama_options():
    """config.OLLAMA_NUM_GPU 가 지정돼 있으면 Ollama 요청에 GPU 옵션으로 전달"""
    if config.OLLAMA_NUM_GPU is None:
        return {}
    return {"num_gpu": config.OLLAMA_NUM_GPU}


def embed_texts(texts):
    """글 목록 -> 의미 숫자 목록 (Ollama 사용)"""
    payload = {"model": config.EMBED_MODEL, "input": texts}
    if ollama_options():
        payload["options"] = ollama_options()
    r = requests.post(f"{config.OLLAMA_URL}/api/embed", json=payload, timeout=600)
    if r.status_code == 404:
        raise RuntimeError(
            f"임베딩 모델 '{config.EMBED_MODEL}'이 없습니다. "
            f"터미널에서 `ollama pull {config.EMBED_MODEL}` 을 먼저 실행하세요."
        )
    if r.status_code == 500:
        raise RuntimeError(
            "Ollama가 오류로 종료됐습니다 (GPU/Vulkan 문제일 수 있음). "
            "config.py의 OLLAMA_NUM_GPU = 0 으로 바꿔 CPU로 실행해 보세요.\n"
            f"상세: {r.text[:200]}"
        )
    r.raise_for_status()
    return r.json()["embeddings"]


def check_ollama():
    """Ollama가 켜져 있고 임베딩 모델이 있는지 미리 확인"""
    try:
        embed_texts(["테스트"])
    except requests.exceptions.ConnectionError:
        print("❌ Ollama에 연결할 수 없습니다. Ollama 앱이 실행 중인지 확인하세요.")
        sys.exit(1)
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def get_collection():
    """검색 DB(Chroma) 열기. 없으면 새로 만듦"""
    db_path = config.DATA_DIR / "db"
    db_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(db_path))
    return client.get_or_create_collection(
        "library", metadata={"hnsw:space": "cosine"}
    )
