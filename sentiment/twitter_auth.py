"""
Twitter Authentication Module
Handles login and cookie management for Twikit
"""

import os
import time
import asyncio
import httpx
from random import randint
from twikit import Client
from twikit.errors import TooManyRequests, BadRequest
from termcolor import cprint
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Note: We no longer patch httpx globally since it breaks other libraries (OpenAI, etc.)
# Manual cookie import doesn't need this patch anyway

COOKIES_FILE = 'cookies.json'

def get_client():
    """Get an authenticated client using saved cookies"""
    import json
    
    client = Client('en-US')
    if os.path.exists(COOKIES_FILE):
        try:
            # Load our custom cookie format
            with open(COOKIES_FILE, 'r') as f:
                cookies_data = json.load(f)
            
            # Extract cookie values into a simple dict
            cookie_dict = {}
            for name, cookie_info in cookies_data.items():
                if isinstance(cookie_info, dict) and 'value' in cookie_info:
                    cookie_dict[name] = cookie_info['value']
                else:
                    cookie_dict[name] = cookie_info
            
            # Use twikit's set_cookies method
            client.set_cookies(cookie_dict)
            
            cprint(f"✅ Loaded {len(cookie_dict)} cookies", "green")
            return client
        except Exception as e:
            cprint(f"⚠️ Error loading cookies: {e}", "yellow")
            import traceback
            traceback.print_exc()
            return None
    return None

async def login():
    """Perform login using credentials from .env"""
    try:
        # Get credentials from env
        USERNAME = os.getenv('TWITTER_USERNAME')
        EMAIL = os.getenv('TWITTER_EMAIL')
        PASSWORD = os.getenv('TWITTER_PASSWORD')

        if not all([USERNAME, EMAIL, PASSWORD]):
            cprint("❌ Error: Missing Twitter credentials in .env file!", "red")
            cprint("📝 Please add TWITTER_USERNAME, TWITTER_EMAIL, and TWITTER_PASSWORD to .env", "yellow")
            return False

        # Initialize client
        client = Client('en-US')
        
        cprint("🔑 Attempting to log in to Twitter...", "cyan")

        # Login using credentials
        await client.login(
            auth_info_1=USERNAME,
            auth_info_2=EMAIL,
            password=PASSWORD
        )

        # Save cookies
        client.save_cookies(COOKIES_FILE)
        cprint("✅ Login successful! Cookies saved to cookies.json", "green")
        return True

    except BadRequest as e:
        cprint(f"❌ Login failed: {str(e)}", "red")
        cprint("💡 Check your credentials or try logging in manually first.", "yellow")
        return False
    except TooManyRequests as e:
        cprint(f"❌ Rate limited: {str(e)}", "red")
        return False
    except Exception as e:
        cprint(f"❌ Unexpected error: {str(e)}", "red")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(login())
