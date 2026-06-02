from lbh.coordinates import Box, CoordinateSpace, CoordinateTransform, Point, Size


def test_resized_image_to_desktop_round_trip():
    transform = CoordinateTransform(desktop_size=Size(1920, 1080), resized_size=Size(1280, 720))
    desktop_point = transform.point_to_desktop(Point(640, 360, CoordinateSpace.RESIZED_IMAGE))
    assert desktop_point.x == 960
    assert desktop_point.y == 540
    resized_point = transform.desktop_to_resized_image(desktop_point)
    assert resized_point.x == 640
    assert resized_point.y == 360


def test_active_window_coordinate_conversion():
    transform = CoordinateTransform(
        desktop_size=Size(1920, 1080),
        resized_size=Size(1280, 720),
        active_window_box=Box(100, 200, 900, 700, CoordinateSpace.DESKTOP),
    )
    desktop_point = transform.point_to_desktop(Point(20, 30, CoordinateSpace.ACTIVE_WINDOW))
    assert desktop_point.x == 120
    assert desktop_point.y == 230
