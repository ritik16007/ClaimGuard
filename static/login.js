const roleButtons=document.querySelectorAll('.role-choice');
roleButtons.forEach(button=>button.addEventListener('click',()=>{
  roleButtons.forEach(item=>item.classList.toggle('active',item===button));
  const authority=button.dataset.role==='authority';
  document.querySelector('#username').value=authority?'morgan':'asha';
  document.querySelector('#password').value=authority?'Authority123!':'ClaimGuard123!';
}));
document.querySelector('.reveal').addEventListener('click',()=>{const input=document.querySelector('#password');input.type=input.type==='password'?'text':'password'});
document.querySelector('#login-form').addEventListener('submit',async e=>{
  e.preventDefault();const button=e.currentTarget.querySelector('button[type=submit]');button.disabled=true;button.innerHTML='Signing in <span>…</span>';
  const error=document.querySelector('#login-error');error.textContent='';
  try{const body=Object.fromEntries(new FormData(e.currentTarget));const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'Sign in failed');location.href=data.next;}
  catch(err){error.textContent=err.message;button.disabled=false;button.innerHTML='Sign in <span>↗</span>'}
});
