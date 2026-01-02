#!/usr/bin/env python3
"""
Kalshi v2 Authentication Helper
Provides utilities for loading and validating Kalshi API credentials
"""

import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


def load_private_key_pem(key_path):
    """
    Load RSA private key from PEM file using cryptography.hazmat
    This avoids MalformedFraming errors by properly parsing the PEM format.
    
    Args:
        key_path: Absolute or relative path to the .pem file
        
    Returns:
        cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey object
        
    Raises:
        FileNotFoundError: If the key file doesn't exist
        ValueError: If the key cannot be loaded or is malformed
    """
    # Convert to absolute path
    abs_key_path = os.path.abspath(key_path)
    
    if not os.path.exists(abs_key_path):
        raise FileNotFoundError(f"Private key file not found: {abs_key_path}")
    
    try:
        with open(abs_key_path, 'rb') as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,  # Kalshi keys are not password-protected
                backend=default_backend()
            )
        
        # Validate it's an RSA key
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise ValueError(f"Key at {abs_key_path} is not an RSA private key")
        
        return private_key
        
    except Exception as e:
        raise ValueError(f"Failed to load private key from {abs_key_path}: {str(e)}")


def validate_and_save_key_from_string(private_key_pem_string, output_path):
    """
    Validate a PEM string and save it to a file.
    This ensures the key is properly formatted before saving.
    
    Args:
        private_key_pem_string: The PEM key as a string
        output_path: Path where to save the validated key file
        
    Returns:
        str: Absolute path to the saved key file
        
    Raises:
        ValueError: If the key string is invalid
    """
    # Convert to absolute path
    abs_output_path = os.path.abspath(output_path)
    
    # Validate by trying to load it
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as tmp_file:
        tmp_file.write(private_key_pem_string)
        tmp_path = tmp_file.name
    
    try:
        # Validate the key can be loaded
        load_private_key_pem(tmp_path)
        
        # If valid, write to final location
        with open(abs_output_path, 'w') as output_file:
            output_file.write(private_key_pem_string)
            # Ensure file ends with newline
            if not private_key_pem_string.endswith('\n'):
                output_file.write('\n')
        
        # Set restrictive permissions (owner read/write only)
        os.chmod(abs_output_path, 0o600)
        
        return abs_output_path
        
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass


def get_key_path_from_env_or_default():
    """
    Get the key file path from environment variable or use default location.
    
    Returns:
        str: Absolute path to the key file
    """
    # Check for KEY_PATH in environment
    env_key_path = os.getenv('KALSHI_KEY_PATH')
    if env_key_path:
        return os.path.abspath(env_key_path)
    
    # Default to kalshi_private_key.pem in the same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_path = os.path.join(script_dir, 'kalshi_private_key.pem')
    return os.path.abspath(default_path)



