async function post(path, body){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})}); if(!r.ok){const e=await r.json().catch(()=>({})); throw new Error(e.detail||JSON.stringify(e));} return r.json();}
async function get(path){const r=await fetch(path); if(!r.ok){const e=await r.json().catch(()=>({})); throw new Error(e.detail||JSON.stringify(e));} return r.json();}
const out = document.getElementById("out");
function show(x){ out.textContent = typeof x==="string"? x : JSON.stringify(x,null,2); }

async function doChat(){ try{ const prompt=document.getElementById("prompt").value; const sessionId=getSelectedSession(); if(!sessionId){show("Please select a session first"); return;} show(await post("/api/chat",{prompt, session_id:sessionId})); }catch(e){show(String(e));}}
async function doEvolve(){ try{ const task=document.getElementById("prompt").value; show(await post("/api/evolve",{task, assertions: [], n:5})); }catch(e){show(String(e));}}
async function doSearch(){ try{ const q=document.getElementById("prompt").value; show(await post("/api/web/search",{query:q})); }catch(e){show(String(e));}}
async function doRagBuild(){ try{ show(await post("/api/rag/build",{})); }catch(e){show(String(e));}}
async function doRagQuery(){ try{ const q=document.getElementById("prompt").value; show(await post("/api/rag/query",{q})); }catch(e){show(String(e));}}
async function addTodo(){ try{ const t=document.getElementById("todoText").value; await post("/api/todo/add",{text:t}); show(await get("/api/todo/list")); }catch(e){show(String(e));}}

// Session management
function getSelectedSession(){ const select=document.getElementById("sessionSelect"); return select.value ? parseInt(select.value) : null; }

async function loadSessions(){ 
  try{ 
    const data=await get("/api/session/list"); 
    const select=document.getElementById("sessionSelect"); 
    select.innerHTML="<option value=''>Select session...</option>";
    data.sessions.forEach(s=>{ 
      const opt=document.createElement("option"); opt.value=s.id; opt.textContent=`${s.title} (${new Date(s.created_at*1000).toLocaleDateString()})`; select.appendChild(opt); 
    }); 
  }catch(e){show(String(e));} 
}

async function newSession(){ 
  try{ 
    const title=prompt("Session title:", "New session"); 
    if(title!==null){ 
      const data=await post("/api/session/create",{title}); 
      await loadSessions(); 
      document.getElementById("sessionSelect").value=data.id; 
      show(`Created session ${data.id}`); 
    } 
  }catch(e){show(String(e));} 
}

async function doMemoryQuery(){ try{ const q=document.getElementById("prompt").value; show(await post("/api/memory/query",{q})); }catch(e){show(String(e));}}

async function buildMemory(){ try{ show(await post("/api/memory/build",{})); }catch(e){show(String(e));}}

// Meta-evolution functions
async function runMetaEvolution() {
  try {
    const taskClass = document.getElementById("metaTaskClass").value.trim();
    const task = document.getElementById("prompt").value.trim();
    const n = parseInt(document.getElementById("metaIterations").value);
    const useBandit = document.getElementById("metaBandit").checked;
    const eps = parseFloat(document.getElementById("metaEps").value);
    const memoryK = parseInt(document.getElementById("metaMemoryK").value);
    const ragK = parseInt(document.getElementById("metaRagK").value);
    
    // Get selected framework mask
    const frameworkSelect = document.getElementById("metaFramework");
    const frameworkMask = Array.from(frameworkSelect.selectedOptions).map(opt => opt.value);
    
    if (!taskClass || !task) {
      show("Please fill in Task Class and enter a prompt above");
      return;
    }
    
    // Show progress
    const metaOutput = document.getElementById("metaOutput");
    metaOutput.textContent = "🚀 Starting meta-evolution...\n";
    
    const sessionId = getSelectedSession();
    if(!sessionId){ show('Please select or create a session first'); return; }
    const payload = {
      session_id: sessionId,
      task_class: taskClass,
      task: task,
      n: n,
      use_bandit: useBandit,
      eps: eps,
      memory_k: memoryK,
      rag_k: ragK,
      framework_mask: frameworkMask.length > 0 ? frameworkMask : null
    };
    // Force engine and Groq compare options
    const forceEngine = document.getElementById("mrForceEngine").value;
    const compareGroq = document.getElementById("mrCompareGroq").checked;
    const judgeMode = document.getElementById("mrJudge").checked ? "pairwise_groq" : "off";
    if (forceEngine) payload.force_engine = forceEngine;
    if (compareGroq) payload.compare_with_groq = true;
    payload.judge_mode = judgeMode;
    payload.judge_include_rationale = true;
    
    // Disable controls and show progress
    const btn = document.getElementById('btnRunMeta');
    const controls = [
      'metaTaskClass','metaIterations','metaBandit','metaEps','metaMemoryK','metaRagK','metaFramework','mrForceEngine','mrCompareGroq','mrJudge'
    ];
    btn.disabled = true; btn.textContent = 'Running...';
    controls.forEach(id=>{ const el=document.getElementById(id); if(el) el.disabled = true; });
    saveMetaState();

    const started = await post("/api/meta/run_async", payload);
    metaOutput.textContent = `Run ${started.run_id} started...`;
    try { openRunStream(started.run_id, n); } catch(_e) { /* fallback continues */ }
    await pollRunProgress(started.run_id, n);

  } catch(e) {
    document.getElementById("metaOutput").textContent = `❌ Error: ${String(e)}`;
  } finally {
    const btn = document.getElementById('btnRunMeta');
    const controls = [
      'metaTaskClass','metaIterations','metaBandit','metaEps','metaMemoryK','metaRagK','metaFramework','mrForceEngine','mrCompareGroq','mrJudge'
    ];
    btn.disabled = false; btn.textContent = '🚀 Run Meta-Evolution';
    controls.forEach(id=>{ const el=document.getElementById(id); if(el) el.disabled = false; });
  }
}

async function uiListGroq(){
  try{
    const j = await get("/api/health/groq_models");
    document.getElementById("groqModels").textContent = JSON.stringify(j, null, 2);
  }catch(e){ alert("Groq models query failed: " + e); }
}

async function viewMetaLogs() {
  try {
    const logs = await get("/api/meta/logs?limit=20");
    const metaOutput = document.getElementById("metaOutput");
    
    metaOutput.textContent = `📊 Recent Meta-Evolution Logs:
${logs.logs.map(log => 
  `[${log.timestamp}] ${log.artifact_type}: ${JSON.stringify(log.data, null, 2)}`
).join('\n\n')}`;
  } catch(e) {
    document.getElementById("metaOutput").textContent = `❌ Error fetching logs: ${String(e)}`;
  }
}

// Dashboard removed: simplified UI

async function pollRunProgress(runId, expectedN){
  const metaOutput = document.getElementById("metaOutput");
  let done = false;
  while(!done){
    try{
      const data = await get(`/api/meta/runs/${runId}`);
      const count = (data.variants||[]).length;
      const best = (typeof data.best_score === 'number') ? data.best_score.toFixed(3) : data.best_score;
      metaOutput.textContent = `Run ${runId}: ${count}/${expectedN} iterations completed.\nBest: ${best}`;
      await showLatestRun(runId);
      if (data.finished_at) {
        metaOutput.textContent = JSON.stringify(data, null, 2);
        done = true;
        refreshDashboard();
        break;
      }
    }catch(e){ console.warn('poll error', e); }
    await new Promise(r=> setTimeout(r, 1200));
  }
}

let _evtSource = null;
function openRunStream(runId, expectedN){
  try { if (_evtSource) { _evtSource.close(); _evtSource = null; } } catch(_e) {}
  const es = new EventSource(`/api/meta/stream?run_id=${runId}`);
  _evtSource = es;
  const metaOutput = document.getElementById("metaOutput");
  let count = 0;
  es.onmessage = (e)=>{
    try{
      const data = JSON.parse(e.data);
      if (data.type === 'iter'){
        count = data.i + 1;
        const bestLine = metaOutput.textContent.split('\n')[1]||'';
        metaOutput.textContent = `Run ${runId}: ${count}/${expectedN} iterations completed.\n${bestLine}`;
        appendVariantRow(data);
      } else if (data.type === 'judge'){
        showJudgeResults(data.judge);
        // Subtle toast
        try{ showToast(`Judge verdict: ${JSON.stringify(data.judge.verdict||data.judge)}`); }catch(_e){}
      } else if (data.type === 'done'){
        metaOutput.textContent = JSON.stringify(data.result, null, 2);
        try { _evtSource.close(); } catch(_e) {}
        _evtSource = null;
        refreshDashboard();
      }
    }catch(_e){ /* ignore parse errors */ }
  };
  es.onerror = ()=>{
    // Keep polling fallback running
  };
}

function appendVariantRow(v){
  const tbody = document.querySelector('#latestRunTable tbody');
  if(!tbody) return;
  const tr = document.createElement('tr');
  const modelId = v.model_id || '';
  const isGroq = (modelId||'').startsWith('groq:');
  const engine = v.engine || (isGroq ? 'groq' : 'ollama');
  const model = isGroq ? modelId.replace(/^groq:/,'') : modelId;
  const ts = v.timestamp ? new Date(v.timestamp*1000).toLocaleString() : '';
  tr.innerHTML = `
    <td style="padding:6px;border-bottom:1px solid #eee;">${(v.i??0)+1}</td>
    <td style="padding:6px;border-bottom:1px solid #eee;">${v.operator||''}</td>
    <td style="padding:6px;border-bottom:1px solid #eee;">${engine}</td>
    <td style="padding:6px;border-bottom:1px solid #eee;">${model}</td>
    <td style="padding:6px;border-bottom:1px solid #eee;">${(v.score??0).toFixed(3)}</td>
    <td style="padding:6px;border-bottom:1px solid #eee;">${v.duration_ms??''}</td>
    <td style="padding:6px;border-bottom:1px solid #eee;">${ts}</td>
  `;
  tbody.appendChild(tr);
}

function showToast(text){
  const div = document.createElement('div');
  div.textContent = text;
  div.style.position='fixed'; div.style.bottom='16px'; div.style.right='16px';
  div.style.background='var(--panel-2)'; div.style.color='var(--text)'; div.style.padding='10px 14px'; div.style.border='1px solid var(--border)'; div.style.borderRadius='8px';
  div.style.boxShadow='0 4px 10px rgba(0,0,0,0.35)'; div.style.fontSize='12px';
  document.body.appendChild(div);
  setTimeout(()=>{ try{ document.body.removeChild(div);}catch(_e){} }, 2500);
}

// No-op dashboard refresher retained for compatibility
function refreshDashboard(){}

function saveMetaState(){
  const state = {
    tc: document.getElementById('metaTaskClass').value,
    n: document.getElementById('metaIterations').value,
    bandit: document.getElementById('metaBandit').checked,
    eps: document.getElementById('metaEps').value,
    mk: document.getElementById('metaMemoryK').value,
    rk: document.getElementById('metaRagK').value,
    fm: Array.from(document.getElementById('metaFramework').selectedOptions).map(o=>o.value),
    fe: document.getElementById('mrForceEngine').value,
    cmp: document.getElementById('mrCompareGroq').checked,
    judge: document.getElementById('mrJudge').checked
  };
  try { localStorage.setItem('metaState', JSON.stringify(state)); } catch(_e){}
}

function loadMetaState(){
  try{
    const s = JSON.parse(localStorage.getItem('metaState')||'null');
    if(!s) return;
    const set = (id, fn) => { const el=document.getElementById(id); if(el) fn(el); };
    set('metaTaskClass', el=> el.value = s.tc||'');
    set('metaIterations', el=> el.value = s.n||'5');
    set('metaBandit', el=> el.checked = !!s.bandit);
    set('metaEps', el=> el.value = s.eps||'0.1');
    set('metaMemoryK', el=> el.value = s.mk||'3');
    set('metaRagK', el=> el.value = s.rk||'3');
    set('mrForceEngine', el=> el.value = s.fe||'');
    set('mrCompareGroq', el=> el.checked = !!s.cmp);
    set('mrJudge', el=> el.checked = !!s.judge);
    const fm = document.getElementById('metaFramework');
    if (fm && Array.isArray(s.fm)) {
      Array.from(fm.options).forEach(opt => { opt.selected = s.fm.includes(opt.value); });
    }
  }catch(_e){}
}

// removed legacy UI helpers (Meta Run/Eval)

// Health check functionality
async function checkHealth() {
  try {
    const [ollama, engines] = await Promise.all([
      get("/api/health").catch(()=>({status:'down'})),
      get("/api/health/groq").catch(()=>({groq:{status:'down'}}))
    ]);
    // Update Ollama badge
    const ollamaEl = document.getElementById("ollamaHealth");
    if (ollama?.status === "ok") {
      ollamaEl.textContent = `Ollama: ✓ ${ollama.model || 'OK'}`;
      ollamaEl.className = "health-badge health-ok";
    } else {
      ollamaEl.textContent = "Ollama: ✗ Down";
      ollamaEl.className = "health-badge health-down";
    }
    // Update Groq badge
    const groqEl = document.getElementById("groqHealth");
    const g = engines?.groq;
    if (g?.status === "ok") {
      groqEl.textContent = "Groq: ✓ OK";
      groqEl.className = "health-badge health-ok";
    } else {
      groqEl.textContent = `Groq: ✗ ${g?.detail || "Down"}`;
      groqEl.className = "health-badge health-down";
    }
  } catch (e) {
    console.error("Health check failed:", e);
    document.getElementById("ollamaHealth").textContent = "Ollama: ? Error";
    document.getElementById("groqHealth").textContent = "Groq: ? Error";
  }
}

// Enhanced judge visibility
function showJudgeResults(judgeData) {
  const judgePanel = document.getElementById("judgeResults");
  const judgeContent = document.getElementById("judgeContent");
  
  if (judgeData && judgeData.mode) {
    let content = `<strong>Mode:</strong> ${judgeData.mode}<br>`;
    
    if (judgeData.verdict) {
      content += `<strong>Verdict:</strong> ${judgeData.verdict}<br>`;
    }
    
    if (judgeData.challenger_model) {
      content += `<strong>Challenger Model:</strong> ${judgeData.challenger_model}<br>`;
    }
    
    if (judgeData.error) {
      content += `<strong>Error:</strong> <span style="color:#d73527;">${judgeData.error}</span>`;
    }
    
    judgeContent.innerHTML = content;
    judgePanel.style.display = "block";
  } else {
    judgePanel.style.display = "none";
  }
}

// (duplicate runMetaEvolution removed)

// Load sessions and check health on page load
window.addEventListener('load', () => { 
  loadMetaState(); 
  loadSessions(); 
  checkHealth(); 
  // Keyboard shortcut: run meta (Ctrl/Cmd+Enter)
  window.addEventListener('keydown', (e)=>{
    const mod = e.ctrlKey || e.metaKey;
    if(mod && e.key === 'Enter'){
      const btn=document.getElementById('btnRunMeta'); if(btn && !btn.disabled){ runMetaEvolution(); e.preventDefault(); }
    }
  });
});

async function showLatestRun(runId) {
  try {
    const data = await get(`/api/meta/runs/${runId}`);
    const tbody = document.querySelector('#latestRunTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    data.variants.forEach((v, idx) => {
      const tr = document.createElement('tr');
      const modelId = v.model_id || '';
      const isGroq = modelId.startsWith('groq:');
      const engine = isGroq ? 'groq' : 'ollama';
      const model = isGroq ? modelId.replace(/^groq:/,'') : modelId;
      const ts = v.timestamp ? new Date(v.timestamp*1000).toLocaleString() : '';
      tr.innerHTML = `
        <td style="padding:6px;border-bottom:1px solid #eee;">${idx+1}</td>
        <td style="padding:6px;border-bottom:1px solid #eee;">${v.operator||''}</td>
        <td style="padding:6px;border-bottom:1px solid #eee;">${engine}</td>
        <td style="padding:6px;border-bottom:1px solid #eee;">${model}</td>
        <td style="padding:6px;border-bottom:1px solid #eee;">${(v.score??0).toFixed(3)}</td>
        <td style="padding:6px;border-bottom:1px solid #eee;">${v.duration_ms??''}</td>
        <td style="padding:6px;border-bottom:1px solid #eee;">${ts}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error('Failed to load latest run:', e);
  }
}
