"""
HAR2API - Convert HAR files to API clients
"""

__version__ = "0.1.0"
__author__ = "Your Name"

from .core import HARParser, HARAnalyzer, APISpec
from .generators import ClientGenerator
from .capture import CDPCapturer
from .config import HAR2APIConfig


def generate_client(
    har_file: str,
    output: str = "api_client.py",
    class_name: str = "APIClient",
    language: str = "python"
) -> str:
    """
    Generate API client from HAR file
    
    Args:
        har_file: Path to HAR file
        output: Output file path
        class_name: Name of the API client class
        language: Output language (python or typescript)
    
    Returns:
        Path to generated file
    """
    from .core import HARParser
    from .generators import ClientGenerator
    
    parser = HARParser()
    spec = parser.parse_file(har_file)
    
    generator = ClientGenerator()
    
    if language == "python":
        code = generator.generate_python(spec, class_name)
    elif language == "typescript":
        code = generator.generate_typescript(spec, class_name)
    else:
        raise ValueError(f"Unsupported language: {language}")
    
    with open(output, 'w') as f:
        f.write(code)
    
    return output


def capture_har(
    port: int = 9222,
    duration: int = 30,
    output: Optional[str] = None
) -> str:
    """
    Capture HAR from Chrome
    
    Args:
        port: Chrome debugging port
        duration: Capture duration in seconds
        output: Output file path
    
    Returns:
        Path to captured HAR file
    """
    from .capture import CDPCapturer
    
    capturer = CDPCapturer(port=port)
    tabs = capturer.get_tabs()
    
    if not tabs:
        raise RuntimeError("No Chrome tabs found. Make sure Chrome is running with --remote-debugging-port")
    
    # Connect to first tab
    tab = tabs[0]
    ws_url = tab.get('webSocketDebuggerUrl')
    if not ws_url:
        raise RuntimeError("No WebSocket URL found for tab")
    
    capturer.connect_to_tab(tab.get('id'), ws_url)
    capturer.start_capture()
    
    import time
    time.sleep(duration)
    
    entries = capturer.stop_capture()
    har_data = capturer.export_har(output)
    
    return output or f"har_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.har"


__all__ = [
    'HARParser',
    'HARAnalyzer',
    'APISpec',
    'ClientGenerator',
    'CDPCapturer',
    'HAR2APIConfig',
    'generate_client',
    'capture_har',
    '__version__'
]
