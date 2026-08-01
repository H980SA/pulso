cmake_minimum_required(VERSION 3.8)
project(pulso_gazebo)

find_package(ament_cmake REQUIRED)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(drive_model_contract test/test_drive_model_contract.py)
endif()

install(DIRECTORY launch worlds models config DESTINATION share/${PROJECT_NAME})

ament_package()
