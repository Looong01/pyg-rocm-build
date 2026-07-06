#=============================================================================
# Copyright (c) 2018-2024, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#=============================================================================

# Modifications Copyright (c) 2024-2025 Advanced Micro Devices, Inc.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

cmake_minimum_required(VERSION 3.23.1 FATAL_ERROR)

###################################################################################################
# - compiler function -----------------------------------------------------------------------------

function(ConfigureExample EXAMPLE_NAME EXAMPLE_SRC)
    add_executable(${EXAMPLE_NAME} "${EXAMPLE_SRC}")
    set_target_properties(${EXAMPLE_NAME} PROPERTIES
                                          RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/examples")
    target_include_directories(${EXAMPLE_NAME} PRIVATE
                                             "${CMAKE_CURRENT_SOURCE_DIR}")
    target_compile_options(${EXAMPLE_NAME} PRIVATE -Wall -Wextra -Wno-unused-parameter) #todo(HIP):remove -Wno-unused-parameter
    target_link_libraries(${EXAMPLE_NAME} PRIVATE cuco hip::device hip::hipcub)
endfunction(ConfigureExample)

###################################################################################################
### Example sources ###############################################################################
###################################################################################################

file(GLOB CU_SOURCES
  ./*/*.cu)

set_source_files_properties(${CU_SOURCES} 
	                   PROPERTIES LANGUAGE HIP)


ConfigureExample(STATIC_SET_HOST_BULK_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_set/host_bulk_example.cu")
ConfigureExample(STATIC_SET_DEVICE_REF_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_set/device_ref_example.cu")
ConfigureExample(STATIC_SET_DEVICE_SUBSETS_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_set/device_subsets_example.cu")
ConfigureExample(STATIC_SET_SHARED_MEMORY_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_set/shared_memory_example.cu")
ConfigureExample(STATIC_SET_MAPPING_TABLE_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_set/mapping_table_example.cu")
ConfigureExample(STATIC_MULTISET_HOST_BULK_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_multiset/host_bulk_example.cu")
ConfigureExample(STATIC_MAP_HOST_BULK_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_map/host_bulk_example.cu")
ConfigureExample(STATIC_MAP_DEVICE_SIDE_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_map/device_ref_example.cu")
ConfigureExample(STATIC_MAP_CUSTOM_TYPE_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_map/custom_type_example.cu")
ConfigureExample(STATIC_MAP_COUNT_BY_KEY_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_map/count_by_key_example.cu")
ConfigureExample(STATIC_MULTIMAP_HOST_BULK_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/static_multimap/host_bulk_example.cu")
# Note(HIP/AMD): hyperloglog is currently not supported due to missing reduce api in cooperative_groups
#ConfigureExample(HYPERLOGLOG_HOST_BULK_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/hyperloglog/host_bulk_example.cu")
#ConfigureExample(HYPERLOGLOG_DEVICE_REF_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/hyperloglog/device_ref_example.cu")
ConfigureExample(BLOOM_FILTER_HOST_BULK_EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/bloom_filter/host_bulk_example.cu")
