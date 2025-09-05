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

// Load sessions on page load
window.addEventListener('load', loadSessions);