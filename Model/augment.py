import cv2
import numpy as np

class ImageEnhancer:
    def __init__(self, enable_color=True, enable_edge=False, enable_sharpen=True, enable_edgeboost=False):
        self.enable_color = enable_color
        self.enable_edge = enable_edge
        self.enable_sharpen = enable_sharpen
        self.enable_edgeboost = enable_edgeboost

    # ---- existing functions ----
    def enhance_color(self, frame):
        # skip full equalizeHist (expensive) → CLAHE on V only
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4,4))
        hsv[..., 2] = clahe.apply(hsv[..., 2])       # brighten only V
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


    def enhance_edges(self, frame, weight=0.7):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 150)
        edges_colored = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        return cv2.addWeighted(frame, 1.0, edges_colored, weight, 0)

    def sharpen(self, frame):
        kernel = np.array([[0, -1, 0],
                           [-1, 5, -1],
                           [0, -1, 0]])
        return cv2.filter2D(frame, -1, kernel)

    # ---- new plugin: edge contrast booster ----
    def edge_contrast_boost(self, frame, edge_weight=1.0, detail_strength=1.0):
        # single grayscale conversion, cheaper filters
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        blur = cv2.blur(frame, (3,3))                # faster than Gaussian
        detail = cv2.addWeighted(frame, 1 + detail_strength, blur, -detail_strength, 0)
        edges_bgr = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        return cv2.addWeighted(detail, 1, edges_bgr, edge_weight, 0)


    # ---- main processing ----
    def process(self, frame):
        if self.enable_color:
            frame = self.enhance_color(frame)
        if self.enable_edge:
            frame = self.enhance_edges(frame)
        if self.enable_sharpen:
            frame = self.sharpen(frame)
        if self.enable_edgeboost:
            frame = self.edge_contrast_boost(frame)
        return frame

def run_cam_test():
    """Run webcam test for live enhancement"""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Cannot open camera")
        return

    enhancer = ImageEnhancer()
    use_enhance = True
    print("Press [a] to toggle enhancement, [q] to quit.")

    while True:
        ret, frame = cap.read()
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