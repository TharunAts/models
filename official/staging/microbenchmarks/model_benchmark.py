# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
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
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import itertools as it
import json
import os
import timeit
import typing

from official.staging.microbenchmarks import constants
from official.staging.microbenchmarks import schedule_base
from official.utils.testing.perfzero_benchmark import PerfZeroBenchmark


TASK_DIR = os.path.join(os.path.split(os.path.realpath(__file__))[0], "tasks")
MODEL_PATHS = {
    "CNN": "cnn.py",
    "MLP": "mlp.py",
    "LOGREG": "logreg.py",
    "LSTM": "lstm.py"
}


class TaskRunner(schedule_base.Runner):
  pass

  def get_cmd(self, task, result_path):
    # PerfZero seems to need `python3` rather than `python`.
    template = (
        "python3 {task_dir}/{task_file} --num_cores {num_cores} "
        "--num_gpus {num_gpus} --batch_size {batch_size} "
        "--result_path {result_path} "
        "--run_mode_kwargs='{run_mode_kwargs}'")

    return template.format(
        task_dir=TASK_DIR, task_file=MODEL_PATHS[task.name],
        num_cores=task.num_cores, num_gpus=task.num_gpus,
        batch_size=task.batch_size, result_path=result_path,
        run_mode_kwargs=schedule_base.RUN_MODE_STR[
          task.experimental_run_tf_function],
    )


class MicroBenchmark(PerfZeroBenchmark):
  def __init__(self, output_dir=None, default_flags=None, root_data_dir=None):
    super(MicroBenchmark, self).__init__(
        output_dir=output_dir,
        default_flags=default_flags,
        flag_methods=[])

  def _get_name(self, overwrite_name=None):
    # This must be overridden to avoid an Estimator dependency issue.
    return overwrite_name or "N/A"

  def _run_and_report_benchmark(self, tasks, runner, repeats, report_name):
    # type: (typing.List[constants.TaskConfig], schedule_base.Runner, int, str) -> None
    start_time = timeit.default_timer()
    results = runner.run(tasks, repeats=repeats)
    wall_time = timeit.default_timer() - start_time

    result_file = os.path.join(self.output_dir, "results.json")
    with open(result_file, "wt") as f:
      json.dump(results, f)
    print("Results written to {}".format(result_file))

    name = "{}.{}".format(self.__class__.__name__, report_name)
    self.report_benchmark(iters=-1, wall_time=wall_time, name=name)

  def _run_task(self, name, report_name):
    tasks = []

    for data_mode, batch_size, experimental_run_tf_function in it.product(
        [constants.NUMPY, constants.DATASET],
        [32, 64, 128, 256, 512],
        schedule_base.RUN_MODE_STR.keys()):

      # CPU benchmarks.
      for num_cores in [2, 4, 8]:
        tasks.append(constants.TaskConfig(
            name=name, num_cores=num_cores, num_gpus=0,
            batch_size=batch_size, data_mode=data_mode,
            experimental_run_tf_function=experimental_run_tf_function)
        )

      # GPU benchmark.
      tasks.append(constants.TaskConfig(
          name=name, num_cores=4, num_gpus=1,
          batch_size=batch_size, data_mode=data_mode,
          experimental_run_tf_function=experimental_run_tf_function)
      )

    self._run_and_report_benchmark(tasks, TaskRunner(num_gpus=8), repeats=3, report_name=report_name)

  def run_mlp(self):
    self._run_task("MLP", "run_mlp")

  def run_cnn(self):
    self._run_task("CNN", "run_cnn")

  def run_logreg(self):
    self._run_task("LOGREG", "run_logreg")

  def run_lstm(self):
    self._run_task("LSTM", "run_lstm")

  def run_baseline(self):
    tasks = []
    for name in ["MLP", "CNN", "LOGREG", "LSTM"]:
      # CPU reference.
      tasks.append(constants.TaskConfig(
          name=name, num_cores=2, num_gpus=0, batch_size=32,
          data_mode=constants.NUMPY, experimental_run_tf_function=False))

      # GPU reference.
      tasks.append(constants.TaskConfig(
          name=name, num_cores=2, num_gpus=1, batch_size=32,
          data_mode=constants.NUMPY, experimental_run_tf_function=False))

    self._run_and_report_benchmark(tasks, TaskRunner(num_gpus=8), repeats=10, report_name="run_baseline")
