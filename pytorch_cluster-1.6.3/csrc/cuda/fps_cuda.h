#pragma once

#include "../extensions.h"

torch::Tensor fps_cuda(torch::Tensor src, torch::Tensor ptr,
                       torch::Tensor ratio, bool random_start);
