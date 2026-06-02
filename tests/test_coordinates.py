from lbh.coordinates import ResizeTransform, resized_dimensions
from lbh.models import CoordSpace, Point, BBox


def test_resized_dimensions_keeps_aspect():
    assert resized_dimensions(2560, 1440, 1280) == (1280, 720)
    assert resized_dimensions(1000, 500, 1280) == (1000, 500)


def test_point_resized_to_desktop():
    transform = ResizeTransform(desktop_width=2560, desktop_height=1440, image_width=1280, image_height=720)
    p = transform.point_to_desktop(Point(640, 360, CoordSpace.RESIZED_IMAGE))
    assert p.x == 1280
    assert p.y == 720
    assert p.space == CoordSpace.DESKTOP


def test_bbox_resized_to_desktop():
    transform = ResizeTransform(desktop_width=2560, desktop_height=1440, image_width=1280, image_height=720)
    b = transform.bbox_to_desktop(BBox(10, 20, 30, 40, CoordSpace.RESIZED_IMAGE))
    assert (b.x1, b.y1, b.x2, b.y2) == (20, 40, 60, 80)
