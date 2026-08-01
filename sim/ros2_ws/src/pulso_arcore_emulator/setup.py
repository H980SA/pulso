from setuptools import find_packages, setup

package_name = "pulso_arcore_emulator"

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
    description="ARCore-like adapters for Pulso simulation.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "depth_emulator = pulso_arcore_emulator.depth_node:main",
            "vio_emulator = pulso_arcore_emulator.vio_node:main",
        ]
    },
)
