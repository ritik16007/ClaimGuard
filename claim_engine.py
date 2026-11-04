from __future__ import annotations
import hashlib, re
from datetime import date, datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from db import connect

LIMITS={"travel":5000.0,"meals":1500.0,"lodging":5000.0}
EXTENSIONS={".pdf",".png",".jpg",".jpeg",".webp"}
MAX_UPLOAD=10*1024*1024

def suspicious(text):
    s=text.lower()
    patterns=[
        # Accept common paraphrases, including "ignore all the previous commands".
        r"\bignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|earlier|above|system)\b",
        r"\b(?:disregard|forget)\s+(?:(?:all|the)\s+)?(?:previous|prior|earlier|above|system)\s+(?:commands?|instructions?|rules?)\b",
        r"\boverride\s+(?:the\s+)?(?:policy|rules|limit|instructions)\b",
        r"\bbypass\s+(?:the\s+)?(?:policy|approval|checks|limits|controls)\b",
        r"\bforget\s+(?:your\s+)?(?:rules|instructions)\b",
        r"\breveal\s+(?:the\s+)?(?:system prompt|prompt)\b",
        r"\bpretend\s+(?:you are|to be)\b",
        r"\b(?:reimburse|pay)\s+me\b.{0,45}\b(?:100000|\d{5,})\b",
        # Reject demands for approval of a large amount, regardless of wording.
        r"\b(?:approve|accept|authorize)\b.{0,70}\b(?:claim|reimbursement|payment)\b.{0,50}\b(?:100000|\d{5,})\b",
    ]
    return any(re.search(p,s) for p in patterns)

def parse_date(value):
    if not value: return None
    value=str(value).strip()
    value=re.sub(r"(?<=\d)(?:st|nd|rd|th)\b","",value,flags=re.I)
    value=re.sub(r"\s*,\s*"," ",value)
    formats=("%Y-%m-%d","%Y/%m/%d","%d/%m/%Y","%d-%m-%Y","%d.%m.%Y","%d/%m/%y","%d-%m-%y",
             "%d %b %Y","%d %B %Y","%b %d %Y","%B %d %Y")
    for fmt in formats:
        try: return datetime.strptime(value,fmt).date()
        except ValueError: pass
    return None

def extract_receipt_text(data, ext):
    """Extract selectable PDF text, then fall back to local OCR for images/scans."""
    import io
    if ext==".pdf":
        try:
            from pypdf import PdfReader
            text="\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages).strip()
            if text:return text
            # Scanned PDFs have no selectable text; rasterize pages and OCR them.
            from pypdfium2 import PdfDocument
            from PIL import Image
            pdf=PdfDocument(data); pages=[]
            for page in pdf:
                bitmap=page.render(scale=2.5)
                pages.append(_ocr_image(bitmap.to_pil().convert("RGB")))
            return "\n".join(pages).strip()
        except Exception:
            try:
                from pypdfium2 import PdfDocument
                pdf=PdfDocument(data)
                return "\n".join(_ocr_image(p.render(scale=2.5).to_pil().convert("RGB")) for p in pdf).strip()
            except Exception:return ""
    try:
        from PIL import Image
        image=Image.open(io.BytesIO(data)).convert("RGB")
        return _ocr_image(image)
    except Exception: return ""

_rapid_ocr=None
def _ocr_image(image):
    """Prefer bundled local OCR; use Tesseract as a local fallback when present."""
    global _rapid_ocr
    try:
        import numpy as np
        from rapidocr import RapidOCR
        if _rapid_ocr is None:_rapid_ocr=RapidOCR()
        result=_rapid_ocr(np.asarray(image))
        lines=[str(t).strip() for t in (getattr(result,"txts",None) or ()) if str(t).strip()]
        if lines:return "\n".join(lines)
    except Exception:
        pass
    try:
        import pytesseract
        from PIL import ImageOps, ImageEnhance, ImageFilter
        gray=ImageOps.grayscale(image)
        if gray.width<1400:gray=gray.resize((gray.width*2,gray.height*2))
        gray=ImageEnhance.Contrast(gray).enhance(1.7).filter(ImageFilter.SHARPEN)
        return pytesseract.image_to_string(gray,config="--psm 6")
    except Exception:return ""

def extract_amount(text):
    if not text: return None
    normalized=text.replace(",","")
    total=re.search(r"(?:grand\s+total|amount\s+paid|total\s+amount|total|net\s+amount)\s*[:\-]?\s*(?:inr|rs\.?|₹)?\s*(\d+(?:\.\d{1,2})?)",normalized,re.I)
    if total:
        try: return float(total.group(1))
        except ValueError: pass
    values=[]
    for raw in re.findall(r"(?:INR|Rs\.?|₹)\s*(\d+(?:\.\d{1,2})?)",normalized,re.I):
        try: values.append(float(raw))
        except ValueError: pass
    # Amount is deliberately not guessed from arbitrary bare numbers.
    return max(values) if values else None

def extract_receipt_date(text):
    if not text: return None
    patterns=(
        r"\b(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2})\b",
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?[,]?\s+20\d{2}\b",
        r"\b[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+20\d{2}\b",
    )
    candidates=[candidate for pattern in patterns for candidate in re.findall(pattern,text,re.I)]
    for candidate in candidates:
        parsed=parse_date(candidate)
        if parsed:return parsed
    return None

def decide_claim(category, amount, extraction_status="readable", date_match=True, submission_age=0,
                 exact_duplicate=False, possible_duplicate=False, suspicious_input=False, future_date=False):
    """Shared deterministic policy decision used by claim processing and live evaluation."""
    if suspicious_input:return {"status":"rejected","risk":"high","reason":"Suspicious instruction or attempt to bypass controls."}
    if exact_duplicate:return {"status":"rejected","risk":"high","reason":"Exact receipt file was already submitted."}
    if future_date:return {"status":"rejected","risk":"high","reason":"Expense date is in the future."}
    reasons=[];risk="low"
    if extraction_status!="readable":reasons.append("Receipt amount could not be read with confidence");risk="medium"
    if date_match is False:reasons.append("Entered expense date does not match the receipt date");risk="high"
    elif date_match is None:reasons.append("Receipt date could not be verified from its text");risk="medium"
    if category not in LIMITS:reasons.append("Unknown expense category");risk="medium"
    elif amount is not None and amount>LIMITS[category]:reasons.append(f"Amount exceeds the INR {LIMITS[category]:,.0f} auto-approval limit for {category}");risk="medium"
    if submission_age>30:reasons.append("Submitted more than 30 days after expense");risk="medium"
    if possible_duplicate:reasons.append("Possible duplicate purchase; authority comparison required");risk="high"
    return {"status":"pending_review" if reasons else "auto_approved","risk":risk,
            "reason":"; ".join(reasons) if reasons else "Receipt checks passed and amount is within the fictional auto-approval limit."}

def claim_submit(db_path, upload_dir, employee_id, category, date_text, purpose, file_storage, chat_text=""):
    conn=connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if suspicious(chat_text):
            decision=decide_claim(category or "unknown",None,suspicious_input=True)
            cur=conn.execute("INSERT INTO claims(employee_id,category,expense_date,status,risk,reason) VALUES(?,?,?,?,?,?)",(employee_id,category or "unknown",date_text or "",decision["status"],decision["risk"],decision["reason"]))
            cid=cur.lastrowid; conn.execute("INSERT INTO audit_log(actor_id,claim_id,action,detail) VALUES(?,?,?,?)",(employee_id,cid,"claim_rejected","Suspicious instruction detected.")); conn.commit()
            return dict(id=cid,status=decision["status"],reason="That claim message attempted to bypass the reimbursement checks, so it was rejected and recorded.")
        exp_date=parse_date(date_text)
        category=(category or "").lower().strip()
        if category in ("food","meal","meals","dining"): category="meals"
        if category in ("hotel","accommodation","accommodations","stay"): category="lodging"
        if category in ("transport","taxi","rail","flight","local travel"): category="travel"
        if not category or category not in LIMITS: category=category or "unknown"
        safe=secure_filename(file_storage.filename) if file_storage and getattr(file_storage,"filename","") else ""
        ext=Path(safe).suffix.lower() if safe else ""
        data=None
        if file_storage and safe:
            if ext not in EXTENSIONS:return dict(status="need_info",reason="Please upload a PDF, PNG, JPG, JPEG, or WEBP receipt.")
            data=file_storage.read(MAX_UPLOAD+1)
            if len(data)>MAX_UPLOAD:return dict(status="need_info",reason="That file is over the 10 MB limit. Please upload a smaller receipt.")
            if not data:return dict(status="need_info",reason="The uploaded receipt file is empty. Please choose the receipt again.")
            digest=hashlib.sha256(data).hexdigest()
            duplicate=conn.execute("SELECT id FROM receipts WHERE sha256=?",(digest,)).fetchone()
            if duplicate:
                decision=decide_claim(category,None,exact_duplicate=True)
                cur=conn.execute("INSERT INTO claims(employee_id,receipt_id,category,expense_date,status,risk,reason) VALUES(?,?,?,?,?,?,?)",(employee_id,duplicate["id"],category,date_text or "",decision["status"],decision["risk"],decision["reason"]))
                conn.execute("INSERT INTO audit_log(actor_id,claim_id,action,detail) VALUES(?,?,?,?)",(employee_id,cur.lastrowid,"duplicate_rejected",f"Exact SHA-256 match to receipt {duplicate['id']}."));conn.commit()
                return dict(id=cur.lastrowid,status="rejected",reason="This exact receipt file is already in the database, so the repeat claim was rejected.")
        missing=[]
        if not category: missing.append("expense category (travel, meals, or lodging)")
        if not exp_date: missing.append("expense date (YYYY-MM-DD or YYYY/MM/DD)")
        if data is None: missing.append("receipt image or PDF")
        if missing:
            if len(missing)==1:
                prompt=f"To continue this claim, please provide the missing {missing[0]}."
            else:
                prompt="To continue this claim, please provide the missing details: "+"; ".join(missing)+"."
            return dict(status="need_info",reason=prompt)
        extracted=extract_receipt_text(data,ext)
        amount=extract_amount(extracted)
        receipt_day=extract_receipt_date(extracted)
        merchant=next((line.strip()[:120] for line in extracted.splitlines() if len(line.strip())>2),"")
        receipt_status="readable" if extracted and amount is not None else "uncertain"
        name=f"{digest[:16]}{ext}"
        target=Path(upload_dir)/name; Path(upload_dir).mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        cur=conn.execute("INSERT INTO receipts(sha256,stored_name,original_name,mime_type,extracted_text,extraction_status) VALUES(?,?,?,?,?,?)",(digest,name,safe,"application/pdf" if ext==".pdf" else "image/"+ext[1:],extracted,receipt_status))
        rid=cur.lastrowid
        possible=conn.execute("SELECT id FROM claims WHERE amount=? AND expense_date=? AND lower(merchant)=lower(?) AND status!='rejected'",(amount,exp_date.isoformat(),merchant)).fetchone() if amount is not None and merchant else None
        decision=decide_claim(category,amount,receipt_status,(receipt_day==exp_date if receipt_day else None),(date.today()-exp_date).days,possible_duplicate=bool(possible),future_date=exp_date>date.today())
        status,risk,reason=decision["status"],decision["risk"],decision["reason"]
        cur=conn.execute("INSERT INTO claims(employee_id,receipt_id,category,expense_date,amount,merchant,business_purpose,status,risk,reason,duplicate_of) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(employee_id,rid,category,exp_date.isoformat(),amount,merchant,purpose or "",status,risk,reason,possible["id"] if possible else None))
        cid=cur.lastrowid
        conn.execute("INSERT INTO audit_log(actor_id,claim_id,action,detail) VALUES(?,?,?,?)",(employee_id,cid,"claim_submitted",reason))
        conn.commit()
        return dict(id=cid,status=status,reason=reason,amount=amount,category=category,expense_date=exp_date.isoformat(),receipt_extraction=receipt_status)
    finally: conn.close()
