from claim_engine import decide_claim
from rag import retrieve
from db import connect

RULE_CASES=[
    ("Travel at cap",("travel",5000,"readable",True,0),"auto_approved"),
    ("Travel over cap",("travel",5001,"readable",True,0),"pending_review"),
    ("Meals at cap",("meals",1500,"readable",True,0),"auto_approved"),
    ("Meals over cap",("meals",1501,"readable",True,0),"pending_review"),
    ("Lodging at cap",("lodging",5000,"readable",True,0),"auto_approved"),
    ("Unknown category",("souvenirs",500,"readable",True,0),"pending_review"),
    ("Uncertain receipt",("travel",500,"uncertain",None,0),"pending_review"),
    ("Date mismatch",("meals",500,"readable",False,0),"pending_review"),
    ("Possible duplicate",("travel",500,"readable",True,0,"possible"),"pending_review"),
    ("31-day submission",("meals",500,"readable",True,31),"pending_review"),
    ("Exact duplicate",("travel",500,"readable",True,0,"exact"),"rejected"),
    ("Future date",("travel",500,"readable",True,0,"future"),"rejected"),
    ("Prompt injection",("travel",500,"readable",True,0,"attack"),"rejected"),
]
RETRIEVAL_CASES=[
    ("What is the hotel allowance?","Meals and Accommodation",3),
    ("What is the meal limit?","Meals and Accommodation",1),
    ("How much is taxi fare limit?","Travel Expense Policy",3),
    ("What is the submission deadline?","Travel Expense Policy",7),
    ("What happens with duplicate submissions?","Reimbursement Approval Rules",4),
    ("Who approves claims awaiting manager review?","Reimbursement Approval Rules",3),
    ("How do I handle a lost receipt?","Expense Exceptions and FAQ",2),
    ("Does approval trigger a bank payout?","Reimbursement Approval Rules",5),
    ("How much annual leave can I take?",None,None),
]

def evaluate(db_path):
    rule_rows=[]
    for name,args,expected in RULE_CASES:
        values=list(args);flags={}
        if len(values)>5:
            flag=values.pop()
            flags={"exact_duplicate":flag=="exact","future_date":flag=="future","suspicious_input":flag=="attack"}
            if flag=="possible":flags={"possible_duplicate":True}
        decision=decide_claim(*values,**flags)
        rule_rows.append({"case":name,"expected":expected,"observed":decision["status"],"pass":decision["status"]==expected})
    conn=connect(db_path);rag_rows=[]
    for question,doc,page in RETRIEVAL_CASES:
        hits=retrieve(conn,question,1);top=hits[0] if hits else None
        ok=(top is None) if doc is None else bool(top and top["document"]==doc and top["page"]==page)
        rag_rows.append({"question":question,"expected":f"{doc} p.{page}" if doc else "abstain","observed":f"{top['document']} p.{top['page']} · {top['heading']}" if top else "abstain","pass":ok})
    chunks=conn.execute("SELECT COUNT(*) FROM policy_vectors").fetchone()[0];conn.close()
    return {"policy_rules":{"passed":sum(r["pass"] for r in rule_rows),"total":len(rule_rows),"cases":rule_rows},
            "policy_retrieval":{"passed":sum(r["pass"] for r in rag_rows),"total":len(rag_rows),"cases":rag_rows,"chunks":chunks,
            "note":"Fixture evaluation only: receipt OCR and language-model writing quality are not measured here."}}
