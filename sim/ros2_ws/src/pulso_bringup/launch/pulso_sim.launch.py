from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    bringup_share = Path(get_package_share_directory("pulso_bringup"))
    launch_file = (
        Path(get_package_share_directory("pulso_gazebo"))
        / "launch"
        / "pulso_sim.launch.py"
    )
    rviz = LaunchConfiguration("rviz")
    headless = LaunchConfiguration("headless")
    use_sim_time = LaunchConfiguration("use_sim_time", default="true")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "rviz",
                default_value="false",
                description="Open the preconfigured Pulso operator visualization.",
            ),
            DeclareLaunchArgument(
                "headless",
                default_value="false",
                description="Run only the Gazebo server for CI and remote smoke tests.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(launch_file.as_posix()),
                launch_arguments={
                    "headless": headless,
                    "use_sim_time": use_sim_time,
                }.items(),
            ),
            Node(
                package="pulso_visualization",
                executable="status_visualizer",
                name="pulso_status_visualizer",
                condition=IfCondition(rviz),
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="pulso_rviz",
                condition=IfCondition(rviz),
                arguments=["-d", (bringup_share / "config" / "pulso.rviz").as_posix()],
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
        ]
    )
