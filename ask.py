"""
내 서재에 질문하기

사용법
  python ask.py "자동화 수익화 사례 알려줘"          # 검색 + AI 답변
  python ask.py "자동화 수익화" --search-only        # AI 없이 관련 발췌만 보기
  python ask.py "블로그 자동화" --ideas              # 발췌를 조합해 아이디어 뽑기
  python ask.py                                      # 질문 계속 입력하는 대화 모드
"""
import argparse
import json

import requests

import config
from common import check_ollama, embed_texts, get_collection, ollama_options, setup_console

ANSWER_PROMPT = (
    "당신은 사용자의 개인 서재를 참고해 답하는 도우미입니다.\n"
    "- 아래 [발췌]에 있는 내용을 근거로 답하고, 근거마다 [번호]를 붙이세요.\n"
    "- 발췌에 없는 내용은 '서재에서는 찾지 못했습니다'라고 말하고, "
    "일반 지식을 덧붙일 때는 '(추가 의견)'이라고 구분하세요.\n"
    "- 책 문장을 길게 그대로 옮기지 말고, 자기 말로 짧게 정리하세요.\n"
    "- 한국어로, 쉽고 간단하게 쓰세요."
)

IDEAS_PROMPT = (
    "당신은 사용자의 개인 서재에서 영감을 뽑아 아이디어를 내는 도우미입니다.\n"
    "- 아래 [발췌]들의 내용을 조합해서, 질문에 맞는 실행 가능한 아이디어 5개를 제안하세요.\n"
    "- 아이디어마다 (1) 한 줄 요약 (2) 어떤 발췌에서 힌트를 얻었는지 [번호] "
    "(3) 오늘 바로 해볼 첫 단계 를 적으세요.\n"
    "- 책 문장을 그대로 옮기지 말고 자기 말로 쓰세요.\n"
    "- 한국어로, 쉽고 간단하게 쓰세요."
)


def search(question, k=None, per_book=None):
    """질문과 비슷한 조각을 찾되, 한 책이 결과를 독차지하지 않게 함"""
    k = k or config.TOP_K
    per_book = per_book or config.MAX_PER_BOOK
    col = get_collection()
    if col.count() == 0:
        return []

    emb = embed_texts([question])[0]
    res = col.query(
        query_embeddings=[emb],
        n_results=min(k * 4, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits, count = [], {}
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        bid = meta["book_id"]
        if count.get(bid, 0) >= per_book:
            continue
        count[bid] = count.get(bid, 0) + 1
        hits.append({"text": doc, "title": meta["title"], "loc": meta["loc"], "score": 1 - dist})
        if len(hits) >= k:
            break
    return hits


def show_hits(hits):
    for i, h in enumerate(hits, start=1):
        preview = h["text"].replace("\n", " ")
        preview = preview[:200] + ("…" if len(preview) > 200 else "")
        print(f"[{i}] {h['title']} · {h['loc']}  (유사도 {h['score']:.2f})")
        print(f"    {preview}\n")


def ask_llm(question, hits, ideas=False):
    context = "\n\n".join(
        f"[{i}] ({h['title']} · {h['loc']})\n{h['text']}" for i, h in enumerate(hits, start=1)
    )
    payload = {
        "model": config.CHAT_MODEL,
        "stream": True,
        "think": False,  # Qwen3 같은 모델의 '긴 생각 과정'을 끄고 바로 답하게 함 (빠름)
        "messages": [
            {"role": "system", "content": IDEAS_PROMPT if ideas else ANSWER_PROMPT},
            {"role": "user", "content": f"질문: {question}\n\n[발췌]\n{context}"},
        ],
    }
    if ollama_options():
        payload["options"] = ollama_options()
    with requests.post(
        f"{config.OLLAMA_URL}/api/chat", json=payload, stream=True, timeout=600
    ) as r:
        if r.status_code == 404:
            print(f"❌ 답변 모델 '{config.CHAT_MODEL}'이 없습니다. config.py의 CHAT_MODEL을 "
                  f"`ollama list`에 보이는 이름으로 바꾸세요.")
            return
        if r.status_code == 500:
            print("❌ Ollama가 오류로 종료됐습니다 (GPU/Vulkan 문제일 수 있음). "
                  "config.py의 OLLAMA_NUM_GPU = 0 으로 바꿔 CPU로 실행해 보세요.")
            return
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            print(data.get("message", {}).get("content", ""), end="", flush=True)
    print()


def run_once(question, search_only=False, ideas=False):
    hits = search(question)
    if not hits:
        print("검색 결과가 없습니다. 먼저 `python ingest.py`로 책을 등록했는지 확인하세요.")
        return
    print("\n── 서재에서 찾은 발췌 ──")
    show_hits(hits)
    if not search_only:
        print("── AI 답변 ──")
        ask_llm(question, hits, ideas=ideas)


def main():
    setup_console()
    ap = argparse.ArgumentParser(description="내 서재에 질문하기")
    ap.add_argument("question", nargs="?", help="질문 (비우면 대화 모드)")
    ap.add_argument("--search-only", action="store_true", help="AI 답변 없이 발췌만 보기")
    ap.add_argument("--ideas", action="store_true", help="발췌를 조합해 아이디어 만들기")
    args = ap.parse_args()

    check_ollama()
    if args.question:
        run_once(args.question, args.search_only, args.ideas)
        return

    print("질문을 입력하세요. (끝내려면 빈 줄에서 Enter)")
    while True:
        q = input("\n질문> ").strip()
        if not q:
            break
        run_once(q, args.search_only, args.ideas)


if __name__ == "__main__":
    main()
