from __future__ import annotations

from enum import Enum
from typing import List, Tuple

import numpy as np

import hats.pixel_math.healpix_shim as hp


class ValidatorsErrors(str, Enum):
    """Error messages for the coordinate validators"""

    INVALID_DEC = "declination must be in the -90.0 to 90.0 degree range"
    INVALID_RADIUS = "cone radius must be positive"
    INVALID_NUM_VERTICES = "polygon must contain a minimum of 3 vertices"
    DUPLICATE_VERTICES = "polygon has duplicated vertices"
    DEGENERATE_POLYGON = "polygon is degenerate"
    INVALID_RADEC_RANGE = "invalid ra or dec range"
    INVALID_COORDS_SHAPE = "invalid coordinates shape"
    INVALID_CONCAVE_SHAPE = "polygon must be convex"


def validate_radius(radius_arcsec: float):
    """Validates that a cone search radius is positive

    Args:
        radius_arcsec (float): The cone radius, in arcseconds

    Raises:
        ValueError: if radius is non-positive
    """
    if radius_arcsec <= 0:
        raise ValueError(ValidatorsErrors.INVALID_RADIUS.value)


def validate_declination_values(dec: float | List[float]):
    """Validates that declination values are in the [-90,90] degree range

    Args:
        dec (float | List[float]): The declination values to be validated

    Raises:
        ValueError: if declination values are not in the [-90,90] degree range
    """
    dec_values = np.array(dec)
    lower_bound, upper_bound = -90.0, 90.0
    if not np.all((dec_values >= lower_bound) & (dec_values <= upper_bound)):
        raise ValueError(ValidatorsErrors.INVALID_DEC.value)


def validate_polygon(vertices: list[tuple[float, float]]):
    """Checks if the polygon contain a minimum of three vertices, that they are
    unique and that the polygon does not fall on a great circle.

    Args:
        vertices (list[tuple[float,float]]): The list of vertice coordinates for
            the polygon, (ra, dec), in degrees.

    Raises:
        ValueError: exception if the polygon is invalid.
    """
    vertices = np.array(vertices)
    if vertices.shape[1] != 2:
        raise ValueError(ValidatorsErrors.INVALID_COORDS_SHAPE.value)
    _, dec = vertices.T
    validate_declination_values(dec)
    if len(vertices) < 3:
        raise ValueError(ValidatorsErrors.INVALID_NUM_VERTICES.value)
    if len(vertices) != len(np.unique(vertices, axis=0)):
        raise ValueError(ValidatorsErrors.DUPLICATE_VERTICES.value)
    check_polygon_is_valid(vertices)


def check_polygon_is_valid(vertices: np.ndarray):
    """Check if the polygon has no degenerate corners and it is convex.

    Based on HEALpy's `queryPolygonInternal` implementation:
    https://github.com/cds-astro/cds.moc/blob/master/src/healpix/essentials/HealpixBase.java.

    Args:
        vertices (np.ndarray): The polygon vertices, in cartesian coordinates

    Returns:
        True if polygon is valid, False otherwise.
    """
    vertices_xyz = hp.ang2vec(*vertices.T, lonlat=True)
    n_vertices = len(vertices_xyz)
    flip = 0
    for i in range(n_vertices):
        normal = np.cross(vertices_xyz[i], vertices_xyz[(i + 1) % n_vertices])
        hnd = normal.dot(vertices_xyz[(i + 2) % n_vertices])
        if np.isclose(hnd, 0, atol=1e-10):
            raise ValueError(ValidatorsErrors.DEGENERATE_POLYGON.value)
        if i == 0:
            flip = -1 if hnd < 0 else 1
        elif flip * hnd <= 0:
            raise ValueError(ValidatorsErrors.INVALID_CONCAVE_SHAPE.value)


def validate_box(ra: Tuple[float, float] | None, dec: Tuple[float, float] | None):
    """Checks if ra and dec values are valid for the box search.

    - At least one range of ra or dec must have been provided
    - Ranges must be pairs of non-duplicate minimum and maximum values, in degrees
    - Declination values, if existing, must be in ascending order
    - Declination values, if existing, must be in the [-90,90] degree range

    Args:
        ra (Tuple[float, float]): Right ascension range, in degrees
        dec (Tuple[float, float]): Declination range, in degrees
    """
    invalid_range = False
    if ra is not None:
        if len(ra) != 2 or len(ra) != len(set(ra)):
            invalid_range = True
    if dec is not None:
        if len(dec) != 2 or dec[0] >= dec[1]:
            invalid_range = True
        validate_declination_values(list(dec))
    if (ra is None and dec is None) or invalid_range:
        raise ValueError(ValidatorsErrors.INVALID_RADEC_RANGE.value)
