/*
 * Copyright (c) 2021-2024, NVIDIA CORPORATION.
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

// Modifications Copyright (c) 2024-2025 Advanced Micro Devices, Inc.
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

#include <cuco/detail/__config>
#include <cuco/detail/bitwise_compare.cuh>

#include <cuda/std/array>
#include <cuda/std/bit>
#include <cuda/std/cmath>
#include <cuda/std/limits>
#include <cuda/std/type_traits>
#include <thrust/tuple.h>

#include <cstddef>

namespace cuco {
namespace detail {

// TODO(HIP/AMD): find a better place for this
// TODO(HIP/AMD): switched to 64 wavefront version in all cases. Reevaluate in the future.
#if 0
using lane_mask = unsigned int;
#else
using lane_mask = unsigned long long int;
#endif

/**
 * \brief Find First Set
 * \return index of first set bit of lowest significance.
 * \note Return value type matches that of the underlying device builtin.
 * \note While `uint64_t` is defined as `unsigned long int` on x86_64,
 *       the HIP `__ffsll` device function provides `__ffsll` with `unsigned long long int`
 *       argument, which is also an 64-bit integer type on x86_64.
 *       However, the compilers typically see both as different types.
 *       We work with `uint64t` and `uint32t` here, so explicit instantiations
 *       for both are added here.
 */
template <typename T>
__device__ inline int __FFS(T v);

template <>
__device__ inline int __FFS<int32_t>(int32_t v) {
  return __ffs(v);
}

template <>
__device__ inline int __FFS<int64_t>(int64_t v) {
  return __ffsll(static_cast<unsigned long long int>(v));
}

template <>
__device__ inline int __FFS<uint32_t>(uint32_t v) {
  return __ffs(v);
}

template <>
__device__ inline int __FFS<unsigned long long>(unsigned long long v) {
  return __ffsll(static_cast<unsigned long long int>(v));
}

template <>
__device__ inline int __FFS<uint64_t>(uint64_t v) {
  return __ffsll(static_cast<unsigned long long int>(v));
}

__host__ __device__ inline void __trap(){
  #ifndef NDEBUG
  //#warning "__trap(): the call of __builtin_trap() will abort the host process. \
  This deviates from the CUDA implementation where __trap() terminates a kernel \
  and the host process is notified via an error status."
    __builtin_trap();
  #endif
}

/**
 * \return Number of bits set to 1.
 * \note Return value type matches that of the underlying device builtin.
 */
template <typename T>
__device__ inline int __POPC(T v);


template <>
__device__ inline int __POPC<int32_t>(int32_t v) {
  return __popc(v);
}

template <>
__device__ inline int __POPC<int64_t>(int64_t v) {
  return __popcll(v);
}

template <>
__device__ inline int __POPC<uint32_t>(uint32_t v) {
  return __popc(v);
}

template <>
__device__ inline int __POPC<uint64_t>(uint64_t v) {
  return __popcll(v);
}

template <>
__device__ inline int __POPC<unsigned long long>(unsigned long long v) {
  return __popcll(v);
}  

/**
 * @brief For the `n` least significant bits in the given unsigned 64-bit integer `x`,
 * returns the number of set bits.
 */
__device__ __forceinline__ int32_t count_least_significant_bits(uint64_t x, int32_t n)
{
  return __popcll(x & (1UL << n) - 1UL);
}

/**
 * @brief Converts pair to `thrust::tuple` to allow assigning to a zip iterator.
 *
 * @tparam Key The slot key type
 * @tparam Value The slot value type
 */
template <typename Key, typename Value>
struct slot_to_tuple {
  /**
   * @brief Converts a pair to a `thrust::tuple`.
   *
   * @tparam S The slot type
   *
   * @param s The slot to convert
   * @return A thrust::tuple containing `s.first` and `s.second`
   */
  template <typename S>
  __host__ __device__ thrust::tuple<Key, Value> operator()(S const& s)  // todo(hip): double check if __host__ is needed, file ticket?
  {
    return thrust::tuple<Key, Value>(s.first, s.second);
  }
};

/**
 * @brief Device functor returning whether the input slot `s` is filled.
 *
 * @tparam Key The slot key type
 */
template <typename Key>
struct slot_is_filled {
  Key empty_key_sentinel_;  ///< The value of the empty key sentinel

  /**
   * @brief Indicates if the target slot `s` is filled.
   *
   * @tparam S The slot type
   *
   * @param s The slot to query
   * @return `true` if slot `s` is filled
   */
  template <typename S>
  __device__ bool operator()(S const& s)
  {
    return not cuco::detail::bitwise_compare(thrust::get<0>(s), empty_key_sentinel_);
  }
};

template <typename SizeType, typename HashType>
__host__ __device__ constexpr SizeType to_positive(HashType hash)
{
  if constexpr (cuda::std::is_signed_v<SizeType>) {
    return cuda::std::abs(static_cast<SizeType>(hash));
  } else {
    return static_cast<SizeType>(hash);
  }
}

/**
 * @brief Converts a given hash value into a valid (positive) size type.
 *
 * @tparam SizeType The target type
 * @tparam HashType The input type
 *
 * @return Converted hash value
 */
template <typename SizeType, typename HashType>
__host__ __device__ constexpr SizeType sanitize_hash(HashType hash) noexcept
{
  if constexpr (cuda::std::is_same_v<HashType, cuda::std::array<std::uint64_t, 2>>) {
#if !defined(CUCO_HAS_INT128)
    static_assert(false,
                  "CUCO_HAS_INT128 undefined. Need unsigned __int128 type when sanitizing "
                  "cuda::std::array<std::uint64_t, 2>");
#endif
    unsigned __int128 ret{};
    memcpy(&ret, &hash, sizeof(unsigned __int128));
    return to_positive<SizeType>(static_cast<SizeType>(ret));
  } else {
    return to_positive<SizeType>(hash);
  }
}

/**
 * @brief Converts a given hash value and cg_rank, into a valid (positive) size type.
 *
 * @tparam SizeType The target type
 * @tparam CG Cooperative group type
 * @tparam HashType The input type
 *
 * @return Converted hash value
 */
template <typename SizeType, typename CG, typename HashType>
__device__ constexpr SizeType sanitize_hash(CG const& group, HashType hash) noexcept
{
  auto const base_hash = sanitize_hash<SizeType>(hash);
  auto const max_size  = cuda::std::numeric_limits<SizeType>::max();
  auto const cg_rank   = static_cast<SizeType>(group.thread_rank());

  if (base_hash > (max_size - cg_rank)) { return cg_rank - (max_size - base_hash); }
  return base_hash + cg_rank;
}

}  // namespace detail
}  // namespace cuco
