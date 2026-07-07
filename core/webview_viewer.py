import sys
import webview

def main():
    if len(sys.argv) < 3:
        print("Usage: python webview_viewer.py <title> <url>")
        sys.exit(1)
        
    title = sys.argv[1]
    url = sys.argv[2]
    
    # Open native window
    webview.create_window(title, url, width=1200, height=800)
    webview.start()

if __name__ == '__main__':
    main()
