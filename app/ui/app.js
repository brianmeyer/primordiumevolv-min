// Streamlined Evolution UI - Human-centered design focused on self-evolution

let currentRunId = null;
let evolutionEventSource = null;
let evolutionTimerInterval = null;
let evolutionStartTs = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    checkHealth();
    setupRatingSystem();
    // Load and persist rating prefs UI controls if present
    const modeEl = document.getElementById('ratingsMode');
    const delayEl = document.getElementById('readingDelayMs');
    if (modeEl) {
        modeEl.value = localStorage.getItem('ratings_mode') || 'prompted';
        modeEl.addEventListener('change', () => localStorage.setItem('ratings_mode', modeEl.value));
    }
    if (delayEl) {
        delayEl.value = localStorage.getItem('reading_delay_ms') || '2000';
        delayEl.addEventListener('change', () => localStorage.setItem('reading_delay_ms', String(delayEl.value)));
    }
    
    // Auto-check health every 2 minutes (reduced from 30 seconds to reduce API calls)
    healthCheckInterval = setInterval(checkHealth, 120000);
});

// Handle tab visibility changes to reduce API calls when tab is not active
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        console.log('Tab hidden, pausing health checks');
    } else {
        console.log('Tab visible, resuming health checks');
        // Check health immediately when tab becomes visible
        setTimeout(checkHealth, 1000);
    }
});

// Global variables for rating system
let currentVariantId = null;
let currentIterationOutput = null;

// Health check state management
let healthCheckInProgress = false;
let healthCheckInterval = null;

// Health Check
async function checkHealth() {
    // Prevent overlapping health checks
    if (healthCheckInProgress) {
        console.log('Health check already in progress, skipping...');
        return;
    }
    
    // Skip if tab is not visible (reduce API calls when user is not looking)
    if (document.hidden) {
        console.log('Tab not visible, skipping health check...');
        return;
    }
    
    healthCheckInProgress = true;
    console.log('Checking health...');
    
    try {
        // Check Ollama
        console.log('Checking Ollama health...');
        const ollamaResponse = await fetch('/api/health/ollama');
        const ollamaData = await ollamaResponse.json();
        console.log('Ollama health:', ollamaData);
        const ollamaHealth = document.getElementById('ollamaHealth');
        if (ollamaHealth) {
            ollamaHealth.textContent = `Ollama: ${ollamaData.status}`;
            ollamaHealth.className = ollamaData.status === 'ok' ? 'status-badge status-ok' : 'status-badge status-error';
        }
        
        // Check Groq  
        console.log('Checking Groq health...');
        const groqResponse = await fetch('/api/health/groq');
        const groqData = await groqResponse.json();
        console.log('Groq health:', groqData);
        const groqHealth = document.getElementById('groqHealth');
        if (groqHealth) {
            // Extract just groq status from the response
            const groqStatus = groqData.groq ? groqData.groq.status : groqData.status;
            groqHealth.textContent = `Groq: ${groqStatus}`;
            groqHealth.className = groqStatus === 'ok' ? 'status-badge status-ok' : 'status-badge status-error';
        }
    } catch (error) {
        console.error('Health check failed:', error);
        // Show error state
        const ollamaHealth = document.getElementById('ollamaHealth');
        const groqHealth = document.getElementById('groqHealth');
        if (ollamaHealth) {
            ollamaHealth.textContent = 'Ollama: error';
            ollamaHealth.className = 'status-badge status-error';
        }
        if (groqHealth) {
            groqHealth.textContent = 'Groq: error';
            groqHealth.className = 'status-badge status-error';
        }
    } finally {
        healthCheckInProgress = false;
    }
}

// Main Evolution Function
async function startEvolution() {
    const task = document.getElementById('evolutionTask').value.trim();
    if (!task) {
        alert('Please describe a task for the AI to get better at!');
        return;
    }
    
    console.log('Starting evolution for task:', task);
    
    const taskType = document.getElementById('taskType').value;
    const iterations = parseInt(document.getElementById('evolutionIterations').value);
    const epsilon = parseFloat(document.getElementById('advEpsilon').value);
    const memoryK = parseInt(document.getElementById('advMemoryK').value);
    const strategy = document.getElementById('advStrategy').value;
    const ragK = parseInt(document.getElementById('advRagK').value);
    const useWeb = document.getElementById('advUseWeb').checked;
    
    console.log('Evolution config:', { taskType, iterations, epsilon, memoryK, strategy, ragK, useWeb });
    
    // Show progress UI
    showEvolutionProgress();
    
    // Disable start button
    const startBtn = document.getElementById('startEvolution');
    startBtn.disabled = true;
    startBtn.textContent = '🧬 Evolving...';
    
    try {
        console.log('Sending evolution request...');
        // Ensure a session exists
        let sid = null;
        try {
            const sess = await fetch('/api/session/list').then(r=>r.json());
            sid = (sess.sessions&&sess.sessions[0]&&sess.sessions[0].id) || null;
            if(!sid){
                const created = await fetch('/api/session/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'Auto Session'})}).then(r=>r.json());
                sid = created.id;
            }
        } catch(_e) {}

        // Build framework mask
        const frameworkMask = ['SEAL','SAMPLING'].concat(useWeb? ['WEB']: []);

        const response = await fetch('/api/meta/run_async', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sid,
                task_class: taskType,
                task: task,
                n: iterations,
                use_bandit: true,
                bandit_algorithm: strategy,
                eps: epsilon,
                memory_k: memoryK,
                rag_k: ragK,
                framework_mask: frameworkMask
            }),
        });
        
        console.log('Evolution response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Evolution request failed:', errorText);
            throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
        }
        
        const data = await response.json();
        if(data.run_id){
            console.log('Evolution started with run_id:', data.run_id);
            currentRunId = data.run_id;
            startEvolutionStream(data.run_id, iterations);
        } else {
            throw new Error('No run_id returned');
        }
        
    } catch (error) {
        console.error('Evolution failed:', error);
        showError('Evolution failed: ' + error.message);
        resetEvolutionButton();
    }
}

function showEvolutionProgress() {
    document.getElementById('evolutionProgress').classList.remove('hidden');
    document.getElementById('evolutionResults').classList.add('hidden');
    
    // Reset progress
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('evolutionSteps').innerHTML = '';
    document.getElementById('currentOutput').textContent = 'Starting evolution...';
}

function startEvolutionStream(runId, totalIterations) {
    console.log('Starting evolution stream for run_id:', runId);
    
    if (evolutionEventSource) {
        evolutionEventSource.close();
    }
    
    evolutionEventSource = new EventSource(`/api/meta/stream?run_id=${runId}`);
    
    evolutionEventSource.onmessage = function(event) {
        console.log('Evolution stream event:', event.data);
        try {
            // Handle -Infinity values that can't be parsed by JSON.parse
            const cleanedData = event.data.replace(/-Infinity/g, 'null');
            const data = JSON.parse(cleanedData);
            handleEvolutionEvent(data, totalIterations);
        } catch (error) {
            console.error('Failed to parse evolution event:', error, 'Raw data:', event.data);
        }
    };
    
    evolutionEventSource.onopen = function(event) {
        console.log('Evolution stream connected');
        addEvolutionStep('📡 Connected to evolution stream', 'running');
        // Start elapsed timer
        evolutionStartTs = Date.now();
        startElapsedTimer();
        setStreamStatus('Streaming…', true);
    };
    
    evolutionEventSource.onerror = function(error) {
        console.error('Evolution stream error:', error);
        addEvolutionStep('❌ Stream connection error', 'error');
        evolutionEventSource.close();
        stopElapsedTimer();
        setStreamStatus('Disconnected', false);
        setTimeout(() => {
            resetEvolutionButton();
        }, 2000);
    };
}

function handleEvolutionEvent(data, totalIterations) {
    if (data.type === 'iter_selected') {
        addEvolutionStep(`🧩 Iteration ${data.i + 1}: ${data.operator} selected`, 'running');
        return;
    }
    if (data.type === 'iter_gen_start') {
        updateLastStep(`⚙️ Iteration ${data.i + 1}: generating…`, 'running');
        return;
    }
    if (data.type === 'iter_gen_done') {
        const ms = typeof data.duration_ms === 'number' ? data.duration_ms : 0;
        const pl = typeof data.prompt_length === 'number' ? data.prompt_length : 0;
        updateLastStep(`🧪 Iteration ${data.i + 1}: generated (${ms} ms, ${pl} chars)`, 'running');
        return;
    }
    if (data.type === 'iter_score_done') {
        const rb = data.reward_breakdown || {};
        const out = toFixedSafe(rb.outcome, 3);
        const proc = toFixedSafe(rb.process, 3);
        const cost = toFixedSafe(rb.cost, 3);
        let judgeInfo = '';
        if (data.judge_info && Array.isArray(data.judge_info.judges) && data.judge_info.judges.length > 0) {
            const judgeScores = data.judge_info.judges.map(j => `${(j.model || '').toString().split('/').pop().split('-')[0]}: ${toFixedSafe(j.score, 2)}`).join(', ');
            const tb = data.judge_info.tie_breaker_used ? ' (tie-breaker)' : '';
            judgeInfo = ` — judges: ${judgeScores}${tb}`;
        }
        updateLastStep(`📊 Iteration ${data.i + 1}: scored reward=${toFixedSafe(data.total_reward, 3)} (o:${out} p:${proc} − c:${cost})${judgeInfo}`, 'running');
        return;
    }
    if (data.type === 'iter_saved') {
        updateLastStep(`💾 Iteration ${data.i + 1}: saved (variant_id=${data.variant_id})`, 'completed');
        currentVariantId = data.variant_id || null;
        showRatingPanel();
        if (typeof totalIterations === 'number'){
            updateProgress(Math.min(100, Math.round(100*(data.i+1)/Math.max(1,totalIterations))));
        }
        return;
    }
    if (data.type === 'iter_error') {
        addEvolutionStep(`❌ Iteration ${data.i + 1} failed: ${data.message || 'unknown error'}`, 'error');
        if (typeof totalIterations === 'number'){
            updateProgress(Math.min(100, Math.round(100*(data.i+1)/Math.max(1,totalIterations))));
        }
        return;
    }
    if (data.type === 'iter'){
        // Format judge information for display
        let judgeInfo = '';
        if (data.judge_info && data.judge_info.judges && data.judge_info.judges.length > 0) {
            const judgeScores = data.judge_info.judges.map(j => `${j.model.split('/').pop().split('-')[0]}: ${toFixedSafe(j.score, 2)}`).join(', ');
            const tieBreaker = data.judge_info.tie_breaker_used ? ' (tie-breaker)' : '';
            judgeInfo = ` | judges: ${judgeScores}${tieBreaker}`;
        }
        
        addEvolutionStep(`🔄 Iteration ${data.i + 1}: ${data.operator} | score ${toFixedSafe(data.score, 3)}${judgeInfo}`, 'running');
        updateLastStep(`✅ Iteration ${data.i + 1}: ${data.operator} | score ${toFixedSafe(data.score, 3)}${judgeInfo}`, 'completed');
        if (typeof totalIterations === 'number'){ 
            updateProgress(Math.min(100, Math.round(100*(data.i+1)/Math.max(1,totalIterations))));
        }
        
        // Enable rating for this iteration
        currentVariantId = data.variant_id || null;
        if (data.output) {
            currentIterationOutput = data.output;
            document.getElementById('currentOutput').textContent = data.output;
            showRatingPanel();
        }
        
        return;
    }
    if (data.type === 'judge'){
        addEvolutionStep(`🧑‍⚖️ Judge: ${JSON.stringify(data.judge.verdict||data.judge)}`, 'completed');
        return;
    }
    if (data.type === 'done'){
        handleEvolutionComplete(data.result);
        hideRatingPanel();
        stopElapsedTimer();
        setStreamStatus('Complete', false);
        return;
    }
    if (data.type === 'error'){
        showError('Evolution error: ' + data.message);
        resetEvolutionButton();
        hideRatingPanel();
        stopElapsedTimer();
        setStreamStatus('Error', false);
        return;
    }
}

function addEvolutionStep(text, className = '') {
    const stepsContainer = document.getElementById('evolutionSteps');
    const step = document.createElement('div');
    step.className = `evolution-step ${className}`;
    step.innerHTML = `
        <span>${text}</span>
        <span class="text-muted">Running...</span>
    `;
    stepsContainer.appendChild(step);
    step.scrollIntoView({ behavior: 'smooth' });
}

function updateLastStep(text, className = '') {
    const stepsContainer = document.getElementById('evolutionSteps');
    const lastStep = stepsContainer.lastElementChild;
    if (lastStep) {
        lastStep.className = `evolution-step ${className}`;
        lastStep.innerHTML = `<span>${text}</span>`;
    }
}

function updateProgress(percentage) {
    document.getElementById('progressBar').style.width = `${percentage}%`;
}

function toFixedSafe(val, n) {
    const num = typeof val === 'number' ? val : 0;
    if (!isFinite(num)) return '0.000';
    return num.toFixed(n);
}

function startElapsedTimer() {
    try { clearInterval(evolutionTimerInterval); } catch(_) {}
    const el = document.getElementById('elapsedTime');
    if (!el) return;
    evolutionTimerInterval = setInterval(() => {
        if (!evolutionStartTs) return;
        const secs = Math.floor((Date.now() - evolutionStartTs) / 1000);
        const mm = String(Math.floor(secs / 60)).padStart(2, '0');
        const ss = String(secs % 60).padStart(2, '0');
        el.textContent = `${mm}:${ss}`;
    }, 1000);
}

function stopElapsedTimer() {
    try { clearInterval(evolutionTimerInterval); } catch(_) {}
    evolutionTimerInterval = null;
}

function setStreamStatus(text, spinning) {
    const el = document.getElementById('streamStatus');
    if (!el) return;
    if (spinning) {
        el.innerHTML = `<span class="spinner"></span> ${text}`;
    } else {
        el.textContent = text;
    }
}

function handleEvolutionComplete(result) {
    if (evolutionEventSource) {
        evolutionEventSource.close();
        evolutionEventSource = null;
    }
    
    // Complete progress
    updateProgress(100);
    
    // Show results
    setTimeout(() => {
        showEvolutionResults(result);
        resetEvolutionButton();
    }, 1000);
}

function showEvolutionResults(result) {
    document.getElementById('evolutionProgress').classList.add('hidden');
    document.getElementById('evolutionResults').classList.remove('hidden');
    
    const baseline = (result && typeof result.baseline === 'number') ? result.baseline : 0.1;
    const bestScore = (result && typeof result.best_score === 'number') ? result.best_score : 0;
    let improvementStr = '0.0';
    if (result && typeof result.improvement === 'number') {
        const pct = (result.improvement / Math.max(baseline, 0.1)) * 100;
        improvementStr = `${pct > 0 ? '+' : ''}${pct.toFixed(1)}`;
    }
    
    const resultsHTML = `
        <div class="result-card">
            <div class="result-score">${toFixedSafe(bestScore, 3)}</div>
            <div class="result-improvement">${improvementStr}% improvement</div>
            <div class="text-center text-muted">
                Best strategy: ${(result && result.best_recipe && result.best_recipe.system) ? result.best_recipe.system : 'Default system'} 
                ${(result && result.best_recipe && result.best_recipe.use_web) ? '+ Web Research' : ''}
                ${(result && result.best_recipe && result.best_recipe.use_memory) ? '+ Memory' : ''}
            </div>
        </div>
        
        <details style="margin-top:16px">
            <summary style="cursor:pointer;color:var(--muted)">📊 View Detailed Results</summary>
            <div style="margin-top:12px;padding:12px;background:var(--code);border-radius:8px;font-family:monospace;font-size:0.9em">
                ${JSON.stringify(result, null, 2)}
            </div>
        </details>
        
        <div style="margin-top:16px;text-center">
            <button onclick="startNewEvolution()" class="primary-btn">
                🚀 Start New Evolution
            </button>
        </div>
    `;
    
    document.getElementById('resultsContent').innerHTML = resultsHTML;
}

function resetEvolutionButton() {
    const startBtn = document.getElementById('startEvolution');
    startBtn.disabled = false;
    startBtn.textContent = '🚀 Start Evolution';
}

function startNewEvolution() {
    document.getElementById('evolutionResults').classList.add('hidden');
    document.getElementById('evolutionTask').focus();
}

// Session Management Helper
async function ensureSession() {
    try {
        const sess = await fetch('/api/session/list').then(r=>r.json());
        let sid = (sess.sessions&&sess.sessions[0]&&sess.sessions[0].id) || null;
        if(!sid){
            const created = await fetch('/api/session/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'Quick Test Session'})}).then(r=>r.json());
            sid = created.id;
        }
        return sid;
    } catch(_e) {
        // Fallback to session ID 1 if session management fails
        return 1;
    }
}

// Quick Test Functions
async function quickTest() {
    const prompt = document.getElementById('testPrompt').value.trim();
    if (!prompt) {
        alert('Please enter a test prompt!');
        return;
    }
    
    const output = document.getElementById('testOutput');
    output.style.display = 'block';
    output.textContent = 'Testing...';
    
    try {
        const sessionId = await ensureSession();
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt: prompt,
                session_id: sessionId
            }),
        });
        
        const data = await response.json();
        output.textContent = data.response || 'No response';
    } catch (error) {
        output.textContent = 'Error: ' + error.message;
    }
}

async function streamTest() {
    const prompt = document.getElementById('testPrompt').value.trim();
    if (!prompt) {
        alert('Please enter a test prompt!');
        return;
    }
    
    const output = document.getElementById('testOutput');
    output.style.display = 'block';
    output.textContent = 'Streaming...';
    
    try {
        const sessionId = await ensureSession();
        const response = await fetch(`/api/chat/stream?prompt=${encodeURIComponent(prompt)}&session_id=${sessionId}`);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        output.textContent = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data === '[DONE]') return;
                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.done) return;
                        output.textContent += parsed.token || '';
                    } catch (e) {
                        // Skip invalid JSON
                    }
                }
            }
        }
    } catch (error) {
        output.textContent = 'Error: ' + error.message;
    }
}

// Toggle epsilon visibility based on strategy selection
function toggleEpsilonVisibility() {
    const strategy = document.getElementById('advStrategy').value;
    const epsilonGroup = document.getElementById('epsilonGroup');
    const epsilonInput = document.getElementById('advEpsilon');
    
    if (strategy === 'epsilon_greedy') {
        epsilonGroup.style.opacity = '1';
        epsilonInput.disabled = false;
    } else {
        epsilonGroup.style.opacity = '0.5';
        epsilonInput.disabled = true;
    }
}

// Evolution History
async function loadEvolutionHistory() {
    try {
        const response = await fetch('/api/meta/stats');
        const data = await response.json();
        
        const historyDiv = document.getElementById('evolutionHistory');
        
        if (data.recent_runs.length === 0) {
            historyDiv.innerHTML = '<p class="text-muted">No evolution runs yet.</p>';
            return;
        }
        
        const historyHTML = data.recent_runs.map(run => {
            const status = run.finished_at ? '✅ Completed' : '⏳ Running';
            const score = run.best_score ? run.best_score.toFixed(3) : 'N/A';
            const date = new Date(run.started_at * 1000).toLocaleString();
            
            return `
                <div class="evolution-step" style="margin:4px 0">
                    <span>#${run.id} - ${run.task_class}</span>
                    <span class="text-muted">${status} | Score: ${score} | ${date}</span>
                </div>
            `;
        }).join('');
        
        historyDiv.innerHTML = historyHTML;
    } catch (error) {
        document.getElementById('evolutionHistory').innerHTML = '<p style="color:var(--danger)">Error loading history: ' + error.message + '</p>';
    }
}

// Analytics Dashboard
async function loadAnalytics() {
    try {
        const response = await fetch('/api/meta/analytics');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        
        const overviewDiv = document.getElementById('analyticsOverview');
        const errorDiv = document.getElementById('analyticsError');
        
        // Hide error, show content
        errorDiv.classList.add('hidden');
        overviewDiv.classList.remove('hidden');
        
        // Update overview stats
        const bs = data.basic_stats || {};
        const it = data.improvement_trend || {};
        document.getElementById('totalRuns').textContent = bs.total_runs || 0;
        document.getElementById('timespanDays').textContent = `Over ${Math.round(bs.timespan_days || 0)} days`;
        const imp = (typeof it.improvement === 'number') ? `${it.improvement.toFixed(1)}%` : 'N/A';
        document.getElementById('improvementPercent').textContent = imp;
        const avgScore = (typeof bs.overall_avg_score === 'number') ? bs.overall_avg_score.toFixed(3) : 'N/A';
        document.getElementById('overallAvgScore').textContent = avgScore;
        
        // Color improvement based on positive/negative
        const improvementEl = document.getElementById('improvementPercent');
        if ((it.improvement || 0) > 0) {
            improvementEl.style.color = 'var(--success)';
        } else if ((it.improvement || 0) < 0) {
            improvementEl.style.color = 'var(--danger)';
        }
        
        // Render score progression chart
        renderScoreChart(data.score_progression);
        
        // Render operators chart
        renderOperatorsChart(data.top_operators);
        // Operator coverage (first K)
        const coverage = (data.operators && typeof data.operators.coverage_first_k === 'number') ? data.operators.coverage_first_k : 'N/A';
        const covEl = document.getElementById('operatorCoverageK');
        if (covEl) covEl.textContent = coverage;
        
        // Render task performance chart
        renderTaskChart(data.task_performance);

        // Judges panel
        if (data.judges) {
            document.getElementById('judgeEvaluated').textContent = data.judges.evaluated ?? '-';
            const tbr = (data.judges.tie_breaker_rate != null) ? (data.judges.tie_breaker_rate * 100).toFixed(1) + '%' : '-';
            document.getElementById('tieBreakerRate').textContent = tbr;
            document.getElementById('evalP50').textContent = data.judges.eval_latency_ms?.p50 ?? '-';
            document.getElementById('evalP90').textContent = data.judges.eval_latency_ms?.p90 ?? '-';
            // Mirror in Costs panel
            const p50 = data.judges.eval_latency_ms?.p50 ?? '-';
            const p90 = data.judges.eval_latency_ms?.p90 ?? '-';
            document.getElementById('costEvalP50').textContent = p50;
            document.getElementById('costEvalP90').textContent = p90;
        }

        // Golden summary by task_type
        if (data.golden) {
            const el = document.getElementById('goldenSummary');
            const entries = Object.entries(data.golden);
            if (entries.length === 0) {
                el.innerHTML = '<p class="text-muted">No Golden Set history yet.</p>';
            } else {
                let html = '<div style="display:flex;flex-direction:column;gap:8px">';
                for (const [tt, m] of entries) {
                    html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:var(--surface);border-radius:4px">
                        <strong>${tt}</strong>
                        <div style="display:flex;gap:16px">
                          <span>Pass: ${(m.pass_rate*100).toFixed(0)}%</span>
                          <span>Reward: ${(m.avg_total_reward??0).toFixed(3)}</span>
                          <span>Cost: ${(m.avg_cost_penalty??0).toFixed(3)}</span>
                          <span>Steps: ${(m.avg_steps??0).toFixed(1)}</span>
                        </div>
                    </div>`;
                }
                html += '</div>';
                el.innerHTML = html;
                // Costs panel: show a weighted average if available
                const avgCosts = entries.map(([_,m]) => m.avg_cost_penalty).filter(x => typeof x === 'number');
                if (avgCosts.length) {
                    const mean = avgCosts.reduce((a,b)=>a+b,0)/avgCosts.length;
                    document.getElementById('goldenAvgCost').textContent = mean.toFixed(3);
                }
            }
        }
        // Voices panel (if provided)
        if (data.voices && Array.isArray(data.voices)) {
            const el = document.getElementById('voicesChart');
            if (el) {
                let html = '<div style="display:flex;flex-direction:column;gap:8px">';
                data.voices.forEach(v => {
                    html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:var(--surface);border-radius:4px">
                        <span style="max-width:60%">${v.system}</span>
                        <div style="display:flex;gap:12px">
                            <span>Uses: ${v.uses}</span>
                            <span>Reward: ${(v.avg_total_reward??0).toFixed(3)}</span>
                            <span>Cost: ${(v.avg_cost_penalty??0).toFixed(3)}</span>
                        </div>
                    </div>`;
                });
                html += '</div>';
                el.innerHTML = html;
            }
        }

        // Thresholds panel
        if (data.thresholds) {
            const th = data.thresholds;
            const elD = document.getElementById('thDelta'); if (elD) elD.textContent = th.delta_reward_min ?? '-';
            const elC = document.getElementById('thCost'); if (elC) elC.textContent = th.cost_ratio_max ?? '-';
            const elP = document.getElementById('thPass'); if (elP) elP.textContent = th.golden_pass_rate_target ?? '-';
        }

    } catch (error) {
        console.error('Failed to load analytics:', error);
        document.getElementById('analyticsError').classList.remove('hidden');
        document.getElementById('analyticsOverview').classList.add('hidden');
    }
}

// Memory Analytics Dashboard
async function loadMemoryAnalytics() {
    try {
        const response = await fetch('/api/meta/analytics/memory');
        const data = await response.json();
        
        // Update memory analytics
        const memoryOverview = document.getElementById('memoryOverview');
        const memoryRecentRuns = document.getElementById('memoryRecentRuns');
        const memoryError = document.getElementById('memoryError');
        
        if (!data.enabled) {
            // Show disabled message
            memoryError.classList.remove('hidden');
            memoryError.innerHTML = `<p class="text-muted">🧠 Memory system is disabled. Enable with FF_MEMORY=1 in your environment.</p>`;
            memoryOverview.classList.add('hidden');
            memoryRecentRuns.classList.add('hidden');
            return;
        }
        
        // Hide error, show content
        memoryError.classList.add('hidden');
        memoryOverview.classList.remove('hidden');
        memoryRecentRuns.classList.remove('hidden');
        
        const analytics = data.analytics || {};
        const recentRuns = data.recent_runs || [];
        
        // Update overview statistics
        document.getElementById('memoryHitRate').textContent = 
            analytics.hit_rate ? `${(analytics.hit_rate * 100).toFixed(1)}%` : '0%';
        document.getElementById('memoryAvgRewardLift').textContent = 
            analytics.avg_reward_lift ? `+${(analytics.avg_reward_lift * 100).toFixed(1)}%` : 'N/A';
        document.getElementById('memoryStoreSize').textContent = 
            analytics.store_size || '0';
        document.getElementById('memoryPrimerTokensP50').textContent = 
            analytics.primer_tokens_p50 || '0';
        document.getElementById('memoryPrimerTokensP95').textContent = 
            analytics.primer_tokens_p95 || '0';
        document.getElementById('memoryTotalRuns').textContent = 
            analytics.total_runs || '0';
        
        // Render by-task-class breakdown
        if (analytics.by_task_class && analytics.by_task_class.length > 0) {
            let taskClassHTML = '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">';
            analytics.by_task_class.forEach(tc => {
                const hitRate = tc.hit_rate ? `${(tc.hit_rate * 100).toFixed(1)}%` : '0%';
                const avgLift = tc.avg_lift ? `+${(tc.avg_lift * 100).toFixed(1)}%` : 'N/A';
                taskClassHTML += `
                    <div class="result-card" style="text-align:center;padding:12px">
                        <h5 style="margin:0;color:var(--accent)">${tc.task_class}</h5>
                        <div style="font-size:0.9em;color:var(--muted)">Runs: ${tc.runs_count}</div>
                        <div>Hit Rate: ${hitRate}</div>
                        <div>Avg Lift: ${avgLift}</div>
                    </div>
                `;
            });
            taskClassHTML += '</div>';
            document.getElementById('memoryTaskClassBreakdown').innerHTML = taskClassHTML;
        } else {
            document.getElementById('memoryTaskClassBreakdown').innerHTML = 
                '<p class="text-muted">No task class data available</p>';
        }
        
        // Render recent runs table
        if (recentRuns.length > 0) {
            let runsHTML = `
                <table style="width:100%;border-collapse:collapse">
                    <thead>
                        <tr style="background:var(--accent);color:white">
                            <th style="padding:8px;text-align:left">Run ID</th>
                            <th style="padding:8px;text-align:left">Task Class</th>
                            <th style="padding:8px;text-align:center">Hits</th>
                            <th style="padding:8px;text-align:center">Primer Tokens</th>
                            <th style="padding:8px;text-align:center">Store Size</th>
                            <th style="padding:8px;text-align:left">Created</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            recentRuns.forEach(run => {
                const createdDate = new Date(run.created_at).toLocaleDateString();
                const memoryUsed = run.used_memory ? '✅' : '❌';
                runsHTML += `
                    <tr style="border-bottom:1px solid var(--border)">
                        <td style="padding:6px">${run.run_id}</td>
                        <td style="padding:6px">${run.task_class}</td>
                        <td style="padding:6px;text-align:center">${run.memory_hits}</td>
                        <td style="padding:6px;text-align:center">${run.memory_primer_tokens}</td>
                        <td style="padding:6px;text-align:center">${run.memory_store_size}</td>
                        <td style="padding:6px;font-size:0.9em">${createdDate}</td>
                    </tr>
                `;
            });
            
            runsHTML += '</tbody></table>';
            document.getElementById('memoryRecentRunsTable').innerHTML = runsHTML;
        } else {
            document.getElementById('memoryRecentRunsTable').innerHTML = '<p class="text-muted">No recent memory runs</p>';
        }
        
    } catch (error) {
        console.error('Failed to load memory analytics:', error);
        const memoryError = document.getElementById('memoryError');
        memoryError.classList.remove('hidden');
        memoryError.innerHTML = `<p style="color:var(--danger)">❌ Error loading memory analytics: ${error.message}</p>`;
        document.getElementById('memoryOverview').classList.add('hidden');
        document.getElementById('memoryRecentRuns').classList.add('hidden');
    }
}

// Tab switching for Analytics
function selectAnalyticsTab(name) {
    const tabs = ['overview','runs','operators','voices','judges','golden','costs','thresholds','memory'];
    tabs.forEach(t => {
        const el = document.getElementById(`tab-${t}`);
        if (el) el.classList.toggle('hidden', t !== name);
    });
    if (name === 'runs') {
        loadEvolutionHistory();
    } else if (name === 'memory') {
        loadMemoryAnalytics();
    } else {
        // Load analytics data for all other tabs (overview, operators, voices, etc.)
        loadAnalytics();
    }
}

window.selectAnalyticsTab = selectAnalyticsTab;

// Golden Set runner with streaming
async function runGoldenSet() {
    try {
        const out = document.getElementById('goldenRunResult');
        const button = document.querySelector('button[onclick="runGoldenSet()"]');
        
        // Update UI to show it's running
        out.textContent = '🏁 Starting Golden Set evaluation...';
        if (button) {
            button.disabled = true;
            button.textContent = '🏁 Running...';
        }
        
        // Start async golden run
        const res = await fetch('/api/golden/run_async', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({}) 
        });
        
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }
        
        const data = await res.json();
        if (!data.run_id) {
            throw new Error('No run_id returned');
        }
        
        // Start streaming
        startGoldenStream(data.run_id, button, out);
        
    } catch (e) {
        const out = document.getElementById('goldenRunResult');
        const button = document.querySelector('button[onclick="runGoldenSet()"]');
        out.textContent = 'Golden run failed: ' + e.message;
        if (button) {
            button.disabled = false;
            button.textContent = '🏁 Run Golden Set';
        }
    }
}

function startGoldenStream(runId, button, outputElement) {
    const eventSource = new EventSource(`/api/golden/stream?run_id=${runId}`);
    let completed = 0;
    let total = 0;
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('Golden Set event:', data);
            
            switch (data.event) {
                case 'connected':
                    outputElement.textContent = '📡 Connected to Golden Set stream...';
                    break;
                    
                case 'started':
                    total = data.total_tests || 0;
                    outputElement.textContent = `🏁 Starting ${total} Golden Set tests...`;
                    break;
                    
                case 'progress':
                    completed = data.completed || 0;
                    const percent = total > 0 ? ((completed / total) * 100).toFixed(0) : 0;
                    outputElement.textContent = `🏁 Running test ${data.test_id} (${completed}/${total} - ${percent}%)`;
                    break;
                    
                case 'test_complete':
                    const result = data.result || {};
                    const reward = (result.total_reward || 0).toFixed(3);
                    outputElement.textContent = `✅ Test ${data.test_id} complete: reward ${reward} (${completed}/${total})`;
                    break;
                    
                case 'completed':
                    const agg = data.aggregate || {};
                    outputElement.textContent = `✅ Golden Set complete: pass_rate ${(agg.pass_rate*100||0).toFixed(0)}%, reward ${(agg.avg_total_reward??0).toFixed(3)}, cost ${(agg.avg_cost_penalty??0).toFixed(3)}, steps ${(agg.avg_steps??0).toFixed(1)}`;
                    eventSource.close();
                    if (button) {
                        button.disabled = false;
                        button.textContent = '🏁 Run Golden Set';
                    }
                    // Refresh analytics
                    loadAnalytics();
                    break;
                    
                case 'error':
                    outputElement.textContent = `❌ Golden Set error: ${data.message}`;
                    eventSource.close();
                    if (button) {
                        button.disabled = false;
                        button.textContent = '🏁 Run Golden Set';
                    }
                    break;
                    
                case 'keep-alive':
                    // Just keep connection alive
                    break;
            }
        } catch (e) {
            console.error('Error parsing Golden Set event:', e);
        }
    };
    
    eventSource.onerror = function(event) {
        console.error('Golden Set stream error:', event);
        outputElement.textContent = '❌ Golden Set stream disconnected';
        eventSource.close();
        if (button) {
            button.disabled = false;
            button.textContent = '🏁 Run Golden Set';
        }
    };
}

function renderScoreChart(scoreProgression) {
    const chartContent = document.getElementById('scoreChartContent');
    if (!scoreProgression || scoreProgression.length === 0) {
        chartContent.innerHTML = '<p class="text-muted" style="text-align:center;padding:40px">No score data available</p>';
        return;
    }
    
    // Simple text-based chart showing score progression
    let html = '<div style="display:flex;flex-direction:column;gap:8px">';
    
    scoreProgression.forEach((run, index) => {
        const score = run.score !== null ? run.score.toFixed(3) : 'N/A';
        const rollingAvg = run.rolling_avg ? run.rolling_avg.toFixed(3) : 'N/A';
        const date = new Date(run.timestamp * 1000).toLocaleDateString();
        
        html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:${index % 2 === 0 ? 'var(--panel)' : 'var(--surface)'};border-radius:4px">
            <span class="text-muted">${date} (${run.task_class})</span>
            <div style="display:flex;gap:16px;align-items:center">
                <span>Score: <strong>${score}</strong></span>
                <span class="text-muted">Rolling Avg: ${rollingAvg}</span>
            </div>
        </div>`;
    });
    
    html += '</div>';
    chartContent.innerHTML = html;
}

function renderOperatorsChart(operators) {
    const chartContent = document.getElementById('operatorsChart');
    if (!operators || operators.length === 0) {
        chartContent.innerHTML = '<p class="text-muted">No operator data available</p>';
        return;
    }
    
    let html = '<div style="display:flex;flex-direction:column;gap:8px">';
    
    operators.forEach((op, index) => {
        const rewardBar = Math.max(0, Math.min(100, (op.avg_reward / 30) * 100)); // Scale to 100px max
        const avgTimeMs = op.avg_time_per_use / 1000; // Convert to seconds
        
        html += `<div style="padding:8px;background:var(--surface);border-radius:6px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <strong>${op.name}</strong>
                <span class="text-muted">${op.uses} uses</span>
            </div>
            <div style="display:flex;align-items:center;gap:12px">
                <div style="flex:1">
                    <div style="background:var(--panel);border-radius:4px;height:8px;overflow:hidden">
                        <div style="background:linear-gradient(90deg,var(--primary),var(--accent));height:100%;width:${rewardBar}%;transition:width 0.5s ease"></div>
                    </div>
                </div>
                <div style="min-width:80px;text-align:right">
                    <div style="font-size:0.9em"><strong>${op.avg_reward.toFixed(2)}</strong> reward</div>
                    <div style="font-size:0.8em;color:var(--muted)">${avgTimeMs.toFixed(1)}s avg</div>
                </div>
            </div>
        </div>`;
    });
    
    html += '</div>';
    chartContent.innerHTML = html;
}

function renderTaskChart(taskPerformance) {
    const chartContent = document.getElementById('taskChart');
    if (!taskPerformance || taskPerformance.length === 0) {
        chartContent.innerHTML = '<p class="text-muted">No task performance data available</p>';
        return;
    }
    
    let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">';
    
    taskPerformance.forEach(task => {
        const avgScore = task.avg_score ? task.avg_score.toFixed(3) : 'N/A';
        const bestScore = task.best_score ? task.best_score.toFixed(3) : 'N/A';
        
        html += `<div style="padding:12px;background:var(--surface);border-radius:6px;text-align:center">
            <div style="font-weight:bold;color:var(--primary);margin-bottom:4px">${task.task_class}</div>
            <div style="font-size:0.9em;margin-bottom:2px">Avg: <strong>${avgScore}</strong></div>
            <div style="font-size:0.9em;margin-bottom:2px">Best: <strong>${bestScore}</strong></div>
            <div style="font-size:0.8em;color:var(--muted)">${task.runs} runs</div>
        </div>`;
    });
    
    html += '</div>';
    chartContent.innerHTML = html;
}

function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'result-card';
    errorDiv.style.borderColor = 'var(--danger)';
    errorDiv.innerHTML = `
        <div style="color:var(--danger);text-align:center">
            <h4>Error</h4>
            <p>${message}</p>
        </div>
    `;
    
    document.getElementById('evolutionResults').classList.remove('hidden');
    document.getElementById('resultsContent').innerHTML = '';
    document.getElementById('resultsContent').appendChild(errorDiv);
}

// Explicitly attach functions to window object for global access
// Rating System Functions
function setupRatingSystem() {
    const detailedRating = document.getElementById('detailedRating');
    const ratingValue = document.getElementById('ratingValue');
    const rateGood = document.getElementById('rateGood');
    const ratePoor = document.getElementById('ratePoor');
    const submitRating = document.getElementById('submitRating');
    
    if (!detailedRating) return; // Elements not ready yet
    
    // Update rating display
    detailedRating.addEventListener('input', function() {
        ratingValue.textContent = `${this.value}/10`;
    });
    
    // Quick rating buttons
    rateGood.addEventListener('click', function() {
        detailedRating.value = 8;
        ratingValue.textContent = '8/10';
        submitRating.style.background = 'var(--success)';
    });
    
    ratePoor.addEventListener('click', function() {
        detailedRating.value = 3;
        ratingValue.textContent = '3/10';
        submitRating.style.background = 'var(--danger)';
    });
    
    // Submit rating
    submitRating.addEventListener('click', submitHumanRating);
}

function showRatingPanel() {
    const panel = document.getElementById('ratingPanel');
    if (panel) {
        const mode = (localStorage.getItem('ratings_mode') || 'prompted');
        if (mode === 'off') {
            panel.classList.add('hidden');
            return;
        }
        const delay = parseInt(localStorage.getItem('reading_delay_ms') || '2000');
        panel.classList.add('hidden');
        setTimeout(() => {
            panel.classList.remove('hidden');
        }, Math.max(0, Math.min(8000, isNaN(delay) ? 2000 : delay)));
        
        // Reset rating form
        document.getElementById('detailedRating').value = 5;
        document.getElementById('ratingValue').textContent = '5/10';
        document.getElementById('ratingFeedback').value = '';
        document.getElementById('submitRating').style.background = '';
        document.getElementById('ratingStatus').textContent = '';
    }
}

function hideRatingPanel() {
    const panel = document.getElementById('ratingPanel');
    if (panel) {
        panel.classList.add('hidden');
    }
}

async function submitHumanRating() {
    if (!currentVariantId) {
        showRatingStatus('❌ No response to rate', 'var(--danger)');
        return;
    }
    
    const rating = parseInt(document.getElementById('detailedRating').value);
    const feedback = document.getElementById('ratingFeedback').value.trim();
    const humanScore = rating; // Use 1-10 scale directly
    
    try {
        showRatingStatus('⏳ Submitting rating...', 'var(--muted)');
        
        const response = await fetch('/api/meta/rate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                variant_id: currentVariantId,
                human_score: humanScore,
                feedback: feedback
            }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        showRatingStatus(`✅ Rating submitted (${rating}/10)`, 'var(--success)');
        
        // Hide panel after successful submission
        setTimeout(() => {
            hideRatingPanel();
        }, 2000);
        
    } catch (error) {
        console.error('Rating submission failed:', error);
        showRatingStatus(`❌ Failed to submit rating: ${error.message}`, 'var(--danger)');
    }
}

function showRatingStatus(message, color) {
    const status = document.getElementById('ratingStatus');
    if (status) {
        status.textContent = message;
        status.style.color = color;
    }
}

window.checkHealth = checkHealth;
window.startEvolution = startEvolution;
window.quickTest = quickTest;
window.streamTest = streamTest;
window.loadEvolutionHistory = loadEvolutionHistory;
window.loadAnalytics = loadAnalytics;
window.runGoldenSet = runGoldenSet;
window.startNewEvolution = startNewEvolution;
window.submitHumanRating = submitHumanRating;

// Legacy compatibility functions (for existing backend calls)
function doChat() { quickTest(); }
function streamChat() { streamTest(); }
function doEvolve() { startEvolution(); }
function runMetaEvolution() { startEvolution(); }
function newSession() { /* No-op for compatibility */ }
function loadSessions() { /* No-op for compatibility */ }
function doSearch() { alert('Use evolution mode with web research enabled instead'); }
function doRagBuild() { alert('RAG is automatically built during evolution'); }
function doRagQuery() { alert('Use Quick Test instead'); }
function doMemoryQuery() { alert('Use Quick Test instead'); }
function buildMemory() { alert('Memory is automatically built during evolution'); }
function thumbs() { /* No-op for compatibility */ }
function uiListGroq() { /* No-op for compatibility */ }
function viewMetaLogs() { loadEvolutionHistory(); }

// Utility functions for legacy compatibility
async function post(path, body){
    const r=await fetch(path,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(body||{})
    }); 
    if(!r.ok){
        const e=await r.json().catch(()=>({})); 
        throw new Error(e.detail||JSON.stringify(e));
    } 
    return r.json();
}

async function get(path){
    const r=await fetch(path); 
    if(!r.ok){
        const e=await r.json().catch(()=>({})); 
        throw new Error(e.detail||JSON.stringify(e));
    } 
    return r.json();
}

const out = document.getElementById("out") || document.createElement('div');
function show(x){ 
    if(out) out.textContent = typeof x==="string"? x : JSON.stringify(x,null,2); 
}

function getSelectedSession(){ return 1; } // Default session for compatibility
