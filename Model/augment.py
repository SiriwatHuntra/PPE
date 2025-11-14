import cv2
import numpy as np

class ImageEnhancer:
    def __init__(self, enable_color=True, enable_sharpen=True, enable_apply_mask=True):
        self.enable_color = enable_color
        self.enable_sharpen = enable_sharpen
        self.eneapply_mask = enable_apply_mask

    # ---- existing functions ----
    def enhance_color(self, frame):
        # skip full equalizeHist (expensive) → CLAHE on V only
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4,4))
        hsv[..., 2] = clahe.apply(hsv[..., 2])       # brighten only V
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


    def sharpen(self, frame):
        kernel = np.array([[0, -1, 0],
                           [-1, 5, -1],
                           [0, -1, 0]])
        return cv2.filter2D(frame, -1, kernel)


    def apply_mask(self, frame, mask):
        frame = cv2.resize(frame, (976, 725))
        frame = cv2.bitwise_and(frame, frame, mask=mask)  # Apply mask
        return cv2.bitwise_and(frame, frame, mask=mask)


    # ---- main processing ----
    def process(self, frame):
        if self.eneapply_mask:
            frame = self.apply_mask(frame, mask = cv2.imread('asset/Masking.png', 0))  # Load as grayscale, mask image 976x725
        if self.enable_color:
            frame = self.enhance_color(frame)
        if self.enable_sharpen:
            frame = self.sharpen(frame)
        return frame

def run_cam_test():
    """Run webcam test for live enhancement"""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open camera")
        return

    #appliy masking
    

    enhancer = ImageEnhancer()
    use_enhance = True
    print("Press [a] to toggle enhancement, [q] to quit.")

    while True:
        ret, frame = cap.read()
        frame = cv2.resize(frame, (976, 725))
        if not ret:
            break

        if use_enhance:
            frame = enhancer.process(frame)

        cv2.putText(frame, f"Enhance: {'ON' if use_enhance else 'OFF'}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Live Enhancement", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('a'):
            use_enhance = not use_enhance

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_cam_test()