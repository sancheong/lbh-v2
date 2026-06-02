from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .models import BBox, CoordSpace, Point


def resized_dimensions(width: int, height: int, max_width: int) -> tuple[int, int]:
    if max_width <= 0:
        raise ValueError("max_width must be positive")
    if width <= max_width:
        return width, height
    new_height = round(height * max_width / width)
    return max_width, new_height


@dataclass(frozen=True)
class ResizeTransform:
    desktop_width: int
    desktop_height: int
    image_width: int
    image_height: int

    @property
    def scale_x_to_desktop(self) -> float:
        return self.desktop_width / self.image_width

    @property
    def scale_y_to_desktop(self) -> float:
        return self.desktop_height / self.image_height

    def point_to_desktop(self, point: Point) -> Point:
        if point.space == CoordSpace.DESKTOP:
            return point
        if point.space != CoordSpace.RESIZED_IMAGE:
            raise ValueError(f"Cannot convert {point.space} with ResizeTransform")
        return Point(
            round(point.x * self.scale_x_to_desktop),
            round(point.y * self.scale_y_to_desktop),
            CoordSpace.DESKTOP,
        )

    def bbox_to_desktop(self, bbox: BBox) -> BBox:
        if bbox.space == CoordSpace.DESKTOP:
            return bbox
        if bbox.space != CoordSpace.RESIZED_IMAGE:
            raise ValueError(f"Cannot convert {bbox.space} with ResizeTransform")
        return BBox(
            round(bbox.x1 * self.scale_x_to_desktop),
            round(bbox.y1 * self.scale_y_to_desktop),
            round(bbox.x2 * self.scale_x_to_desktop),
            round(bbox.y2 * self.scale_y_to_desktop),
            CoordSpace.DESKTOP,
        )


@dataclass(frozen=True)
class CropTransform:
    """Map crop-image coordinates into desktop coordinates.

    The crop is assumed to be cut from desktop coordinates, optionally resized.
    """

    desktop_x1: int
    desktop_y1: int
    desktop_width: int
    desktop_height: int
    crop_image_width: int
    crop_image_height: int

    @property
    def scale_x_to_desktop(self) -> float:
        return self.desktop_width / self.crop_image_width

    @property
    def scale_y_to_desktop(self) -> float:
        return self.desktop_height / self.crop_image_height

    def point_to_desktop(self, point: Point) -> Point:
        if point.space == CoordSpace.DESKTOP:
            return point
        if point.space != CoordSpace.CROP_IMAGE:
            raise ValueError(f"Cannot convert {point.space} with CropTransform")
        return Point(
            self.desktop_x1 + round(point.x * self.scale_x_to_desktop),
            self.desktop_y1 + round(point.y * self.scale_y_to_desktop),
            CoordSpace.DESKTOP,
        )

    def bbox_to_desktop(self, bbox: BBox) -> BBox:
        if bbox.space == CoordSpace.DESKTOP:
            return bbox
        if bbox.space != CoordSpace.CROP_IMAGE:
            raise ValueError(f"Cannot convert {bbox.space} with CropTransform")
        return BBox(
            self.desktop_x1 + round(bbox.x1 * self.scale_x_to_desktop),
            self.desktop_y1 + round(bbox.y1 * self.scale_y_to_desktop),
            self.desktop_x1 + round(bbox.x2 * self.scale_x_to_desktop),
            self.desktop_y1 + round(bbox.y2 * self.scale_y_to_desktop),
            CoordSpace.DESKTOP,
        )


def ensure_desktop_point(point: Point, transform: ResizeTransform | CropTransform) -> Point:
    if point.space == CoordSpace.DESKTOP:
        return point
    return transform.point_to_desktop(point)


def ensure_desktop_bbox(bbox: BBox, transform: ResizeTransform | CropTransform) -> BBox:
    if bbox.space == CoordSpace.DESKTOP:
        return bbox
    return transform.bbox_to_desktop(bbox)
