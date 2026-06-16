"""
youtube_auth.py — One-time YouTube authentication setup
Run this ONCE on your Mac to get your YouTube token.

Steps:
1. Download client_secrets.json from Google Cloud Console
2. Run: python youtube_auth.py
3. Browser opens → log in → Allow
4. Run: python youtube_auth.py --export
5. Copy the output into GitHub Secret 'YOUTUBE_TOKEN'
"""

import os
import sys
import json
import base64

def main():
    export_mode = "--export" in sys.argv

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("❌ Run: pip install google-auth google-auth-oauthlib")
        sys.exit(1)

    SCOPES     = ["https://www.googleapis.com/auth/youtube.upload",
                  "https://www.googleapis.com/auth/youtube"]
    TOKEN_FILE = "youtube_token.json"
    SECRETS    = "client_secrets.json"

    if export_mode:
        if not os.path.exists(TOKEN_FILE):
            print(f"❌ {TOKEN_FILE} not found — run without --export first!")
            sys.exit(1)

        # Export as base64 encoded JSON for GitHub Secret
        token_json = open(TOKEN_FILE).read()
        b64        = base64.b64encode(token_json.encode()).decode()

        print("\n✅ Copy this into GitHub Secret 'YOUTUBE_TOKEN':\n")
        print(b64)
        print("\n⚠️  Delete the old YOUTUBE_TOKEN secret first, then add this new one.")
        return

    if not os.path.exists(SECRETS):
        print(f"❌ {SECRETS} not found!")
        print("\nTo get it:")
        print("1. Go to https://console.cloud.google.com")
        print("2. APIs & Services → Credentials")
        print("3. Click your OAuth 2.0 Client ID → Download JSON")
        print("4. Save as client_secrets.json in this folder")
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save as JSON (not pickle — version independent)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    print("✅ Authentication successful!")
    print(f"   Token saved to {TOKEN_FILE}")
    print("\n⚠️  Next: export token for GitHub Actions:")
    print("   python youtube_auth.py --export")
    print("   Delete old YOUTUBE_TOKEN secret on GitHub, add the new value.")

if __name__ == "__main__":
    main()
