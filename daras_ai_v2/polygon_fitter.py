import math

import cv2
import numpy as np

CONTOUR_HIREARCY = cv2.RETR_EXTERNAL
CONTOUR_MODE = cv2.CHAIN_APPROX_SIMPLE


def roll_pts_to_have_same_origin(arr):
    min_idx = min(enumerate(arr), key=lambda x: sum(x[1]))[0]
    return np.roll(arr, shift=-min_idx, axis=0)


def appx_best_fit_ngon(mask_cv2, n: int = 4):
    contour = _find_largest_contour(mask_cv2)

    # # alternate method
    # peri = cv2.arcLength(contour, True)
    # poly = cv2.approxPolyDP(contour, 0.01 * peri, True)
    # poly = poly.reshape((4, 2))
    # poly = np.flip(poly, axis=0)
    # poly = np.float32(poly)
    # poly = roll_pts_to_have_same_origin(poly)
    # return poly

    # convex hull of the input mask
    poly = cv2.convexHull(contour)
    poly = np.array(poly).reshape((len(poly), 2))

    # run until we cut down to n vertices
    while len(poly) > n:
        best_candidate = None

        # for all edges in hull ( <edge_idx_1>, <edge_idx_2> ) ->
        for edge_idx_1 in range(len(poly)):
            edge_idx_2 = (edge_idx_1 + 1) % len(poly)

            adj_idx_1 = (edge_idx_1 - 1) % len(poly)
            adj_idx_2 = (edge_idx_1 + 2) % len(poly)

            edge_pt_1 = poly[edge_idx_1]
            edge_pt_2 = poly[edge_idx_2]
            adj_pt_1 = poly[adj_idx_1]
            adj_pt_2 = poly[adj_idx_2]

            angle1 = angle_between(adj_pt_1, edge_pt_1, edge_pt_2)
            angle2 = angle_between(edge_pt_1, edge_pt_2, adj_pt_2)

            # we need to first make sure that the sum of the interior angles the edge
            # makes with the two adjacent edges is more than 180°
            if angle1 + angle2 <= math.pi:
                continue

            # find the new vertex if we delete this edge
            adj_edge_1 = line(adj_pt_1, edge_pt_1)
            adj_edge_2 = line(edge_pt_2, adj_pt_2)
            intersect = intersection(adj_edge_1, adj_edge_2)

            # the area of the triangle we'll be adding
            area = triangle_area(edge_pt_1, intersect, edge_pt_2)

            # should be the lowest
            if best_candidate and best_candidate[1] < area:
                continue

            # delete the edge and add the intersection of adjacent edges to the hull
            better_hull = list(poly)
            better_hull[edge_idx_1] = intersect
            del better_hull[edge_idx_2]
            best_candidate = (better_hull, area)

        if not best_candidate:
            raise ValueError("Could not find the best fit n-gon!")

        poly = best_candidate[0]

    # back to python land
    poly = np.float32(poly)

    poly = roll_pts_to_have_same_origin(poly)

    return poly


def best_fit_rotated_rect(mask_cv2):
    contour = _find_largest_contour(mask_cv2)

    box2d = cv2.minAreaRect(contour)
    rect = cv2.boxPoints(box2d)

    rect = roll_pts_to_have_same_origin(rect)

    center, size, angle = box2d

    rect_width, rect_height = size
    if rect_width > rect_height:
        angle = (angle + 180) % 180
    else:
        angle = (angle + 90) % 180

    img_height, img_width, _ = mask_cv2.shape
    if img_width > img_height:
        rotation = angle - 180
    else:
        rotation = angle - 90

    rot_mat = cv2.getRotationMatrix2D(center, rotation, 1)
    rect = cv2.transform(rect.reshape((1, 4, 2)), rot_mat).reshape((4, 2))

    return rect


def _find_largest_contour(mask_cv2):
    mask_cv2 = cv2.cvtColor(mask_cv2, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(mask_cv2, 1, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, CONTOUR_HIREARCY, CONTOUR_MODE)
    best_contour = max(contours, key=len)
    return best_contour


def triangle_area(pt_a, pt_b, pt_c):
    a = math.sqrt(length2(pt_b, pt_c))
    b = math.sqrt(length2(pt_a, pt_c))
    c = math.sqrt(length2(pt_a, pt_b))

    s = (a + b + c) / 2

    area = math.sqrt((s * (s - a) * (s - b) * (s - c)))

    return area


def angle_between(pt_a, pt_b, pt_c):
    # square of lengths
    a2 = length2(pt_b, pt_c)
    b2 = length2(pt_a, pt_c)
    c2 = length2(pt_a, pt_b)

    # length of sides
    a = math.sqrt(a2)
    # b = math.sqrt(b2)
    c = math.sqrt(c2)

    # From Cosine law
    angle_b = math.acos((a2 + c2 - b2) / (2 * a * c))

    return angle_b


def length2(pt0, pt1):
    return (pt0[0] - pt1[0]) ** 2 + (pt0[1] - pt1[1]) ** 2


def line(p1, p2):
    A = p1[1] - p2[1]
    B = p2[0] - p1[0]
    C = p1[0] * p2[1] - p2[0] * p1[1]
    return A, B, -C


def intersection(L1, L2):
    D = L1[0] * L2[1] - L1[1] * L2[0]
    Dx = L1[2] * L2[1] - L1[1] * L2[2]
    Dy = L1[0] * L2[2] - L1[2] * L2[0]
    if D != 0:
        x = Dx / D
        y = Dy / D
        return x, y
    else:
        return False
