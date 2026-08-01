from setuptools import find_packages, setup

package_name = "pulso_sim_adapter"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    tests_require=["pytest"],
    zip_safe=True,
    maintainer="Pulso Team",
    maintainer_email="pulso@example.invalid",
    description="Gazebo-to-Pulso sensor normalization.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "range_adapter = pulso_sim_adapter.range_node:main",
            "cloud_adapter = pulso_sim_adapter.cloud_node:main",
            "base_state_adapter = pulso_sim_adapter.base_state_node:main",
            "person_perception = pulso_sim_adapter.person_perception_node:main",
        ]
    },
)
