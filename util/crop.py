"""This is a script to convert ppt photos taken at conferences
to more frendly square images

Modified after 
https://www.pyimagesearch.com/2014/09/01/build-kick-ass-mobile-document-scanner-just-5-minutes/
"""
import numpy as np
import argparse
import cv2
import os
import glob
from skimage.filters import threshold_local

# TODO: Add manual selection of points in case of bad results


def order_points(pts):
  # initialzie a list of coordinates that will be ordered
  # such that the first entry in the list is the top-left,
  # the second entry is the top-right, the third is the
  # bottom-right, and the fourth is the bottom-left
  rect = np.zeros((4, 2), dtype = "float32")
 
  # the top-left point will have the smallest sum, whereas
  # the bottom-right point will have the largest sum
  s = pts.sum(axis = 1)
  rect[0] = pts[np.argmin(s)]
  rect[2] = pts[np.argmax(s)]
 
  # now, compute the difference between the points, the
  # top-right point will have the smallest difference,
  # whereas the bottom-left will have the largest difference
  diff = np.diff(pts, axis = 1)
  rect[1] = pts[np.argmin(diff)]
  rect[3] = pts[np.argmax(diff)]
 
  # return the ordered coordinates
  return rect 

def four_point_transform(image, pts):
  # obtain a consistent order of the points and unpack them
  # individually
  rect = order_points(pts)
  (tl, tr, br, bl) = rect
 
  # compute the width of the new image, which will be the
  # maximum distance between bottom-right and bottom-left
  # x-coordiates or the top-right and top-left x-coordinates
  widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
  widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
  maxWidth = max(int(widthA), int(widthB))
 
  # compute the height of the new image, which will be the
  # maximum distance between the top-right and bottom-right
  # y-coordinates or the top-left and bottom-left y-coordinates
  heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
  heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
  maxHeight = max(int(heightA), int(heightB))
 
  # now that we have the dimensions of the new image, construct
  # the set of destination points to obtain a "birds eye view",
  # (i.e. top-down view) of the image, again specifying points
  # in the top-left, top-right, bottom-right, and bottom-left
  # order
  dst = np.array([
    [0, 0],
    [maxWidth - 1, 0],
    [maxWidth - 1, maxHeight - 1],
    [0, maxHeight - 1]], dtype = "float32")
 
  # compute the perspective transform matrix and then apply it
  M = cv2.getPerspectiveTransform(rect, dst)
  warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
 
  # return the warped image
  return warped


def process(input_path, debug=0, is_dark=True):
  # load the image and compute the ratio of the old height
  # to the new height, clone it, and resize it
  image = cv2.imread(input_path)
  ratio = 1000.0 / image.shape[0]
  orig = image.copy()
  image = cv2.resize(image, (0, 0), fx=ratio, fy=ratio)
   
  # convert the image to grayscale, blur it, and find edges
  # in the image
  # gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
  # Modification: project max color. Some slides with dark top banner
  gray = np.max(image, axis=2)
  # cv2.imshow("Gray", gray)
  # cv2.waitKey(0)
  # cv2.destroyAllWindows()
  gray = cv2.GaussianBlur(gray, (5, 5), 0)
  # Modification: some slides with dark themes
  if is_dark:
    lower = np.percentile(gray, 20)
    higher = np.percentile(gray, 50)
  else:
    lower = np.percentile(gray, 40)
    higher = np.percentile(gray, 80)
  edged = cv2.Canny(gray, lower, higher)
  kernel = np.ones((5, 5), np.uint8)
  edged = cv2.dilate(edged, kernel=kernel)

  # fix the issue where the edge does not close at boundary
  # pad the edged image by padding ones around the edge
  edged_ones = np.ones(np.array(edged.shape) + 4, dtype=np.uint8) * 255
  edged_ones[2:-2, 2:-2] = edged
  edged = edged_ones
   
  # show the original image and the edge detected image
  if debug:
    print("STEP 1: Edge Detection")
    cv2.imshow("Image", image)
    cv2.imshow("Edged", edged)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

  def find_largest_rect_contour(edged):
    # find the contours in the edged image, keeping only the
    # largest ones, and initialize the screen contour
    cnts = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    # cnts = cv2.findContours(edged.copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[1]

    cnts = sorted(cnts, key = cv2.contourArea, reverse = True)[:5]
    # print(cnts)
    screenCnt, original_c = None, None

    # loop over the contours
    for c in cnts:
      # remove too big bboxes
      if cv2.contourArea(c) / np.size(edged) > 0.9:
        continue
      # approximate the contour
      peri = cv2.arcLength(c, True)
      approx = cv2.approxPolyDP(c, 0.1 * peri, True)
     
      # if our approximated contour has four points, then we
      # can assume that we have found our screen
      if len(approx) == 4:
        screenCnt = approx
        original_c = c
        break
    return screenCnt, original_c

  screenCnt, original_c = find_largest_rect_contour(edged)
  if screenCnt is None or original_c is None:
    raise ValueError('edge not found')

  # infill 
  cv2.fillPoly(edged, pts =[original_c], color=(255,255,255))
  if debug:
    cv2.imshow(" ", edged)
    cv2.waitKey(0)

  # then open up to remove dangling edges
  kernel = np.ones((20, 20), np.uint8)
  edged = cv2.morphologyEx(edged, cv2.MORPH_OPEN, kernel)
  if debug:
    cv2.imshow(" ", edged)
    cv2.waitKey(0)

  screenCnt, original_c = find_largest_rect_contour(edged)

  # show the contour (outline) of the piece of paper
  if debug:
    print("STEP 2: Find contours of paper")
    image_with_bbox = cv2.drawContours(image.copy(), [screenCnt], -1, (0, 255, 0), 2)
    cv2.imshow("Outline", image_with_bbox)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

  # apply the four point transform to obtain a top-down
  # view of the original image
  warped = four_point_transform(image, screenCnt.reshape(4, 2))
   
  # convert the warped image to grayscale, then threshold it
  # to give it that 'black and white' paper effect
  # warped = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
  # T = threshold_local(warped, 11, offset = 10, method = "gaussian")
  # warped = (warped > T).astype("uint8") * 255
   
  # show the original and scanned images
  # print("STEP 3: Apply perspective transform")
  # cv2.imshow("Scanned", cv2.resize(warped, (400, 400)))
  # cv2.waitKey(0)

  output_path = input_path + '.warped.jpg'
  cv2.imwrite(output_path, warped)


def batch_process(image_path_list):
  for image_path in image_path_list:
    try:
      process(image_path)
    except:
      print(image_path)  


if __name__ == '__main__':

  # construct the argument parser and parse the arguments
  ap = argparse.ArgumentParser()
  ap.add_argument("-i", "--image", required = False,
    help = "Path to the image to be scanned")
  ap.add_argument("-d", "--directory", required = False,
    help = "Path to the image directory to be scanned")
  ap.add_argument('--debug', action='store_true')
  ap.add_argument('--dark', action='store_true')
  args = vars(ap.parse_args())
  
  if args["image"] is not None: 
    input_path = args["image"]
    process(input_path, args["debug"], is_dark=args["dark"]) 
  else:
    input_path_list = glob.glob(os.path.join(args['directory'], '*'))
    input_path_list = [input_path for input_path in input_path_list if 'warped' not in input_path]
    batch_process(input_path_list)
  