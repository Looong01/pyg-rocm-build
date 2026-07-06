/*
 * Copyright (c) 2023-2024, NVIDIA CORPORATION.
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

#include <test_utils.hpp>

#include <cuco/extent.cuh>

#include <catch2/catch_template_test_macros.hpp>

TEMPLATE_TEST_CASE_SIG(
  "utility extent tests", "", ((typename SizeType, int dummy), SizeType, dummy), (int32_t,1), (int64_t,1), (std::size_t,1)) // FIXME(HIP/AMD): dummy fixes ambiguous get_wrapper calls in catch2
{
  SizeType constexpr num            = 1234;
  SizeType constexpr gold_reference = 314;  // 157 x 2
  auto constexpr cg_size            = 2;
  auto constexpr bucket_size        = 4;

  SECTION("Static extent must be evaluated at compile time.")
  {
    auto const size = cuco::extent<SizeType, num>{};
    STATIC_REQUIRE(num == size);
  }

  SECTION("Dynamic extent is evaluated at run time.")
  {
    auto const size = cuco::extent(num);
    REQUIRE(size == num);
  }

  SECTION("Compute static valid extent at compile time.")
  {
    auto constexpr size = cuco::extent<SizeType, num>{};
    auto constexpr res  = cuco::make_bucket_extent<cg_size, bucket_size>(size);
    STATIC_REQUIRE(gold_reference == res.value());
  }

  SECTION("Compute dynamic valid extent at run time.")
  {
    auto const size = cuco::extent<SizeType>{num};
    auto const res  = cuco::make_bucket_extent<cg_size, bucket_size>(size);
    REQUIRE(gold_reference == res.value());
  }
}
