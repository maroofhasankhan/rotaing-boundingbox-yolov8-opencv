from ultralytics import YOLO
import cv2
import numpy as np
import os
from datetime import datetime, timezone

def rescaleFrame(frame, scale=0.75):
  width = int(frame.shape[1] * scale)
  height = int(frame.shape[0] * scale)
  return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

def enhance_image(roi):
  lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
  l, a, b = cv2.split(lab)
  clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
  cl = clahe.apply(l)
  enhanced = cv2.merge([cl, a, b])
  enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
  return enhanced

def get_binary_mask(roi):
  enhanced = enhance_image(roi)
  gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
  blurred = cv2.GaussianBlur(gray, (5, 5), 0)
  _, thresh1 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
  thresh2 = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                cv2.THRESH_BINARY, 11, 2)
  binary = cv2.bitwise_or(thresh1, thresh2)
  kernel = np.ones((3,3), np.uint8)
  binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
  binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
  return binary

def get_accurate_rotated_bbox(image, bbox, min_area_ratio=0.1):
  x1, y1, x2, y2 = map(int, bbox)
  roi = image[y1:y2, x1:x2]
  
  roi_height, roi_width = roi.shape[:2]
  roi_area = roi_height * roi_width
  
  binary = get_binary_mask(roi)
  contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
  
  if not contours:
      return None, None
  
  valid_contours = []
  for contour in contours:
      area = cv2.contourArea(contour)
      if area > roi_area * min_area_ratio:
          valid_contours.append(contour)
  
  if not valid_contours:
      return None, None
  
  c = max(valid_contours, key=cv2.contourArea)
  epsilon = 0.02 * cv2.arcLength(c, True)
  approx = cv2.approxPolyDP(c, epsilon, True)
  hull = cv2.convexHull(approx)
  
  rotated_rect = cv2.minAreaRect(hull)
  box = cv2.boxPoints(rotated_rect)
  box = np.int0(box)
  
  box[:,0] += x1
  box[:,1] += y1
  
  center_x, center_y = rotated_rect[0]
  adjusted_rect = ((center_x + x1, center_y + y1), rotated_rect[1], rotated_rect[2])
  
  return adjusted_rect, box

def draw_rotated_bbox(image, rotated_box, color=(0, 255, 0), thickness=2):
  cv2.polylines(image, [rotated_box], True, color, thickness)
  center = np.mean(rotated_box, axis=0).astype(int)
  cv2.circle(image, tuple(center), 3, (0, 0, 255), -1)
  return image

def pixel_to_cm(width_pixels, height_pixels, depth_cm=70, focal_length_pixels=1000):
  width_cm = (width_pixels * depth_cm) / focal_length_pixels
  height_cm = (height_pixels * depth_cm) / focal_length_pixels
  return width_cm, height_cm

def process_frame(frame, model, save_dir, conf_threshold=0.4, focal_length_pixels=1000):
  results = model(frame)
  detections = results[0].boxes
  
  processed_frame = frame.copy()
  save_frame = False
  
  for box in detections:
      cls = int(box.cls.item())
      conf = float(box.conf.item())
      
      if conf >= conf_threshold:
          save_frame = True
          xyxy = [float(x) for x in box.xyxy[0]]
          
          rotated_rect, rotated_box = get_accurate_rotated_bbox(frame, xyxy)
          
          if rotated_box is not None:
              processed_frame = draw_rotated_bbox(processed_frame, rotated_box)
              
              center, (width_pixels, height_pixels), angle = rotated_rect
              
              width_cm, height_cm = pixel_to_cm(width_pixels, height_pixels, 
                                              depth_cm=100, 
                                              focal_length_pixels=focal_length_pixels)
              
              text = f"Class: {cls}, Conf: {conf*100:.1f}%"
              dimensions_text = f"W: {width_cm:.1f}cm, H: {height_cm:.1f}cm"
              
              cv2.putText(processed_frame, text, 
                         (int(center[0]), int(center[1])), 
                         cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
              cv2.putText(processed_frame, dimensions_text, 
                         (int(center[0]), int(center[1]) + 20), 
                         cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
              
              print(f"Object {cls}: Center: {center}, Width: {width_cm:.1f}cm, "
                    f"Height: {height_cm:.1f}cm, Angle: {angle:.1f}, Conf: {conf*100:.1f}%")
  
  if save_frame:
      utc_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
      filename = f"detection_{utc_timestamp}_conf_{conf*100:.1f}.jpg"
      save_path = os.path.join(save_dir, filename)
      cv2.imwrite(save_path, processed_frame)
      print(f"Saved frame to: {save_path}")

  return processed_frame

def main():
  save_dir = "high_confidence_detections"
  os.makedirs(save_dir, exist_ok=True)
  
  model = YOLO("C:\\Users\\Admin\\Downloads\\best.pt")
  cap = cv2.VideoCapture(0)
  focal_length_pixels = 1000
  
  while True:
      ret, frame = cap.read()
      if not ret:
          print("Failed to grab frame")
          break
          
      frame = rescaleFrame(frame, scale=0.75)
      processed_frame = process_frame(frame, model, 
                                   save_dir,
                                   conf_threshold=0.4,
                                   focal_length_pixels=focal_length_pixels)
      
      cv2.imshow('Object Detection with Measurements', processed_frame)
      
      if cv2.waitKey(1) & 0xFF == ord('q'):
          break
  
  cap.release()
  cv2.destroyAllWindows()

if __name__ == "__main__":
  main()