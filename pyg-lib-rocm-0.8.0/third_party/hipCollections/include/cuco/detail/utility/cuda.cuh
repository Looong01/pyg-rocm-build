/*
 * Copyright (c) 2023, NVIDIA CORPORATION.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 */

// Modifications Copyright (c) 2025 Advanced Micro Devices, Inc.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

#pragma once

#include <cuco/detail/utility/cuda.hpp>

#include <hip/hip_runtime.h>
#include <hip/hip_cooperative_groups.h>

#include <cstdint>

#if defined(CUCO_DISABLE_KERNEL_VISIBILITY_WARNING_SUPPRESSION)
#define CUCO_SUPPRESS_KERNEL_WARNINGS
#elif defined(__NVCC__) && (defined(__GNUC__) || defined(__clang__))
// handle when nvcc is the CUDA compiler and gcc or clang is host
#define CUCO_SUPPRESS_KERNEL_WARNINGS _Pragma("nv_diag_suppress 1407")
_Pragma("GCC diagnostic ignored \"-Wattributes\"")
#elif defined(__clang__)
// handle when clang is the CUDA compiler
#define CUCO_SUPPRESS_KERNEL_WARNINGS _Pragma("clang diagnostic ignored \"-Wattributes\"")
#elif defined(__NVCOMPILER)
#define CUCO_SUPPRESS_KERNEL_WARNINGS #pragma diag_suppress attribute_requires_external_linkage
#endif

#ifndef CUCO_KERNEL
#define CUCO_KERNEL __attribute__((visibility("hidden"))) __global__
#endif
namespace cuco {
namespace detail {

/// CUDA warp size
__device__ int32_t warp_size() noexcept {
  return warpSize;
}

/**
 * @brief Returns the global thread index in a 1D scalar grid
 *
 * @return The global thread index
 */
__device__ static inline index_type global_thread_id() noexcept
{
  return index_type{threadIdx.x} + index_type{blockDim.x} * index_type{blockIdx.x};
}

/**
 * @brief Returns the grid stride of a 1D grid
 *
 * @return The grid stride
 */
__device__ static inline index_type grid_stride() noexcept
{
  return index_type{gridDim.x} * index_type{blockDim.x};
}

/**
 * @brief Constexpr helper to extract the size of a Cooperative Group.
 *
 * @tparam Tile The Cooperative Group type
 */
template <typename Tile>
struct tile_size;

/**
 * @brief Specialization of `cuco::detail::tile_size` for 'cooperative_groups::thread_block_tile'.
 *
 * @tparam CGSize The Cooperative Group size
 * @tparam ParentCG The Cooperative Group the tile has been created from
 */
template <uint32_t CGSize, class ParentCG>
struct tile_size<cooperative_groups::thread_block_tile<CGSize, ParentCG>> {
  static constexpr uint32_t value = CGSize;  ///< Size of the `thread_block_tile`
};

template <typename Tile>
__device__ constexpr uint32_t tile_size_v = tile_size<Tile>::value;

}  // namespace detail
}  // namespace cuco
