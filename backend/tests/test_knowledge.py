import hashlib
import math
import re
import time

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.flows.compiler import FlowCompiler
from app.flows.schema import FlowGraph
from app.flows.validator import validate
from app.kb.embedder import set_embedder
from app.kb.parsing import CHUNK_CHARS, Section, chunk
from app.kb.retrieval import Hit, SearchResult
from app.kb.tags import normalize_tag, parse_tags, visible_to
from app.main import app
from app.trace.events import Tracer

DOC = """Fatura ödemeleri
Faturanızı her ayın 15'ine kadar mobil uygulamadan veya otomatik ödeme talimatıyla ödeyebilirsiniz.

Modem arızaları
Modem ışıkları kırmızı yanıp sönüyorsa cihazı 30 saniye kapatıp yeniden açın. Sorun sürerse arıza kaydı açılır.

Çalışma saatleri
Müşteri hizmetleri hafta içi 08:00-22:00 arasında hizmet verir.
"""


class WordEmbedder:
    """Deterministic stand-in for bge-m3: hashed bag of words, so shared words mean similarity."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * settings.embedding_dim
            for word in re.findall(r"\w+", text.lower()):
                v[int(hashlib.md5(word.encode()).hexdigest(), 16) % settings.embedding_dim] += 1
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


@pytest.fixture(scope="module")
def client():
    set_embedder(WordEmbedder())
    with TestClient(app) as c:
        yield c


def auth(client) -> dict:
    r = client.post("/api/auth/login", data={"username": "admin@test.local", "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def wait_ready(client, h, kb_id, timeout=15) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        kb = client.get(f"/api/knowledge-bases/{kb_id}", headers=h).json()
        if kb["documents"] and all(d["status"] in ("ready", "failed") for d in kb["documents"]):
            return kb
        time.sleep(0.1)
    raise AssertionError("documents were not indexed in time")


def test_chunking_packs_paragraphs_with_overlap():
    long = " ".join(f"Cümle numarası {i} burada bitiyor." for i in range(120))
    pieces = chunk([Section(long, page=3)])
    assert len(pieces) > 1
    assert all(len(p.text) <= CHUNK_CHARS + 50 for p in pieces)
    assert all(p.page == 3 for p in pieces)
    # The start of each chunk repeats the end of the previous one.
    assert pieces[1].text[:30] in pieces[0].text


def test_upload_index_and_search(client):
    h = auth(client)
    kb = client.post("/api/knowledge-bases", json={"name": "Destek SSS"}, headers=h).json()
    files = [
        ("files", ("sss.txt", DOC.encode("utf-8"), "text/plain")),
        ("files", ("bos.txt", b"   \n\n  ", "text/plain")),
    ]
    r = client.post(f"/api/knowledge-bases/{kb['id']}/documents", files=files, headers=h)
    assert r.status_code == 201, r.text

    detail = wait_ready(client, h, kb["id"])
    by_name = {d["filename"]: d for d in detail["documents"]}
    assert by_name["sss.txt"]["status"] == "ready" and by_name["sss.txt"]["chunk_count"] >= 1
    assert by_name["bos.txt"]["status"] == "failed" and "metin" in by_name["bos.txt"]["error"]

    hits = client.post(
        f"/api/knowledge-bases/{kb['id']}/search", json={"query": "modem ışıkları kırmızı"}, headers=h
    ).json()["hits"]
    assert hits and "Modem" in hits[0]["text"] and hits[0]["document"] == "sss.txt"


def test_unsupported_upload_is_rejected(client):
    h = auth(client)
    kb = client.post("/api/knowledge-bases", json={"name": "Resimler"}, headers=h).json()
    r = client.post(
        f"/api/knowledge-bases/{kb['id']}/documents",
        files=[("files", ("logo.png", b"\x89PNG", "image/png"))],
        headers=h,
    )
    assert r.status_code == 400 and "desteklenmiyor" in r.json()["detail"]


def kb_graph(kb_ids: list[str], global_kb_ids: list[str] | None = None, caller_tags: str = "") -> FlowGraph:
    return FlowGraph.model_validate(
        {
            "global": {"kb_ids": global_kb_ids or [], "caller_tags": caller_tags},
            "variables": [{"name": "musteri_tipi", "default": ""}],
            "nodes": [
                {"id": "s", "type": "start"},
                {
                    "id": "sss",
                    "type": "kb_answer",
                    "kb_ids": kb_ids,
                    "exits": [{"id": "bitti", "description": "Arayanın başka sorusu yok"}],
                },
                {"id": "e", "type": "end", "text": "Hoşça kalın."},
            ],
            "edges": [
                {"id": "1", "source": "s", "target": "sss"},
                {"id": "2", "source": "sss", "source_handle": "bitti", "target": "e"},
            ],
        }
    )


def test_kb_node_validation():
    assert "no_kb" in {i.code for i in validate(kb_graph([]))}
    assert "missing_kb" in {i.code for i in validate(kb_graph(["silinmis"]), known_kb_ids=set())}
    assert not validate(kb_graph(["kb1"]), known_kb_ids={"kb1"})


async def test_kb_node_searches_and_traces():
    async def fake_search(kb_ids, query, top_k, tags=None):
        hit = Hit(chunk_id=1, kb_id=kb_ids[0], document_id="d", document="sss.pdf", page=2,
                  score=0.81, text="Ödemeler ayın 15'ine kadar yapılır.")
        return SearchResult(query=query, hits=[hit], ms=5)

    tracer = Tracer()
    compiler = FlowCompiler(kb_graph(["kb1"], global_kb_ids=["kb1"]), tracer, searcher=fake_search)
    node = await compiler.initial_node(compiler.initial_state())
    assert node["name"] == "sss"
    names = {f.name for f in node["functions"]}
    assert names == {"bilgi_ara", "adimi_bitir_1"}
    assert [f.name for f in compiler.global_functions()] == ["sirket_bilgisi_ara"]
    assert "sirket_bilgisi_ara" in node["role_message"]

    search = next(f for f in node["functions"] if f.name == "bilgi_ara")
    result, next_node = await search.handler({"soru": "Son ödeme günü ne?"}, SimpleNamespace(state={}))
    assert next_node is None  # stays on the step so the LLM answers
    assert result["bulunan_bilgiler"][0]["kaynak"] == "sss.pdf, sayfa 2"
    event = next(e for e in tracer.events if e.type == "kb_search")
    assert event.node_id == "sss" and event.data["hits"][0]["score"] == 0.81
    assert event.data["tags"] is None  # the flow doesn't filter by tags


def test_tag_normalization_and_rule():
    assert normalize_tag("  Mevcut   MÜŞTERİ ") == "mevcut müşteri"
    assert normalize_tag("IĞDIR") == "ığdır"
    assert parse_tags("Yeni müşteri, , yeni MÜŞTERİ,vip") == ["yeni müşteri", "vip"]
    assert visible_to([], ["vip"]) and visible_to(["vip"], None)
    assert visible_to(["vip", "yeni müşteri"], ["vip"])
    assert not visible_to(["vip"], []) and not visible_to(["vip"], ["yeni müşteri"])


async def test_caller_tags_reach_the_search():
    seen = []

    async def fake_search(kb_ids, query, top_k, tags=None):
        seen.append(tags)
        return SearchResult(query=query, hits=[], ms=1)

    graph = kb_graph(["kb1"], caller_tags="{{ musteri_tipi }}")
    compiler = FlowCompiler(graph, Tracer(), searcher=fake_search)
    node = await compiler.initial_node(compiler.initial_state())
    search = next(f for f in node["functions"] if f.name == "bilgi_ara")
    await search.handler({"soru": "x"}, SimpleNamespace(state={"musteri_tipi": "Mevcut Müşteri"}))
    await search.handler({"soru": "x"}, SimpleNamespace(state={"musteri_tipi": ""}))
    # Unknown caller: only entries for everyone.
    assert seen == [["mevcut müşteri"], []]


def test_tagged_kb_without_caller_tags_is_a_warning():
    issues = validate(kb_graph(["kb1"]), known_kb_ids={"kb1"}, tagged_kb_ids={"kb1"})
    assert [(i.severity, i.code) for i in issues] == [("warning", "no_caller_tags")]
    assert not validate(kb_graph(["kb1"], caller_tags="{{ musteri_tipi }}"), {"kb1"}, {"kb1"})
    bad = validate(kb_graph(["kb1"], caller_tags="{{ yok }}"), {"kb1"}, {"kb1"})
    assert "unknown_variable" in {i.code for i in bad}


def test_qa_entries_tags_and_chunk_edits(client):
    h = auth(client)
    kb = client.post("/api/knowledge-bases", json={"name": "Etiketli SSS"}, headers=h).json()
    url = f"/api/knowledge-bases/{kb['id']}"
    for name in ("Mevcut Müşteri", "yeni müşteri", "kampanya"):
        client.post("/api/tags", json={"name": name}, headers=h)

    def qa(question, answer, tags):
        r = client.post(f"{url}/qa", json={"question": question, "answer": answer, "tags": tags}, headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    loyal = qa("Sadakat indirimi var mı?", "Mevcut müşterilere yüzde 20 sadakat indirimi uygulanır.", ["Mevcut Müşteri"])
    welcome = qa("Hoş geldin indirimi var mı?", "Yeni müşterilere ilk üç ay yüzde 50 indirim uygulanır.", ["yeni müşteri"])
    both = qa("İndirim nasıl uygulanır?", "İndirimler faturaya otomatik yansır.", [])
    assert loyal["kind"] == "qa" and loyal["tags"] == ["mevcut müşteri"] and loyal["status"] == "ready"
    assert loyal["filename"] == "Sadakat indirimi var mı?"

    def found(tags):
        body = {"query": "indirim var mı", "top_k": 10} | ({} if tags == "all" else {"tags": tags})
        hits = client.post(f"{url}/search", json=body, headers=h).json()["hits"]
        return {hit["document_id"] for hit in hits}

    assert found("all") == {loyal["id"], welcome["id"], both["id"]}
    assert found(["MEVCUT müşteri"]) == {loyal["id"], both["id"]}
    assert found([]) == {both["id"]}

    # Editing an answer re-embeds it; tags can change later.
    r = client.patch(f"{url}/documents/{welcome['id']}", json={"answer": "Yeni müşterilere ilk ay ücretsiz.", "tags": ["yeni müşteri", "kampanya"]}, headers=h)
    assert r.status_code == 200 and r.json()["tags"] == ["yeni müşteri", "kampanya"]
    [chunk] = client.get(f"{url}/documents/{welcome['id']}/chunks", headers=h).json()
    assert chunk["text"] == "Soru: Hoş geldin indirimi var mı?\nCevap: Yeni müşterilere ilk ay ücretsiz."
    counts = {t["name"]: t["entry_count"] for t in client.get("/api/tags", headers=h).json()}
    assert counts["kampanya"] == 1 and counts["mevcut müşteri"] == 1 and counts["yeni müşteri"] == 1

    # Files: tags apply to every chunk; chunks can be edited or removed by hand.
    client.post(f"{url}/documents", files=[("files", ("sss.txt", (DOC * 4).encode("utf-8"), "text/plain"))], headers=h)
    detail = wait_ready(client, h, kb["id"])
    doc = next(d for d in detail["documents"] if d["kind"] == "file")
    client.patch(f"{url}/documents/{doc['id']}", json={"tags": ["mevcut müşteri"]}, headers=h)
    chunks = client.get(f"{url}/documents/{doc['id']}/chunks", headers=h).json()
    assert len(chunks) >= 2
    r = client.patch(f"{url}/chunks/{chunks[0]['id']}", json={"text": "Fatura son ödeme günü ayın 20'sidir."}, headers=h)
    assert r.status_code == 200 and r.json()["edited"]
    assert client.delete(f"{url}/chunks/{chunks[1]['id']}", headers=h).status_code == 204
    doc = next(d for d in client.get(url, headers=h).json()["documents"] if d["id"] == doc["id"])
    assert doc["edited_chunks"] == 1 and doc["chunk_count"] == len(chunks) - 1 and doc["tags"] == ["mevcut müşteri"]

    hits = client.post(f"{url}/search", json={"query": "son ödeme günü", "tags": ["yeni müşteri"]}, headers=h).json()["hits"]
    assert all(hit["document_id"] != doc["id"] for hit in hits)
    hits = client.post(f"{url}/search", json={"query": "son ödeme günü ayın 20", "tags": ["mevcut müşteri"]}, headers=h).json()["hits"]
    assert hits[0]["text"] == "Fatura son ödeme günü ayın 20'sidir." and hits[0]["tags"] == ["mevcut müşteri"]


def test_tags_are_defined_on_screen_and_managed(client):
    h = auth(client)
    r = client.post("/api/tags", json={"name": "  Kurumsal  ", "description": "Şirket hattı olanlar", "color": "sky"}, headers=h)
    assert r.status_code == 201 and r.json()["name"] == "kurumsal" and r.json()["color"] == "sky"
    tag_id = r.json()["id"]
    assert client.post("/api/tags", json={"name": "KURUMSAL"}, headers=h).status_code == 409
    assert client.post("/api/tags", json={"name": "a, b"}, headers=h).status_code == 400

    kb = client.post("/api/knowledge-bases", json={"name": "Kurumsal SSS"}, headers=h).json()
    url = f"/api/knowledge-bases/{kb['id']}"
    body = {"question": "Kurumsal fatura nasıl alınır?", "answer": "Vergi numaranızı iletmeniz yeterli.", "tags": ["tanımsız"]}
    r = client.post(f"{url}/qa", json=body, headers=h)
    assert r.status_code == 400 and "tanımlı bir etiket değil" in r.json()["detail"]
    entry = client.post(f"{url}/qa", json=body | {"tags": ["Kurumsal"]}, headers=h).json()
    assert entry["tags"] == ["kurumsal"]

    # Renaming rewrites the tag on entries and on the chunks the search filters.
    r = client.patch(f"/api/tags/{tag_id}", json={"name": "Kurumsal Müşteri"}, headers=h)
    assert r.status_code == 200 and r.json()["entry_count"] == 1
    entry = next(d for d in client.get(url, headers=h).json()["documents"] if d["id"] == entry["id"])
    assert entry["tags"] == ["kurumsal müşteri"]
    search = {"query": "kurumsal fatura", "tags": ["kurumsal müşteri"]}
    assert client.post(f"{url}/search", json=search, headers=h).json()["hits"][0]["tags"] == ["kurumsal müşteri"]

    # Deleting leaves the entry for everyone.
    assert client.delete(f"/api/tags/{tag_id}", headers=h).status_code == 204
    entry = next(d for d in client.get(url, headers=h).json()["documents"] if d["id"] == entry["id"])
    assert entry["tags"] == []
    hits = client.post(f"{url}/search", json={"query": "kurumsal fatura", "tags": []}, headers=h).json()["hits"]
    assert hits and hits[0]["tags"] == []
