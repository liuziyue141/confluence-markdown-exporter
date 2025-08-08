#!/usr/bin/env python3
"""Simple customer creation script for Confluence RAG integration."""

import os
import sys
from pathlib import Path
from typing import Optional
import yaml
from getpass import getpass

from confluence_rag_integration.customers.customer_manager import CustomerManager
from dotenv import load_dotenv
load_dotenv()


def get_required_input(prompt: str, env_var: Optional[str] = None) -> str:
    """Get required input from user or environment variable."""
    if env_var and os.getenv(env_var):
        value = os.getenv(env_var)
        print(f"{prompt} [Using {env_var}]")
        return value
    
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("This field is required. Please try again.")


def get_optional_input(prompt: str, default: str = None) -> str:
    """Get optional input with default value."""
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    
    value = input(prompt).strip()
    return value if value else default


def create_customer_interactive():
    """Interactive customer creation with minimal required inputs."""
    print("\n🚀 Simple Customer Creation for Confluence RAG Integration")
    print("=" * 60)
    print("This will create a new customer configuration.\n")
    
    # Required fields
    print("📋 Required Information:")
    customer_id = get_required_input("Customer ID (e.g., acme_corp): ")
    customer_name = get_required_input("Customer Name (e.g., ACME Corporation): ")
    confluence_url = get_required_input("Confluence URL (e.g., https://acme.atlassian.net/): ")
    
    # Credentials
    print("\n🔐 Confluence Credentials:")
    confluence_username = get_required_input("Confluence Username/Email: ", "CONFLUENCE_USERNAME")
    
    if os.getenv("CONFLUENCE_TOKEN"):
        print("Confluence API Token: [Using CONFLUENCE_TOKEN environment variable]")
        confluence_api_token = "${CONFLUENCE_TOKEN}"
    else:
        confluence_api_token = getpass("Confluence API Token: ")
    
    # Space keys
    print("\n📂 Confluence Spaces to Export:")
    print("Enter space keys one per line (press Enter twice when done):")
    space_keys = []
    while True:
        space_key = input("Space key: ").strip().upper()
        if not space_key:
            if space_keys:
                break
            print("At least one space key is required.")
            continue
        space_keys.append(space_key)
        print(f"  Added: {space_key}")
    
    # Optional RAG settings with sensible defaults
    print("\n⚙️  Optional RAG Settings (press Enter for defaults):")
    embedding_model = get_optional_input("Embedding model", "gemini-embedding-001")
    chunk_size = get_optional_input("Chunk size", "1000")
    chunk_size = int(chunk_size) if chunk_size else 1000
    
    # Database connection
    if os.getenv("DB_CONNECTION"):
        print("Database connection: [Using DB_CONNECTION environment variable]")
        db_connection = "${DB_CONNECTION}"
    else:
        db_connection = get_optional_input(
            "Database connection string",
            "postgresql+psycopg://user:pass@localhost:5432/vectordb"
        )
    
    indexer_type = get_optional_input("Indexer type (simple/parent_document)", "simple")
    
    # Build configuration
    config = {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "confluence_url": confluence_url.rstrip('/') + '/',
        "confluence_username": confluence_username,
        "confluence_api_token": confluence_api_token,
        "space_keys": space_keys,
        "embedding_model": embedding_model,
        "chunk_size": chunk_size,
        "db_connection": db_connection,
        "indexer_type": indexer_type
    }
    
    # Show configuration
    print("\n📄 Configuration Summary:")
    print("-" * 40)
    for key, value in config.items():
        if key == "confluence_api_token" and not value.startswith("${"):
            print(f"  {key}: ***hidden***")
        elif key == "space_keys":
            print(f"  {key}: {', '.join(value)}")
        else:
            print(f"  {key}: {value}")
    
    # Confirm creation
    confirm = input("\n✅ Create this customer? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("❌ Customer creation cancelled.")
        return None
    
    # Save to temporary file in data/temp_config (gitignored for security)
    temp_dir = Path("data/temp_config")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_config_file = temp_dir / f"temp_config_{customer_id}.yaml"
    try:
        with open(temp_config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        manager = CustomerManager()
        customer_config = manager.create_customer(temp_config_file)
        
        print(f"\n✅ Successfully created customer: {customer_config.customer_id}")
        print(f"📁 Customer data directory: data/customers/{customer_config.customer_id}/")
        
        # Cleanup temp file (keep directory for future use)
        if temp_config_file.exists():
            temp_config_file.unlink()
        
        # Show next steps
        print("\n📌 Next Steps:")
        print(f"1. Export and Index spaces: python export_index_pipeline.py {customer_id}")
        
        return customer_config
        
    except Exception as e:
        print(f"\n❌ Error creating customer: {str(e)}")
        if temp_config_file.exists():
            temp_config_file.unlink()
        return None


def create_customer_from_template(template_file: str = None):
    """Create customer from a template config file."""
    if not template_file:
        template_file = "customer_config_template.yaml"
    
    template_path = Path(template_file)
    if not template_path.exists():
        print(f"❌ Template file not found: {template_file}")
        print("\n💡 Creating a template file for you...")
        
        template_config = {
            "customer_id": "your_customer_id",
            "customer_name": "Your Customer Name",
            "confluence_url": "https://your-instance.atlassian.net/",
            "confluence_username": "your-email@example.com",
            "confluence_api_token": "${CONFLUENCE_TOKEN}",
            "space_keys": ["SPACE1", "SPACE2"],
            "embedding_model": "gemini-embedding-001",
            "chunk_size": 1000,
            "db_connection": "${DB_CONNECTION}",
            "indexer_type": "simple"
        }
        
        with open(template_path, 'w') as f:
            yaml.dump(template_config, f, default_flow_style=False, sort_keys=False)
        
        print(f"✅ Created template file: {template_file}")
        print(f"📝 Edit this file with your customer's details, then run:")
        print(f"   python create_customer.py --template {template_file}")
        return None
    
    try:
        manager = CustomerManager()
        customer_config = manager.create_customer(template_path)
        print(f"✅ Successfully created customer: {customer_config.customer_id}")
        print(f"📁 Customer data directory: data/customers/{customer_config.customer_id}/")
        return customer_config
    except Exception as e:
        print(f"❌ Error creating customer: {str(e)}")
        return None


def main():
    """Main entry point for customer creation."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Simple customer creation for Confluence RAG integration"
    )
    parser.add_argument(
        "--template", "-t",
        help="Create customer from template config file",
        default=None
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Quick mode: use environment variables for credentials"
    )
    
    args = parser.parse_args()
    
    if args.template:
        create_customer_from_template(args.template)
    else:
        if args.quick:
            # Check for required environment variables
            required_env = ["CONFLUENCE_TOKEN", "DB_CONNECTION"]
            missing = [var for var in required_env if not os.getenv(var)]
            if missing:
                print(f"❌ Quick mode requires environment variables: {', '.join(missing)}")
                print("\n💡 Set them with:")
                for var in missing:
                    print(f"   export {var}='your-value-here'")
                sys.exit(1)
        
        create_customer_interactive()


if __name__ == "__main__":
    main()