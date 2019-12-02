# Copyright (c) 2019, NVIDIA CORPORATION. All rights reserved.
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

from nvidia.dali.pipeline import Pipeline
import nvidia.dali.ops as ops
import nvidia.dali.types as types
import nvidia.dali as dali
import numpy as np
from numpy.testing import assert_array_equal, assert_allclose
from functools import partial
from test_utils import check_batch
from test_utils import compare_pipelines
from test_utils import RandomDataIterator
import math

class ToDecibelsPipeline(Pipeline):
    def __init__(self, device, batch_size, iterator, multiplier, reference, cutoff_db,
                 num_threads=1, device_id=0):
        super(ToDecibelsPipeline, self).__init__(batch_size, num_threads, device_id)
        self.device = device
        self.iterator = iterator
        self.inputs = ops.ExternalSource()
        self.dB = ops.ToDecibels(device = self.device,
                                 multiplier=multiplier,
                                 reference=reference,
                                 cutoff_db=cutoff_db)

    def define_graph(self):
        self.data = self.inputs()
        out = self.data.gpu() if self.device == 'gpu' else self.data
        out = self.dB(out)
        return out

    def iter_setup(self):
        data = self.iterator.next()
        self.feed_input(self.data, data)

def to_db_func(multiplier, reference, cutoff_db, input_data):
    if not reference:
        reference = np.amax(input_data)
    min_ratio = 10 ** (cutoff_db / multiplier)
    out = multiplier * np.log10(np.maximum(min_ratio, input_data / reference))
    return out

class ToDecibelsPythonPipeline(Pipeline):
    def __init__(self, device, batch_size, iterator, multiplier, reference, cutoff_db,
                 num_threads=1, device_id=0, func=to_db_func):
        super(ToDecibelsPythonPipeline, self).__init__(
              batch_size, num_threads, device_id,
              seed=12345, exec_async=False, exec_pipelined=False)
        self.device = "cpu"
        self.iterator = iterator
        self.inputs = ops.ExternalSource()

        function = partial(func, multiplier, reference, cutoff_db)
        self.dB = ops.PythonFunction(function=function)

    def define_graph(self):
        self.data = self.inputs()
        out = self.dB(self.data)
        return out

    def iter_setup(self):
        data = self.iterator.next()
        self.feed_input(self.data, data)

def check_operator_to_decibels_vs_python(device, batch_size, input_shape,
                                         multiplier, reference, cutoff_db):
    eii1 = RandomDataIterator(batch_size, shape=input_shape, dtype=np.float32)
    eii2 = RandomDataIterator(batch_size, shape=input_shape, dtype=np.float32)
    compare_pipelines(
        ToDecibelsPipeline(device, batch_size, iter(eii1),
                          multiplier=multiplier, reference=reference, cutoff_db=cutoff_db),
        ToDecibelsPythonPipeline(device, batch_size, iter(eii2),
                          multiplier=multiplier, reference=reference, cutoff_db=cutoff_db),
        batch_size=batch_size, N_iterations=5, eps=1e-04)

def test_operator_to_decibels_vs_python():
    for device in ['cpu']:
        for batch_size in [3]:
            for multiplier, reference, cutoff_db, shape in [(10.0, None, -80.0, (1, 4096)),
                                                            (20.0, 1.0, -200.0, (2, 1000)),
                                                            (20.0, 1e-6, -120.0, (2, 3, 40))]:
                yield check_operator_to_decibels_vs_python, device, batch_size, shape, \
                    multiplier, reference, cutoff_db
