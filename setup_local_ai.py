"""Install pinned local model runtimes and models; all inference stays on this PC."""
from __future__ import annotations
import hashlib, subprocess, sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
MODEL_DIR=ROOT/"models"
MODEL=MODEL_DIR/"qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_SHA256="6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf"

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def download():
    MODEL_DIR.mkdir(exist_ok=True)
    if MODEL.exists() and digest(MODEL)==MODEL_SHA256:
        print("Verified local language model already exists.",flush=True);return
    partial=MODEL.with_suffix(".part")
    print("Downloading the pinned Qwen 1.5B local model (about 1 GB)…",flush=True)
    req=Request(MODEL_URL,headers={"User-Agent":"ClaimGuard-local-demo/1.0"})
    with urlopen(req,timeout=90) as src,partial.open("wb") as dst:
        count=0
        while block:=src.read(1024*1024):
            dst.write(block);count+=1
            if count%50==0:print(f"  {count} MiB downloaded",flush=True)
    if digest(partial)!=MODEL_SHA256:
        partial.unlink(missing_ok=True);raise RuntimeError("Model checksum did not match; the incomplete model was discarded.")
    partial.replace(MODEL)

def main():
    print("Installing CPU-only local inference and embedding packages…",flush=True)
    subprocess.run([sys.executable,"-m","pip","install","--only-binary=:all:","llama-cpp-python==0.3.18","--extra-index-url","https://abetlen.github.io/llama-cpp-python/whl/cpu"],check=True)
    subprocess.run([sys.executable,"-m","pip","install","fastembed==0.5.1"],check=True)
    download()
    print("Downloading and warming the local BGE-small policy embedding model…",flush=True)
    from fastembed import TextEmbedding
    embedder=TextEmbedding(model_name="BAAI/bge-small-en-v1.5",cache_dir=str(MODEL_DIR/"embeddings"))
    next(embedder.embed(["ClaimGuard fictional reimbursement policy retrieval check."]))
    marker=MODEL_DIR/"embedding-ready.txt";marker.write_text("BAAI/bge-small-en-v1.5\n",encoding="utf-8")
    print("Checking local language model inference…",flush=True)
    from llama_cpp import Llama
    llm=Llama(model_path=str(MODEL),n_ctx=2048,n_threads=max(2,min(8,__import__('os').cpu_count() or 4)),verbose=False)
    result=llm.create_chat_completion(messages=[{"role":"user","content":"Answer with a short greeting."}],temperature=0,max_tokens=48)
    reply=result["choices"][0]["message"]["content"].strip()
    if not reply:raise RuntimeError("The local model loaded but returned an empty answer.")
    from db import init_db
    init_db(ROOT/"instance"/"claimguard.sqlite3",ROOT/"policies")
    print("Local model answered: "+reply)
    print("The 24 policy pages are now stored as semantic BGE vectors in SQLite.")
    print("Setup complete. Reopen ClaimGuard.")

if __name__=="__main__":main()
