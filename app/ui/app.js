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

// Dashboard functionality
let trendChart, rewardChart, shareChart;

async function fetchStats() {
  return await get('/api/meta/stats');
}

async function fetchTrend(taskClass) {
  return await get('/api/meta/trend' + (taskClass ? ('?task_class=' + encodeURIComponent(taskClass)) : ''));
}

async function fetchRecipes(taskClass) {
  return await get('/api/meta/recipes' + (taskClass ? ('?task_class=' + encodeURIComponent(taskClass)) : ''));
}

async function refreshDashboard() {
  try {
    const tc = document.getElementById('dashTaskClass').value.trim();
    
    // Fetch data
    const [trend, stats, recipes] = await Promise.all([
      fetchTrend(tc),
      fetchStats(),
      fetchRecipes(tc)
    ]);
    
    // Trend chart
    const labels = trend.trend.map(p => new Date(p.ts*1000).toLocaleDateString());
    const data = trend.trend.map(p => p.best_score);
    
    trendChart && trendChart.destroy();
    trendChart = new Chart(document.getElementById('trendChart'), {
      type: 'line',
      data: { 
        labels, 
        datasets: [{ 
          label: 'Best Score', 
          data, 
          borderColor: 'rgb(75, 192, 192)',
          backgroundColor: 'rgba(75, 192, 192, 0.2)',
          tension: 0.1
        }] 
      },
      options: {
        responsive: true,
        scales: {
          y: { beginAtZero: true }
        }
      }
    });
    
    // Operator rewards chart
    const opLabels = stats.operator_stats.map(o => o.name);
    const rewards = stats.operator_stats.map(o => o.avg_reward);
    
    rewardChart && rewardChart.destroy();
    rewardChart = new Chart(document.getElementById('rewardChart'), {
      type: 'bar',
      data: { 
        labels: opLabels, 
        datasets: [{ 
          label: 'Avg Reward', 
          data: rewards,
          backgroundColor: 'rgba(54, 162, 235, 0.5)',
          borderColor: 'rgb(54, 162, 235)',
          borderWidth: 1
        }] 
      },
      options: {
        responsive: true,
        scales: {
          y: { beginAtZero: true }
        }
      }
    });
    
    // Selection share chart
    const counts = stats.operator_stats.map(o => o.n);
    const colors = [
      '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
      '#FF9F40', '#C9CBCF', '#FF6384', '#36A2EB', '#FFCE56'
    ];
    
    shareChart && shareChart.destroy();
    shareChart = new Chart(document.getElementById('shareChart'), {
      type: 'pie',
      data: { 
        labels: opLabels, 
        datasets: [{ 
          label: 'Selections', 
          data: counts,
          backgroundColor: colors.slice(0, opLabels.length)
        }] 
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              font: { size: 10 }
            }
          }
        }
      }
    });
    
    // Recipes list
    document.getElementById('recipesList').textContent = recipes.recipes.length > 0 
      ? JSON.stringify(recipes.recipes, null, 2)
      : "No recipes found for this task class.";
      
    show(`Dashboard updated! Showing ${trend.trend.length} runs, ${stats.operator_stats.length} operators, ${recipes.recipes.length} recipes.`);
    
  } catch(e) {
    show(String(e));
  }
}

// Load sessions on page load
window.addEventListener('load', loadSessions);