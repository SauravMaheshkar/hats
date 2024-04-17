from typing import List

import numba
import numpy as np
import pandas as pd
from numba import njit

from hipscat.pixel_math.healpix_pixel_function import get_pixels_from_intervals
from hipscat.pixel_tree.pixel_alignment_types import PixelAlignmentType
from hipscat.pixel_tree.pixel_tree import PixelTree

LEFT_INCLUDE_ALIGNMENT_TYPES = [PixelAlignmentType.LEFT, PixelAlignmentType.OUTER]
RIGHT_INCLUDE_ALIGNMENT_TYPES = [PixelAlignmentType.RIGHT, PixelAlignmentType.OUTER]


NONE_PIX = np.array([-1, -1])
LEFT_SIDE = True
RIGHT_SIDE = False


# pylint: disable=R0903
class PixelAlignment:
    """Represents how two pixel trees align with each other, meaning which pixels match
    or overlap between the catalogs, and a new tree with the smallest pixels from each tree

    For more information on the pixel alignment algorithm, view this document:
    https://docs.google.com/document/d/1gqb8qb3HiEhLGNav55LKKFlNjuusBIsDW7FdTkc5mJU/edit?usp=sharing

    Attributes:
        pixel_mapping: A dataframe where each row contains a pixel from each tree that match, and
            which pixel in the aligned tree they match with
        pixel_tree: The aligned tree generated by using the smallest pixels in each tree. For
            example, a tree with pixels at order 0, pixel 1, and a tree with order 1, pixel 4,5,6,
            and 7, would result in the smaller order 1 pixels in the aligned tree.
        alignment_type: The type of alignment describing how to handle nodes which exist in one tree
            but not the other. Options are:

                - inner - only use pixels that appear in both catalogs
                - left - use all pixels that appear in the left catalog and any overlapping from the right
                - right - use all pixels that appear in the right catalog and any overlapping from the left
                - outer - use all pixels from both catalogs
    """

    PRIMARY_ORDER_COLUMN_NAME = "primary_Norder"
    PRIMARY_PIXEL_COLUMN_NAME = "primary_Npix"
    JOIN_ORDER_COLUMN_NAME = "join_Norder"
    JOIN_PIXEL_COLUMN_NAME = "join_Npix"
    ALIGNED_ORDER_COLUMN_NAME = "aligned_Norder"
    ALIGNED_PIXEL_COLUMN_NAME = "aligned_Npix"

    def __init__(
        self,
        aligned_tree: PixelTree,
        pixel_mapping: pd.DataFrame,
        alignment_type: PixelAlignmentType,
    ) -> None:
        self.pixel_tree = aligned_tree
        self.pixel_mapping = pixel_mapping
        self.alignment_type = alignment_type


def align_trees(
    left: PixelTree, right: PixelTree, alignment_type: PixelAlignmentType = PixelAlignmentType.INNER
) -> PixelAlignment:
    """Generate a `PixelAlignment` object from two pixel trees

    A `PixelAlignment` represents how two pixel trees align with each other, meaning which pixels
    match or overlap between the catalogs, and includes a new tree with the smallest pixels from
    each tree

    For more information on the pixel alignment algorithm, view this document:
    https://docs.google.com/document/d/1gqb8qb3HiEhLGNav55LKKFlNjuusBIsDW7FdTkc5mJU/edit?usp=sharing

    Args:
        left: The left tree to align
        right: The right tree to align
        alignment_type: The type of alignment describing how to handle nodes which exist in one tree
            but not the other. Options are:

                - inner - only use pixels that appear in both catalogs
                - left - use all pixels that appear in the left catalog and any overlapping from the right
                - right - use all pixels that appear in the right catalog and any overlapping from the left
                - outer - use all pixels from both catalogs

    Returns:
        The `PixelAlignment` object with the alignment from the two trees
    """
    max_n = max(left.tree_order, right.tree_order)

    # Shifts left and right intervals to the same order
    left_aligned = left.tree << (2 * (max_n - left.tree_order))
    right_aligned = right.tree << (2 * (max_n - right.tree_order))

    if alignment_type == PixelAlignmentType.INNER:
        mapping = perform_inner_align_trees(left_aligned, right_aligned)
    else:
        include_all_left = alignment_type in LEFT_INCLUDE_ALIGNMENT_TYPES
        include_all_right = alignment_type in RIGHT_INCLUDE_ALIGNMENT_TYPES
        mapping = perform_align_trees(left_aligned, right_aligned, include_all_left, include_all_right)
        mapping = np.array(mapping).T
    result_tree = mapping[4:6].T if len(mapping) > 0 else np.empty((0, 2), dtype=np.int64)
    result_mapping = get_pixel_mapping_df(mapping, max_n)
    return PixelAlignment(PixelTree(result_tree, max_n), result_mapping, alignment_type)


def get_pixel_mapping_df(mapping: np.ndarray, map_order: int) -> pd.DataFrame:
    """Construct a DataFrame with HEALPix orders and pixels mapping left right and aligned pixels

    Args:
        mapping (np.ndarray): array of shape (6, len(aligned_pixels)) where the first two rows are the
            intervals for the left pixels, the next two for right pixels, and the last two for aligned pixels
        map_order (int): The HEALPix order of the intervals in the mapping array

    Returns:
        A DataFrame with the orders and pixels of the aligned left and right pixels,
    """
    if len(mapping) > 0:
        l_orders, l_pixels = get_pixels_from_intervals(mapping[0:2].T, map_order).T
        r_orders, r_pixels = get_pixels_from_intervals(mapping[2:4].T, map_order).T
        a_orders, a_pixels = get_pixels_from_intervals(mapping[4:6].T, map_order).T
    else:
        l_orders, l_pixels, r_orders, r_pixels, a_orders, a_pixels = [], [], [], [], [], []
    result_mapping = pd.DataFrame.from_dict(
        {
            PixelAlignment.PRIMARY_ORDER_COLUMN_NAME: l_orders,
            PixelAlignment.PRIMARY_PIXEL_COLUMN_NAME: l_pixels,
            PixelAlignment.JOIN_ORDER_COLUMN_NAME: r_orders,
            PixelAlignment.JOIN_PIXEL_COLUMN_NAME: r_pixels,
            PixelAlignment.ALIGNED_ORDER_COLUMN_NAME: a_orders,
            PixelAlignment.ALIGNED_PIXEL_COLUMN_NAME: a_pixels,
        }
    )
    result_mapping.replace(-1, None, inplace=True)
    return result_mapping


# pylint: disable=too-many-statements
@njit(numba.int64[::1, :](numba.int64[:, :], numba.int64[:, :]))
def perform_inner_align_trees(
    left: np.ndarray,
    right: np.ndarray,
) -> np.ndarray:
    """Performs an inner alignment on arrays of pixel intervals

    Pixel interval lists must be of to the same order

    Args:
        left (np.ndarray): the left array of intervals
        right (np.ndarray): the right array of intervals

    Returns (List[np.ndarray]):
        The pixel mapping of the matching left, right, and aligned pixels with each row containing an array of
        [left_order, left_pixel, right_order, right_pixel, aligned_order, aligned_pixel]
    """
    max_out_len = left.shape[0] + right.shape[0]
    mapping = np.zeros((max_out_len, 6), dtype=np.int64)
    left_index = 0
    right_index = 0
    last_index = 0
    while left_index < len(left) and right_index < len(right):
        left_pix = left[left_index]
        right_pix = right[right_index]
        if left_pix[0] >= right_pix[1]:
            # left pix ahead of right, no overlap, so move right on
            right_index += 1
            continue
        if right_pix[0] >= left_pix[1]:
            # right pix ahead of left, no overlap, so move left on
            left_index += 1
            continue
        left_size = left_pix[1] - left_pix[0]
        right_size = right_pix[1] - right_pix[0]
        if left_size == right_size:
            # overlapping & same size => same pixel so add and move both on
            mapping[last_index][0:2], mapping[last_index][2:4], mapping[last_index][4:6] = (
                left_pix,
                right_pix,
                left_pix,
            )
            last_index += 1
            left_index += 1
            right_index += 1
            continue
        if left_size < right_size:
            # overlapping and left smaller so add left and move left on
            mapping[last_index][0:2], mapping[last_index][2:4], mapping[last_index][4:6] = (
                left_pix,
                right_pix,
                left_pix,
            )
            last_index += 1
            left_index += 1
            continue
        # else overlapping and right smaller so add right and move right on
        mapping[last_index][0:2], mapping[last_index][2:4], mapping[last_index][4:6] = (left_pix, right_pix, right_pix)
        last_index += 1
        right_index += 1
    return mapping[:last_index].T


@njit(
    numba.types.void(
        numba.int64,
        numba.int64,
        numba.int64[:],
        numba.boolean,
        numba.types.List(numba.int64[::1]),
    )
)
def _add_pixels_until(
    add_from: int,
    add_to: int,
    matching_pix: np.ndarray,
    is_left_pixel: bool,
    mapping: List[np.ndarray],
):
    """Adds pixels of the greatest possible order to fill output from `add-from` to `add_to`

    Adds these pixels to the mapping as the aligned pixel, with matching pix added as either the left or right
    side of the mapping and none pixel for the other.

    Args:
        add_from (int): The pixel number to add pixels from
        add_to (int): The pixel number to add pixels to
        matching_pix (int): The matching pixel from the side of the catalog that exists to map the new pixels
            to in the mapping
        is_left_pixel (int): Is the matching pixel from the left side of the alignment
        mapping (List[np.ndarray]): The List mapping left, right, and aligned pixels to add the new pixels to
    """
    while add_from < add_to:
        # maximum power of 4 that is a factor of add_from
        max_p4_from = add_from & -add_from
        if max_p4_from & 0xAAAAAAAAAAAAAAA:
            max_p4_from = max_p4_from >> 1

        # maximum power of 4 less than or equal to (add_to - add_from)
        max_p4_to_log2 = np.int64(np.log2(add_to - add_from))
        max_p4_to = 1 << (max_p4_to_log2 - (max_p4_to_log2 & 1))

        pixel_size = min(max_p4_to, max_p4_from)
        pixel = np.array([add_from, add_from + pixel_size])
        if is_left_pixel:
            mapping.append(np.concatenate((matching_pix, NONE_PIX, pixel)))
        else:
            mapping.append(np.concatenate((NONE_PIX, matching_pix, pixel)))
        add_from = add_from + pixel_size


@njit(
    numba.types.void(
        numba.int64,
        numba.int64[:, :],
        numba.int64,
        numba.boolean,
        numba.types.List(numba.int64[::1]),
    )
)
def _add_remaining_pixels(
    added_until: int,
    pixel_list: np.ndarray,
    index: int,
    is_left_pixel: bool,
    mapping: List[np.ndarray],
):
    """Adds pixels to output and mapping from a given index in a list of pixel intervals

    Args:
        added_until (int): Where the alignment has been added until
        pixel_list (np.ndarray): The list of pixels from the side of the alignment to add the remaining
            pixels of
        index (int): The index of the pixel list to add the pixels from
        is_left_pixel (bool): Is the pixel list from left side of the alignment
        mapping (List[np.ndarray]): The List mapping left, right, and aligned pixels to add the new pixels to
    """

    # first pixel may be partially covered
    pix = pixel_list[index]
    if pix[0] < added_until < pix[1]:
        _add_pixels_until(added_until, pix[1], pix, is_left_pixel, mapping)
        index += 1
    if added_until >= pix[1]:
        index += 1
    while index < len(pixel_list):
        pix = pixel_list[index]
        if is_left_pixel:
            mapping.append(np.concatenate((pix, NONE_PIX, pix)))
        else:
            mapping.append(np.concatenate((NONE_PIX, pix, pix)))
        index += 1


# pylint: disable=too-many-statements
@njit(numba.types.List(numba.int64[::1])(numba.int64[:, :], numba.int64[:, :], numba.boolean, numba.boolean))
def perform_align_trees(
    left: np.ndarray,
    right: np.ndarray,
    include_all_left: bool,
    include_all_right: bool,
) -> List[np.ndarray]:
    """Performs an alignment on arrays of pixel intervals

    Pixel interval lists must be of to the same order

    Args:
        left (np.ndarray): the left array of intervals
        right (np.ndarray): the right array of intervals
        include_all_left (bool): if all pixels from the left tree should be covered in the final alignment
        include_all_right (bool): if all pixels from the right tree should be covered in the final alignment

    Returns (List[np.ndarray]):
        The pixel mapping of the matching left, right, and aligned pixels with each row containing an array of
        [left_order, left_pixel, right_order, right_pixel, aligned_order, aligned_pixel]
    """
    added_until = 0
    mapping = []
    left_index = 0
    right_index = 0
    while left_index < len(left) and right_index < len(right):
        left_pix = left[left_index]
        right_pix = right[right_index]
        if left_pix[0] >= right_pix[1]:
            # left pix ahead of right, no overlap, so move right on
            if include_all_right:
                if added_until <= right_pix[0]:
                    # should cover right pix and no coverage of right pix => add whole right pix
                    mapping.append(np.concatenate((NONE_PIX, right_pix, right_pix)))
                    added_until = right_pix[1]
                elif added_until < right_pix[1]:
                    # should cover right pix and partial coverage of right pix => cover rest of right pix
                    _add_pixels_until(added_until, right_pix[1], right_pix, RIGHT_SIDE, mapping)
                    added_until = right_pix[1]
            right_index += 1
            continue
        if right_pix[0] >= left_pix[1]:
            # right pix ahead of left, no overlap, so move left on
            if include_all_left:
                if added_until <= left_pix[0]:
                    # should cover left pix and no coverage of left pix => add whole left pix
                    mapping.append(np.concatenate((left_pix, NONE_PIX, left_pix)))
                    added_until = left_pix[1]
                elif added_until < left_pix[1]:
                    # should cover left pix and partial coverage of left pix => cover rest of left pix
                    _add_pixels_until(added_until, left_pix[1], left_pix, LEFT_SIDE, mapping)
                    added_until = left_pix[1]
            left_index += 1
            continue
        left_size = left_pix[1] - left_pix[0]
        right_size = right_pix[1] - right_pix[0]
        if left_size == right_size:
            # overlapping & same size => same pixel so add and move both on
            mapping.append(np.concatenate((left_pix, right_pix, left_pix)))
            added_until = left_pix[1]
            left_index += 1
            right_index += 1
            continue
        if left_size < right_size:
            # overlapping and left smaller so add left and move left on
            if include_all_right and left_pix[0] > right_pix[0] and left_pix[0] > added_until:
                # need to cover all of right pix and start of left pix has a gap to current coverage
                # so fill in gap
                add_from = max(added_until, right_pix[0])
                _add_pixels_until(add_from, left_pix[0], right_pix, RIGHT_SIDE, mapping)
            mapping.append(np.concatenate((left_pix, right_pix, left_pix)))
            added_until = left_pix[1]
            left_index += 1
            continue
        # else overlapping and right smaller so add right and move right on

        if include_all_left and right_pix[0] > left_pix[0] and right_pix[0] > added_until:
            # need to cover all of left pix and start of right pix has a gap to current coverage
            # so fill in gap
            add_from = max(added_until, left_pix[0])
            _add_pixels_until(add_from, right_pix[0], left_pix, LEFT_SIDE, mapping)
        mapping.append(np.concatenate((left_pix, right_pix, right_pix)))
        added_until = right_pix[1]
        right_index += 1

    # After loop, if either tree needs to be fully covered and loop hasn't checked all pixels from that tree
    # then cover the remaining pixels
    if include_all_right and right_index < len(right):
        _add_remaining_pixels(added_until, right, right_index, RIGHT_SIDE, mapping)
    if include_all_left and left_index < len(left):
        _add_remaining_pixels(added_until, left, left_index, LEFT_SIDE, mapping)
    return mapping
