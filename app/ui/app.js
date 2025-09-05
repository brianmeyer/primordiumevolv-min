async function post(path, body){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})}); if(!r.ok){const e=await r.json().catch(()=>({})); throw new Error(e.detail||JSON.stringify(e));} return r.json();}
async function get(path){const r=await fetch(path); if(!r.ok){const e=await r.json().catch(()=>({})); throw new Error(e.detail||JSON.stringify(e));} return r.json();}
const out = document.getElementById("out");
function show(x){ out.textContent = typeof x==="string"? x : JSON.stringify(x,null,2); }

async function doChat(){ try{ const prompt=document.getElementById("prompt").value; show(await post("/api/chat",{prompt})); }catch(e){show(String(e));}}
async function doEvolve(){ try{ const task=document.getElementById("prompt").value; show(await post("/api/evolve",{task, assertions: [], n:5})); }catch(e){show(String(e));}}
async function doSearch(){ try{ const q=document.getElementById("prompt").value; show(await post("/api/web/search",{query:q})); }catch(e){show(String(e));}}
async function doRagBuild(){ try{ show(await post("/api/rag/build",{})); }catch(e){show(String(e));}}
async function doRagQuery(){ try{ const q=document.getElementById("prompt").value; show(await post("/api/rag/query",{q})); }catch(e){show(String(e));}}
async function addTodo(){ try{ const t=document.getElementById("todoText").value; await post("/api/todo/add",{text:t}); show(await get("/api/todo/list")); }catch(e){show(String(e));}}