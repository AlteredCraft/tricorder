cmake_minimum_required(VERSION 3.16)
set(FACTORY_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.tools/M5Tab5-UserDemo")
set(EXTRA_COMPONENT_DIRS
    "${FACTORY_ROOT}/platforms/tab5/components"
    "${FACTORY_ROOT}/dependencies/lvgl")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(tricorder)
