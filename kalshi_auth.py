#!/usr/bin/env python3
"""
Kalshi v2 Authentication Module
Handles authentication setup following Kalshi API v2 requirements:
- RSA-PSS with SHA256 signing
- timestamp + method + path (path stripped of query params AND /trade-api/v2 prefix)
- Proper PEM key loading using cryptography.hazmat
"""

import os
import time
import base64
from pathlib import Path
from dotenv import load_dotenv
from kalshi_python_sync import Configuration, KalshiClient
from kalshi_python_sync.auth import KalshiAuth as _KalshiAuthBase
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from kalshi_auth_helper import (
    load_private_key_pem,
    validate_and_save_key_from_string,
    get_key_path_from_env_or_default
)

# Load environment variables - explicitly load from .env in current directory
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)


class KalshiAuth(_KalshiAuthBase):
    """
    Fixed KalshiAuth that properly strips the /trade-api/v2 prefix from paths
    when calculating signatures. The API expects signatures on just /portfolio/...
    not /trade-api/v2/portfolio/...
    """
    
    def __init__(self, key_id: str, private_key_pem: str):
        """
        Initialize KalshiAuth with proper private key loading from PEM content.
        
        Args:
            key_id: The API key ID
            private_key_pem: The private key in PEM format (string content)
        """
        # Load the private key from PEM content
        from cryptography.hazmat.primitives import serialization
        self.private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8') if isinstance(private_key_pem, str) else private_key_pem,
            password=None,
            backend=default_backend()
        )
        self.key_id = key_id
    
    def create_auth_headers(self, method: str, url: str) -> dict:
        """Create Kalshi authentication headers for a request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL (can be full URL or just path)
        
        Returns:
            Dictionary of authentication headers to add to request
        """
        current_time_milliseconds = int(time.time() * 1000)
        timestamp_str = str(current_time_milliseconds)
        
        # Extract path from URL
        if url.startswith('http'):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path = parsed.path
        else:
            path = url.split('?')[0]
        
        # IMPORTANT: Keep /trade-api/v2 in the path when signing!
        # Per Kalshi SDK specification, the full path including /trade-api/v2 
        # must be included in the signature. Previously stripping this prefix 
        # was causing 401 Unauthorized errors on POST requests.
        
        # Create message to sign: timestamp + method + full path (with /trade-api/v2)
        msg_string = timestamp_str + method.upper() + path
        
        # Sign the message using RSA-PSS
        message = msg_string.encode('utf-8')
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature_b64,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
        }


def initialize_kalshi_client():
    """
    Initialize and return authenticated Kalshi client following v2 requirements.
    
    Authentication Process:
    1. Load API_KEY_ID from .env
    2. Load or create private key file (using cryptography.hazmat for validation)
    3. Initialize KalshiAuth with proper PEM file (absolute path)
    4. Return authenticated KalshiClient
    
    The SDK handles RSA-PSS with SHA256 signing internally.
    Signing message format: timestamp + method + path (path without query params)
    
    Returns:
        KalshiClient: Authenticated client instance
        
    Raises:
        ValueError: If credentials are missing or invalid
        FileNotFoundError: If key file cannot be found or created
    """
    # Get API Key ID from environment
    api_key_id = os.getenv('KALSHI_API_KEY_ID')
    if not api_key_id:
        raise ValueError(
            "KALSHI_API_KEY_ID not found in environment variables. "
            "Please set it in your .env file."
        )
    
    # Get key path from environment or use default
    key_path = get_key_path_from_env_or_default()
    
    # Check if key file exists, if not, try to create from PRIVATE_KEY env var
    if not os.path.exists(key_path):
        private_key_pem = os.getenv('KALSHI_PRIVATE_KEY')
        if private_key_pem:
            # Validate and save the key from environment variable
            try:
                key_path = validate_and_save_key_from_string(private_key_pem, key_path)
                print(f"✓ Created and validated private key file at: {key_path}")
            except ValueError as e:
                raise ValueError(
                    f"Failed to validate private key from KALSHI_PRIVATE_KEY: {str(e)}"
                )
        else:
            raise FileNotFoundError(
                f"Private key file not found at {key_path} and KALSHI_PRIVATE_KEY "
                "not set in environment. Please either:\n"
                "1. Set KALSHI_KEY_PATH to point to your .pem file, or\n"
                "2. Set KALSHI_PRIVATE_KEY with your PEM key content"
            )
    else:
        # Validate existing key file
        try:
            load_private_key_pem(key_path)
            print(f"✓ Loaded and validated private key from: {key_path}")
        except ValueError as e:
            raise ValueError(f"Invalid private key file at {key_path}: {str(e)}")
    
    # Ensure we're using absolute path
    abs_key_path = os.path.abspath(key_path)
    
    # Read the PEM file content as a string (KalshiAuth expects string, not file path)
    with open(abs_key_path, 'r') as key_file:
        private_key_pem_content = key_file.read()
    
    # Initialize Configuration and Client
    try:
        config = Configuration()
        client = KalshiClient(config)
        
        # Set up authentication using KalshiAuth
        # The SDK's KalshiAuth handles RSA-PSS with SHA256 signing internally
        # Signature format: timestamp + method + path (path stripped of query params)
        # Note: KalshiAuth expects PEM content as string, not file path
        client.kalshi_auth = KalshiAuth(api_key_id, private_key_pem_content)
        
        return client
        
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Kalshi client: {str(e)}")

