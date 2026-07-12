import os
import time
import subprocess
from PIL import ImageGrab
import threading

def capture():
    # Start the app
    proc = subprocess.Popen(["python3", "main.py"], env=os.environ.copy())
    
    # Wait for app to load
    time.sleep(5)
    
    # We need to simulate typing and sending. But pyautogui might not be installed.
    # Instead, we can just patch main.py temporarily to start with a chat, OR
    # we can use AppleScript to send keystrokes to the Python app!
    
    applescript = """
    tell application "System Events"
        # Type a question
        keystroke "Qual a tendência de publicações sobre IA?"
        delay 1
        keystroke return
    end tell
    """
    
    subprocess.run(["osascript", "-e", applescript])
    
    # Wait for AI streaming to finish
    time.sleep(15)
    
    # Ensure evidence directory exists
    os.makedirs("docs/evidence", exist_ok=True)
    
    # Capture the screen (using screencapture command)
    # We will just capture the whole screen or the active window
    subprocess.run(["screencapture", "-x", "-m", "docs/evidence/chat_streaming_full.png"])
    
    print("Screenshot saved to docs/evidence/chat_streaming_full.png")
    
    proc.terminate()
    
if __name__ == "__main__":
    capture()
