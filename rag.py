"""Small offline SQLite vector retrieval over the fictional policy handbook."""
from __future__ import annotations
import hashlib, json, math, re, struct
from pathlib import Path
from policy_content import pages, write_sources

DIM = 512
EMBED_MARKER=Path(__file__).resolve().parent/"models"/"embedding-ready.txt"
_semantic_model=None
STOP={"what","is","the","a","an","for","of","to","do","i","how","can","my","your","me","in","on","and","or","does","happens","who","are","with","about","much","have","long","get","it","this"}
SYNONYMS={
    "hotel":["lodging","accommodation","room"],"lodging":["hotel","accommodation"],"allowance":["limit","cap"],"amount":["limit","cap"],"maximum":["limit","cap"],"limit":["cap","maximum","amount","auto-approval","auto","approved"],"cap":["limit","maximum","amount"],
    "meal":["meals","food","dining"],"meals":["meal","food","dining"],"taxi":["cab","local","transport","fare"],"fare":["taxi","transport","charge"],"transport":["travel","taxi","fare"],
    "duplicate":["repeat","repeated","same"],"repeated":["duplicate","repeat"],"same":["duplicate","repeat"],"submission":["submit","claim"],"submissions":["submit","claim","repeat"],
    "manager":["authority","reviewer","approval"],"approves":["approve","authority"],"approved":["approve","approval"],"review":["reviewer","authority"],"decides":["decision","authority"],
    "lost":["missing","unreadable"],"payout":["payment","transfer","bank"],"payouts":["payment","transfer","bank"],"bank":["payment","transfer"],"deadline":["days","submit"],"late":["deadline","days"],
    "receipt":["bill","proof"],"bill":["receipt","proof"],"food":["meal","meals"],"accommodation":["hotel","lodging"],"unknown":["unfamiliar","category"],
}
TOPIC_DOCUMENTS={
    "meals": ("meal", "meals", "food", "dining"),
    "travel": ("travel", "taxi", "cab", "metro", "bus", "transport", "flight", "train", "mileage", "fare"),
    "lodging": ("hotel", "lodging", "accommodation", "stay"),
}

def mode():
    if not EMBED_MARKER.exists(): return "feature-hash-v2"
    try:
        from fastembed import TextEmbedding
        return "bge-small-en-v1.5"
    except ImportError:return "feature-hash-v1"

def _semantic_embed(text):
    global _semantic_model
    from fastembed import TextEmbedding
    if _semantic_model is None:
        _semantic_model=TextEmbedding(model_name="BAAI/bge-small-en-v1.5",cache_dir=str(EMBED_MARKER.parent/"embeddings"))
    return [float(x) for x in next(_semantic_model.embed([text]))]

def embed(text: str) -> list[float]:
    """Deterministic local feature-hash embedding; requires no API or model download."""
    if mode()=="bge-small-en-v1.5":return _semantic_embed(text)
    words = re.findall(r"[a-z0-9]+", text.lower())
    features = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    vec = [0.0] * DIM
    for token in features:
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        n = int.from_bytes(digest[:4], "little") % DIM
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[n] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]

def pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)

def unpack(raw: bytes) -> list[float]:
    return list(struct.unpack(f"{len(raw)//4}f", raw))

def index_policies(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS policy_vector_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    source_pages=list(pages())
    content_hash=hashlib.sha256(json.dumps(source_pages,sort_keys=True).encode("utf-8")).hexdigest()
    existing = conn.execute("SELECT COUNT(*) FROM policy_vectors").fetchone()[0]
    meta=conn.execute("SELECT key,value FROM policy_vector_meta WHERE key IN ('embedding_mode','content_hash')").fetchall()
    meta=dict((r["key"],r["value"]) for r in meta)
    current_mode=mode()
    if existing == len(source_pages) and meta.get("embedding_mode")==current_mode and meta.get("content_hash")==content_hash:
        return
    conn.execute("DELETE FROM policy_vectors")
    for page in source_pages:
        conn.execute("INSERT INTO policy_vectors(document,page,heading,content,embedding) VALUES(?,?,?,?,?)",
                     (page["document"], page["page"], page["heading"], page["text"], pack(embed(page["text"]))))
    conn.execute("INSERT OR REPLACE INTO policy_vector_meta(key,value) VALUES('embedding_mode',?)",(current_mode,))
    conn.execute("INSERT OR REPLACE INTO policy_vector_meta(key,value) VALUES('content_hash',?)",(content_hash,))
    conn.commit()

def retrieve(conn, query: str, limit: int = 4):
    q = embed(query)
    rows = conn.execute("SELECT id,document,page,heading,content,embedding FROM policy_vectors").fetchall()
    ranked = []
    terms=[w for w in re.findall(r"[a-z0-9]+",query.lower()) if w not in STOP and len(w)>1]
    query_words=set(terms)
    requested_docs=set()
    for doc_key, aliases in TOPIC_DOCUMENTS.items():
        if query_words.intersection(aliases):
            requested_docs.add("Travel Expense Policy" if doc_key=="travel" else "Meals and Accommodation")
    for row in rows:
        v = unpack(row["embedding"])
        cosine = sum(a*b for a,b in zip(q,v))
        content_words=set(re.findall(r"[a-z0-9]+",row["content"].lower()))
        heading_words=set(re.findall(r"[a-z0-9]+",row["heading"].lower()))
        matched=0
        covered=set()
        exact_bonus=0.0
        for term in terms:
            group={term,*SYNONYMS.get(term,[])}
            singular=term[:-1] if term.endswith("s") and len(term)>4 else term
            group.add(singular)
            found=group & content_words
            if found-covered:
                matched += 1
                covered.update(found)
            if term in content_words: exact_bonus += 0.30
            if term in heading_words: exact_bonus += 0.25
        lexical=matched/max(len(terms),1) + exact_bonus/max(len(terms),1)
        # Semantic similarity alone often ranks a generic receipt/evidence page
        # above the requested category. Keep a topic-specific question inside
        # its policy document, then prefer sections whose heading answers the
        # question (for example, "Business meals" for a meal limit query).
        category_bonus = 0.0
        if requested_docs:
            if row["document"] in requested_docs:
                category_bonus += 0.45
            else:
                category_bonus -= 0.45
        heading_text=row["heading"].lower()
        heading_bonus=sum(0.10 for term in terms if term in heading_text)
        topic_heading_bonus=0.0
        for aliases in TOPIC_DOCUMENTS.values():
            if query_words.intersection(aliases) and any(alias in heading_text for alias in aliases):
                topic_heading_bonus=max(topic_heading_bonus,0.35)
        score = (cosine + lexical*0.25 if mode()=="bge-small-en-v1.5" else lexical + max(cosine,0)*0.015) + category_bonus + heading_bonus + topic_heading_bonus
        ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [{"score": round(score, 4), "id": row["id"], "document": row["document"],
             "page": row["page"], "heading": row["heading"], "content": row["content"]}
            for score,row in ranked[:limit] if score > (-0.10 if requested_docs else (0.24 if mode()=="bge-small-en-v1.5" else 0.14))]

def write_policy_pdfs(directory: Path):
    """Write simple, dependency-free PDFs, one source section per printed page."""
    from policy_content import DOCS
    directory.mkdir(parents=True, exist_ok=True)
    for title, sections in DOCS:
        page_streams=[]
        for number,(heading,body) in enumerate(sections,1):
            lines=[title, f"FICTIONAL COMPANY POLICY  |  PAGE {number}", "", heading, ""]
            words=body.split(); line=""
            for word in words:
                if len(line)+len(word)+1>88:
                    lines.append(line); line=word
                else: line=(line+" "+word).strip()
            if line: lines.append(line)
            lines += ["", "INR | ClaimGuard MVP sample handbook | Not a real company policy"]
            commands=["BT", "/F1 11 Tf", "52 790 Td", "15 TL"]
            for text in lines:
                clean=text.encode("ascii","replace").decode("ascii").replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
                commands += [f"({clean}) Tj", "T*"]
            commands.append("ET")
            page_streams.append("\n".join(commands).encode("ascii"))
        objects=[b"<< /Type /Catalog /Pages 2 0 R >>"]
        kids=[]
        # Reserve pages and streams then write a stable xref table.
        for i,stream in enumerate(page_streams):
            page_id=3+i*2; stream_id=page_id+1; kids.append(f"{page_id} 0 R")
            objects += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents {stream_id} 0 R >>".encode(),
                        f"<< /Length {len(stream)} >>\nstream\n".encode()+stream+b"\nendstream"]
        objects.insert(1,f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode())
        data=bytearray(b"%PDF-1.4\n%ClaimGuard sample policy\n"); offsets=[0]
        for i,obj in enumerate(objects,1):
            offsets.append(len(data)); data.extend(f"{i} 0 obj\n".encode()+obj+b"\nendobj\n")
        xref=len(data); data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
        for off in offsets[1:]: data.extend(f"{off:010d} 00000 n \n".encode())
        data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        (directory/f"{title}.pdf").write_bytes(data)
