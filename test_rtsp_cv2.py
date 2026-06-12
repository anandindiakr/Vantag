"""Test cv2 VideoCapture against specific RTSP paths for each camera."""
import cv2
import sys

cameras_to_test = {
    "192.168.1.109": [
        "rtsp://192.168.1.109:554/",
        "rtsp://192.168.1.109:554/stream1",
        "rtsp://192.168.1.109:554/Streaming/Channels/101",
        "rtsp://admin:@192.168.1.109:554/Streaming/Channels/101",
        "rtsp://admin:admin@192.168.1.109:554/Streaming/Channels/101",
        "rtsp://admin:12345@192.168.1.109:554/Streaming/Channels/101",
        "rtsp://admin:@192.168.1.109:554/stream1",
        "rtsp://admin:admin@192.168.1.109:554/stream1",
        "rtsp://admin:12345@192.168.1.109:554/stream1",
        "rtsp://admin:@192.168.1.109:554/live",
        "rtsp://admin:12345@192.168.1.109:554/live",
    ],
    "192.168.1.248": [
        "rtsp://192.168.1.248:554/",
        "rtsp://192.168.1.248:554/stream1",
        "rtsp://admin:@192.168.1.248:554/stream1",
        "rtsp://admin:admin@192.168.1.248:554/stream1",
        "rtsp://admin:12345@192.168.1.248:554/stream1",
        "rtsp://192.168.1.248:554/11",
        "rtsp://192.168.1.248:554/12",
        "rtsp://admin:@192.168.1.248:554/11",
        "rtsp://admin:admin@192.168.1.248:554/11",
        "rtsp://admin:12345@192.168.1.248:554/11",
        "rtsp://192.168.1.248:554/live/ch00_0",
        "rtsp://admin:@192.168.1.248:554/live/ch00_0",
        "rtsp://admin:admin@192.168.1.248:554/live/ch00_0",
        "rtsp://admin:12345@192.168.1.248:554/live/ch00_0",
        "rtsp://admin:@192.168.1.248:554/cam/realmonitor?channel=1&subtype=0",
        "rtsp://admin:admin@192.168.1.248:554/cam/realmonitor?channel=1&subtype=0",
    ],
    "192.168.1.251": [
        "rtsp://192.168.1.251:554/",
        "rtsp://192.168.1.251:554/stream1",
        "rtsp://admin:@192.168.1.251:554/stream1",
        "rtsp://admin:admin@192.168.1.251:554/stream1",
        "rtsp://admin:12345@192.168.1.251:554/stream1",
        "rtsp://192.168.1.251:554/11",
        "rtsp://admin:@192.168.1.251:554/11",
        "rtsp://admin:admin@192.168.1.251:554/11",
        "rtsp://admin:12345@192.168.1.251:554/11",
        "rtsp://192.168.1.251:554/live/ch00_0",
        "rtsp://admin:@192.168.1.251:554/live/ch00_0",
        "rtsp://admin:admin@192.168.1.251:554/live/ch00_0",
        "rtsp://admin:12345@192.168.1.251:554/live/ch00_0",
        "rtsp://admin:@192.168.1.251:554/cam/realmonitor?channel=1&subtype=0",
        "rtsp://admin:admin@192.168.1.251:554/cam/realmonitor?channel=1&subtype=0",
    ],
}

print("Testing RTSP streams with cv2.VideoCapture (5s timeout each)...\n")

# Set cv2 to fast timeout
cv2.setNumThreads(1)

found = {}
for ip, paths in cameras_to_test.items():
    print(f"\n=== {ip} ===")
    for url in paths:
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        opened = cap.isOpened()
        if opened:
            ret, frame = cap.read()
            has_frame = ret and frame is not None
            cap.release()
            if has_frame:
                print(f"  [LIVE VIDEO] {url}")
                found[ip] = url
                break
            else:
                print(f"  [OPENED but no frame] {url}")
        else:
            cap.release()
            print(f"  [FAIL] {url}")
        if ip in found:
            break

print("\n\n=== RESULTS ===")
for ip, url in found.items():
    print(f"  {ip}: {url}")

if not found:
    print("  No cameras found with cv2 - streams may require VLC-style parameters or different codec")
