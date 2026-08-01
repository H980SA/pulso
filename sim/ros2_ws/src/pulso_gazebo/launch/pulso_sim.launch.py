import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, SetEnvironmentVariable
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, FindExecutable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    gazebo_share = Path(get_package_share_directory("pulso_gazebo"))
    description_share = Path(get_package_share_directory("pulso_description"))
    world = gazebo_share / "worlds" / "pulso_disaster.sdf"
    bridge = gazebo_share / "config" / "bridge.yaml"
    slam_config = gazebo_share / "config" / "slam_toolbox.yaml"
    robot_xacro = description_share / "urdf" / "openbot.urdf.xacro"

    use_sim_time = LaunchConfiguration("use_sim_time")
    headless = LaunchConfiguration("headless")
    hil = LaunchConfiguration("hil")
    hil_port = LaunchConfiguration("hil_port")
    perception = LaunchConfiguration("perception")
    perception_site = os.environ.get("PULSO_PERCEPTION_SITE_PACKAGES", "")
    perception_pythonpath = ":".join(
        part for part in (perception_site, os.environ.get("PYTHONPATH", "")) if part
    )
    yolo_model = os.environ.get("PULSO_YOLO_MODEL", "")
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument(
                "hil",
                default_value="true",
                description="Expose the contract-only Android WebSocket gateway.",
            ),
            DeclareLaunchArgument(
                "hil_port",
                default_value="9091",
                description="Rosbridge WebSocket port used by the S25 app.",
            ),
            DeclareLaunchArgument(
                "headless",
                default_value="false",
                description="Run only the Gazebo server for CI and remote smoke tests.",
            ),
            DeclareLaunchArgument(
                "perception",
                default_value="true",
                description="Run the real YOLO11n-pose saliency model.",
            ),
            SetEnvironmentVariable(
                "IGN_GAZEBO_RESOURCE_PATH",
                f"{gazebo_share / 'models'}:{gazebo_share / 'worlds'}",
            ),
            ExecuteProcess(
                cmd=["ign", "gazebo", "-r", world.as_posix()],
                condition=UnlessCondition(headless),
                output="screen",
            ),
            ExecuteProcess(
                cmd=["ign", "gazebo", "-s", "-r", world.as_posix()],
                condition=IfCondition(headless),
                output="screen",
            ),
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="pulso_gz_bridge",
                parameters=[{"config_file": bridge.as_posix(), "use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[
                    {
                        "robot_description": Command(
                            [FindExecutable(name="xacro"), " ", robot_xacro.as_posix()]
                        ),
                        "use_sim_time": use_sim_time,
                    }
                ],
                output="screen",
            ),
            Node(
                package="joint_state_publisher",
                executable="joint_state_publisher",
                name="pulso_sim_joint_states",
                parameters=[{"use_sim_time": use_sim_time, "rate": 30}],
                output="screen",
            ),
            # Fortress scopes the IMU sensor frame with model/link names while
            # the physical-parity URDF exposes the phone mount as
            # `phone_imu_link`.  They are coincident, so this identity transform
            # makes the raw IMU visible to RViz without rewriting sensor data.
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="pulso_gazebo_imu_frame",
                arguments=[
                    "--x", "0", "--y", "0", "--z", "0",
                    "--roll", "0", "--pitch", "0", "--yaw", "0",
                    "--frame-id", "phone_imu_link",
                    "--child-frame-id", "pulso_openbot/phone_sensor_link/phone_imu",
                ],
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_arcore_emulator",
                executable="depth_emulator",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_arcore_emulator",
                executable="vio_emulator",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_sim_adapter",
                executable="range_adapter",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_sim_adapter",
                executable="cloud_adapter",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pointcloud_to_laserscan",
                executable="pointcloud_to_laserscan_node",
                name="pulso_depth_scan",
                remappings=[
                    ("cloud_in", "/pulso/phone/depth/points"),
                    ("scan", "/pulso/navigation/scan"),
                ],
                parameters=[
                    {
                        "use_sim_time": use_sim_time,
                        "target_frame": "base_link",
                        "transform_tolerance": 0.08,
                        "min_height": -0.18,
                        "max_height": 0.55,
                        "angle_min": -1.20,
                        "angle_max": 1.20,
                        # Fortress' converter uses ceil(N) while Karto uses
                        # round(N)+1. This increment keeps both at 276 rays.
                        "angle_increment": 0.00872,
                        "scan_time": 0.10,
                        "range_min": 0.10,
                        "range_max": 5.0,
                        "use_inf": True,
                        "inf_epsilon": 1.0,
                    }
                ],
                output="screen",
            ),
            Node(
                package="slam_toolbox",
                executable="async_slam_toolbox_node",
                name="slam_toolbox",
                parameters=[slam_config.as_posix(), {"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_sim_adapter",
                executable="base_state_adapter",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_safety",
                executable="safety_gate",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_navigation",
                executable="navigation",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_hil",
                executable="gateway",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="pulso_sim_adapter",
                executable="person_perception",
                name="pulso_person_perception",
                condition=IfCondition(perception),
                parameters=[
                    {
                        "use_sim_time": use_sim_time,
                        "model_path": yolo_model,
                        "provider": "cuda",
                        "threshold": 0.18,
                        "inference_period_s": 0.65,
                    }
                ],
                additional_env={"PYTHONPATH": perception_pythonpath},
                output="screen",
            ),
            Node(
                package="rosbridge_server",
                executable="rosbridge_websocket",
                name="pulso_rosbridge",
                condition=IfCondition(hil),
                parameters=[
                    {
                        "port": ParameterValue(hil_port, value_type=int),
                        "address": "127.0.0.1",
                        "authenticate": False,
                        "ssl": False,
                        "max_message_size": 4_000_000,
                        "topics_pub_glob": (
                            "['/pulso/hil/action_intent',"
                            "'/pulso/hil/observation',"
                            "'/pulso/navigation/candidates',"
                            "'/pulso/hil/action_result',"
                            "'/pulso/navigation/metaview/compressed',"
                            "'/pulso/navigation/metaview_scene',"
                            "'/pulso/phone/rgb/compressed',"
                            "'/pulso/phone/rgb/camera_info',"
                            "'/pulso/phone/telemetry',"
                            "'/pulso/hil/perception_tracks',"
                            "'/pulso/hil/brain_trace',"
                            "'/pulso/hil/gemma_input',"
                            "'/pulso/hil/gemma_view/compressed',"
                            "'/pulso/hil/perception_telemetry']"
                        ),
                        "topics_sub_glob": (
                            "['/pulso/hil/action_intent',"
                            "'/pulso/hil/observation',"
                            "'/pulso/navigation/candidates',"
                            "'/pulso/hil/action_result',"
                            "'/pulso/navigation/metaview/compressed',"
                            "'/pulso/navigation/metaview_scene',"
                            "'/pulso/phone/rgb/compressed',"
                            "'/pulso/phone/rgb/camera_info',"
                            "'/pulso/phone/telemetry',"
                            "'/pulso/hil/perception_tracks',"
                            "'/pulso/hil/brain_trace',"
                            "'/pulso/hil/gemma_input',"
                            "'/pulso/hil/gemma_view/compressed',"
                            "'/pulso/hil/perception_telemetry']"
                        ),
                        "services_glob": "[]",
                        "actions_glob": "[]",
                    }
                ],
                output="screen",
            ),
        ]
    )
