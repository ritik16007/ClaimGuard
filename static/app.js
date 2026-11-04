const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusLabel={auto_approved:'Auto-approved',pending_review:'Needs review',approved_for_payment:'Approved · payment',payment_recorded:'Payment recorded',rejected:'Rejected'};
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),3300)}
async function api(url,options={}){const res=await fetch(url,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(options.headers||{})}});let data={};try{data=await res.json()}catch{}if(!res.ok)throw Error(data.error||'Something went wrong. Please try again.');return data}
function money(v){return v==null?'Unread':new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(v)}
function pill(status){return `<span class="status-pill status-${esc(status)}">${esc(statusLabel[status]||status)}</span>`}
function stat(title,value,note,icon){return `<article class="stat-card"><div class="stat-head">${title}<span class="stat-icon">${icon}</span></div><div class="stat-number">${value}</div><div class="stat-note">${note}</div></article>`}
function empty(icon,title,detail){return `<div class="empty-state"><div class="empty-icon">${icon}</div><strong>${title}</strong><div style="margin-top:6px">${detail}</div></div>`}
function evalTable(rows,rag=false){const head=rag?'<th>QUESTION</th><th>EXPECTED</th><th>TOP RETRIEVAL</th><th>RESULT</th>':'<th>SCENARIO</th><th>EXPECTED</th><th>OBSERVED</th><th>RESULT</th>';return `<table class="data-table"><thead><tr>${head}</tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(rag?r.question:r.case)}</td><td>${esc(r.expected)}</td><td>${esc(r.observed)}</td><td><span class="status-pill ${r.pass?'status-auto_approved':'status-pending_review'}">${r.pass?'Pass':'Check'}</span></td></tr>`).join('')}</tbody></table>`}
function claimTable(claims,mode='employee'){
 if(!claims.length)return empty(mode==='review'?'✓':'▤',mode==='review'?'Nothing needs review':'No claims yet',mode==='review'?'New exceptions will appear here.':'Your submitted expenses will show here.');
 const headings=mode==='review'?'<th>EMPLOYEE</th><th>EXPENSE</th><th>RECEIPT CHECK</th><th>DECISION</th><th></th>':mode==='payment'?'<th>EMPLOYEE</th><th>EXPENSE</th><th>AMOUNT</th><th>APPROVAL</th><th></th>':mode==='recent'?'<th>EMPLOYEE</th><th>EXPENSE</th><th>AMOUNT</th><th>STATUS</th>':'<th>EXPENSE</th><th>AMOUNT</th><th>RECEIPT</th><th>STATUS</th><th>SUBMITTED</th>';
 return `<table class="data-table"><thead><tr>${headings}</tr></thead><tbody>${claims.map(c=>{
  const expense=`<span class="table-primary">${esc(c.category[0]?.toUpperCase()+c.category.slice(1))} · ${esc(c.expense_date)}</span><span class="table-sub">${esc(c.reason)}</span>`;
  const receipt=c.receipt_name?`<a class="receipt-link" href="/api/receipt/${c.receipt_id}/file" target="_blank" rel="noopener">${esc(c.receipt_name)}</a><span class="table-sub">${esc(c.extraction_status||'stored')}</span>`:'—';
  if(mode==='review')return `<tr><td>${esc(c.employee||'Employee')}<span class="table-sub">Claim #${c.id}</span></td><td>${expense}<span class="table-sub">${money(c.amount)}</span></td><td>${receipt}</td><td>${pill(c.status)}</td><td><div class="review-actions"><button class="small-button approve" data-decision="approve" data-id="${c.id}">Approve</button><button class="small-button reject" data-decision="reject" data-id="${c.id}">Reject</button></div></td></tr>`;
  if(mode==='payment')return `<tr><td>${esc(c.employee||'Employee')}<span class="table-sub">Claim #${c.id}</span></td><td>${expense}</td><td>${money(c.amount)}</td><td>${pill(c.status)}</td><td><button class="small-button approve payment-action" data-payment="${c.id}">Confirm demo payment</button></td></tr>`;
  if(mode==='recent')return `<tr><td>${esc(c.employee||'Employee')}<span class="table-sub">Claim #${c.id}</span></td><td>${expense}</td><td>${money(c.amount)}</td><td>${pill(c.status)}</td></tr>`;
  return `<tr><td>${expense}</td><td>${money(c.amount)}</td><td>${receipt}</td><td>${pill(c.status)}</td><td>${esc(c.created_at||'—')}</td></tr>`;
 }).join('')}</tbody></table>`;
}
async function loadWorkspace(){
 try{
  const [claimsData,status]=await Promise.all([api('/api/claims'),api('/api/status')]);const claims=claimsData.claims;
  $('#ai-status').textContent=!status.policy_ready?'Indexing handbook…':status.local_model?'Local AI ready':'Grounded assistant ready';
  const pending=claims.filter(c=>c.status==='pending_review'),queue=claims.filter(c=>['auto_approved','approved_for_payment'].includes(c.status));
  if(CLAIMGUARD_ROLE==='employee'){
   $('#stats-grid').innerHTML=[stat('Submitted claims',claims.length,'Your complete history','▤'),stat('In review',pending.length,'Awaiting authority','◷'),stat('Ready for payment',claims.filter(c=>c.status==='auto_approved'||c.status==='approved_for_payment').length,'Approved · not yet paid','↗'),stat('Recorded',claims.filter(c=>c.status==='payment_recorded').length,'Demo confirmation only','✓')].join('');
   $('#home-claims').innerHTML=claimTable(claims.slice(0,4));$('#all-claims').innerHTML=claimTable(claims);
  }else{
   $('#stats-grid').innerHTML=[stat('Needs review',pending.length,'Exceptions requiring you','◷'),stat('Payment queue',queue.length,'Approved · awaiting action','↗'),stat('Paid · demo',claims.filter(c=>c.status==='payment_recorded').length,'Authority recorded only','✓'),stat('Policy pages',status.policy_chunks,'Local retrieval index','⌕')].join('');
   $('#review-count').textContent=pending.length;$('#review-claims').innerHTML=claimTable(pending,'review');$('#payment-claims').innerHTML=claimTable(queue,'payment');$('#home-claims').innerHTML=claimTable(claims.slice(0,5),'recent');
   const overview=await api('/api/authority/overview');$('#audit-list').innerHTML=overview.audit.length?overview.audit.map(a=>`<div class="audit-row"><span class="audit-dot"></span><div><strong>${esc(a.action.replaceAll('_',' '))} · Claim #${esc(a.claim_id)}</strong><p>${esc(a.detail)}</p><small>${esc(a.actor||'System')} · ${esc(a.created_at)}</small></div></div>`).join(''):empty('◷','No recorded activity','Decisions will appear here.');
   const evaluation=await api('/api/authority/evaluation');const rp=evaluation.policy_rules,qp=evaluation.policy_retrieval;$('#eval-stats').innerHTML=[stat('Policy engine',`${rp.passed}/${rp.total}`,`${Math.round(100*rp.passed/rp.total)}% deterministic scenarios pass`,'✓'),stat('Policy retrieval',`${qp.passed}/${qp.total}`,`${Math.round(100*qp.passed/qp.total)}% first source match`,'⌕'),stat('Indexed pages',qp.chunks,'SQLite policy vectors','▧'),stat('Local LLM',evaluation.local_model?'Ready':'Not installed',evaluation.local_model?'Qwen runs on this PC':'Grounded retrieval fallback active','✳')].join('');$('#eval-rules').innerHTML=evalTable(rp.cases);$('#eval-rag').innerHTML=evalTable(qp.cases,true);
  }
  const policies=await api('/api/policies');$('#policy-grid').innerHTML=policies.documents.length?policies.documents.map(d=>`<article class="policy-card"><div class="policy-file">▧</div><div><h3>${esc(d.document)}</h3><p>Fictional company reimbursement handbook with guidance, evidence requirements, and review paths.</p><div class="policy-meta"><span>${d.pages} pages</span><span>Indexed locally</span><a href="${esc(d.pdf_url)}" target="_blank" rel="noopener">Download PDF ↗</a></div></div></article>`).join(''):empty('⌕','Indexing the policy handbook','Your local policy search will be available shortly.');
 }catch(e){toast(e.message)}
}
function switchTab(tab){$$('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.tab===tab));$$('.view').forEach(x=>x.classList.toggle('active',x.id==='view-'+tab));if(tab==='assistant')$('#chat-input')?.focus()}
$$('[data-tab]').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.tab)));
$$('[data-goto]').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.goto)));
$('#logout').addEventListener('click',async()=>{await api('/api/logout',{method:'POST'});location.href='/login'});
const fileInput=$('#receipt-file');if(fileInput)fileInput.addEventListener('change',()=>{$('#file-chip').textContent=fileInput.files[0]?`📎 ${fileInput.files[0].name}`:''});
const messages=$('#chat-messages');
function addMessage(text,who='assistant',foot=''){const row=document.createElement('div');row.className=`message ${who==='user'?'user-message':'assistant-message'}`;row.innerHTML=`<div class="message-avatar">${who==='user'?'◉':'✳'}</div><div class="bubble-wrap"><div class="sender-label">${who==='user'?'YOU':'CLAIMGUARD'} <span>JUST NOW</span></div><div class="bubble"></div>${foot?`<div class="message-foot">${esc(foot)}</div>`:''}</div>`;row.querySelector('.bubble').textContent=text;messages.appendChild(row);messages.scrollTop=messages.scrollHeight;return row}
const form=$('#chat-form');if(form){
 $('#chat-input').addEventListener('input',e=>{e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,110)+'px'});
 $$('.suggestion').forEach(b=>b.addEventListener('click',()=>{$('#chat-input').value=b.dataset.prompt;form.requestSubmit()}));
 form.addEventListener('submit',async e=>{e.preventDefault();const input=$('#chat-input'),message=input.value.trim(),file=fileInput.files[0];if(!message&&!file)return;const display=message||`Please help me file a claim with this receipt: ${file.name}`;addMessage(display,'user');input.value='';input.style.height='auto';const pending=addMessage('','assistant');pending.querySelector('.bubble').innerHTML='<span class="thinking"><i></i><i></i><i></i></span>';const warmupNotice=setTimeout(()=>{const bubble=pending.querySelector('.bubble');if(bubble&&bubble.querySelector('.thinking'))bubble.textContent='Loading the local assistant for its first answer. This can take a little longer; later replies should be quicker.'},3500);const send=$('.send-button');send.disabled=true;
  try{const body=new FormData();body.append('message',display);if(file)body.append('receipt',file);const result=await api('/api/chat',{method:'POST',body});pending.querySelector('.bubble').textContent=result.reply;if(result.kind==='claim'&&result.claim.status!=='need_info'&&file){fileInput.value='';$('#file-chip').textContent=''}await loadWorkspace();}
  catch(err){pending.querySelector('.bubble').textContent=err.message}finally{clearTimeout(warmupNotice);send.disabled=false;messages.scrollTop=messages.scrollHeight}
 });
}
document.addEventListener('click',async e=>{
 const decision=e.target.closest('[data-decision]');if(decision){const action=decision.dataset.decision;let note='';if(action==='reject'){note=prompt('Add a reason for rejection:')||'';if(!note.trim()){toast('Please provide a reason for rejecting this claim.');return}}else{note=prompt('Optional review note:')||''}try{await api(`/api/authority/claims/${decision.dataset.id}/decision`,{method:'POST',body:JSON.stringify({action,note})});toast(`Claim ${action==='approve'?'approved for payment':'rejected'}.`);loadWorkspace()}catch(err){toast(err.message)}return}
 const payment=e.target.closest('[data-payment]');if(payment){if(!confirm('Record a demo payment confirmation? This does not transfer money.'))return;try{const r=await api(`/api/authority/claims/${payment.dataset.payment}/payment`,{method:'POST',body:JSON.stringify({})});toast(r.message);loadWorkspace()}catch(err){toast(err.message)}return}
});
loadWorkspace();
