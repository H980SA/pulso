from pathlib import Path
import math
import xml.etree.ElementTree as ET

import pytest


WORLD = Path(__file__).parents[1] / "worlds" / "pulso_disaster.sdf"
WHEEL_NAMES = (
    "front_left_wheel",
    "rear_left_wheel",
    "front_right_wheel",
    "rear_right_wheel",
)


@pytest.fixture(scope="module")
def rover() -> ET.Element:
    root = ET.parse(WORLD).getroot()
    return next(model for model in root.findall(".//model") if model.get("name") == "pulso_openbot")


def test_wheel_axles_are_explicitly_expressed_in_the_model_frame(rover: ET.Element) -> None:
    joints = {joint.get("name"): joint for joint in rover.findall("joint")}
    for wheel_name in WHEEL_NAMES:
        axis = joints[f"{wheel_name.removesuffix('_wheel')}_joint"].find("axis/xyz")
        assert axis is not None
        assert axis.get("expressed_in") == "__model__"
        assert tuple(float(value) for value in axis.text.split()) == (0.0, 1.0, 0.0)


def test_diff_drive_geometry_matches_physical_wheels(rover: ET.Element) -> None:
    links = {link.get("name"): link for link in rover.findall("link")}
    plugin = next(
        item for item in rover.findall("plugin") if item.get("name", "").endswith("DiffDrive")
    )
    assert float(plugin.findtext("wheel_radius")) == pytest.approx(0.033)
    assert float(plugin.findtext("wheel_separation")) == pytest.approx(0.184)

    lateral_positions = []
    for wheel_name in WHEEL_NAMES:
        link = links[wheel_name]
        pose = tuple(float(value) for value in link.findtext("pose").split())
        lateral_positions.append(pose[1])
        assert pose[3] == pytest.approx(math.pi / 2.0, abs=1e-6)
        assert float(link.findtext("collision/geometry/cylinder/radius")) == pytest.approx(
            0.033
        )
    assert max(lateral_positions) - min(lateral_positions) == pytest.approx(0.184)


def test_wheel_contact_has_more_rolling_than_lateral_grip(rover: ET.Element) -> None:
    for link in rover.findall("link"):
        if link.get("name") not in WHEEL_NAMES:
            continue
        friction = link.find("collision/surface/friction/ode")
        assert friction is not None
        # Link-local +Z becomes the axle after the 90-degree wheel roll.
        assert friction.findtext("fdir1").split() == ["0", "0", "1"]
        assert float(friction.findtext("mu2")) > float(friction.findtext("mu"))
