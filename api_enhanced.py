# api_enhanced.py - Control Plane (API only)
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Optional
from aiohttp import web
from celery.result import AsyncResult

# Import Celery tasks
from celery_config import app as celery_app
from chrome_tasks_enhanced import (
    start_chrome_session_task,
    stop_chrome_session_task,
    restart_chrome_session_task,
    navigate_task,
    click_task,
    evaluate_task,
    execute_js_task,
    extract_data_task,
    extract_multiple_task,
    save_html_task,
    screenshot_task,
    cdp_command_task,
    batch_operations_task,
    get_session_data_task,
    get_session_status_task,
    list_sessions_task,
    health_check_task
)

# Import Google Sheets DB for direct data access
from google_sheets_db import get_db, GoogleSheetsDB

logger = logging.getLogger(__name__)


class ChromeAPI:
    """
    Control Plane - HTTP API for Chrome Automation
    All browser operations are delegated to Celery workers
    Data retrieval uses Google Sheets DB directly
    """

    def __init__(self):
        self.app = web.Application()
        self.setup_routes()
        self.session_cache = {}
        
        # Initialize Google Sheets DB for data retrieval
        try:
            self.db = get_db(interactive=False)
            logger.info("✅ Google Sheets DB initialized for data retrieval")
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize Google Sheets DB: {e}")
            self.db = None

    def setup_routes(self):
        """Setup all API routes - Control Plane only"""

        # Session Management
        self.app.router.add_post('/api/session/{name}/start', self.start_session)
        self.app.router.add_post('/api/session/{name}/stop', self.stop_session)
        self.app.router.add_post('/api/session/{name}/restart', self.restart_session)
        self.app.router.add_get('/api/session/{name}/status', self.get_status)
        self.app.router.add_get('/api/sessions', self.list_sessions)

        # Browser Actions (all async via Celery)
        self.app.router.add_post('/api/session/{name}/navigate', self.navigate)
        self.app.router.add_post('/api/session/{name}/click', self.click)
        self.app.router.add_post('/api/session/{name}/evaluate', self.evaluate)
        self.app.router.add_post('/api/session/{name}/execute', self.execute_js)
        self.app.router.add_get('/api/session/{name}/screenshot', self.screenshot)
        self.app.router.add_post('/api/session/{name}/cdp', self.cdp_command)

        # Data Extraction
        self.app.router.add_post('/api/session/{name}/extract', self.extract_data)
        self.app.router.add_post('/api/session/{name}/extract/multiple', self.extract_multiple)
        self.app.router.add_post('/api/session/{name}/save/html', self.save_html)

        # Data Retrieval - DIRECT DB ACCESS (not via Celery)
        self.app.router.add_get('/api/session/{name}/data', self.get_session_data_direct)
        self.app.router.add_get('/api/session/{name}/data/{key}', self.get_extracted_data_direct)
        self.app.router.add_get('/api/session/{name}/url', self.get_url)
        self.app.router.add_get('/api/session/{name}/html', self.get_html)

        # Batch Operations
        self.app.router.add_post('/api/session/{name}/batch', self.batch_operations)

        # Task Management
        self.app.router.add_get('/api/task/{task_id}/status', self.get_task_status)
        self.app.router.add_get('/api/task/{task_id}/result', self.get_task_result)

        # System
        self.app.router.add_get('/api/health', self.health_check)
        self.app.router.add_get('/api/info', self.get_info)

    # ========================================================================
    # Session Management - Control Plane
    # ========================================================================

    async def start_session(self, request):
        """Start a Chrome session - delegates to Celery"""
        try:
            data = await request.json()
        except:
            data = {}

        name = data.get('name', 'unstop')
        url = data.get('url', 'https://unstop.com/')
        wait = data.get('wait', True)
        timeout = data.get('timeout', 60)

        # Submit to Celery
        task = start_chrome_session_task.delay(name, url)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'url': url,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        # Wait for result if requested
        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def stop_session(self, request):
        """Stop a Chrome session - delegates to Celery"""
        name = request.match_info['name']
        wait = request.query.get('wait', 'true').lower() == 'true'
        timeout = int(request.query.get('timeout', 30))

        task = stop_chrome_session_task.delay(name)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def restart_session(self, request):
        """Restart a Chrome session - delegates to Celery"""
        name = request.match_info['name']
        wait = request.query.get('wait', 'true').lower() == 'true'
        timeout = int(request.query.get('timeout', 60))

        task = restart_chrome_session_task.delay(name)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def get_status(self, request):
        """Get session status - delegates to Celery"""
        name = request.match_info['name']

        task = get_session_status_task.delay(name)

        try:
            result = task.get(timeout=10)
            return web.json_response(result)
        except TimeoutError:
            return web.json_response({
                'success': False,
                'error': 'Timeout getting session status',
                'session_name': name
            }, status=408)
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e),
                'session_name': name
            }, status=500)

    async def list_sessions(self, request):
        """List all sessions - delegates to Celery"""
        task = list_sessions_task.delay()

        try:
            result = task.get(timeout=10)
            return web.json_response(result)
        except TimeoutError:
            return web.json_response({
                'success': False,
                'error': 'Timeout listing sessions'
            }, status=408)
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    # ========================================================================
    # Browser Actions - Control Plane
    # ========================================================================

    async def navigate(self, request):
        """Navigate to URL - delegates to Celery"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        url = data.get('url')
        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 30)
        extract_after = data.get('extract_after', True)

        if not url:
            return web.json_response({'error': 'URL required'}, status=400)

        task = navigate_task.delay(name, url, extract_after)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'url': url,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def click(self, request):
        """Click an element - delegates to Celery"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        selector = data.get('selector')
        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 30)

        if not selector:
            return web.json_response({'error': 'Selector required'}, status=400)

        task = click_task.delay(name, selector)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'selector': selector,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def evaluate(self, request):
        """Evaluate JavaScript - delegates to Celery"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        expression = data.get('expression')
        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 30)
        save_key = data.get('save_key', None)

        if not expression:
            return web.json_response({'error': 'Expression required'}, status=400)

        task = evaluate_task.delay(name, expression, save_key)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def execute_js(self, request):
        """Execute JavaScript with async support - delegates to Celery"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        script = data.get('script')
        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 60)
        save_key = data.get('save_key', None)

        if not script:
            return web.json_response({'error': 'Script required'}, status=400)

        task = execute_js_task.delay(name, script, save_key)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def screenshot(self, request):
        """Take screenshot - delegates to Celery"""
        name = request.match_info['name']
        wait = request.query.get('wait', 'true').lower() == 'true'
        timeout = int(request.query.get('timeout', 30))
        save = request.query.get('save', 'true').lower() == 'true'

        task = screenshot_task.delay(name, save)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def cdp_command(self, request):
        """Execute CDP command - delegates to Celery"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        method = data.get('method')
        params = data.get('params', {})
        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 30)

        if not method:
            return web.json_response({'error': 'Method required'}, status=400)

        task = cdp_command_task.delay(name, method, params)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'method': method,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    # ========================================================================
    # Data Extraction - Control Plane
    # ========================================================================

    async def extract_data(self, request):
        """Extract data using selector - delegates to Celery"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        selector = data.get('selector')
        attribute = data.get('attribute', None)
        key = data.get('key', f'extracted_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 30)

        if not selector:
            return web.json_response({'error': 'Selector required'}, status=400)

        task = extract_data_task.delay(name, selector, attribute, key)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'selector': selector,
            'key': key,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def extract_multiple(self, request):
        """Extract multiple selectors - delegates to Celery"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        selectors = data.get('selectors', {})
        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 30)
        save_key = data.get('save_key', f'multiple_extract_{datetime.now().strftime("%Y%m%d_%H%M%S")}')

        if not selectors:
            return web.json_response({'error': 'Selectors required'}, status=400)

        task = extract_multiple_task.delay(name, selectors, save_key)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'selectors': list(selectors.keys()),
            'key': save_key,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    async def save_html(self, request):
        """Save HTML content - delegates to Celery"""
        try:
            data = await request.json()
        except:
            data = {}

        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 30)
        extract_title = data.get('extract_title', True)
        save_key = data.get('save_key', None)

        task = save_html_task.delay(name, extract_title, save_key)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    # ========================================================================
    # Data Retrieval - DIRECT DATABASE ACCESS (Option 3)
    # These endpoints use Google Sheets DB directly instead of Celery
    # ========================================================================

    async def get_session_data_direct(self, request):
        """
        Get all stored data for a session - DIRECT DB ACCESS
        Uses Google Sheets DB instead of Celery for faster response
        """
        name = request.match_info['name']
        
        try:
            if not self.db:
                # Fallback to Celery if DB not available
                logger.warning("Google Sheets DB not available, falling back to Celery")
                task = get_session_data_task.delay(name)
                result = task.get(timeout=10)
                return web.json_response(result)
            
            # Get data directly from Google Sheets
            session_data = self.db.get_session_data(name)
            
            # Format the response
            response = {
                'success': True,
                'session_name': name,
                'data': session_data,
                'source': 'google_sheets_db',
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"✅ Retrieved session data for {name} from Google Sheets")
            return web.json_response(response)
            
        except Exception as e:
            logger.error(f"Error getting session data from DB: {e}")
            
            # Fallback to Celery if DB fails
            try:
                logger.info("Falling back to Celery for session data")
                task = get_session_data_task.delay(name)
                result = task.get(timeout=10)
                return web.json_response(result)
            except Exception as celery_error:
                return web.json_response({
                    'success': False,
                    'error': f'DB error: {str(e)}, Celery fallback error: {str(celery_error)}',
                    'session_name': name
                }, status=500)

    async def get_extracted_data_direct(self, request):
        """
        Get specific extracted data by key - DIRECT DB ACCESS
        Uses Google Sheets DB instead of Celery for faster response
        """
        name = request.match_info['name']
        key = request.match_info['key']
        
        try:
            if not self.db:
                # Fallback to Celery if DB not available
                logger.warning("Google Sheets DB not available, falling back to Celery")
                task = get_session_data_task.delay(name)
                result = task.get(timeout=10)
                extracted = result.get('data', {}).get('extracted', [])
                for item in extracted:
                    if item.get('data_key') == key:
                        return web.json_response({
                            'success': True,
                            'key': key,
                            'data': {
                                'value': item.get('data_value'),
                                'type': item.get('data_type'),
                                'captured_at': item.get('captured_at')
                            }
                        })
                return web.json_response({
                    'success': False,
                    'key': key,
                    'message': 'No data found for this key'
                })
            
            # Get data directly from Google Sheets
            extracted_data = self.db.get_extracted_data_by_key(name, key)
            
            if extracted_data:
                return web.json_response({
                    'success': True,
                    'key': key,
                    'data': extracted_data,
                    'source': 'google_sheets_db',
                    'timestamp': datetime.now().isoformat()
                })
            else:
                return web.json_response({
                    'success': False,
                    'key': key,
                    'message': 'No data found for this key',
                    'session_name': name
                })
                
        except Exception as e:
            logger.error(f"Error getting extracted data from DB: {e}")
            
            # Fallback to Celery if DB fails
            try:
                logger.info("Falling back to Celery for extracted data")
                task = get_session_data_task.delay(name)
                result = task.get(timeout=10)
                extracted = result.get('data', {}).get('extracted', [])
                for item in extracted:
                    if item.get('data_key') == key:
                        return web.json_response({
                            'success': True,
                            'key': key,
                            'data': {
                                'value': item.get('data_value'),
                                'type': item.get('data_type'),
                                'captured_at': item.get('captured_at')
                            }
                        })
                return web.json_response({
                    'success': False,
                    'key': key,
                    'message': 'No data found for this key'
                })
            except Exception as celery_error:
                return web.json_response({
                    'success': False,
                    'error': f'DB error: {str(e)}, Celery fallback error: {str(celery_error)}'
                }, status=500)

    async def get_url(self, request):
        """Get current URL - delegates to Celery"""
        name = request.match_info['name']

        # Use evaluate task to get URL
        task = evaluate_task.delay(name, 'window.location.href', None)

        try:
            result = task.get(timeout=10)
            if result.get('success'):
                return web.json_response({
                    'success': True,
                    'url': result.get('result', {}).get('result')
                })
            return web.json_response(result)
        except TimeoutError:
            return web.json_response({
                'success': False,
                'error': 'Timeout getting URL'
            }, status=408)
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    async def get_html(self, request):
        """Get page HTML - delegates to Celery"""
        name = request.match_info['name']
        save = request.query.get('save', 'false').lower() == 'true'

        # Use evaluate task to get HTML
        script = 'document.documentElement.outerHTML'
        task = evaluate_task.delay(name, script, 'page_html' if save else None)

        try:
            result = task.get(timeout=10)
            if result.get('success'):
                html = result.get('result', {}).get('result', '')
                return web.json_response({
                    'success': True,
                    'html': html,
                    'size': len(html)
                })
            return web.json_response(result)
        except TimeoutError:
            return web.json_response({
                'success': False,
                'error': 'Timeout getting HTML'
            }, status=408)
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    # ========================================================================
    # Batch Operations - Control Plane
    # ========================================================================

    async def batch_operations(self, request):
        """Execute multiple operations - delegates to Celery"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        operations = data.get('operations', [])
        name = request.match_info['name']
        wait = data.get('wait', True)
        timeout = data.get('timeout', 120)
        stop_on_error = data.get('stop_on_error', True)

        if not operations:
            return web.json_response({'error': 'Operations required'}, status=400)

        task = batch_operations_task.delay(name, operations, stop_on_error)

        response = {
            'success': True,
            'task_id': task.id,
            'session_name': name,
            'operations_count': len(operations),
            'status': 'submitted',
            'timestamp': datetime.now().isoformat()
        }

        if wait:
            try:
                result = task.get(timeout=timeout)
                response['result'] = result
                response['status'] = 'completed'
            except TimeoutError:
                response['status'] = 'timeout'
                response['error'] = f'Task timed out after {timeout}s'
            except Exception as e:
                response['status'] = 'error'
                response['error'] = str(e)

        return web.json_response(response)

    # ========================================================================
    # Task Management - Control Plane
    # ========================================================================

    async def get_task_status(self, request):
        """Get Celery task status"""
        task_id = request.match_info['task_id']
        task = AsyncResult(task_id, app=celery_app)

        response = {
            'task_id': task_id,
            'state': task.state,
            'ready': task.ready(),
            'successful': task.successful() if task.ready() else None,
            'timestamp': datetime.now().isoformat()
        }

        if task.ready():
            if task.successful():
                try:
                    response['result'] = task.get(propagate=False)
                except Exception as e:
                    response['error'] = str(e)
            else:
                response['error'] = str(task.info) if task.info else 'Task failed'

        return web.json_response(response)

    async def get_task_result(self, request):
        """Get Celery task result (wait if needed)"""
        task_id = request.match_info['task_id']
        timeout = int(request.query.get('timeout', 60))

        task = AsyncResult(task_id, app=celery_app)

        try:
            result = task.get(timeout=timeout)
            return web.json_response({
                'success': True,
                'task_id': task_id,
                'result': result,
                'state': task.state,
                'timestamp': datetime.now().isoformat()
            })
        except TimeoutError:
            return web.json_response({
                'success': False,
                'task_id': task_id,
                'error': f'Timeout waiting for result after {timeout}s',
                'state': task.state
            }, status=408)
        except Exception as e:
            return web.json_response({
                'success': False,
                'task_id': task_id,
                'error': str(e),
                'state': task.state
            }, status=500)

    # ========================================================================
    # System - Control Plane
    # ========================================================================

    async def health_check(self, request):
        """Health check endpoint"""
        health_status = {
            'status': 'ok',
            'service': 'chrome-control-plane',
            'timestamp': datetime.now().isoformat(),
            'celery': {
                'status': 'connected' if celery_app.control.ping(timeout=2) else 'unreachable'
            }
        }
        
        # Check Google Sheets DB status
        if self.db:
            health_status['database'] = {
                'status': 'connected',
                'type': 'google_sheets',
                'sheet_id': self.db.sheet_id
            }
        else:
            health_status['database'] = {
                'status': 'unavailable',
                'type': 'google_sheets'
            }
        
        return web.json_response(health_status)

    async def get_info(self, request):
        """Get API info"""
        info = {
            'service': 'Chrome Control Plane API',
            'version': '2.0',
            'architecture': 'Control Plane - Task Submission with Direct DB Access',
            'endpoints': [
                '/api/session/{name}/start',
                '/api/session/{name}/stop',
                '/api/session/{name}/restart',
                '/api/session/{name}/status',
                '/api/sessions',
                '/api/session/{name}/navigate',
                '/api/session/{name}/click',
                '/api/session/{name}/evaluate',
                '/api/session/{name}/execute',
                '/api/session/{name}/screenshot',
                '/api/session/{name}/extract',
                '/api/session/{name}/extract/multiple',
                '/api/session/{name}/batch',
                '/api/session/{name}/data',  # Direct DB access
                '/api/session/{name}/data/{key}',  # Direct DB access
                '/api/task/{task_id}/status',
                '/api/task/{task_id}/result',
                '/api/health',
                '/api/info'
            ],
            'celery_workers': celery_app.control.ping(timeout=2) if celery_app else [],
            'database': {
                'type': 'google_sheets',
                'status': 'connected' if self.db else 'unavailable',
                'sheet_id': self.db.sheet_id if self.db else None
            }
        }
        
        return web.json_response(info)

    def run(self, host="127.0.0.1", port=5000):
        """Run the API server"""
        print("=" * 60)
        print("🚀 Chrome Control Plane API v2.0")
        print("=" * 60)
        print(f"📡 Listening on: http://{host}:{port}")
        print(f"📋 Architecture: Control Plane (Task Submission + Direct DB Access)")
        print(f"⚙️  Browser operations delegated to Celery workers")
        print(f"📊 Data retrieval uses Google Sheets DB directly")
        print("=" * 60)

        web.run_app(self.app, host=host, port=port)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    api = ChromeAPI()
    api.run()
