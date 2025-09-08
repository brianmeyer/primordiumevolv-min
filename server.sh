#!/bin/bash
# Server management script for primordium-evolv

PORT=${PORT:-8000}
LOGFILE="server.log"

case "$1" in
    start)
        # Kill any existing servers first
        echo "Stopping existing servers..."
        pkill -f "uvicorn app.main:app" 2>/dev/null || true
        
        sleep 1
        
        # Clear any leftover cache files
        echo "Cleaning up caches..."
        python -c "
try:
    from app.cache_manager import clear_all_caches, clear_streaming_queues
    clear_all_caches()
    clear_streaming_queues()
except:
    print('Cache cleanup failed (normal on first run)')
" 2>/dev/null || echo "Cache cleanup skipped"
        
        # Start server
        echo "Starting server on port $PORT..."
        python -m uvicorn app.main:app --host 127.0.0.1 --port $PORT --log-level info > "$LOGFILE" 2>&1 &
        SERVER_PID=$!
        echo "Server started with PID $SERVER_PID"
        echo "Logs: tail -f $LOGFILE"
        ;;
        
    stop)
        echo "Stopping all uvicorn servers..."
        pkill -f "uvicorn app.main:app"
        echo "Servers stopped"
        ;;
        
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
        
    status)
        PIDS=$(pgrep -f "uvicorn app.main:app" 2>/dev/null)
        if [ -z "$PIDS" ]; then
            echo "No servers running"
        else
            echo "Running servers:"
            ps aux | grep "uvicorn app.main:app" | grep -v grep
        fi
        ;;
        
    logs)
        if [ -f "$LOGFILE" ]; then
            tail -f "$LOGFILE"
        else
            echo "No log file found at $LOGFILE"
        fi
        ;;
        
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start   - Stop any existing servers and start a new one"
        echo "  stop    - Stop all servers"
        echo "  restart - Stop and start"
        echo "  status  - Show running servers"
        echo "  logs    - Follow server logs"
        exit 1
        ;;
esac