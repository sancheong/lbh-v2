from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .errors import ValidationError


class CoordinateSpace(str, Enum):
    DESKTOP = "desktop"
    RESIZED_IMAGE = "resized_image"
    ACTIVE_WINDOW = "active_window"
    CROP = "crop"


@dataclass(frozen=True)
class Size:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValidationError("Size width and height must be positive.")

    def to_dict(self) -> dict[str, int]:
        return {"width": self.width, "height": self.height}


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    space: CoordinateSpace

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Point":
        if "space" not in payload:
            raise ValidationError("Points must include a coordinate space.")
        return cls(
            x=float(payload["x"]),
            y=float(payload["y"]),
            space=CoordinateSpace(str(payload["space"])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "space": self.space.value}


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    right: float
    bottom: float
    space: CoordinateSpace

    def __post_init__(self) -> None:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValidationError("Boxes must have positive width and height.")

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center(self) -> Point:
        return Point(
            x=self.left + self.width / 2.0,
            y=self.top + self.height / 2.0,
            space=self.space,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Box":
        if "space" not in payload:
            raise ValidationError("Boxes must include a coordinate space.")
        return cls(
            left=float(payload["left"]),
            top=float(payload["top"]),
            right=float(payload["right"]),
            bottom=float(payload["bottom"]),
            space=CoordinateSpace(str(payload["space"])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
            "space": self.space.value,
        }


@dataclass(frozen=True)
class CoordinateTransform:
    desktop_size: Size
    resized_size: Size
    active_window_box: Box | None = None
    crop_box: Box | None = None
    crop_image_size: Size | None = None

    @classmethod
    def from_observation(cls, payload: Mapping[str, Any]) -> "CoordinateTransform":
        active_window = payload.get("active_window") or {}
        active_window_box = None
        if all(active_window.get(key) is not None for key in ("left", "top", "right", "bottom")):
            active_window_box = Box(
                left=float(active_window["left"]),
                top=float(active_window["top"]),
                right=float(active_window["right"]),
                bottom=float(active_window["bottom"]),
                space=CoordinateSpace.DESKTOP,
            )
        crop_box = Box.from_dict(payload["crop_box"]) if payload.get("crop_box") else None
        crop_image_size = (
            Size(
                width=int(payload["crop_image_size"]["width"]),
                height=int(payload["crop_image_size"]["height"]),
            )
            if payload.get("crop_image_size")
            else None
        )
        return cls(
            desktop_size=Size(int(payload["original_width"]), int(payload["original_height"])),
            resized_size=Size(int(payload["image_width"]), int(payload["image_height"])),
            active_window_box=active_window_box,
            crop_box=crop_box,
            crop_image_size=crop_image_size,
        )

    def bounds_for(self, space: CoordinateSpace) -> Box:
        if space == CoordinateSpace.DESKTOP:
            return Box(0, 0, self.desktop_size.width, self.desktop_size.height, space)
        if space == CoordinateSpace.RESIZED_IMAGE:
            return Box(0, 0, self.resized_size.width, self.resized_size.height, space)
        if space == CoordinateSpace.ACTIVE_WINDOW:
            if not self.active_window_box:
                raise ValidationError("No active window metadata is available.")
            return Box(0, 0, self.active_window_box.width, self.active_window_box.height, space)
        if space == CoordinateSpace.CROP:
            if not self.crop_box:
                raise ValidationError("No crop metadata is available.")
            crop_width = self.crop_image_size.width if self.crop_image_size else self.crop_box.width
            crop_height = self.crop_image_size.height if self.crop_image_size else self.crop_box.height
            return Box(0, 0, crop_width, crop_height, space)
        raise ValidationError(f"Unsupported coordinate space: {space}")

    def validate_point(self, point: Point) -> None:
        bounds = self.bounds_for(point.space)
        if point.x < bounds.left or point.x > bounds.right:
            raise ValidationError(f"Point x={point.x} is outside {point.space.value} bounds.")
        if point.y < bounds.top or point.y > bounds.bottom:
            raise ValidationError(f"Point y={point.y} is outside {point.space.value} bounds.")

    def point_to_desktop(self, point: Point) -> Point:
        self.validate_point(point)
        if point.space == CoordinateSpace.DESKTOP:
            return point
        if point.space == CoordinateSpace.RESIZED_IMAGE:
            return Point(
                x=round(point.x * self.desktop_size.width / self.resized_size.width),
                y=round(point.y * self.desktop_size.height / self.resized_size.height),
                space=CoordinateSpace.DESKTOP,
            )
        if point.space == CoordinateSpace.ACTIVE_WINDOW:
            if not self.active_window_box:
                raise ValidationError("Cannot convert active_window coordinates without active window metadata.")
            return Point(
                x=round(self.active_window_box.left + point.x),
                y=round(self.active_window_box.top + point.y),
                space=CoordinateSpace.DESKTOP,
            )
        if point.space == CoordinateSpace.CROP:
            if not self.crop_box:
                raise ValidationError("Cannot convert crop coordinates without crop metadata.")
            crop_width = self.crop_image_size.width if self.crop_image_size else self.crop_box.width
            crop_height = self.crop_image_size.height if self.crop_image_size else self.crop_box.height
            return Point(
                x=round(self.crop_box.left + point.x * self.crop_box.width / crop_width),
                y=round(self.crop_box.top + point.y * self.crop_box.height / crop_height),
                space=CoordinateSpace.DESKTOP,
            )
        raise ValidationError(f"Unsupported coordinate space: {point.space.value}")

    def desktop_to_resized_image(self, point: Point) -> Point:
        if point.space != CoordinateSpace.DESKTOP:
            raise ValidationError("desktop_to_resized_image requires a desktop-space point.")
        self.validate_point(point)
        return Point(
            x=round(point.x * self.resized_size.width / self.desktop_size.width),
            y=round(point.y * self.resized_size.height / self.desktop_size.height),
            space=CoordinateSpace.RESIZED_IMAGE,
        )

    def desktop_to_active_window(self, point: Point) -> Point:
        if point.space != CoordinateSpace.DESKTOP:
            raise ValidationError("desktop_to_active_window requires a desktop-space point.")
        if not self.active_window_box:
            raise ValidationError("No active window metadata is available.")
        self.validate_point(point)
        return Point(
            x=round(point.x - self.active_window_box.left),
            y=round(point.y - self.active_window_box.top),
            space=CoordinateSpace.ACTIVE_WINDOW,
        )

    def box_to_desktop(self, box: Box) -> Box:
        top_left = self.point_to_desktop(Point(box.left, box.top, box.space))
        bottom_right = self.point_to_desktop(Point(box.right, box.bottom, box.space))
        return Box(
            left=top_left.x,
            top=top_left.y,
            right=bottom_right.x,
            bottom=bottom_right.y,
            space=CoordinateSpace.DESKTOP,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "desktop_size": self.desktop_size.to_dict(),
            "resized_size": self.resized_size.to_dict(),
            "active_window_box": self.active_window_box.to_dict() if self.active_window_box else None,
            "crop_box": self.crop_box.to_dict() if self.crop_box else None,
            "crop_image_size": self.crop_image_size.to_dict() if self.crop_image_size else None,
        }
