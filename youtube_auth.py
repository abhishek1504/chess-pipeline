"""
youtube_auth.py — One-time YouTube authentication setup
Run this ONCE on your Mac to get your YouTube token.

Steps:
1. Download client_secrets.json from Google Cloud Console
   (APIs & Services → Credentials → OAuth 2.0 Client → Desktop → Download)
2. Run: python youtube_auth.py
3. Browser opens → log in with your YouTube account → Allow
4. Token saved as youtube_token.pickle — add contents to GitHub Secrets

For GitHub Actions, we need the token as a base64 string:
    python youtube_auth.py --export
This prints the base64 token to copy into YOUTUBE_TOKEN GitHub Secret.
"""

import os
import sys
import pickle
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
    TOKEN_FILE = "youtube_token.pickle"
    SECRETS    = "client_secrets.json"

    if export_mode and os.path.exists(TOKEN_FILE):
        # Export token as base64 for GitHub Secrets
        with open(TOKEN_FILE, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        print("\n✅ Copy this into GitHub Secret 'YOUTUBE_TOKEN':\n")
        print(b64)
        return

    if not os.path.exists(SECRETS):
        print(f"❌ {SECRETS} not found!")
        print("\nTo get it:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Select your project → APIs & Services → Credentials")
        print("3. Click your OAuth 2.0 Client ID → Download JSON")
        print("4. Save as client_secrets.json in this folder")
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    print("✅ Authentication successful!")
    print(f"   Token saved to {TOKEN_FILE}")
    print("\nNext step — export token for GitHub Actions:")
    print("   python youtube_auth.py --export")
    print("   Copy the output into GitHub Secret 'YOUTUBE_TOKEN'")

if __name__ == "__main__":
    main()
