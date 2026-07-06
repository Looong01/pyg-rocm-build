/*
 * Copyright (c) 2020-2024, NVIDIA CORPORATION.
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

#include <test_utils.hpp>

#include <cuco/dynamic_map.cuh>

#include <cuda/functional>
#include <thrust/device_vector.h>
#include <thrust/execution_policy.h>
#include <thrust/functional.h>
#include <thrust/iterator/counting_iterator.h>
#include <thrust/iterator/transform_iterator.h>
#include <thrust/sequence.h>
#include <thrust/tuple.h>

#include <catch2/catch_template_test_macros.hpp>

TEMPLATE_TEST_CASE_SIG("experimental::dynamic_map: unique sequence",
                       "",
                       ((typename Key, typename T, int dummy), Key, T, dummy), //FIXME(hip): dummy fixes ambiguous get_wrapper calls in catch2
                       (int32_t, int32_t, 1),
                       (int32_t, int64_t, 1),
                       (int64_t, int32_t, 1),
                       (int64_t, int64_t, 1))
{
  constexpr std::size_t num_keys{1'000'000};

  cuco::experimental::dynamic_map<Key, T> map{
    30'000'000, cuco::empty_key<Key>{-1}, cuco::empty_value<T>{-1}};

  thrust::device_vector<Key> d_keys(num_keys);
  thrust::device_vector<T> d_values(num_keys);

  thrust::sequence(thrust::device, d_keys.begin(), d_keys.end());
  thrust::sequence(thrust::device, d_values.begin(), d_values.end());

  auto pairs_begin =
    thrust::make_transform_iterator(thrust::make_counting_iterator<int>(0),
                                    cuda::proclaim_return_type<cuco::pair<Key, T>>(
                                      [] __device__(auto i) { return cuco::pair<Key, T>(i, i); }));

  thrust::device_vector<T> d_results(num_keys);
  thrust::device_vector<bool> d_contained(num_keys);

  // bulk function test cases

  SECTION("All inserted keys-value pairs should be contained")
  {
    map.insert(pairs_begin, pairs_begin + num_keys);
    map.contains(d_keys.begin(), d_keys.end(), d_contained.begin());

    REQUIRE(cuco::test::all_of(d_contained.begin(), d_contained.end(), thrust::identity{}));
  }

  SECTION("Non-inserted keys-value pairs should not be contained")
  {
    // segfaults
    map.contains(d_keys.begin(), d_keys.end(), d_contained.begin());

    REQUIRE(cuco::test::none_of(d_contained.begin(), d_contained.end(), thrust::identity{}));
  }
}
