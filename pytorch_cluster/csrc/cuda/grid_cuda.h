#pragma once

#include "../extensions.h"

torch::Tensor grid_cuda(torch::Tensor pos, torch::Tensor size,
                        torch::optional<torch::Tensor> optional_start,
                        torch::optional<torch::Tensor> optional_end);
