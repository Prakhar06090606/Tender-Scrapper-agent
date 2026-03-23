# run.py — Windows entry point. Use: py run.py
import sys, asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Tender Agent starting...")
    print("📖 Docs: http://localhost:8000/docs")
    print("🛑 Press Ctrl+C to stop")
    print("⏰ First scrape begins 2 minutes after startup")
    print("=" * 50)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        loop="asyncio",
        # Faster startup — don't wait for full app init before accepting connections
        timeout_graceful_shutdown=5,
    )
