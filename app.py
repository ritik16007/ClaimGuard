from __future__ import annotations
import os,re
import secrets
import threading
from datetime import date
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, session, url_for, send_file, abort
from db import connect, init_db
from rag import retrieve
from claim_engine import claim_submit, suspicious
from local_ai import available as model_available, answer as local_answer

ROOT=Path(__file__).resolve().parent
POLICY_TERMS={"reimbursement","reimburse","expense","claim","receipt","policy","travel","taxi","meal","food","hotel","lodging","accommodation","limit","allowance","approval","duplicate","deadline","mileage","payment","exception","submit","bill"}
CATEGORY_WORDS={"travel":"travel","taxi":"travel","transport":"travel","flight":"travel","train":"travel","meals":"meals","meal":"meals","food":"meals","dining":"meals","lodging":"lodging","hotel":"lodging","accommodation":"lodging","stay":"lodging"}

POLICY_ANCHOR_RE=re.compile(r"\b(?:reimburse\w*|claims?|receipts?|polic(?:y|ies)|approv\w*|allowances?|eligib\w*|deadline|submiss\w*|duplicate\w*|mileage|business travel|business trip|manager review|payment queue)\b",re.I)
POLICY_RULE_RE=re.compile(r"\b(?:limit|cap|allowance|eligible|eligibility|reimburse\w*|policy|claim|receipt|approval|deadline|submit\w*|duplicate|proof|document\w*|company)\b",re.I)

def is_reimbursement_question(message):
    text=message.strip()
    if POLICY_ANCHOR_RE.search(text):
        return True
    # A category alone (for example, "living expense") is not enough.
    # Pair a supported category with a rule/question term such as "limit".
    has_category=any(re.search(r"\b"+re.escape(word)+r"\b",text,re.I) for word in CATEGORY_WORDS)
    return has_category and bool(POLICY_RULE_RE.search(text))
def create_app(config=None):
    data_dir=Path(os.environ.get("CLAIMGUARD_DATA_DIR",ROOT/"instance"))
    app=Flask(__name__,instance_path=str(ROOT/"instance"),instance_relative_config=True)
    app.config.update(SECRET_KEY=os.environ.get("CLAIMGUARD_SECRET"),DATABASE=str(data_dir/"claimguard.sqlite3"),UPLOAD_DIR=str(data_dir/"uploads"),MAX_CONTENT_LENGTH=11*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax")
    if config: app.config.update(config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True,exist_ok=True)
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True,exist_ok=True)
    if not app.config["SECRET_KEY"]:
        key_path=Path(app.config["DATABASE"]).parent/"secret.key"
        if not key_path.exists():key_path.write_text(secrets.token_hex(32),encoding="ascii")
        app.config["SECRET_KEY"]=key_path.read_text(encoding="ascii").strip()
    testing=bool(app.config.get("TESTING"))
    if not testing:print("ClaimGuard: preparing the local database...",flush=True)
    init_db(app.config["DATABASE"],ROOT/"policies",build_index=testing)
    policy_ready=threading.Event()
    if testing:
        policy_ready.set()
    else:
        def prepare_policy_index():
            try:
                print("ClaimGuard: preparing the 24-page policy search index in the background...",flush=True)
                init_db(app.config["DATABASE"],ROOT/"policies",build_index=True)
                policy_ready.set()
                conn=connect(app.config["DATABASE"]);count=conn.execute("SELECT COUNT(*) FROM policy_vectors").fetchone()[0];conn.close()
                print(f"ClaimGuard: policy index ready ({count} pages).",flush=True)
            except Exception:
                app.logger.exception("Policy index setup failed")
        threading.Thread(target=prepare_policy_index,name="claimguard-policy-index",daemon=True).start()
    app.extensions["policy_index_ready"]=policy_ready

    def user():
        if "user_id" not in session:return None
        conn=connect(app.config["DATABASE"]); row=conn.execute("SELECT id,username,full_name,role FROM users WHERE id=?",(session["user_id"],)).fetchone();conn.close()
        return dict(row) if row else None

    def role_required(role=None):
        u=user()
        if not u:return jsonify(error="Please sign in again."),401
        if role and u["role"]!=role:return jsonify(error="You do not have access to that screen."),403
        return u

    @app.get("/")
    def home(): return redirect(url_for("workspace") if user() else url_for("login_page"))
    @app.get("/login")
    def login_page(): return render_template("login.html")
    @app.post("/api/login")
    def login():
        from werkzeug.security import check_password_hash
        data=request.get_json(silent=True) or request.form
        username=str(data.get("username",""))[:80].strip().lower(); password=str(data.get("password",""))
        conn=connect(app.config["DATABASE"]); row=conn.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone();conn.close()
        if not row or not check_password_hash(row["password_hash"],password):return jsonify(error="That username or password did not match."),401
        session.clear();session["user_id"]=row["id"]
        return jsonify(user={"name":row["full_name"],"role":row["role"]},next=url_for("workspace"))
    @app.post("/api/logout")
    def logout():session.clear();return jsonify(ok=True)
    @app.get("/app")
    def workspace():
        u=user()
        if not u:return redirect(url_for("login_page"))
        return render_template("app.html",user=u)

    @app.get("/api/me")
    def me():
        u=user();return (jsonify(user=u),200) if u else (jsonify(error="Not signed in"),401)
    @app.get("/api/status")
    def status():
        conn=connect(app.config["DATABASE"]); count=conn.execute("SELECT COUNT(*) FROM policy_vectors").fetchone()[0];conn.close()
        return jsonify(local_model=model_available(),policy_ready=policy_ready.is_set(),policy_chunks=count,model_name="Qwen 2.5 1.5B Instruct (local)" if model_available() else "Local model not installed; grounded policy assistant is active")
    @app.get("/api/policies")
    def policies():
        u=role_required()
        if not isinstance(u,dict):return u
        conn=connect(app.config["DATABASE"])
        rows=conn.execute("SELECT document,COUNT(*) pages,MIN(page) first_page FROM policy_vectors GROUP BY document ORDER BY MIN(id)").fetchall();conn.close()
        return jsonify(documents=[{**dict(r),"pdf_url":url_for("policy_pdf",filename=r["document"]+".pdf")} for r in rows])
    @app.get("/policies/<path:filename>")
    def policy_pdf(filename):
        u=user()
        if not u:return redirect(url_for("login_page"))
        conn=connect(app.config["DATABASE"]);allowed={r["document"]+".pdf" for r in conn.execute("SELECT DISTINCT document FROM policy_vectors")};conn.close()
        if filename not in allowed:abort(404)
        path=ROOT/"policies"/filename
        if not path.is_file():abort(404)
        return send_file(path,as_attachment=True,download_name=filename)

    def answer_policy(message):
        query=message.strip()
        if suspicious(query):return "I can’t follow requests to override policy or bypass claim checks. I can help with reimbursement rules or filing a claim."
        if not is_reimbursement_question(query):
            return "Sorry, I can only help with company reimbursement policies and filing reimbursement claims."
        if not policy_ready.is_set():
            return "I’m preparing the local policy library. Please try that question again in a few seconds; claim filing is available meanwhile."
        conn=connect(app.config["DATABASE"])
        hits=retrieve(conn,query,4);conn.close()
        if not hits:return "I couldn’t find a relevant section in the sample reimbursement handbook. Please ask an authority to review this question."
        # Give the model only the strongest retrieved section. Extra passages
        # were making simple questions (such as a meal cap) include unrelated
        # travel evidence.
        hits=hits[:1]
        # A local model can rewrite grounded evidence. Without it, quote retrieved policy passages directly.
        generated=local_answer(query,hits)
        if generated:return generated
        best=hits[:1]
        return "\n\n".join(f"{p['content']}\nSource: {p['document']}, page {p['page']} — {p['heading']}" for p in best)

    def parse_message(text):
        low=text.lower()
        category=next((v for k,v in CATEGORY_WORDS.items() if re.search(r"\b"+re.escape(k)+r"\b",low)),"")
        if not category:
            unknown=re.search(r"\b(?:claim(?:ing)?\s+for|category\s*(?:is|:)?|expense\s+for)\s+(?:a|an|the\s+)?([a-z][a-z-]{2,24})",low)
            if unknown: category=unknown.group(1)
        m=re.search(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2})\b",text)
        expdate=m.group(1) if m else ""
        # A question that mentions submitting a claim is not itself a claim
        # submission. Route to the claim engine only for an explicit filing
        # action; an uploaded receipt still starts a claim below.
        filing_action=bool(
            re.search(r"^\s*(?:please\s+)?(?:file|submit|create|start|raise)\s+(?:(?:a|an|the|my|new)\s+)?(?:[a-z-]+\s+){0,2}(?:claim|expense|reimbursement)\b",low)
            or re.search(r"\b(?:i want to|i need to|please help me|help me|can you|could you)\s+(?:please\s+)?(?:file|submit|create|start|raise)\b",low)
        )
        intent=filing_action
        return category,expdate,intent

    @app.post("/api/chat")
    def chat():
        u=role_required("employee")
        if not isinstance(u,dict):return u
        message=(request.form.get("message") or (request.get_json(silent=True) or {}).get("message") or "").strip()[:4000]
        if not message:return jsonify(reply="Type a reimbursement question or describe a claim to get started.",kind="assistant")
        if suspicious(message) and (request.files.get("receipt") or re.search(r"\b(claim|reimburse|pay)\b",message,re.I)):
            result=claim_submit(app.config["DATABASE"],app.config["UPLOAD_DIR"],u["id"],"","", "",None,message)
            return jsonify(reply=result["reason"],kind="claim",claim=result)
        category,expdate,intent=parse_message(message)
        upload=request.files.get("receipt")
        if intent or upload:
            purpose=re.sub(r"\b(file|submit|claim|reimburse|reimbursement)\b","",message,flags=re.I).strip(" .,:;- ")[:240]
            result=claim_submit(app.config["DATABASE"],app.config["UPLOAD_DIR"],u["id"],category,expdate,purpose,upload,message)
            if result.get("status")=="need_info":
                return jsonify(reply=result["reason"],kind="claim",claim=result)
            return jsonify(reply=f"Claim #{result['id']} is {result['status'].replace('_',' ')}. {result['reason']}"+(" No payment has been made; an authority handles any payment confirmation." if result["status"]=="auto_approved" else ""),kind="claim",claim=result)
        return jsonify(reply=answer_policy(message),kind="policy")

    def serialize_claim(row):
        d=dict(row);d["amount"]=float(d["amount"]) if d["amount"] is not None else None
        return d
    @app.get("/api/claims")
    def claims():
        u=role_required()
        if not isinstance(u,dict):return u
        conn=connect(app.config["DATABASE"])
        if u["role"]=="authority": rows=conn.execute("SELECT c.*,u.full_name employee,r.original_name receipt_name,r.extraction_status FROM claims c JOIN users u ON u.id=c.employee_id LEFT JOIN receipts r ON r.id=c.receipt_id ORDER BY c.id DESC").fetchall()
        else:rows=conn.execute("SELECT c.*,r.original_name receipt_name,r.extraction_status FROM claims c LEFT JOIN receipts r ON r.id=c.receipt_id WHERE employee_id=? ORDER BY c.id DESC",(u["id"],)).fetchall()
        conn.close();return jsonify(claims=[serialize_claim(r) for r in rows])
    @app.get("/api/authority/overview")
    def overview():
        u=role_required("authority")
        if not isinstance(u,dict):return u
        conn=connect(app.config["DATABASE"])
        counts={r["status"]:r["n"] for r in conn.execute("SELECT status,COUNT(*) n FROM claims GROUP BY status")}
        chunks=conn.execute("SELECT COUNT(*) FROM policy_vectors").fetchone()[0]
        audit=conn.execute("SELECT a.*,u.full_name actor FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 8").fetchall();conn.close()
        return jsonify(counts=counts,policy_chunks=chunks,local_model=model_available(),audit=[dict(x) for x in audit])
    @app.get("/api/authority/evaluation")
    def evaluation_report():
        u=role_required("authority")
        if not isinstance(u,dict):return u
        from evaluation import evaluate
        report=evaluate(app.config["DATABASE"]);report["local_model"]=model_available()
        return jsonify(report)
    @app.post("/api/authority/claims/<int:claim_id>/decision")
    def decision(claim_id):
        u=role_required("authority")
        if not isinstance(u,dict):return u
        data=request.get_json(silent=True) or {};action=data.get("action");note=str(data.get("note", ""))[:500]
        if action not in ("approve","reject"):return jsonify(error="Choose approve or reject."),400
        conn=connect(app.config["DATABASE"]);row=conn.execute("SELECT status FROM claims WHERE id=?",(claim_id,)).fetchone()
        if not row:conn.close();return jsonify(error="Claim not found."),404
        if row["status"]!="pending_review":conn.close();return jsonify(error="Only claims awaiting review can be decided."),409
        status="approved_for_payment" if action=="approve" else "rejected"
        conn.execute("UPDATE claims SET status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP,review_note=? WHERE id=?",(status,u["id"],note,claim_id))
        conn.execute("INSERT INTO audit_log(actor_id,claim_id,action,detail) VALUES(?,?,?,?)",(u["id"],claim_id,"authority_"+action,note or "No additional note."));conn.commit();conn.close()
        return jsonify(ok=True,status=status)
    @app.post("/api/authority/claims/<int:claim_id>/payment")
    def payment(claim_id):
        u=role_required("authority")
        if not isinstance(u,dict):return u
        conn=connect(app.config["DATABASE"]);row=conn.execute("SELECT status FROM claims WHERE id=?",(claim_id,)).fetchone()
        if not row:conn.close();return jsonify(error="Claim not found."),404
        if row["status"] not in ("auto_approved","approved_for_payment"):conn.close();return jsonify(error="This claim is not in the payment queue."),409
        conn.execute("UPDATE claims SET status='payment_recorded',payment_confirmed_by=?,payment_confirmed_at=CURRENT_TIMESTAMP WHERE id=?",(u["id"],claim_id))
        conn.execute("INSERT INTO audit_log(actor_id,claim_id,action,detail) VALUES(?,?,?,?)",(u["id"],claim_id,"demo_payment_confirmed","Authority recorded demo payment confirmation; no funds were moved."));conn.commit();conn.close()
        return jsonify(ok=True,status="payment_recorded",message="Demo confirmation recorded. No payment service is connected.")
    @app.get("/api/authority/receipt/<int:receipt_id>")
    def receipt_text(receipt_id):
        u=role_required("authority")
        if not isinstance(u,dict):return u
        conn=connect(app.config["DATABASE"]);r=conn.execute("SELECT original_name,extracted_text,extraction_status FROM receipts WHERE id=?",(receipt_id,)).fetchone();conn.close()
        if not r:return jsonify(error="Receipt not found."),404
        return jsonify(receipt=dict(r))
    @app.get("/api/receipt/<int:receipt_id>/file")
    def receipt_file(receipt_id):
        u=role_required()
        if not isinstance(u,dict):return u
        conn=connect(app.config["DATABASE"])
        row=conn.execute("SELECT r.stored_name,r.original_name,EXISTS(SELECT 1 FROM claims c WHERE c.receipt_id=r.id AND c.employee_id=?) owns FROM receipts r WHERE r.id=?",(u["id"],receipt_id)).fetchone();conn.close()
        if not row:abort(404)
        if u["role"]!="authority" and not row["owns"]:abort(403)
        path=Path(app.config["UPLOAD_DIR"])/row["stored_name"]
        if not path.is_file():abort(404)
        return send_file(path,as_attachment=False,download_name=row["original_name"])
    @app.errorhandler(413)
    def too_large(_):return jsonify(error="That upload is too large. Maximum file size is 10 MB."),413
    return app

app=create_app()
if __name__=="__main__":
    print("ClaimGuard: starting the local web server...",flush=True)
    app.run(host="127.0.0.1",port=int(os.environ.get("PORT","5000")),debug=False)
