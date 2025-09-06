# Changelog

## [2.1.0] - 2025-09-06 - Human Rating System

### 🧑‍⚖️ Human-in-the-Loop Feedback
- **Interactive Rating Panel**: Rate AI responses during evolution with 1-10 scale or thumbs up/down
- **Real-time Rating Interface**: Shows after each iteration response for immediate feedback
- **Feedback Collection**: Optional text feedback alongside numerical ratings
- **Database Integration**: All ratings stored in `human_ratings` table with variant linkage
- **API Endpoint**: `/api/meta/rate` for programmatic rating submission
- **Validation**: Proper input validation (1-10 scores, valid variant IDs)

### 🔧 Technical Implementation
- **New Database Table**: `human_ratings(id, variant_id, human_score, feedback, created_at)`
- **Request Model**: `HumanRatingRequest` with validation constraints
- **Store Function**: `save_human_rating()` for persistent storage
- **UI Integration**: Rating panel appears automatically during evolution
- **Error Handling**: Graceful validation and user feedback

### 📱 User Experience
- **Seamless Workflow**: Rating panel appears after each AI response
- **Multiple Rating Methods**: Quick thumbs up/down or detailed 1-10 scale
- **Visual Feedback**: Real-time rating submission status
- **Non-intrusive Design**: Collapsible panel maintains clean interface

---

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
- **Fixed JavaScript function scope issue**: Resolved "startEvolution is not a function" error by explicitly attaching functions to window object
- **Complete JavaScript functionality restoration**: Added missing `quickTest`, `streamTest`, `loadEvolutionHistory` functions with proper global scope
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