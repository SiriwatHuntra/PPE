import cv2
from Model.Model_optimize import detect_objects   # adjust path if needed

def main():
    cap = cv2.VideoCapture(0)  # 0 = default webcam

    if not cap.isOpened():
        print("❌ Cannot access webcam")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to grab frame")
            break

        # ------ YOLO Detection ------
        counts, annotated = detect_objects(frame)
        print("Detected objects:", counts)
        # ------ Display results ------
        cv2.imshow("Detection Output", annotated)
        waitkey = cv2.waitKey(1) & 0xFF
        if waitkey == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()
    print("🛑 Webcam closed")

if __name__ == "__main__":
    main()
