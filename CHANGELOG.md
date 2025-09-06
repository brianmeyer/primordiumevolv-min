# Changelog

## [2.0.0] - 2025-09-06 - Human-Centered UI Redesign

### 🎯 Major UI Overhaul
- **Complete interface redesign** using human-centered design principles
- **Single primary action**: Focused "🚀 Start Evolution" workflow
- **Natural language prompts**: "What should the AI get better at?" instead of technical jargon
- **Progressive disclosure**: Advanced settings collapsed by default
- **Task-oriented design**: Dropdown for Code, Analysis, Writing, Business, etc.

### 📊 Real-time Progress & Streaming
- **Visual progress bars** with real-time completion percentages
- **Live step tracking**: "🔄 Iteration 2: Trying toggle_web" status updates
- **Streaming output display**: Watch AI responses as they're generated
- **Connection status**: "📡 Connected to evolution stream" feedback
- **Comprehensive logging**: Debug info in browser console (F12)

### 🎨 Improved User Experience
- **Collapsible sections** for clean interface:
  - 💬 Quick Test Current AI
  - ⚙️ Advanced Evolution Settings
  - 📊 View Evolution History
- **Health monitoring**: Auto-updating Ollama/Groq status badges
- **Error handling**: Clear error messages with recovery suggestions
- **Mobile-friendly**: Responsive design for all devices
- **Glassmorphism theme**: Modern dark UI with backdrop blur effects

### 🔧 Technical Improvements
- **Fixed meta-evolution freezing bug**: Runs now always complete properly
- **Enhanced health endpoints**: Added `/api/health/ollama` endpoint
- **Better error handling**: Graceful degradation with user feedback
- **JavaScript fixes**: Corrected static file paths and loading issues
- **Console debugging**: Detailed logging for troubleshooting

### 🚀 New User Flow
1. Enter task description (natural language)
2. Select task type and number of iterations
3. Click "Start Evolution" button
4. Watch real-time progress with streaming updates
5. View results with improvement metrics and best strategies

### 🛠️ Bug Fixes
- Fixed health badges stuck on "checking..." status
- Resolved JavaScript loading issues (404 errors)
- Fixed meta-evolution runs not completing (`finished_at` null bug)
- Improved streaming connection handling with timeout management
- Enhanced error reporting with detailed stack traces

### 📈 Performance Improvements
- **Streaming progress updates**: Real-time feedback during evolution
- **Connection pooling**: Better resource management for long-running operations
- **Caching improvements**: Faster static file serving
- **Background processing**: Non-blocking evolution runs

---

## [1.x.x] - Previous Versions

### Legacy Features (Still Available)
- Multi-engine support (Ollama + Groq)
- Epsilon-greedy bandit optimization
- Recipe persistence and analytics
- Memory system with FAISS vector search
- RAG integration with document indexing  
- Web search capabilities
- Real-time streaming with Server-Sent Events
- Judge mode for comparative evaluation

### Migration Notes
- All legacy functionality preserved in hidden compatibility layer
- Old API endpoints remain functional
- Previous configurations still work
- Technical users can access advanced features through collapsible sections