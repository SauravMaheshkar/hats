"""Methods for creating partitioned data paths"""

from __future__ import annotations

import re
from typing import Dict, List
from urllib.parse import urlencode

from fsspec.implementations.http import HTTPFileSystem

from hipscat.io.file_io.file_pointer import FilePointer, append_paths_to_pointer, get_fs
from hipscat.pixel_math.healpix_pixel import INVALID_PIXEL, HealpixPixel

ORDER_DIRECTORY_PREFIX = "Norder"
DIR_DIRECTORY_PREFIX = "Dir"
PIXEL_DIRECTORY_PREFIX = "Npix"
JOIN_ORDER_DIRECTORY_PREFIX = "join_Norder"
JOIN_DIR_DIRECTORY_PREFIX = "join_Dir"
JOIN_PIXEL_DIRECTORY_PREFIX = "join_Npix"

CATALOG_INFO_FILENAME = "catalog_info.json"
PARTITION_INFO_FILENAME = "partition_info.csv"
PARTITION_JOIN_INFO_FILENAME = "partition_join_info.csv"
PROVENANCE_INFO_FILENAME = "provenance_info.json"
PARQUET_METADATA_FILENAME = "_metadata"
PARQUET_COMMON_METADATA_FILENAME = "_common_metadata"
POINT_MAP_FILENAME = "point_map.fits"


def pixel_directory(
    catalog_base_dir: FilePointer,
    pixel_order: int,
    pixel_number: int | None = None,
    directory_number: int | None = None,
) -> FilePointer:
    """Create path pointer for a pixel directory. This will not create the directory.

    One of pixel_number or directory_number is required. The directory name will
    take the HiPS standard form of::

        <catalog_base_dir>/Norder=<pixel_order>/Dir=<directory number>

    Where the directory number is calculated using integer division as::

        (pixel_number/10000)*10000

    Args:
        catalog_base_dir (FilePointer): base directory of the catalog (includes catalog name)
        pixel_order (int): the healpix order of the pixel
        directory_number (int): directory number
        pixel_number (int): the healpix pixel
    Returns:
        FilePointer directory name
    """
    norder = int(pixel_order)
    if directory_number is not None:
        ndir = directory_number
    elif pixel_number is not None:
        npix = int(pixel_number)
        ndir = int(npix / 10_000) * 10_000
    else:
        raise ValueError("One of pixel_number or directory_number is required to create pixel directory")
    return create_hive_directory_name(
        catalog_base_dir,
        [ORDER_DIRECTORY_PREFIX, DIR_DIRECTORY_PREFIX],
        [norder, ndir],
    )


def get_healpix_from_path(path: str) -> HealpixPixel:
    """Find the `pixel_order` and `pixel_number` from a string like the
    following::

        Norder=<pixel_order>/Dir=<directory number>/Npix=<pixel_number>.parquet

    NB: This expects the format generated by the `pixel_catalog_file` method

    Args:
        path (str): path to parse

    Returns:
        Constructed HealpixPixel object representing the pixel in the path.
        `INVALID_PIXEL` if the path doesn't match the expected pattern for any reason.
    """
    match = re.match(r".*Norder=(\d*).*Npix=(\d*).*", path)
    if not match:
        return INVALID_PIXEL
    order, pixel = match.groups()
    return HealpixPixel(int(order), int(pixel))


def pixel_catalog_files(
    catalog_base_dir: FilePointer,
    pixels: List[HealpixPixel],
    query_params: dict = None,
    storage_options: Dict | None = None,
) -> List[FilePointer]:
    """Create a list of path *pointers* for pixel catalog files. This will not create the directory
    or files.

    The catalog file names will take the HiPS standard form of::

        <catalog_base_dir>/Norder=<pixel_order>/Dir=<directory number>/Npix=<pixel_number>.parquet

    Where the directory number is calculated using integer division as::

        (pixel_number/10000)*10000

    Args:
        catalog_base_dir (FilePointer): base directory of the catalog (includes catalog name)
        pixels (List[HealpixPixel]): the healpix pixels to create pointers to
        query_params (dict): Params to append to URL. Ex: {'cols': ['ra', 'dec'], 'fltrs': ['r>=10', 'g<18']}
        storage_options (dict): the storage options for the file system to target when generating the paths

    Returns (List[FilePointer]):
        A list of paths to the pixels, in the same order as the input pixel list.
    """
    fs, _ = get_fs(catalog_base_dir, storage_options)
    base_path_stripped = catalog_base_dir.removesuffix(fs.sep)

    url_params = ""
    if isinstance(fs, HTTPFileSystem) and query_params:
        url_params = dict_to_query_urlparams(query_params)

    return [
        fs.sep.join(
            [
                base_path_stripped,
                f"{ORDER_DIRECTORY_PREFIX}={pixel.order}",
                f"{DIR_DIRECTORY_PREFIX}={pixel.dir}",
                f"{PIXEL_DIRECTORY_PREFIX}={pixel.pixel}.parquet" + url_params,
            ]
        )
        for pixel in pixels
    ]


def dict_to_query_urlparams(query_params: dict) -> str:
    """Converts a dictionary to a url query parameter string

    Args:
        query_params (dict): dictionary of query parameters.
    Returns:
        query parameter string to append to a url
    """

    if not query_params:
        return ""

    query = {}
    for key, value in query_params.items():
        if isinstance(value, list):
            value = ",".join(value).replace(" ", "")
        query[key] = value

    # Build the query string and add the "?" prefix
    url_params = "?" + urlencode(query, doseq=True)
    return url_params


def pixel_catalog_file(catalog_base_dir: FilePointer, pixel_order: int, pixel_number: int) -> FilePointer:
    """Create path *pointer* for a pixel catalog file. This will not create the directory
    or file.

    The catalog file name will take the HiPS standard form of::

        <catalog_base_dir>/Norder=<pixel_order>/Dir=<directory number>/Npix=<pixel_number>.parquet

    Where the directory number is calculated using integer division as::

        (pixel_number/10000)*10000

    Args:
        catalog_base_dir (FilePointer): base directory of the catalog (includes catalog name)
        pixel_order (int): the healpix order of the pixel
        pixel_number (int): the healpix pixel
    Returns:
        string catalog file name
    """
    return create_hive_parquet_file_name(
        catalog_base_dir,
        [ORDER_DIRECTORY_PREFIX, DIR_DIRECTORY_PREFIX, PIXEL_DIRECTORY_PREFIX],
        [int(pixel_order), int(pixel_number / 10_000) * 10_000, int(pixel_number)],
    )


def create_hive_directory_name(base_dir, partition_token_names, partition_token_values):
    """Create path *pointer* for a directory with hive partitioning naming.
    This will not create the directory.

    The directory name will have the form of::

        <catalog_base_dir>/<name_1>=<value_1>/.../<name_n>=<value_n>

    Args:
        catalog_base_dir (FilePointer): base directory of the catalog (includes catalog name)
        partition_token_names (list[string]): list of partition name parts.
        partition_token_values (list[string]): list of partition values that
            correspond to the token name parts.
    """
    partition_tokens = [
        f"{name}={value}" for name, value in zip(partition_token_names, partition_token_values)
    ]
    return append_paths_to_pointer(base_dir, *partition_tokens)


def create_hive_parquet_file_name(base_dir, partition_token_names, partition_token_values):
    """Create path *pointer* for a single parquet with hive partitioning naming.

    The file name will have the form of::

        <catalog_base_dir>/<name_1>=<value_1>/.../<name_n>=<value_n>.parquet

    Args:
        catalog_base_dir (FilePointer): base directory of the catalog (includes catalog name)
        partition_token_names (list[string]): list of partition name parts.
        partition_token_values (list[string]): list of partition values that
            correspond to the token name parts.
    """
    partition_tokens = [
        f"{name}={value}" for name, value in zip(partition_token_names, partition_token_values)
    ]
    return f"{append_paths_to_pointer(base_dir, *partition_tokens)}.parquet"


def get_catalog_info_pointer(catalog_base_dir: FilePointer) -> FilePointer:
    """Get file pointer to `catalog_info.json` metadata file

    Args:
        catalog_base_dir: pointer to base catalog directory
    Returns:
        File Pointer to the catalog's `catalog_info.json` file
    """
    return append_paths_to_pointer(catalog_base_dir, CATALOG_INFO_FILENAME)


def get_partition_info_pointer(catalog_base_dir: FilePointer) -> FilePointer:
    """Get file pointer to `partition_info.csv` metadata file

    Args:
        catalog_base_dir: pointer to base catalog directory
    Returns:
        File Pointer to the catalog's `partition_info.csv` file
    """
    return append_paths_to_pointer(catalog_base_dir, PARTITION_INFO_FILENAME)


def get_provenance_pointer(catalog_base_dir: FilePointer) -> FilePointer:
    """Get file pointer to `provenance_info.json` metadata file

    Args:
        catalog_base_dir: pointer to base catalog directory
    Returns:
        File Pointer to the catalog's `provenance_info.json` file
    """
    return append_paths_to_pointer(catalog_base_dir, PROVENANCE_INFO_FILENAME)


def get_common_metadata_pointer(catalog_base_dir: FilePointer) -> FilePointer:
    """Get file pointer to `_common_metadata` parquet metadata file

    Args:
        catalog_base_dir: pointer to base catalog directory
    Returns:
        File Pointer to the catalog's `_common_metadata` file
    """
    return append_paths_to_pointer(catalog_base_dir, PARQUET_COMMON_METADATA_FILENAME)


def get_parquet_metadata_pointer(catalog_base_dir: FilePointer) -> FilePointer:
    """Get file pointer to `_metadata` parquet metadata file

    Args:
        catalog_base_dir: pointer to base catalog directory
    Returns:
        File Pointer to the catalog's `_metadata` file
    """
    return append_paths_to_pointer(catalog_base_dir, PARQUET_METADATA_FILENAME)


def get_point_map_file_pointer(catalog_base_dir: FilePointer) -> FilePointer:
    """Get file pointer to `point_map.fits` FITS image file.

    Args:
        catalog_base_dir: pointer to base catalog directory
    Returns:
        File Pointer to the catalog's `point_map.fits` FITS image file.
    """
    return append_paths_to_pointer(catalog_base_dir, POINT_MAP_FILENAME)


def get_partition_join_info_pointer(catalog_base_dir: FilePointer) -> FilePointer:
    """Get file pointer to `partition_join_info.csv` association metadata file

    Args:
        catalog_base_dir: pointer to base catalog directory
    Returns:
        File Pointer to the catalog's `partition_join_info.csv` association metadata file
    """
    return append_paths_to_pointer(catalog_base_dir, PARTITION_JOIN_INFO_FILENAME)
