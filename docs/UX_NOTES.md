# PrimordiumEvolv UX Notes

## Developer Experience Guide

### Quick Start
1. Install dependencies: `pip install -r requirements.txt`
2. Start Ollama with a model: `ollama serve` then `ollama pull qwen3:4b`
3. Run server: `python -m uvicorn app.main:app --reload --port 8000`
4. Visit: http://localhost:8000

### Core Workflows

#### 1. Basic Chat & Memory
- **Session Management**: Create sessions to organize conversations
- **Memory Integration**: Chat responses automatically include relevant context from past conversations
- **Memory Building**: Use "Build Memory" to index conversation history for better context retrieval

#### 2. Meta-Evolution (Self-Improvement)
Located in the "🚀 Meta-Evolution Control" section:

**Key Parameters:**
- **Task Class**: Categorizes the type of task (e.g., "code", "analysis", "creative")
- **Iterations**: Number of optimization attempts (1-24, default: 5)
- **Use Bandit**: Enable epsilon-greedy operator selection (recommended: ON)
- **ε (Epsilon)**: Exploration vs exploitation balance (0.1 = 10% random, 90% best-performing)
- **Framework Mask**: Limit operators to specific families:
  - SEAL: Mutations (system prompt, temperature, few-shot examples)
  - WEB: Web search integration
  - SAMPLING: Parameter tuning (top_k, temperature)

**Best Practices:**
- Start with 5-10 iterations for quick tests
- Use specific task classes ("python_debugging", "creative_writing") for better recipe targeting  
- Enable bandit selection for adaptive improvement
- Check framework mask only when targeting specific optimization areas

#### 3. Analytics & Monitoring
The dashboard provides three key visualizations:

**Performance Trend Chart**: Shows best scores over time, filterable by task class
**Operator Rewards Chart**: Bar chart showing average reward per operator
**Selection Share Chart**: Pie chart showing operator usage frequency

**Logs & Inspection:**
- Click "📊 View Logs" to see detailed execution traces with ISO8601 timestamps
- API endpoint `/api/meta/runs/{run_id}` provides detailed run analysis
- Operator performance available at `/api/meta/operators/stats`

### System Architecture

#### Operator Families
- **SEAL (Self-Evolution And Learning)**: Core mutation operators
  - `change_system`: Modify system prompt
  - `change_nudge`: Adjust response style instructions
  - `raise_temp`/`lower_temp`: Temperature adjustments
  - `add_fewshot`: Include example demonstrations
  - `inject_memory`/`inject_rag`: Add context sources

- **WEB**: Web-enhanced operators
  - `toggle_web`: Enable/disable web search integration

- **SAMPLING**: Parameter optimization
  - `raise_top_k`/`lower_top_k`: Sampling diversity control

#### Persistence & Storage
- **SQLite Database**: All runs, variants, recipes, and operator statistics
- **FAISS Indexes**: Vector similarity search for memory and RAG
- **Structured Logs**: JSON artifacts with ISO8601 timestamps in `logs/`
- **Run Artifacts**: Detailed iteration data in `runs/{timestamp}/`

#### Error Handling
Structured error responses with context:
```json
{
  "error": "model_error",
  "detail": "Generation failed: connection timeout",
  "timestamp": "2025-01-15T14:30:45.123Z",
  "context": {"model_id": "qwen3:4b"}
}
```

### Performance Tips

#### Model Management
- Model validation occurs at startup (warns but doesn't crash if unavailable)
- Connection pooling reduces Ollama request latency
- Model list is cached to avoid repeated API calls

#### Memory & RAG Optimization
- Sentence transformer models are cached globally
- Index files stored in `storage/` directory
- Empty content filtering prevents indexing noise
- Similarity thresholds filter low-relevance matches

#### Meta-Evolution Tuning
- **Short Tasks**: Use 3-5 iterations with high epsilon (0.2-0.3) for exploration
- **Complex Tasks**: Use 10-20 iterations with low epsilon (0.05-0.1) for exploitation
- **Framework Masks**: Use SEAL for prompt optimization, WEB for information-heavy tasks
- **Task Classes**: Be specific - "python_debugging" performs better than "coding"

### Troubleshooting

#### Common Issues
1. **"Model not found"**: Check `MODEL_ID` in `.env`, ensure model is pulled in Ollama
2. **Empty RAG results**: Run "RAG Build" first, ensure documents exist in `data/`
3. **Memory errors**: Run "Build Memory" to create/update conversation index
4. **Slow evolution**: Check Ollama model size; smaller models (4b) are faster than larger ones (8b+)

#### Debug Endpoints
- `/api/health`: Check Ollama connectivity and model availability  
- `/api/meta/logs`: View recent structured log entries
- `/api/meta/operators/stats`: Detailed operator performance metrics

### Advanced Usage

#### Custom Operators
Add operators to `app/meta/operators.py` and register in `app/config.py`:
```python
DEFAULT_OPERATORS.append("my_custom_operator")
OP_GROUPS["CUSTOM"] = ["my_custom_operator"]
```

#### Task Class Conventions
Recommended naming for better recipe matching:
- `code_review`, `code_generation`, `code_debugging`
- `analysis_financial`, `analysis_scientific`, `analysis_market`
- `creative_writing`, `creative_brainstorming`
- `technical_documentation`, `user_documentation`

#### Integration Points
- **Web Search**: Uses Tavily API (configure `TAVILY_API_KEY`)
- **Document RAG**: Supports `.txt`, `.md`, `.pdf` in `data/` directory
- **Memory Context**: Automatically enriches chat with relevant conversation history

### Future Enhancements
- Real-time evolution progress streaming
- Custom scoring functions for domain-specific optimization
- Multi-model comparison and A/B testing
- Automatic hyperparameter tuning
- Recipe export/import for team sharing