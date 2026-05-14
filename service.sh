#!/bin/bash
# Daily AI News — Service Manager
# Usage:
#   ./service.sh start     Start both backend & frontend
#   ./service.sh stop      Stop both servers
#   ./service.sh restart   Restart both servers
#   ./service.sh status    Check if servers are running
#   ./service.sh logs      Tail live logs
#   ./service.sh uninstall Remove auto-start completely (stops everything)

BACKEND="com.c270744.daily-ai-news-backend"
FRONTEND="com.c270744.daily-ai-news-frontend"
PLIST_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/daily-ai-news"

case "$1" in
  start)
    echo "Starting Daily AI News..."
    launchctl load "$PLIST_DIR/$BACKEND.plist" 2>/dev/null
    launchctl load "$PLIST_DIR/$FRONTEND.plist" 2>/dev/null
    sleep 2
    echo "Backend:  http://localhost:8000"
    echo "Frontend: http://localhost:5173"
    echo "Done. You can close this terminal."
    ;;

  stop)
    echo "Stopping Daily AI News..."
    launchctl unload "$PLIST_DIR/$BACKEND.plist" 2>/dev/null
    launchctl unload "$PLIST_DIR/$FRONTEND.plist" 2>/dev/null
    echo "Stopped."
    ;;

  restart)
    $0 stop
    sleep 1
    $0 start
    ;;

  status)
    echo "=== Backend ==="
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
      echo "  Running (http://localhost:8000)"
      curl -s http://localhost:8000/api/admin/digest-status | python3 -m json.tool 2>/dev/null
    else
      echo "  NOT running"
    fi
    echo ""
    echo "=== Frontend ==="
    if curl -s http://localhost:5173 > /dev/null 2>&1; then
      echo "  Running (http://localhost:5173)"
    else
      echo "  NOT running"
    fi
    ;;

  logs)
    echo "Tailing logs (Ctrl+C to stop)..."
    tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
    ;;

  uninstall)
    echo "Uninstalling Daily AI News services..."
    launchctl unload "$PLIST_DIR/$BACKEND.plist" 2>/dev/null
    launchctl unload "$PLIST_DIR/$FRONTEND.plist" 2>/dev/null
    rm -f "$PLIST_DIR/$BACKEND.plist"
    rm -f "$PLIST_DIR/$FRONTEND.plist"
    rm -rf "$LOG_DIR"
    echo ""
    echo "Done. Services removed. Servers stopped."
    echo "Your code in ~/daily-ai-news is untouched."
    echo "To fully delete: rm -rf ~/daily-ai-news"
    ;;

  *)
    echo "Usage: $0 {start|stop|restart|status|logs|uninstall}"
    exit 1
    ;;
esac
