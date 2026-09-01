"""
Configuration management for HAR2API
"""

import os
from typing import List, Optional
from dataclasses import dataclass, field
from enum import Enum


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class HARConfig:
    """HAR parsing and analysis configuration"""
    similarity_threshold: float = 0.85
    min_request_frequency: int = 3
    max_endpoints: int = 100
    validate_ssl: bool = True
    max_entry_size: int = 10 * 1024 * 1024  # 10MB


@dataclass
class AuthConfig:
    """Authentication detection configuration"""
    auth_entropy_threshold: float = 4.5
    min_auth_confidence: float = 0.7
    max_token_length: int = 1000
    detect_oauth2: bool = True
    detect_jwt: bool = True


@dataclass
class GeneratorConfig:
    """Code generation configuration"""
    output_languages: List[str] = field(default_factory=lambda: ["python"])
    include_comments: bool = True
    include_examples: bool = True
    max_methods_per_class: int = 50
    use_type_hints: bool = True
    generate_docstrings: bool = True


@dataclass
class CaptureConfig:
    """HAR capture configuration"""
    port: int = 9222
    duration: int = 30
    max_reconnect_attempts: int = 5
    reconnect_delay: int = 2
    websocket_timeout: float = 1.0
    progress_interval: int = 10
    max_entries_per_tab: int = 10000
    include_console_logs: bool = True
    include_dom_events: bool = False
    save_intermediate: bool = True
    intermediate_interval: int = 30
    skip_patterns: List[str] = field(default_factory=lambda: [
        'google-analytics', 'doubleclick', 'facebook', 'analytics',
        'gtag', 'googletag', 'clarity', 'hotjar'
    ])


@dataclass
class HAR2APIConfig:
    """Main configuration for HAR2API"""
    har: HARConfig = field(default_factory=HARConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    
    log_level: LogLevel = LogLevel.INFO
    output_dir: str = "output"
    verbose: bool = False
    
    def __post_init__(self):
        """Create output directory if it doesn't exist"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    @classmethod
    def from_env(cls) -> 'HAR2APIConfig':
        """Create configuration from environment variables"""
        config = cls()
        
        # HAR config
        config.har.similarity_threshold = float(
            os.getenv('HAR_SIMILARITY_THRESHOLD', '0.85')
        )
        config.har.min_request_frequency = int(
            os.getenv('HAR_MIN_FREQUENCY', '3')
        )
        
        # Auth config
        config.auth.auth_entropy_threshold = float(
            os.getenv('AUTH_ENTROPY_THRESHOLD', '4.5')
        )
        config.auth.min_auth_confidence = float(
            os.getenv('AUTH_MIN_CONFIDENCE', '0.7')
        )
        
        # Capture config
        config.capture.port = int(
            os.getenv('CDP_PORT', '9222')
        )
        config.capture.duration = int(
            os.getenv('CAPTURE_DURATION', '30')
        )
        
        # General config
        config.log_level = LogLevel(
            os.getenv('LOG_LEVEL', 'INFO')
        )
        config.output_dir = os.getenv('OUTPUT_DIR', 'output')
        config.verbose = os.getenv('VERBOSE', 'false').lower() == 'true'
        
        return config
