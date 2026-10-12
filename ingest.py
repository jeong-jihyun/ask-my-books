"""
책 -> 글자 뽑기 -> (스캔본이면 OCR) -> 조각내기 -> 검색 DB에 저장

사용법
  python ingest.py --limit 50            # 처음엔 50권만 시험
  python ingest.py                       # 전부 처리 (이미 한 책은 건너뜀)
  python ingest.py --delete-original     # 처리 끝난 원본 파일을 PC에서 삭제 (용량 부족할 때)

중간에 멈춰도(Ctrl+C) 다시 실행하면 이어서 진행됩니다.
"""
import argparse
import hashlib
import json
import re
import shutil
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF (최신 이름)
except ImportError:
    import fitz  # 구버전 이름

import config
from common import check_ollama, embed_texts, get_collection, setup_console

BOOK_TYPES = {".pdf", ".epub"}


# ───────────────────────── 글자 뽑기 ─────────────────────────
_ocr_cmd = None      # None = 아직 확인 안 함, "" = 사용 불가
_ocr_warned = False


def _find_tesseract():
    global _ocr_cmd
    if _ocr_cmd is None:
        _ocr_cmd = config.TESSERACT_CMD or shutil.which("tesseract") or ""
        if _ocr_cmd:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = _ocr_cmd
    return _ocr_cmd


def ocr_page(page):
    """이미지 페이지 한 장을 글자로 바꿈"""
    global _ocr_warned
    if not config.USE_OCR:
        return ""
    if not _find_tesseract():
        if not _ocr_warned:
            print("  ⚠ Tesseract가 설치되어 있지 않아 스캔 페이지는 건너뜁니다. (README 참고)")
            _ocr_warned = True
        return ""
    import pytesseract
    from PIL import Image

    pix = page.get_pixmap(dpi=config.OCR_DPI)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img, lang=config.OCR_LANG).strip()


def extract_pdf(path):
    """PDF -> [("p.1", 글), ("p.2", 글), ...]"""
    pages = []
    doc = fitz.open(path)
    try:
        if doc.needs_pass:
            raise RuntimeError("암호가 걸린 PDF")
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if len(text) < config.MIN_CHARS_PER_PAGE:
                text = ocr_page(page) or text
            pages.append((f"p.{i}", text))
    finally:
        doc.close()
    return pages


class _HtmlToText(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def extract_epub(path):
    """EPUB -> [("챕터 1", 글), ...]  (DRM 걸린 EPUB은 글자가 안 나옵니다)"""
    pages = []
    with zipfile.ZipFile(path) as z:
        names = sorted(
            n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))
        )
        for i, name in enumerate(names, start=1):
            raw = z.read(name).decode("utf-8", errors="replace")
            parser = _HtmlToText()
            parser.feed(raw)
            pages.append((f"챕터 {i}", "".join(parser.parts).strip()))
    return pages


def extract(path):
    return extract_epub(path) if path.suffix.lower() == ".epub" else extract_pdf(path)


# ───────────────────────── 조각내기 ─────────────────────────
def chunk_text(text, size=None, overlap=None):
    """긴 글을 size 글자 정도로 자르되, 문단/문장 끝에서 자르려고 시도"""
    size = size or config.CHUNK_SIZE
    overlap = config.CHUNK_OVERLAP if overlap is None else overlap
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []

    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            lo = start + int(size * 0.6)
            candidates = [
                text.rfind("\n", lo, end),        # 줄바꿈에서 자르기
                text.rfind(". ", lo, end) + 1,    # 문장 끝에서 자르기 (없으면 0)
            ]
            best = max(candidates)
            if best > lo:
                end = best
        piece = text[start:end].strip()
        if len(piece) >= config.MIN_CHUNK:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


# ───────────────────────── 한 권 처리 ─────────────────────────
def ingest_book(path, rel, col):
    book_id = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]
    title = path.stem

    pages = extract(path)
    total_chars = sum(len(t) for _, t in pages)
    if total_chars < 200:
        raise RuntimeError("글자를 거의 못 뽑음 (스캔본 OCR 미설치, 또는 DRM 파일일 수 있음)")

    # 뽑은 글은 텍스트 파일로도 저장 (나중에 원본 없이도 DB를 다시 만들 수 있게)
    text_dir = config.DATA_DIR / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    with open(text_dir / f"{book_id}.txt", "w", encoding="utf-8") as f:
        f.write(f"# {title}\n# 원본: {rel}\n")
        for loc, t in pages:
            f.write(f"\n\n===== {loc} =====\n{t}")

    docs, metas, ids = [], [], []
    for loc, t in pages:
        for c in chunk_text(t):
            ids.append(f"{book_id}-{len(ids)}")
            docs.append(c)
            metas.append({"book_id": book_id, "title": title, "loc": loc, "source": rel})

    # 같은 책을 다시 처리하는 경우(중단 후 재시작 등) 옛 조각을 먼저 지움
    col.delete(where={"book_id": book_id})

    for i in range(0, len(docs), config.EMBED_BATCH):
        j = i + config.EMBED_BATCH
        col.add(
            ids=ids[i:j],
            documents=docs[i:j],
            embeddings=embed_texts(docs[i:j]),
            metadatas=metas[i:j],
        )
    return len(docs)


# ───────────────────────── 전체 실행 ─────────────────────────
def load_manifest(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def main():
    setup_console()
    ap = argparse.ArgumentParser(description="내 서재 책을 검색 가능하게 만들기")
    ap.add_argument("--dir", help="책 폴더 (config.py의 BOOKS_DIR 대신 사용)")
    ap.add_argument("--limit", type=int, default=0, help="새로 처리할 최대 권수 (0=전부)")
    ap.add_argument(
        "--delete-original",
        action="store_true",
        help="처리 성공한 원본 파일을 PC에서 삭제 (마이박스 원본은 그대로 남음)",
    )
    args = ap.parse_args()

    books_dir = Path(args.dir) if args.dir else config.BOOKS_DIR
    if not books_dir.exists():
        print(f"❌ 책 폴더가 없습니다: {books_dir}\n   config.py의 BOOKS_DIR을 확인하세요.")
        return

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = config.DATA_DIR / "done.json"
    failed_path = config.DATA_DIR / "failed.log"
    manifest = load_manifest(manifest_path)

    check_ollama()
    col = get_collection()

    files = sorted(p for p in books_dir.rglob("*") if p.suffix.lower() in BOOK_TYPES)
    todo = []
    for p in files:
        rel = str(p.relative_to(books_dir))
        if manifest.get(rel, {}).get("size") == p.stat().st_size:
            continue  # 이미 처리함
        todo.append((p, rel))
    if args.limit:
        todo = todo[: args.limit]

    print(f"책 {len(files)}권 발견 / 새로 처리할 책 {len(todo)}권")
    ok = fail = 0
    t0 = time.time()

    for n, (p, rel) in enumerate(todo, start=1):
        print(f"[{n}/{len(todo)}] {rel}")
        try:
            size = p.stat().st_size
            chunks = ingest_book(p, rel, col)
            manifest[rel] = {"size": size, "chunks": chunks}
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"   ✔ 조각 {chunks}개 저장")
            ok += 1
            if args.delete_original:
                p.unlink()
                print("   🗑 PC의 원본 파일 삭제")
        except KeyboardInterrupt:
            print("\n중단했습니다. 다시 실행하면 이어서 진행합니다.")
            break
        except Exception as e:
            fail += 1
            print(f"   ✘ 실패: {e}")
            with open(failed_path, "a", encoding="utf-8") as f:
                f.write(f"{rel}\t{e}\n")

    mins = (time.time() - t0) / 60
    print(f"\n완료: 성공 {ok}권 / 실패 {fail}권 / {mins:.1f}분")
    if fail:
        print(f"실패 목록: {failed_path}")


if __name__ == "__main__":
    main()
