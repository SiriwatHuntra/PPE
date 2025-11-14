#----- IMPORT LIBRARY ---------------------------------------------
import cv2 as cv
import json
import numpy as np
from datetime import datetime
from collections import Counter
import logging
from typing import List, Optional, Tuple
import csv
import os
import sys
from LogHandler import init_logger
from Model.augment import ImageEnhancer

logger = init_logger("Inferences")

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

#----- SETUP ------------------------------------------------------

MODEL_PATH = "Model/yolo_XI.onnx"
IMG_SIZE   = 640
CONF_THRES = 0.60   
IOU_THRES  = 0.7  # NMS IoU
CLASS_NAMES = {0: 'Arm', 1: 'Cap', 2: 'Carbon_Mask', 3: 'Clothes', 4: 'Face_Shield', 5: 'Gas_Mask', 6: 'Glove', 7: 'ID_Card', 8: 'Long_Glove', 9: 'OSL', 10: 'Safety_Shoe', 11:'Yellow_Jacket'}
FILE_MAP = {1: "Chemical.json", 2: "Solder.json", 3: "Thickness.json", 4: "GroupL.json", 5: "Manager.json"}
NOT_ALLOWED = ["Arm"]

_pre_alloc = {"blob": None, "size": (IMG_SIZE, IMG_SIZE)}
enhancer = ImageEnhancer(enable_color=True, enable_sharpen=True, enable_apply_mask=True)

with open('JsonAsset/_map.json', 'r') as f:
    TARGET_REF = json.load(f)

with open("JsonAsset/_ColorMap.json", "r") as f:
    CLASS_COLORS = json.load(f)

CLASS_COLORS = {k: tuple(v) for k, v in CLASS_COLORS.items()}

# ---------- Lazy Model Loader (Prevents PyQt DLL crash) ---------
sess = None
in_name = None
out_name = None

def load_model():
    if not os.path.exists(MODEL_PATH):
        logging.error(f"ONNX model not found at: {MODEL_PATH}")
        sys.exit(1)

    global sess, in_name, out_name
    if sess is not None:
        return sess
    import onnxruntime as ort          # ← move import here
    dll_path = os.path.join(sys.prefix, "Lib", "site-packages", "onnxruntime", "capi")
    if os.path.exists(dll_path):
        os.add_dll_directory(dll_path)
    
    #impove session options
    opt = ort.SessionOptions()
    opt.intra_op_num_threads = 6


    sess = ort.InferenceSession(MODEL_PATH, sess_options=opt, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    out_name = sess.get_outputs()[0].name
    return sess



#------ I/O LOGS -----------------------------------------------
#CSV Unused
def export_to_csv(task_name:str, success:bool, image_path:str, 
                  detected:Optional[dict], expected:dict):
    now = datetime.now()
    year  = now.strftime("%Y")
    date  = now.strftime("%Y-%m-%d")
    time_ = now.strftime("%H:%M:%S")
    status = "PASS" if success else "FAIL"

    # Find missing equipment
    missing = {}
    if detected is not None:
        for k, v in expected.items():
            if detected.get(k, 0) < v:
                missing[k] = v - detected.get(k, 0)

    missing_str = "; ".join(f"{k}:{v}" for k,v in missing.items()) if missing else "None"

    # Monthly filename
    filename = f"ValidationLog_{year}-{now.strftime('%m')}.csv"
    file_exists = os.path.isfile(filename)

    with open(filename, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Task","Year","Date","Time","Status","ImageFile","Missing"])
        writer.writerow([task_name, year, date, time_, status, image_path, missing_str])

    logger.info(f"CSV updated: {filename}")
    
def save_image(image, prefix: str = "validate_detection") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"{prefix}_{timestamp}.jpg"
    success = cv.imwrite(filepath, image)
    if success:
        logger.info(f"Image saved: {filepath}")
        return filepath
    else:
        logger.info(f"Failed to save image: {filepath}")
        return None

#------------ MODEL UTILITY ----------------------------------------
class ONNXBox:
    """
    Input:
        xyxy (tuple) - bounding box (x1,y1,x2,y2)
        conf (float) - detection confidence
        cls_id (int) - class index
    Process:
        Store values as numpy arrays with fixed shapes
    Output:
        Object with .xyxy, .conf, .cls attributes
    """
    def __init__(self, xyxy: Tuple[float,float,float,float], conf: float, cls_id: int):
        self.xyxy = np.array([xyxy], dtype=np.float32)  # shape (1,4)
        self.conf = np.array([conf], dtype=np.float32)  # shape (1,)
        self.cls  = np.array([cls_id], dtype=np.float32)  # shape (1,)


def sigmoid(x, out = None):
    """
    Input:
        x (float or np.ndarray) - value(s) to transform
    Process:
        Apply sigmoid activation: 1 / (1 + exp(-x))
    Output:
        float or np.ndarray - values in range (0,1)
    """
    if out is None:
        out = np.empty_like(x)
    np.negative(x, out=out)
    np.exp(out, out= out)
    out += 1
    np.reciprocal(out, out=out)
    return out

def nms_xyxy(boxes, scores, iou=0.45):
    """
    Input:
        boxes (list[np.ndarray]) - list of [x1,y1,x2,y2] boxes
        scores (list/np.ndarray) - confidence scores
        iou (float) - IoU threshold for suppression
    Process:
        - Apply Non-Maximum Suppression (OpenCV dnn.NMSBoxes)
        - Keep best boxes, remove overlapping ones
    Output:
        list[int] - indices of kept boxes
    """
    if len(boxes) == 0: 
        return []
    idxs = cv.dnn.NMSBoxes(
        [[int(b[0]), int(b[1]), int(b[2]-b[0]), int(b[3]-b[1])] for b in boxes],
        scores.tolist(), 0.0, iou
    )
    if len(idxs) == 0: 
        return []
    return [int(i[0]) if isinstance(i, (list,tuple,np.ndarray)) else int(i) for i in idxs]

def iou_matrix(A, B):
    """Compute IoU matrix between all boxes in A and B (NxM)."""
    inter_x1 = np.maximum(A[:, None, 0], B[None, :, 0])
    inter_y1 = np.maximum(A[:, None, 1], B[None, :, 1])
    inter_x2 = np.minimum(A[:, None, 2], B[None, :, 2])
    inter_y2 = np.minimum(A[:, None, 3], B[None, :, 3])
    inter = np.clip(inter_x2 - inter_x1, 0, None) * np.clip(inter_y2 - inter_y1, 0, None)

    areaA = (A[:, 2] - A[:, 0]) * (A[:, 3] - A[:, 1])
    areaB = (B[:, 2] - B[:, 0]) * (B[:, 3] - B[:, 1])
    union = areaA[:, None] + areaB[None, :] - inter
    return inter / np.clip(union, 1e-6, None)

#-------- PROCESSES LOGIC -------------------------------------
def task_select(task_tag: int)-> Optional[dict]:
    """
    Input:
        task_tag (int) - key to select PPE task file from FILE_MAP
    Process:
        - Find mapped JSON filename
        - Load expected PPE list from JsonAsset/<filename>
        - Handle errors (missing file, JSON error, etc.)
    Output:
        dict - expected PPE items (if loaded successfully)
        None - if loading fails
    """
    filename = FILE_MAP.get(task_tag)
    if not filename:
        logger.error(f"No file mapping found for task_tag: {task_tag}")
        return None
    filepath = f"JsonAsset/{filename}"
    try:
        with open(filepath, 'r') as file:
            data = json.load(file)
            logger.info(f"Successfully load PPE list from {filepath}")
            return data         
    except FileNotFoundError:
        logger.error(f"{filepath} not found")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding failed for {filepath}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error while loading {filepath}: {e}")
    return None

def validate_counts(detected: dict, expected: dict) -> bool:
    """
    Input:
        detected (dict) - items found by detection {class: count}
        expected (dict) - required items {class: count}
    Process:
        - Compare detected vs expected dictionaries
        - Log the comparison result
    Output:
        bool - True if detected == expected, else False
    """
    status = detected == expected
    # logger.info(f"""
    #             Validation result: {status}
    #             Detected: {detected}
    #             Expected: {expected}
    #             """)
    return status, detected, expected

def is_overlap(box_target: List[float], box_ref: List[float]) -> float:
    """
    Input:
        box_target (list[float]) - [x1,y1,x2,y2] of first box
        box_ref (list[float]) - [x1,y1,x2,y2] of second box
    Process:
        - Validate input format
        - Compute intersection area
        - Compute union area
        - Calculate IoU = inter / union
    Output:
        float - IoU value in [0,1]
    """
    if len (box_target) != 4 or len(box_ref) != 4:
        logger.error("Annotated box must have four coordinate")
        raise ValueError("Invalid box format. Expected: [x1, y1, x2, y2]")

    x1 = max(box_target[0], box_ref[0])
    y1 = max(box_target[1], box_ref[1])
    x2 = min(box_target[2], box_ref[2])
    y2 = min(box_target[3], box_ref[3])

    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    if inter_area == 0:
        return 0.0

    box_target_area = (box_target[2] - box_target[0]) * (box_target[3] - box_target[1])
    box_ref_area = (box_ref[2] - box_ref[0]) * (box_ref[3] - box_ref[1])
    iou = inter_area / float(box_target_area + box_ref_area - inter_area)
    logger.info(f"IOU computed: {iou:.4f}")
    return iou

def draw_bounding_box(image: np.ndarray, 
                      box, 
                      label: str, 
                      color: tuple[int, int, int] =(0, 0, 255), 
                      thickness: int =2,
                      font_scale: float = 0.6) -> np.ndarray:
    """
    Input:
        image (np.ndarray) - target image (BGR)
        box (ONNXBox or tuple) - bounding box [x1,y1,x2,y2]
        label (str) - class name
        color (tuple[int,int,int]) - box/text color (BGR)
        thickness (int) - line thickness
    Process:
        - Extract box coordinates and confidence
        - Draw rectangle and label text on image
        - Support both ONNXBox and plain tuple input
    Output:
        np.ndarray - image with bounding box + label
    """
    try:
        # Handle both adapters
        draw_color = CLASS_COLORS.get(label, color)

        if hasattr(box, "xyxy") and hasattr(box, "conf"):
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            confi = float(box.conf[0])
        else:
            # Fallback if someone passes plain tuple
            x1, y1, x2, y2 = map(int, box)
            confi = 0.0

        label_conf = f"{label}:{confi:.2f}"
        cv.rectangle(image, (x1, y1), (x2, y2), draw_color, thickness)
        cv.putText(image, label_conf, (x1, max(y1 - 10, 0)),
                   cv.FONT_HERSHEY_SIMPLEX, font_scale, draw_color, 2)
    except Exception as e:
        logger.error(f"Fail to draw boundary box: {e}")
    return image

def pre_processor(im, new_shape= 640):
    h, w = im.shape[:2]
    s = min(new_shape/h, new_shape/w) #check smallest size for reshape image with data less loss
    nh, nw = int(round(h*s)), int(round(w*s)) #applie new scaler
    top = (new_shape - nh)//2
    left = (new_shape - nw)//2
    
    if _pre_alloc["blob"] is None or _pre_alloc["size"] != (new_shape, new_shape):
        _pre_alloc["blob"] = np.empty((1,3, new_shape, new_shape), dtype= np.float32)
        _pre_alloc["size"] = (new_shape, new_shape)
        
    img_resized = cv.resize(im, (nw, nh), interpolation=cv.INTER_LINEAR)
    padded = cv.copyMakeBorder(img_resized, top, new_shape - nh - top,
                               left, new_shape -nw - left, 
                               cv.BORDER_CONSTANT, value=(114, 114, 114))
    
    rgb = cv.cvtColor(padded, cv.COLOR_BGR2RGB).astype(np.float32) / 255.0
    blob = _pre_alloc["blob"]
    blob[0] = np.transpose(rgb, (2, 0, 1))
    
    return blob, s, left, top
 
def letterbox(im, new_shape=640, color=(114,114,114)):
    """
    Input:
        im (np.ndarray) - input image
        new_shape (int) - target size
        color (tuple) - padding color
    Process:
        - Resize image while keeping aspect ratio
        - Pad borders to fit new_shape
    Output:
        (im_padded, scale, pad_left, pad_top)
    """
    h, w = im.shape[:2]
    s = min(new_shape / h, new_shape / w)
    nh, nw = int(round(h*s)), int(round(w*s))
    im_resized = cv.resize(im, (nw, nh), interpolation=cv.INTER_LINEAR)
    top = (new_shape - nh)//2; bottom = new_shape - nh - top
    left = (new_shape - nw)//2; right  = new_shape - nw - left
    im_padded = cv.copyMakeBorder(im_resized, top, bottom, left, right,
                                  cv.BORDER_CONSTANT, value=color)
    return im_padded, s, left, top
 
_IO_MAP = None 
 
def detect_objects(image_bgr: np.ndarray, 
                   equipment_list: Optional[dict] = None,
                   CONFIDENT_THRESHOLD: float = CONF_THRES, 
                   IOU_THRESHOLD: float = 0.01) -> Tuple[Counter, np.ndarray]:
    """
    Run ONNX YOLO detection and annotate image with bounding boxes.
    Returns (Counter, annotated_image)
    """
    image_bgr = cv.resize(image_bgr, (976, 725))
    orig = image_bgr  # keep original reference for later
    H0, W0 = orig.shape[:2]

    # --- Preprocess ---
    
    aug = enhancer.process(image_bgr)

    img, scale, pad_x, pad_y = letterbox(aug, IMG_SIZE)
    blob = cv.dnn.blobFromImage(
        img, scalefactor=1/255.0, size=(IMG_SIZE, IMG_SIZE),
        mean=(0, 0, 0), swapRB=True, crop=False
    )

    sess = load_model()

    # --- Reuse buffer map ---
    global _IO_MAP
    if _IO_MAP is None:
        _IO_MAP = {in_name: blob}
    else:
        _IO_MAP[in_name][:] = blob

    # --- Inference ---
    out = sess.run([out_name], _IO_MAP)[0]
    p = out
    if p.ndim == 3:
        b, a, n = p.shape
        if a <= 20 and n > a:
            p = np.transpose(p, (0, 2, 1))
        p = np.squeeze(p, 0)
    elif p.ndim != 2:
        raise RuntimeError(f"Unexpected ONNX output ndim={p.ndim}")

    boxes_xywh = p[:, :4]
    rest = p[:, 4:]
    nc_known = len(CLASS_NAMES)
    C = rest.shape[1]
    use_obj = C > nc_known

    # --- Confidence calc (optimized) ---
    rest = sigmoid(rest, out=rest)
    if use_obj:
        rest[:, 1:] *= rest[:, [0]]
        conf_vec = rest[:, -nc_known:]
    else:
        conf_vec = rest

    scores = conf_vec.max(axis=1)
    cls_ids = conf_vec.argmax(axis=1)

    keep_mask = scores >= CONFIDENT_THRESHOLD
    if not np.any(keep_mask):
        return Counter(), orig.copy()
    
    boxes_xywh = boxes_xywh[keep_mask]
    scores = scores[keep_mask]
    cls_ids = cls_ids[keep_mask]

    # --- xywh → xyxy ---
    x, y, w, h = [boxes_xywh[:, i] for i in range(4)]
    boxes_xyxy = np.stack([x - w/2, y - h/2, x + w/2, y + h/2], axis=1).astype(np.float32)
    if np.median(boxes_xyxy[:, 2]) <= 1.5:
        boxes_xyxy *= IMG_SIZE

    boxes_xyxy[:, [0, 2]] -= pad_x
    boxes_xyxy[:, [1, 3]] -= pad_y
    boxes_xyxy /= scale
    boxes_xyxy[:, 0::2] = boxes_xyxy[:, 0::2].clip(0, W0)
    boxes_xyxy[:, 1::2] = boxes_xyxy[:, 1::2].clip(0, H0)

    # --- NMS ---
    keep = np.array(nms_xyxy(boxes_xyxy, scores, iou=IOU_THRES), dtype=int)
    if keep.size == 0:
        return Counter(), orig.copy()

    # Apply NMS
    boxes_kept  = boxes_xyxy[keep].astype(int)
    cls_kept    = cls_ids[keep]
    scores_kept = scores[keep]
    labels      = np.vectorize(CLASS_NAMES.get)(cls_kept, cls_kept.astype(str))

    # --- Hard filter classes ---
    mask = np.array([lbl not in NOT_ALLOWED for lbl in labels])
    boxes_kept  = boxes_kept[mask]
    cls_kept    = cls_kept[mask]
    scores_kept = scores_kept[mask]
    labels      = labels[mask]
    
    vis = orig if equipment_list is None else orig.copy()
    
    for box, label, conf in zip(boxes_kept, labels, scores_kept):
        if equipment_list is None or label in equipment_list:
            onnx_box = ONNXBox(tuple(box), float(conf), int(cls_kept[0]))
            vis = draw_bounding_box(vis, onnx_box, label)
            
    # --- Label mapping with vectorized IoU ---
    label_list = []


    for target_name, ref_list in TARGET_REF.items():
        target_boxes = boxes_kept[labels == target_name]
        if target_boxes.size == 0:
            continue
        ref_boxes = np.concatenate(
            [boxes_kept[labels == ref] for ref in ref_list if np.any(labels == ref)],
            axis=0
        ) if any(np.any(labels == ref) for ref in ref_list) else np.empty((0, 4))
        if ref_boxes.size == 0:
            label_list.extend([target_name] * len(target_boxes))
        else:
            ious = iou_matrix(target_boxes, ref_boxes)
            matched = (ious >= IOU_THRESHOLD).any(axis=1)
            label_list.extend(np.array([target_name] * np.count_nonzero(matched)))

    return Counter(label_list), vis

#####   EXE    ######
if __name__ == "__main__":
    task_id = 5

