"""Evidence-only rosbridge for the physical S25 telemetry mirror.

The phone reaches this socket over the private field Wi-Fi. Clients may publish only
the read-only evidence topics consumed by Mission Control; no motion, service,
or action endpoint is exposed.
"""

from launch import LaunchDescription
from launch_ros.actions import Node


PHONE_EVIDENCE_TOPICS = (
    "/pulso/hil/observation",
    "/pulso/navigation/candidates",
    "/pulso/hil/action_result",
    "/pulso/navigation/metaview/compressed",
    "/pulso/navigation/metaview_scene",
    "/pulso/phone/rgb/compressed",
    "/pulso/phone/rgb/camera_info",
    "/pulso/phone/telemetry",
    "/pulso/hil/perception_tracks",
    "/pulso/hil/brain_trace",
    "/pulso/hil/gemma_input",
    "/pulso/hil/gemma_view/compressed",
    "/pulso/hil/perception_telemetry",
)


def _ros_glob(values: tuple[str, ...]) -> str:
    return "[" + ",".join(repr(value) for value in values) + "]"


def generate_launch_description() -> LaunchDescription:
    evidence_glob = _ros_glob(PHONE_EVIDENCE_TOPICS)
    return LaunchDescription(
        [
            Node(
                package="rosbridge_server",
                executable="rosbridge_websocket",
                name="pulso_real_telemetry_bridge",
                parameters=[
                    {
                        "port": 9091,
                        "address": "0.0.0.0",
                        "authenticate": False,
                        "ssl": False,
                        "max_message_size": 4_000_000,
                        "topics_pub_glob": evidence_glob,
                        "topics_sub_glob": evidence_glob,
                        "services_glob": "[]",
                        "actions_glob": "[]",
                    }
                ],
                output="screen",
            )
        ]
    )
