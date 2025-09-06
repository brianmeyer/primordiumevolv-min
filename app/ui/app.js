// Streamlined Evolution UI - Human-centered design focused on self-evolution

let currentRunId = null;
let evolutionEventSource = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    checkHealth();
    
    // Auto-check health every 30 seconds
    setInterval(checkHealth, 30000);
});

// Health Check
async function checkHealth() {
    console.log('Checking health...');
    try {
        // Check Ollama
        console.log('Checking Ollama health...');
        const ollamaResponse = await fetch('/api/health/ollama');
        const ollamaData = await ollamaResponse.json();
        console.log('Ollama health:', ollamaData);
        const ollamaHealth = document.getElementById('ollamaHealth');
        ollamaHealth.textContent = `Ollama: ${ollamaData.status}`;
        ollamaHealth.className = ollamaData.status === 'ok' ? 'status-badge status-ok' : 'status-badge status-error';
        
        // Check Groq  
        console.log('Checking Groq health...');
        const groqResponse = await fetch('/api/health/groq');
        const groqData = await groqResponse.json();
        console.log('Groq health:', groqData);
        const groqHealth = document.getElementById('groqHealth');
        // Extract just groq status from the response
        const groqStatus = groqData.groq ? groqData.groq.status : groqData.status;
        groqHealth.textContent = `Groq: ${groqStatus}`;
        groqHealth.className = groqStatus === 'ok' ? 'status-badge status-ok' : 'status-badge status-error';
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
    const useWeb = document.getElementById('advUseWeb').checked;
    
    console.log('Evolution config:', { taskType, iterations, epsilon, memoryK, useWeb });
    
    // Show progress UI
    showEvolutionProgress();
    
    // Disable start button
    const startBtn = document.getElementById('startEvolution');
    startBtn.disabled = true;
    startBtn.textContent = '🧬 Evolving...';
    
    try {
        console.log('Sending evolution request...');
        const response = await fetch('/api/meta/run', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                task_class: taskType,
                task: task,
                n: iterations,
                use_bandit: true,
                epsilon: epsilon,
                memory_k: memoryK,
                use_web: useWeb
            }),
        });
        
        console.log('Evolution response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Evolution request failed:', errorText);
            throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
        }
        
        const data = await response.json();
        console.log('Evolution started with run_id:', data.run_id);
        currentRunId = data.run_id;
        
        // Start streaming progress
        startEvolutionStream(data.run_id);
        
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

function startEvolutionStream(runId) {
    console.log('Starting evolution stream for run_id:', runId);
    
    if (evolutionEventSource) {
        evolutionEventSource.close();
    }
    
    evolutionEventSource = new EventSource(`/api/meta/stream?run_id=${runId}`);
    
    evolutionEventSource.onmessage = function(event) {
        console.log('Evolution stream event:', event.data);
        const data = JSON.parse(event.data);
        handleEvolutionEvent(data);
    };
    
    evolutionEventSource.onopen = function(event) {
        console.log('Evolution stream connected');
        addEvolutionStep('📡 Connected to evolution stream', 'running');
    };
    
    evolutionEventSource.onerror = function(error) {
        console.error('Evolution stream error:', error);
        addEvolutionStep('❌ Stream connection error', 'error');
        evolutionEventSource.close();
        setTimeout(() => {
            resetEvolutionButton();
        }, 2000);
    };
}

function handleEvolutionEvent(data) {
    switch (data.type) {
        case 'iteration_start':
            addEvolutionStep(`🔄 Iteration ${data.iteration + 1}: Trying ${data.operator}`, 'running');
            updateProgress((data.iteration / data.total_iterations) * 100);
            break;
            
        case 'iteration_complete':
            updateLastStep(`✅ Iteration ${data.iteration + 1}: Score ${data.score.toFixed(3)} (${data.operator})`, 'completed');
            document.getElementById('currentOutput').textContent = data.output || 'No output';
            break;
            
        case 'done':
            handleEvolutionComplete(data.result);
            break;
            
        case 'error':
            showError('Evolution error: ' + data.message);
            resetEvolutionButton();
            break;
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
    
    const improvement = ((result.improvement / Math.max(result.baseline, 0.1)) * 100).toFixed(1);
    
    const resultsHTML = `
        <div class="result-card">
            <div class="result-score">${result.best_score.toFixed(3)}</div>
            <div class="result-improvement">+${improvement}% improvement</div>
            <div class="text-center text-muted">
                Best strategy: ${result.best_recipe.system || 'Default system'} 
                ${result.best_recipe.use_web ? '+ Web Research' : ''}
                ${result.best_recipe.use_memory ? '+ Memory' : ''}
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
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt: prompt,
                session_id: 1
            }),
        });
        
        const data = await response.json();
        output.textContent = data.output || 'No response';
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
        const response = await fetch(`/api/chat/stream?prompt=${encodeURIComponent(prompt)}&session_id=1`);
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
                        output.textContent += parsed.chunk || '';
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
window.checkHealth = checkHealth;
window.startEvolution = startEvolution;
window.quickTest = quickTest;
window.streamTest = streamTest;
window.loadEvolutionHistory = loadEvolutionHistory;
window.startNewEvolution = startNewEvolution;

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