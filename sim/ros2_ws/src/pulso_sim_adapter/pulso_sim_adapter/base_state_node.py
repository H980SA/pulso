"""Simulated OpenBot state that has direct physical equivalents."""

import subprocess

import rclpy
from rclpy.node import Node
from ros_gz_interfaces.msg import Contacts
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Bool


class BaseStateAdapterNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_base_state_adapter")
        self.declare_parameter("mission_battery_minutes", 95.0)
        self.declare_parameter("world_name", "pulso_disaster")
        self.declare_parameter("flashlight_name", "phone_flashlight")
        self._started_ns = self.get_clock().now().nanoseconds
        self._flashlight = False
        self._bumper = False
        self._battery_pub = self.create_publisher(BatteryState, "/pulso/base/battery", 10)
        self._bumper_pub = self.create_publisher(Bool, "/pulso/base/bumper", 10)
        self._flashlight_pub = self.create_publisher(Bool, "/pulso/phone/flashlight/state", 10)
        self.create_subscription(Bool, "/pulso/phone/flashlight/cmd", self._on_flashlight, 10)
        self.create_subscription(
            Contacts, "/pulso/sim/base/bumper_contacts", self._on_contacts, 10
        )
        self.create_timer(0.5, self._publish)

    def _on_flashlight(self, message: Bool) -> None:
        self._flashlight = self._set_gazebo_flashlight(message.data)
        self._flashlight_pub.publish(Bool(data=self._flashlight))

    def _on_contacts(self, message: Contacts) -> None:
        self._bumper = bool(message.contacts)

    def _set_gazebo_flashlight(self, enabled: bool) -> bool:
        world = str(self.get_parameter("world_name").value)
        name = str(self.get_parameter("flashlight_name").value)
        light_state = "1" if enabled else "0"
        request = (
            f'header {{data {{key: "isLightOn" value: "{light_state}"}} '
            'data {key: "visualizeVisual" value: "0"}} '
            f'name: "{name}" type: SPOT '
            'diffuse {r: 1.0 g: 0.91 b: 0.72 a: 1.0} '
            'specular {r: 0.18 g: 0.16 b: 0.12 a: 1.0} '
            'attenuation_constant: 0.25 attenuation_linear: 0.02 '
            'attenuation_quadratic: 0.002 range: 8.0 cast_shadows: false '
            'direction {x: 1.0 y: 0.0 z: 0.0} '
            'spot_inner_angle: 0.28 spot_outer_angle: 0.95 spot_falloff: 0.65 '
            'intensity: 0.5'
        )
        try:
            result = subprocess.run(
                [
                    "ign",
                    "service",
                    "-s",
                    f"/world/{world}/light_config",
                    "--reqtype",
                    "ignition.msgs.Light",
                    "--reptype",
                    "ignition.msgs.Boolean",
                    "--timeout",
                    "1200",
                    "--req",
                    request,
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as failure:
            self.get_logger().error(f"Flashlight service failed: {failure}")
            return False
        acknowledged = result.returncode == 0 and "true" in result.stdout.lower()
        if not acknowledged:
            self.get_logger().error(
                f"Gazebo rejected flashlight={enabled}: {result.stderr.strip()}"
            )
        return enabled if acknowledged else False

    def _publish(self) -> None:
        elapsed_minutes = (self.get_clock().now().nanoseconds - self._started_ns) / 60e9
        capacity_minutes = float(self.get_parameter("mission_battery_minutes").value)
        percentage = max(0.0, 1.0 - elapsed_minutes / capacity_minutes)
        battery = BatteryState()
        battery.header.stamp = self.get_clock().now().to_msg()
        battery.percentage = percentage
        battery.voltage = 12.6 * (0.75 + 0.25 * percentage)
        battery.present = True
        battery.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
        self._battery_pub.publish(battery)
        self._bumper_pub.publish(Bool(data=self._bumper))
        self._flashlight_pub.publish(Bool(data=self._flashlight))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BaseStateAdapterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
