"""Shared utilities for the Confluence RAG integration system."""

import hashlib
import os
import re
import secrets
from pathlib import Path
from typing import Optional

import yaml
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


def sanitize_customer_id(customer_id: str) -> str:
    """
    Sanitize customer ID to ensure it's safe for filesystem and database use.

    Args:
        customer_id: Raw customer identifier

    Returns:
        Sanitized customer ID containing only lowercase letters, numbers, underscores, and hyphens

    Raises:
        ValueError: If customer_id is empty or invalid after sanitization
    """
    if not customer_id:
        raise ValueError("Customer ID cannot be empty")

    # Convert to lowercase and replace invalid characters
    sanitized = re.sub(r"[^a-z0-9_-]", "_", customer_id.lower().strip())

    # Remove multiple consecutive underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    if not sanitized:
        raise ValueError("Customer ID invalid after sanitization")

    # Ensure it starts with a letter or number
    if not re.match(r"^[a-z0-9]", sanitized):
        sanitized = f"customer_{sanitized}"

    return sanitized


def ensure_customer_directory(customer_id: str, base_path: Optional[Path] = None) -> Path:
    """
    Ensure customer directory structure exists and return the customer's base path.

    Args:
        customer_id: Customer identifier
        base_path: Base directory for all customer data (defaults to ./data/customers)

    Returns:
        Path to customer's base directory

    Creates:
        - customer_id/
        - customer_id/exports/
        - customer_id/vector_store/
        - customer_id/cache/
        - customer_id/logs/
    """
    if base_path is None:
        base_path = Path("./data/customers")

    customer_id = sanitize_customer_id(customer_id)
    customer_path = base_path / customer_id

    # Create directory structure
    directories = [
        customer_path,
        customer_path / "exports",
        customer_path / "vector_store",
        customer_path / "cache",
        customer_path / "logs",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    return customer_path


def get_encryption_key(password: Optional[str] = None) -> bytes:
    """
    Generate or derive an encryption key for credential storage.

    Args:
        password: Optional password for key derivation. If not provided, uses environment variable
                 CONFLUENCE_RAG_ENCRYPTION_KEY or generates a random key.

    Returns:
        32-byte encryption key

    Note:
        In production, you should use a secure key management system.
    """
    if password:
        # Derive key from password
        salt = b"confluence_rag_salt"  # In production, use random salt and store it
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    # Try to get key from environment
    env_key = os.getenv("CONFLUENCE_RAG_ENCRYPTION_KEY")
    if env_key:
        return base64.urlsafe_b64decode(env_key.encode())

    # Generate random key (not recommended for production)
    return Fernet.generate_key()


def encrypt_credentials(data: str, password: Optional[str] = None) -> str:
    """
    Encrypt sensitive data like API tokens.

    Args:
        data: Sensitive data to encrypt
        password: Optional password for encryption

    Returns:
        Base64-encoded encrypted data
    """
    key = get_encryption_key(password)
    fernet = Fernet(key)
    encrypted_data = fernet.encrypt(data.encode())
    return base64.urlsafe_b64encode(encrypted_data).decode()


def decrypt_credentials(encrypted_data: str, password: Optional[str] = None) -> str:
    """
    Decrypt sensitive data like API tokens.

    Args:
        encrypted_data: Base64-encoded encrypted data
        password: Optional password for decryption

    Returns:
        Decrypted data

    Raises:
        cryptography.fernet.InvalidToken: If decryption fails
    """
    key = get_encryption_key(password)
    fernet = Fernet(key)
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
    decrypted_data = fernet.decrypt(encrypted_bytes)
    return decrypted_data.decode()


def generate_content_hash(content: str) -> str:
    """
    Generate a hash of content for change detection.

    Args:
        content: Text content to hash

    Returns:
        SHA-256 hash of the content
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def safe_filename(filename: str, max_length: int = 255) -> str:
    """
    Convert a string to a safe filename by removing/replacing invalid characters.

    Args:
        filename: Original filename
        max_length: Maximum length for the filename

    Returns:
        Safe filename string
    """
    # Replace invalid characters
    safe_chars = re.sub(r'[<>:"/\\|?*]', "_", filename)

    # Remove control characters
    safe_chars = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", safe_chars)

    # Limit length
    if len(safe_chars) > max_length:
        name, ext = os.path.splitext(safe_chars)
        available_length = max_length - len(ext)
        safe_chars = name[:available_length] + ext

    return safe_chars.strip()


def get_customer_config_path(customer_id: str, base_path: Optional[Path] = None) -> Path:
    """
    Get the path to a customer's configuration file.

    Args:
        customer_id: Customer identifier
        base_path: Base directory for customer data

    Returns:
        Path to customer's config.yaml file
    """
    customer_path = ensure_customer_directory(customer_id, base_path)
    return customer_path / "config.yaml"


def validate_url(url: str) -> bool:
    """
    Validate if a URL is properly formatted.

    Args:
        url: URL string to validate

    Returns:
        True if URL is valid, False otherwise
    """
    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    return url_pattern.match(url) is not None


def ensure_trailing_slash(url: str) -> str:
    """
    Ensure URL ends with a trailing slash.

    Args:
        url: URL string

    Returns:
        URL with trailing slash
    """
    return url.rstrip("/") + "/"


def create_customer_id_from_url(confluence_url: str) -> str:
    """
    Generate a customer ID from a Confluence URL.

    Args:
        confluence_url: Confluence instance URL

    Returns:
        Sanitized customer ID based on the URL

    Example:
        https://mycompany.atlassian.net/ -> mycompany
        https://confluence.example.com/ -> confluence_example_com
    """
    from urllib.parse import urlparse

    parsed = urlparse(confluence_url)
    hostname = parsed.hostname or ""

    # Extract meaningful parts
    if ".atlassian.net" in hostname:
        # Extract tenant name from Atlassian cloud
        tenant = hostname.split(".atlassian.net")[0]
        return sanitize_customer_id(tenant)
    else:
        # Use full hostname, sanitized
        return sanitize_customer_id(hostname.replace(".", "_"))


def get_environment_variable(
    key: str, default: Optional[str] = None, required: bool = False
) -> Optional[str]:
    """
    Get environment variable with validation.

    Args:
        key: Environment variable name
        default: Default value if not found
        required: Whether the variable is required

    Returns:
        Environment variable value or default

    Raises:
        ValueError: If required variable is not found
    """
    value = os.getenv(key, default)

    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' not found")

    return value

import re

def extract_metadata_from_content(content: str) -> dict:
    """
    Parses the full text of a markdown file to extract metadata from YAML front matter,
    breadcrumbs, title, and article information blocks. Processes content only after 
    the main title (# ...) and removes metadata blocks.

    Args:
        content: The raw string content of a .md file.

    Returns:
        A dictionary containing 'title', 'breadcrumb', 'url', 'tags', 'properties', 
        and 'processed_content'.
    """
    lines = content.split("\n")

    # Default values
    metadata = {
        "title": "Untitled", 
        "breadcrumb": "Uncategorized", 
        "url": None, 
        "tags": [],
        "properties": {},  # Generic properties dictionary for any key-value pairs
        "processed_content": ""
    }

    # Track where content processing should start
    content_start_index = 0
    title_found = False

    # Find the first non-empty line that might be the start of YAML front matter
    yaml_start = -1
    for i, line in enumerate(lines):
        if line.strip() == "---":
            yaml_start = i
            break
    
    # Check for YAML front matter
    if yaml_start >= 0:
        # Find the closing --- for front matter
        end_index = -1
        for i, line in enumerate(lines[yaml_start + 1:], yaml_start + 1):
            if line.strip() == "---":
                end_index = i
                break

        if end_index > yaml_start:
            # Extract content between --- markers
            for line in lines[yaml_start + 1:end_index]:
                line_stripped = line.strip()
                
                # Look for url: pattern
                if line_stripped.startswith("url:"):
                    # Extract URL after "url:"
                    url = line_stripped[4:].strip()
                    metadata["url"] = url
                # Look for tags: pattern (if present)
                elif line_stripped.startswith("tags:"):
                    # Simple extraction for tags on same line
                    tags_str = line_stripped[5:].strip()
                    if tags_str:
                        metadata["tags"] = [tag.strip() for tag in tags_str.split(",")]

    # Find Title and mark where content should start
    for i, line in enumerate(lines):
        if line.startswith("# "):
            metadata["title"] = line.strip("# ").strip()
            content_start_index = i
            title_found = True
            break

    # Find Breadcrumb (usually the first line with '>' before the title)
    if title_found:
        # Only look for breadcrumb before the title
        for line in lines[:content_start_index]:
            if ">" in line and "[" in line and "]" in line:
                # Extracts text from within markdown links like [Text](link)
                parts = re.findall(r"\[(.*?)\]", line)
                if parts:
                    metadata["breadcrumb"] = " > ".join(parts)
                    break

    # Process content starting from the title line
    if title_found:
        processed_lines = []
        i = content_start_index
        
        while i < len(lines):
            line = lines[i]
            
            # Check if this is the start of an IMPORTANT block
            # The pattern in your example is: > [!IMPORTANT]
            if "> [!IMPORTANT]" in line:
                # Skip this line and start extracting properties
                j = i + 1
                block_properties = {}
                
                # Process lines in this block (they all start with >)
                while j < len(lines):
                    current_line = lines[j]
                    
                    # If line doesn't start with >, we're done with the block
                    if not current_line.startswith(">"):
                        break
                    
                    # Remove the leading > and spaces
                    cleaned_line = current_line[1:].strip()
                    
                    # Skip lines that are just formatting (like **Article Information:**)
                    if cleaned_line.startswith("**") and cleaned_line.endswith("**"):
                        j += 1
                        continue
                    
                    # Skip empty quoted lines
                    if not cleaned_line:
                        j += 1
                        continue
                    
                    # Remove leading dash and spaces if present (for list items)
                    if cleaned_line.startswith("- "):
                        cleaned_line = cleaned_line[2:].strip()
                    
                    # Look for key-value pairs separated by ":"
                    if ":" in cleaned_line:
                        # Handle lines that might have markdown links
                        if "[" in cleaned_line and "](" in cleaned_line:
                            # Extract the key and the URL from markdown link
                            key_part = cleaned_line.split(":")[0].strip()
                            # Extract URL from markdown link
                            url_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', cleaned_line)
                            if url_match:
                                value_part = url_match.group(2)  # Get the URL part
                            else:
                                value_part = cleaned_line.split(":", 1)[1].strip()
                        else:
                            # Simple key:value split
                            parts = cleaned_line.split(":", 1)
                            if len(parts) == 2:
                                key_part = parts[0].strip()
                                value_part = parts[1].strip()
                            else:
                                j += 1
                                continue
                        
                        # Clean up the key (convert to snake_case)
                        key = key_part.lower().replace(" ", "_").replace("-", "_")
                        
                        # Store in block_properties
                        block_properties[key] = value_part
                    
                    j += 1
                
                # Add properties to metadata
                
                metadata["properties"].update(block_properties)
                
                # Skip this entire block in the processed content
                i = j
                continue
            
            # Add non-metadata lines to processed content
            processed_lines.append(line)
            i += 1
        
        # Join the processed lines
        metadata["processed_content"] = "\n".join(processed_lines)
        
        # Clean up any remaining empty lines at the start
        while metadata["processed_content"].startswith("\n"):
            metadata["processed_content"] = metadata["processed_content"][1:]
    else:
        # If no title found, return the entire content
        metadata["processed_content"] = content

    return metadata

def has_meaningful_content(text: str, min_length: int = 50, content_density_threshold: float = 0.3) -> bool:
    """
    Check if a chunk has meaningful content beyond just headers and formatting.
    
    Args:
        text: The text to validate
        min_length: Minimum length of meaningful content required
        content_density_threshold: Minimum ratio of content to total text

    Returns:
        True if the text contains meaningful content, False otherwise
    """
    # Remove markdown headers
    cleaned = re.sub(r'^#+\s+.*$', '', text, flags=re.MULTILINE)

    # Remove horizontal rules
    cleaned = re.sub(r'^---+\s*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^\*\*\*+\s*$', '', cleaned, flags=re.MULTILINE)

    # Remove context brackets like [Path > To > Content]
    cleaned = re.sub(r'^\[.*?\]\s*$', '', cleaned, flags=re.MULTILINE)

    # Remove excessive whitespace
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    cleaned = cleaned.strip()

    # Check if we have enough content
    if len(cleaned) < min_length:
        return False

    # Calculate content density (ratio of actual content to original)
    if len(text.strip()) > 0:
        density = len(cleaned) / len(text.strip())
        if density < content_density_threshold:
            return False

    return True

