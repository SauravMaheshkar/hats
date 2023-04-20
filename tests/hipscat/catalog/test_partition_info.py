"""Tests of partition info functionality"""

from hipscat.catalog import PartitionInfo
from hipscat.io import paths
from hipscat.pixel_math import HealpixPixel


def test_load_partition_info_small_sky(small_sky_dir):
    """Instantiate the partition info for catalog with 1 pixel"""
    partition_info_file = paths.get_partition_info_pointer(small_sky_dir)
    partitions = PartitionInfo.read_from_file(partition_info_file)

    order_pixel_pairs = partitions.get_healpix_pixels()
    assert len(order_pixel_pairs) == 1
    expected = [HealpixPixel(0, 11)]
    assert order_pixel_pairs == expected


def test_load_partition_info_small_sky_order1(small_sky_order1_dir):
    """Instantiate the partition info for catalog with 4 pixels"""
    partition_info_file = paths.get_partition_info_pointer(small_sky_order1_dir)
    partitions = PartitionInfo.read_from_file(partition_info_file)

    order_pixel_pairs = partitions.get_healpix_pixels()
    assert len(order_pixel_pairs) == 4
    expected = [
        HealpixPixel(1, 44),
        HealpixPixel(1, 45),
        HealpixPixel(1, 46),
        HealpixPixel(1, 47),
    ]
    assert order_pixel_pairs == expected
