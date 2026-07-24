# api.py - with better error handling for CDP commands
import asyncio
import logging
import json
from aiohttp import web
from daemon import ChromeDaemon

class ChromeAPI:
    def __init__(self):
        self.daemon = ChromeDaemon()
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        self.app.router.add_post('/session/{name}/start', self.start_session)
        self.app.router.add_post('/session/{name}/stop', self.stop_session)
        self.app.router.add_get('/session/{name}/status', self.get_status)
        self.app.router.add_get('/sessions', self.list_sessions)
        self.app.router.add_post('/session/{name}/navigate', self.navigate)
        self.app.router.add_get('/session/{name}/url', self.get_url)
        self.app.router.add_get('/session/{name}/html', self.get_html)
        self.app.router.add_post('/session/{name}/click', self.click)
        self.app.router.add_post('/session/{name}/evaluate', self.evaluate)
        self.app.router.add_get('/session/{name}/screenshot', self.screenshot)
        self.app.router.add_post('/session/{name}/cdp', self.cdp_command)
        self.app.router.add_get('/health', self.health_check)
    
    async def health_check(self, request):
        return web.json_response({'status': 'ok', 'service': 'chrome-daemon'})
    
    async def start_session(self, request):
        try:
            data = await request.json()
        except:
            data = {}
        name = data.get('name', 'unstop')
        url = data.get('url', 'https://unstop.com/')
        
        result = await self.daemon.start_session(name, url)
        return web.json_response(result)
    
    async def stop_session(self, request):
        name = request.match_info['name']
        result = await self.daemon.stop_session(name)
        return web.json_response(result)
    
    async def get_status(self, request):
        name = request.match_info['name']
        session = self.daemon.get_session(name)
        if session:
            return web.json_response({
                'exists': True,
                'session': session,
                'connected': name in self.daemon.active_connections
            })
        return web.json_response({'exists': False})
    
    async def list_sessions(self, request):
        try:
            data = self.daemon.load_session_info()
            sessions = []
            for session_id, session in data.get('sessions', {}).items():
                sessions.append({
                    'id': session_id,
                    'name': session.get('name', ''),
                    'url': session.get('url', ''),
                    'port': session.get('port', 0),
                    'status': session.get('status', 'unknown'),
                    'pid': session.get('pid', 0),
                    'ws_id': session.get('current_ws_id', None)
                })
            return web.json_response({'sessions': sessions, 'count': len(sessions)})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def navigate(self, request):
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        
        url = data.get('url')
        name = request.match_info['name']
        
        if not url:
            return web.json_response({'error': 'URL required'}, status=400)
        
        result = await self.daemon.navigate(name, url)
        return web.json_response(result)
    
    async def get_url(self, request):
        name = request.match_info['name']
        result = await self.daemon.get_url(name)
        return web.json_response(result)
    
    async def get_html(self, request):
        name = request.match_info['name']
        result = await self.daemon.get_html(name)
        return web.json_response(result)
    
    async def click(self, request):
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        
        selector = data.get('selector')
        name = request.match_info['name']
        
        if not selector:
            return web.json_response({'error': 'Selector required'}, status=400)
        
        result = await self.daemon.click(name, selector)
        return web.json_response(result)
    
    async def evaluate(self, request):
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        
        expression = data.get('expression')
        name = request.match_info['name']
        
        if not expression:
            return web.json_response({'error': 'Expression required'}, status=400)
        
        result = await self.daemon.evaluate(name, expression)
        return web.json_response(result)
    
    async def screenshot(self, request):
        name = request.match_info['name']
        result = await self.daemon.screenshot(name)
        return web.json_response(result)
    
    async def cdp_command(self, request):
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        
        method = data.get('method')
        params = data.get('params', {})
        name = request.match_info['name']
        
        if not method:
            return web.json_response({'error': 'Method required'}, status=400)
        
        result = await self.daemon.execute_cdp_command(name, method, params)
        return web.json_response(result)
    
    def run(self, host="127.0.0.1", port=5000):
        print(f"🚀 Chrome Daemon API starting on http://{host}:{port}")
        print(f"📋 Session file: {self.daemon.session_file}")
        print("✅ Ready to accept requests")
        web.run_app(self.app, host=host, port=port)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    api = ChromeAPI()
    
    # Check if unstop session exists
    session = api.daemon.get_session("unstop")
    if not session:
        print("🔄 Starting default unstop session...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(api.daemon.start_session("unstop"))
        if result.get('success'):
            print(f"✅ Session started: {result}")
        else:
            print(f"❌ Failed to start session: {result}")
    else:
        print(f"✅ Found existing unstop session (PID: {session.get('pid')})")
        print(f"   URL: {session.get('url')}")
        print(f"   Port: {session.get('port')}")
        print(f"   WebSocket ID: {session.get('current_ws_id')}")
    
    api.run()
