"""
Quick fix: replaces everything from <script> to end of file in admin/index.html
with a clean version. 

Run: python fix_admin.py
(from project root or anywhere, just update the PATH below if needed)
"""
from pathlib import Path

p = Path(__file__).parent / 'admin' / 'index.html'
html = p.read_text(encoding='utf-8')

# Find the last <script> tag — everything before it is clean HTML/CSS
cut = html.rfind('<script>')
assert cut != -1, "<script> not found"

head = html[:cut]

# Write clean script (all on one line to avoid encoding issues)
script = r"""<script>
const API='https://krashi-mitra-v1.onrender.com';
function getAdminAuth(){let e=localStorage.getItem('km_admin_auth');if(!e){const u=prompt('Admin username','admin')||'admin',p=prompt('Admin password')||'';e=btoa(`${u}:${p}`);localStorage.setItem('km_admin_auth',e);}return'Basic '+e;}
function resetAdminAuth(){localStorage.removeItem('km_admin_auth');toast('Admin login reset. Refresh and enter credentials again.','ok');}
const AUTH=getAdminAuth();
setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleTimeString('en-IN');},1000);
function showPage(name,el){document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));document.getElementById('page-'+name).classList.add('active');el.classList.add('active');if(name==='status')loadStatus();if(name==='uploads')loadFiles();if(name==='cache')loadCache();}
function toast(msg,type='ok'){const t=document.getElementById('toast');t.textContent=msg;t.className=`show ${type}`;setTimeout(()=>t.className='',3000);}
async function safeJson(r){const raw=await r.text();try{return raw?JSON.parse(raw):{};}catch(_){return{_raw:raw};}}

async function loadStatus(){
  const btn=document.querySelector('#page-status .btn-ghost');
  if(btn){btn.innerHTML='<span style="display:inline-block;animation:spin .7s linear infinite;margin-right:4px;">\u21bb</span> Loading';btn.disabled=true;}
  try{
    const r=await fetch(`${API}/admin/status`,{headers:{Authorization:AUTH,'Content-Type':'application/json'}});
    const d=await safeJson(r);
    if(!r.ok)throw new Error(`Server error ${r.status}: ${d.detail||d.message||(d._raw||'').slice(0,160)||'empty'}`);
    setCard('s-gemini',d.gemini_configured?'\u2713':'\u2717',d.gemini_configured?'ok':'err',d.gemini_configured?'Key configured':'Key not set');
    setCard('s-ollama',d.ollama_running?'\u2713':'\u2717',d.ollama_running?'ok':'warn',d.ollama_running?d.ollama_model:'Not running');
    document.getElementById('s-chroma').textContent=d.chroma_chunks??'\u2014';
    document.getElementById('s-cache').textContent=d.cache_entries??'\u2014';
  }catch(e){toast('Backend \u0938\u0947 connect \u0928\u0939\u0940\u0902 \u0939\u094b \u092a\u093e\u092f\u093e: '+e.message,'err');}
  finally{if(btn){btn.textContent='\u21bb Refresh';btn.disabled=false;}}
}
function setCard(id,val,cls,sub){const el=document.getElementById(id);el.textContent=val;el.className=`card-value ${cls}`;if(sub)document.getElementById(id+'-sub').textContent=sub;}

async function testAsk(){
  const q=document.getElementById('test-q').value.trim();if(!q)return;
  const log=document.getElementById('test-log');
  log.innerHTML='<span class="log-warn">AI \u0915\u094b \u0938\u0935\u093e\u0932 \u092d\u0947\u091c\u093e \u091c\u093e \u0930\u0939\u093e \u0939\u0948...</span>';
  try{
    const r=await fetch(`${API}/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q,crop:'wheat_up',language:'hindi',district:'Meerut',user_id:null})});
    const d=await safeJson(r);
    if(!r.ok){log.innerHTML=`<span class="log-err">\u274c Server error ${r.status}: ${escHtml(d.detail||d.message||d._raw||'')}</span>`;return;}
    const src=d.source||'unknown';
    const cached=d.cached?' \u2022 <span style="color:var(--amber)">[CACHE HIT \u2014 API saved \u2705]</span>':'';
    log.innerHTML=`<span class="log-ok">[${src.toUpperCase()}]${cached}</span>\n\n`+escHtml(d.answer||d.message||JSON.stringify(d));
  }catch(e){log.innerHTML=`<span class="log-err">\u274c Network error: ${escHtml(e.message)}</span>`;}
}

async function loadFiles(){
  const tbody=document.getElementById('files-tbody');
  try{
    const r=await fetch(`${API}/admin/files`,{headers:{Authorization:AUTH}});
    const d=await safeJson(r);
    if(!d.files||!d.files.length){tbody.innerHTML='<tr><td colspan="4" style="color:var(--muted)">No PDFs uploaded yet.</td></tr>';return;}
    tbody.innerHTML=d.files.map(f=>`<tr><td>\ud83d\udcc4 ${f.name}</td><td style="font-family:var(--mono);color:var(--muted)">${f.size_kb} KB</td><td style="font-family:var(--mono);color:var(--muted)">${f.uploaded_at}</td><td><button class="btn btn-red" style="padding:4px 10px;font-size:11px;" onclick="deleteFile('${f.name}')">Delete</button></td></tr>`).join('');
  }catch(e){tbody.innerHTML=`<tr><td colspan="4" style="color:var(--red)">Error: ${escHtml(e.message)}</td></tr>`;}
}
async function uploadFile(input){
  const file=input.files[0];if(!file)return;
  const prog=document.getElementById('upload-progress'),bar=document.getElementById('progress-bar'),lbl=document.getElementById('progress-label');
  prog.style.display='block';bar.style.width='30%';lbl.textContent=`Uploading ${file.name}...`;
  const fd=new FormData();fd.append('file',file);
  try{
    bar.style.width='70%';
    const r=await fetch(`${API}/admin/upload`,{method:'POST',headers:{Authorization:AUTH},body:fd});
    const d=await safeJson(r);bar.style.width='100%';
    lbl.textContent=`\u2713 ${d.filename} \u2014 ${d.chunks_indexed} chunks indexed`;
    toast(`\u2705 ${d.filename} uploaded & indexed`,'ok');
    setTimeout(()=>{prog.style.display='none';bar.style.width='0%';},2000);loadFiles();
  }catch(e){lbl.textContent='Upload failed';toast('Upload failed: '+e.message,'err');}
  input.value='';
}
async function deleteFile(name){if(!confirm(`Delete "${name}"?`))return;try{await fetch(`${API}/admin/files/${name}`,{method:'DELETE',headers:{Authorization:AUTH}});toast(`\ud83d\uddd1 ${name} deleted`,'ok');loadFiles();}catch(e){toast('Delete failed','err');}}
const dz=document.getElementById('drop-zone');
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag');});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag'));
dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('drag');const fi=document.getElementById('file-input');fi.files=e.dataTransfer.files;uploadFile(fi);});

async function loadCache(){
  try{
    const r=await fetch(`${API}/admin/cache/stats`,{headers:{Authorization:AUTH}});
    const d=await safeJson(r);
    document.getElementById('c-total').textContent=d.total_entries??'\u2014';
    document.getElementById('c-hits').textContent=d.total_hits??'\u2014';
    document.getElementById('c-size').textContent=(d.cache_file_kb??'\u2014')+' KB';
    const list=document.getElementById('q-list'),qs=d.top_questions||[];
    if(!qs.length){list.innerHTML='<div style="color:var(--muted);font-family:var(--mono);font-size:13px;">Cache is empty.</div>';return;}
    list.innerHTML=qs.map((q,i)=>`<div class="q-item" id="qitem-${i}"><div style="flex:1;min-width:0;"><div class="q-text">${escHtml(q.question)}</div><div class="q-meta" style="margin-top:4px;"><span style="color:var(--green);font-weight:700;">${q.source||'unknown'}</span> \u00b7 ${q.saved_at?.split('T')[0]||''} \u00b7 <span style="color:var(--amber);">${q.hits||0} hits</span></div><div id="qanswer-${i}" style="font-size:12px;color:var(--muted);font-family:var(--hindi);margin-top:6px;display:none;padding:8px;background:var(--bg);border-radius:6px;border:1px solid var(--border);">${escHtml(q.answer||'\u2014')}</div></div><div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0;margin-left:12px;"><button class="btn btn-ghost" style="padding:4px 10px;font-size:11px;" onclick="toggleAnswer(${i})">\ud83d\udc41 Answer</button><button class="btn btn-amber" style="padding:4px 10px;font-size:11px;" onclick="editCacheEntry(${i},${JSON.stringify(q.question).replace(/'/g,'&#39;')},${JSON.stringify(q.answer||'').replace(/'/g,'&#39;')})">\u270f\ufe0f Edit</button><button class="btn btn-red" style="padding:4px 10px;font-size:11px;" onclick="deleteCacheEntry(${i},${JSON.stringify(q.question).replace(/'/g,'&#39;')})">\ud83d\uddd1 Delete</button></div></div>`).join('');
  }catch(e){toast('Cache load failed: '+e.message,'err');}
}
function toggleAnswer(i){const el=document.getElementById(`qanswer-${i}`);el.style.display=el.style.display==='none'?'block':'none';}
async function deleteCacheEntry(i,question){
  if(!confirm(`Delete this entry?\n"${question}"`))return;
  try{const r=await fetch(`${API}/admin/cache/delete`,{method:'DELETE',headers:{Authorization:AUTH,'Content-Type':'application/json'},body:JSON.stringify({question})});const d=await safeJson(r);if(d.deleted){document.getElementById(`qitem-${i}`).style.opacity='0';setTimeout(()=>{document.getElementById(`qitem-${i}`).remove();},300);toast('\u2705 Entry deleted','ok');loadCache();}else{toast('Entry not found','err');}}
  catch(e){toast('Delete failed: '+e.message,'err');}
}
async function editCacheEntry(i,question,currentAnswer){
  const newAnswer=prompt('Edit answer for:\n"'+question+'"',currentAnswer);
  if(!newAnswer||newAnswer===currentAnswer)return;
  try{const r=await fetch(`${API}/admin/cache/edit`,{method:'PUT',headers:{Authorization:AUTH,'Content-Type':'application/json'},body:JSON.stringify({question,new_answer:newAnswer})});const d=await safeJson(r);if(d.updated){toast('\u2705 Answer updated','ok');loadCache();}else{toast('Entry not found','err');}}
  catch(e){toast('Edit failed: '+e.message,'err');}
}
async function clearCache(){
  if(!confirm('\u0938\u092d\u0940 cached entries delete \u0939\u094b\u0902\u0917\u0940\u0964 \u091c\u093e\u0930\u0940 \u0930\u0916\u0947\u0902?'))return;
  try{const r=await fetch(`${API}/admin/cache/clear`,{method:'DELETE',headers:{Authorization:AUTH}});const d=await safeJson(r);toast(`\u2705 ${d.deleted_entries} entries cleared`,'ok');loadCache();}
  catch(e){toast('Clear failed','err');}
}
function toggleAddQA(){const toggle=document.getElementById('add-qa-toggle'),body=document.getElementById('add-qa-body'),isOpen=body.classList.contains('open');body.classList.toggle('open',!isOpen);toggle.classList.toggle('open',!isOpen);if(!isOpen)document.getElementById('qa-question').focus();}
function updateQACount(){const q=document.getElementById('qa-question').value.trim(),a=document.getElementById('qa-answer').value.trim(),btn=document.getElementById('add-qa-btn');document.getElementById('qa-charcount').textContent=`Q: ${q.length} | A: ${a.length}`;btn.disabled=!(q.length>3&&a.length>=20);}
function clearQAForm(){document.getElementById('qa-question').value='';document.getElementById('qa-answer').value='';updateQACount();document.getElementById('qa-question').focus();}
async function addCacheEntry(){
  const question=document.getElementById('qa-question').value.trim(),answer=document.getElementById('qa-answer').value.trim();
  if(!question||answer.length<20)return;
  const btn=document.getElementById('add-qa-btn');btn.disabled=true;btn.textContent='\u23f3 Saving...';
  try{
    const r=await fetch(`${API}/admin/cache/add`,{method:'POST',headers:{Authorization:AUTH,'Content-Type':'application/json'},body:JSON.stringify({question,answer,source:'manual'})});
    const d=await safeJson(r);
    if(d.saved){toast('\u2705 Q&A cache \u092e\u0947\u0902 save \u0939\u094b \u0917\u092f\u093e!','ok');clearQAForm();loadCache();}
    else if(d.duplicate){toast('\u26a0\ufe0f \u092f\u0939 \u0938\u0935\u093e\u0932 \u092a\u0939\u0932\u0947 \u0938\u0947 cache \u092e\u0947\u0902 \u0939\u0948\u0964','err');}
    else{toast('Entry save \u0928\u0939\u0940\u0902 \u0939\u0941\u0908: '+(d.reason||'unknown'),'err');}
  }catch(e){toast('Save failed: '+e.message,'err');}
  finally{btn.disabled=false;btn.textContent='\ud83d\udcbe Cache \u092e\u0947\u0902 Save \u0915\u0930\u0947\u0902';updateQACount();}
}

async function runReindex(){
  const btn=document.getElementById('reindex-btn'),log=document.getElementById('reindex-log');
  btn.disabled=true;btn.textContent='\u23f3 Indexing...';
  log.innerHTML='<span class="log-warn">Starting re-index...</span>\n';
  try{
    const r=await fetch(`${API}/admin/reindex`,{method:'POST',headers:{Authorization:AUTH}});
    const d=await safeJson(r);
    if(!r.ok){const msg=d.detail||d.message||(d._raw||'').slice(0,300)||`HTTP ${r.status}`;log.innerHTML+=`<span class="log-err">\u274c Error ${r.status}: ${escHtml(msg)}</span>`;toast('Re-index failed \u2014 see log','err');}
    else{const chunks=d.total_chunks!==undefined?d.total_chunks:'?';log.innerHTML+=`<span class="log-ok">\u2713 Done \u2014 ${chunks} total chunks in ChromaDB</span>`;toast('\u2705 Re-index complete','ok');}
  }catch(e){log.innerHTML+=`<span class="log-err">\u274c Network error: ${escHtml(e.message)}</span>`;toast('Re-index failed','err');}
  btn.disabled=false;btn.textContent='\u26a1 Run Re-index';
}

function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function toggleTheme(){const isAgri=document.documentElement.classList.toggle('agri');document.getElementById('theme-btn').classList.toggle('agri-on',isAgri);localStorage.setItem('km_theme',isAgri?'agri':'dark');}
(function(){const saved=localStorage.getItem('km_theme');if(saved==='agri'){document.documentElement.classList.add('agri');document.getElementById('theme-btn').classList.add('agri-on');}})();

const adminChatHistory=[];
function addAdminMsg(text,role,source){
  const box=document.getElementById('admin-chat-messages'),isMe=role==='user';
  const div=document.createElement('div');div.style.cssText=`display:flex;flex-direction:column;align-items:${isMe?'flex-end':'flex-start'};gap:4px;`;
  const bubble=document.createElement('div');
  bubble.style.cssText=`max-width:75%;padding:10px 14px;border-radius:${isMe?'16px 16px 4px 16px':'16px 16px 16px 4px'};background:${isMe?'var(--green)':'var(--bg)'};color:${isMe?'#000':'var(--text)'};font-family:var(--hindi);font-size:13px;line-height:1.6;border:1px solid ${isMe?'transparent':'var(--border)'};white-space:pre-wrap;`;
  bubble.textContent=text;div.appendChild(bubble);
  if(source&&!isMe){const src=document.createElement('div');src.style.cssText='font-size:10px;font-family:var(--mono);color:var(--muted);padding:0 4px;';const color=source==='gemini'?'var(--green)':source==='ollama'?'var(--amber)':source==='cache'?'#63b3ed':'var(--red)';src.innerHTML=`<span style="color:${color};font-weight:700;">[${source.toUpperCase()}]</span>`;div.appendChild(src);}
  box.appendChild(div);box.scrollTop=box.scrollHeight;
}
function addAdminTyping(){const box=document.getElementById('admin-chat-messages'),div=document.createElement('div');div.id='admin-typing';div.innerHTML='<div class="ai-thinking"><div class="dots"><span></span><span></span><span></span></div><span class="ai-thinking-text">AI \u0938\u094b\u091a \u0930\u0939\u093e \u0939\u0948...</span></div>';box.appendChild(div);box.scrollTop=box.scrollHeight;}
function removeAdminTyping(){const t=document.getElementById('admin-typing');if(t)t.remove();}
function typewriterAdminMsg(text,source,speed=18){
  return new Promise(resolve=>{
    const box=document.getElementById('admin-chat-messages'),div=document.createElement('div');
    div.style.cssText='display:flex;flex-direction:column;align-items:flex-start;gap:4px;';
    const bubble=document.createElement('div');
    bubble.style.cssText='max-width:75%;padding:10px 14px;border-radius:16px 16px 16px 4px;background:var(--bg);color:var(--text);font-family:var(--hindi);font-size:13px;line-height:1.6;border:1px solid var(--border);white-space:pre-wrap;';
    div.appendChild(bubble);
    if(source){const src=document.createElement('div');src.style.cssText='font-size:10px;font-family:var(--mono);color:var(--muted);padding:0 4px;';const color=source==='cache'?'#63b3ed':source==='gemini'?'var(--green)':'var(--amber)';src.innerHTML=`<span style="color:${color};font-weight:700;">[${source.toUpperCase()}]</span>`;div.appendChild(src);}
    box.appendChild(div);box.scrollTop=box.scrollHeight;
    let i=0;function type(){if(i<text.length){bubble.textContent+=text[i++];box.scrollTop=box.scrollHeight;setTimeout(type,speed);}else{resolve();}}type();
  });
}
async function sendAdminChat(){
  const input=document.getElementById('admin-chat-input'),q=input.value.trim();if(!q)return;
  const crop=document.getElementById('chat-crop').value,lang=document.getElementById('chat-lang').value,btn=document.getElementById('admin-send-btn'),box=document.getElementById('admin-chat-messages');
  if(box.children.length===1&&box.children[0].style.textAlign==='center')box.innerHTML='';
  addAdminMsg(q,'user');input.value='';btn.disabled=true;btn.textContent='\u23f3';addAdminTyping();
  adminChatHistory.push({role:'user',content:q});
  try{
    const r=await fetch(`${API}/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q,crop,language:lang,district:'Meerut'})});
    const d=await safeJson(r);
    const answer=d.answer||d.message||'\u0915\u094b\u0908 \u0909\u0924\u094d\u0924\u0930 \u0928\u0939\u0940\u0902 \u092e\u093f\u0932\u093e\u0964',source=d.source||'unknown';
    removeAdminTyping();
    if(source==='cache'){await typewriterAdminMsg(answer,source);}else{addAdminMsg(answer,'bot',source);}
    adminChatHistory.push({role:'assistant',content:answer});
    const bar=document.getElementById('admin-source-bar');bar.style.display='flex';
    document.getElementById('admin-last-source').textContent=source.toUpperCase();
    document.getElementById('admin-last-source').style.color=source==='gemini'?'var(--green)':source==='ollama'?'var(--amber)':source==='cache'?'#63b3ed':'var(--red)';
    document.getElementById('admin-rag-used').textContent=d.rag_chunks!==undefined?d.rag_chunks:'N/A';
  }catch(e){removeAdminTyping();addAdminMsg('\u274c Server \u0938\u0947 connect \u0928\u0939\u0940\u0902 \u0939\u094b \u092a\u093e\u092f\u093e\u0964','bot','error');}
  btn.disabled=false;btn.textContent='Send \u21b5';input.focus();
}
function clearAdminChat(){const box=document.getElementById('admin-chat-messages');box.innerHTML='<div style="text-align:center;color:var(--muted);font-family:var(--hindi);font-size:13px;margin:auto;">\ud83c\udf3e \u0915\u094b\u0908 \u092d\u0940 \u0915\u0943\u0937\u093f \u0938\u0935\u093e\u0932 \u092a\u0942\u091b\u0947\u0902...</div>';document.getElementById('admin-source-bar').style.display='none';adminChatHistory.length=0;}

async function testRAG(){
  const q=document.getElementById('rag-q').value.trim(),crop=document.getElementById('rag-crop').value;if(!q)return;
  document.getElementById('rag-result').style.display='none';document.getElementById('rag-loading').style.display='block';
  const steps=['step-1','step-2','step-3','step-4'];steps.forEach(s=>document.getElementById(s).classList.remove('active','done'));
  let stepIdx=0;const stepTimer=setInterval(()=>{if(stepIdx>0)document.getElementById(steps[stepIdx-1]).classList.add('done');if(stepIdx<steps.length){document.getElementById(steps[stepIdx]).classList.add('active');stepIdx++;}else{clearInterval(stepTimer);}},600);
  try{
    const r=await fetch(`${API}/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q,crop,language:'hindi',district:'Meerut'})});
    const d=await safeJson(r);
    clearInterval(stepTimer);steps.forEach(s=>document.getElementById(s).classList.add('done'));
    setTimeout(()=>{document.getElementById('rag-loading').style.display='none';document.getElementById('rag-result').style.display='block';},400);
    if(!r.ok){document.getElementById('rag-chunks').textContent=`Error ${r.status}: ${d.detail||d.message||d._raw||''}`;return;}
    const source=d.source||'unknown',fromRAG=source==='rag'||(d.rag_chunks&&d.rag_chunks>0);
    document.getElementById('rag-answer').textContent=d.answer||'\u2014';
    const chunksEl=document.getElementById('rag-chunks');
    chunksEl.innerHTML=d.rag_context?escHtml(d.rag_context).replace(/\n/g,'<br>'):'<span style="color:var(--muted)">No RAG context \u2014 ChromaDB is empty.<br>Run Re-index from the RE-INDEX tab first.</span>';
    const badge=document.getElementById('rag-source-badge');
    badge.textContent=source.toUpperCase();
    badge.style.background=source==='gemini'?'rgba(74,222,128,.15)':source==='ollama'?'rgba(251,191,36,.15)':source==='cache'?'rgba(99,179,237,.15)':'rgba(248,113,113,.15)';
    badge.style.color=source==='gemini'?'var(--green)':source==='ollama'?'var(--amber)':source==='cache'?'#63b3ed':'var(--red)';
    document.getElementById('rag-chunks-count').textContent=d.rag_chunks?`${d.rag_chunks} chunks retrieved`:'';
    const ragBadge=document.getElementById('rag-from-rag');ragBadge.textContent=fromRAG?'\u2705 RAG data used':'\u26a0\ufe0f RAG not used (no relevant chunks found)';ragBadge.style.background=fromRAG?'rgba(74,222,128,.1)':'rgba(251,191,36,.1)';ragBadge.style.color=fromRAG?'var(--green)':'var(--amber)';
  }catch(e){clearInterval(stepTimer);document.getElementById('rag-loading').style.display='none';document.getElementById('rag-chunks').textContent='Network error: '+e.message;document.getElementById('rag-result').style.display='block';}
}

let _activeMic=null;
function startMic(inputId,btnId){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){toast('\u0906\u092a\u0915\u093e browser voice input support \u0928\u0939\u0940\u0902 \u0915\u0930\u0924\u093e\u0964','err');return;}
  const btn=document.getElementById(btnId);if(_activeMic&&_activeMic._btnId===btnId){_activeMic.stop();return;}if(_activeMic)_activeMic.stop();
  const rec=new SR();rec._btnId=btnId;rec.lang='hi-IN';rec.interimResults=true;rec.continuous=false;rec.maxAlternatives=1;
  rec.onstart=()=>{_activeMic=rec;btn.classList.add('listening');btn.textContent='\ud83d\udd34';};
  rec.onresult=(e)=>{document.getElementById(inputId).value=Array.from(e.results).map(r=>r[0].transcript).join('');};
  rec.onerror=(e)=>{if(e.error==='no-speech')toast('\u0915\u094b\u0908 \u0906\u0935\u093e\u091c\u093c \u0928\u0939\u0940\u0902 \u0938\u0941\u0928\u0940 \u2014 \u092b\u093f\u0930 \u0938\u0947 \u0915\u094b\u0936\u093f\u0936 \u0915\u0930\u0947\u0902\u0964','err');else if(e.error==='not-allowed')toast('Microphone permission \u0926\u0947\u0902\u0964','err');else toast('Mic error: '+e.error,'err');btn.classList.remove('listening');btn.textContent='\ud83c\udfa4';_activeMic=null;};
  rec.onend=()=>{btn.classList.remove('listening');btn.textContent='\ud83c\udfa4';_activeMic=null;if(inputId==='admin-chat-input'){const val=document.getElementById('admin-chat-input').value.trim();if(val)sendAdminChat();}};
  rec.start();
}

loadStatus();
</script>
</body>
</html>
"""

p.write_text(head + script, encoding='utf-8')
print(f"Done! Wrote {len(head + script)} bytes.")
