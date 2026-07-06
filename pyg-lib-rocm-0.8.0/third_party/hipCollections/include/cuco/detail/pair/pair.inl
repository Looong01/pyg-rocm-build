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
 * limitations under the License.
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

#include <type_traits>
#include <utility>

// FIXME/WAR(HIP/AMD): We need to include libhipcxx __config here to make
// the macro _LIBCUDACXX_BEGIN_NAMESPACE_STD_NOVERSION from libhipcxx available
// in order to add the symbols from tuple_helpers.inl to the correct namespace.
#include <cuda/std/detail/__config>

namespace cuco {

template <typename First, typename Second>
__host__ __device__ constexpr pair<First, Second>::pair(First const& f, Second const& s)
  : first{f}, second{s}
{
}

template <typename First, typename Second>
template <typename F, typename S>
__host__ __device__ constexpr pair<First, Second>::pair(pair<F, S> const& p)
  : first{p.first}, second{p.second}
{
}

template <typename F, typename S>
__host__ __device__ constexpr pair<std::decay_t<F>, std::decay_t<S>> make_pair(F&& f,
                                                                               S&& s) noexcept
{
  return pair<std::decay_t<F>, std::decay_t<S>>(std::forward<F>(f), std::forward<S>(s));
}

template <class T1, class T2, class U1, class U2>
__host__ __device__ constexpr bool operator==(cuco::pair<T1, T2> const& lhs,
                                              cuco::pair<U1, U2> const& rhs) noexcept
{
  return lhs.first == rhs.first and lhs.second == rhs.second;
}

}  // namespace cuco

// NOTE(HIP/AMD): Older libhipcxx versions use
// the "hip" namespace name while more recent ones use
// "cuda". We therefore use the macros from libhipcxx
// to put the tuple_helpers.inl symbols into the correct 
// namespace.
_LIBCUDACXX_BEGIN_NAMESPACE_STD_NOVERSION
#include <cuco/detail/pair/tuple_helpers.inl>
_LIBCUDACXX_END_NAMESPACE_STD_NOVERSION 
