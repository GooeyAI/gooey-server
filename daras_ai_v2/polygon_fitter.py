import cv2

import numpy as np
import sympy


CONTOUR_HIREARCY = cv2.RETR_EXTERNAL
CONTOUR_MODE = cv2.CHAIN_APPROX_SIMPLE


def roll_pts_to_have_same_origin(arr):
    min_idx = min(enumerate(arr), key=lambda x: sum(x[1]))[0]
    return np.roll(arr, shift=min_idx, axis=0)


def appx_best_fit_ngon(mask_cv2, n: int = 4) -> list[(int, int)]:
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

    # to sympy land
    poly = [sympy.Point(*pt) for pt in poly]

    # run until we cut down to n vertices
    while len(poly) > n:
        best_candidate = None

        # for all edges in hull ( <edge_idx_1>, <edge_idx_2> ) ->
        for edge_idx_1 in range(len(poly)):
            edge_idx_2 = (edge_idx_1 + 1) % len(poly)

            adj_idx_1 = (edge_idx_1 - 1) % len(poly)
            adj_idx_2 = (edge_idx_1 + 2) % len(poly)

            edge_pt_1 = sympy.Point(*poly[edge_idx_1])
            edge_pt_2 = sympy.Point(*poly[edge_idx_2])
            adj_pt_1 = sympy.Point(*poly[adj_idx_1])
            adj_pt_2 = sympy.Point(*poly[adj_idx_2])

            subpoly = sympy.Polygon(adj_pt_1, edge_pt_1, edge_pt_2, adj_pt_2)
            angle1 = subpoly.angles[edge_pt_1]
            angle2 = subpoly.angles[edge_pt_2]

            # we need to first make sure that the sum of the interior angles the edge
            # makes with the two adjacent edges is more than 180°
            if sympy.N(angle1 + angle2) <= sympy.pi:
                continue

            # find the new vertex if we delete this edge
            adj_edge_1 = sympy.Line(adj_pt_1, edge_pt_1)
            adj_edge_2 = sympy.Line(edge_pt_2, adj_pt_2)
            intersect = adj_edge_1.intersection(adj_edge_2)[0]

            # the area of the triangle we'll be adding
            area = sympy.N(sympy.Triangle(edge_pt_1, intersect, edge_pt_2).area)
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

    center, size, angle = box2d

    rect_width, rect_height = size
    if rect_width > rect_height:
        angle += 180
    else:
        angle += 90

    img_height, img_width, _ = mask_cv2.shape
    if img_width > img_height:
        rotation = angle - 180
    else:
        rotation = angle - 90

    rot_mat = cv2.getRotationMatrix2D(center, rotation, 1)
    rect = cv2.transform(rect.reshape((1, 4, 2)), rot_mat).reshape((4, 2))

    rect = roll_pts_to_have_same_origin(rect)

    return rect


def _find_largest_contour(mask_cv2):
    mask_cv2 = cv2.cvtColor(mask_cv2, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(mask_cv2, 1, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, CONTOUR_HIREARCY, CONTOUR_MODE)
    best_contour = max(contours, key=len)
    return best_contour
