#!/usr/bin/env python3
import sys
import time
import socket
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
# Check for required packages
try:
    import numpy as np
    import cupy as cp
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    # Allow import to succeed even without dependencies
    # This enables active_healthcheck.py to import without errors
    DEPENDENCIES_AVAILABLE = False
    np = None
    cp = None
    _import_error = e


class TestResult:
    def __init__(self, test_name: str, passed: bool, error_count: int = 0,
                 elapsed_time: float = 0.0, message: str = ""):
        self.test_name = test_name
        self.passed = passed
        self.error_count = error_count
        self.elapsed_time = elapsed_time
        self.message = message
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        """Convert result to dictionary."""
        return {
            "test_name": self.test_name,
            "passed": self.passed,
            "error_count": self.error_count,
            "elapsed_time": self.elapsed_time,
            "message": self.message,
            "timestamp": self.timestamp
        }

    def __repr__(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return f"TestResult({self.test_name}: {status}, errors={self.error_count}, time={self.elapsed_time:.2f}s)"


class GPUSDCChecker:
    # Max duration per test in seconds
    MAX_DURATION = 15 
    # Available test definitions
    AVAILABLE_TESTS = {
        "memory_patterns": "Test GPU memory with various bit patterns",
        "arithmetic_operations": "Test floating-point arithmetic operations",
        "memory_integrity": "Test memory copy and data integrity",
        "data_transfer": "Test host-to-device and device-to-host transfers",
        "concurrent_operations": "Test concurrent kernel execution",
        "random_stress": "Stress test with random operations"
    }

    def __init__(self, gpu_id: int = 0, array_size: Optional[int] = None):

        if not DEPENDENCIES_AVAILABLE:
            raise RuntimeWarning(f"Required dependencies not available: {_import_error}")

        self.gpu_id = gpu_id

        # Setup GPU
        self._setup_gpu()

        # Set array size based on GPU memory if not specified
        if array_size is None:
            total_mem = self.gpu_properties['totalGlobalMem']
            if total_mem < 4 * 1024**3:  # Less than 4GB
                self.array_size = 16 * 1024 * 1024
            else:
                self.array_size = 32 * 1024 * 1024  # 32M elements (128MB for uint32)
        else:
            self.array_size = array_size

        # Setup logging
        self._setup_logging()

    def _setup_gpu(self):
        try:
            cp.cuda.Device(self.gpu_id).use()
            self.device = cp.cuda.Device(self.gpu_id)
            self.gpu_properties = cp.cuda.runtime.getDeviceProperties(self.gpu_id)
        except cp.cuda.runtime.CUDARuntimeError as e:
            raise RuntimeError(f"Failed to initialize GPU {self.gpu_id}: {e}")

    def _setup_logging(self):
        self.logger = logging.getLogger(f"{__name__}.GPU{self.gpu_id}")
        if not self.logger.handlers:
            handler = logging.NullHandler()
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.WARNING)

    def get_gpu_info(self) -> Dict:
        props = self.gpu_properties
        return {
            "gpu_id": self.gpu_id,
            "name": props['name'].decode(),
            "compute_capability": f"{props['major']}.{props['minor']}",
            "total_memory_gb": props['totalGlobalMem'] / (1024**3),
            "ecc_enabled": bool(props['ECCEnabled']),
            "test_array_size_mb": self.array_size * 4 / (1024**2)
        }

    def test_memory_patterns(self) -> TestResult:
        start_time = time.time()
        errors = 0
        target_duration = self.MAX_DURATION
        patterns = [
            (0x00000000, "All zeros"),
            (0xFFFFFFFF, "All ones"),
            (0xAAAAAAAA, "Alternating 1010"),
            (0x55555555, "Alternating 0101"),
            (0x0F0F0F0F, "Alternating nibbles"),
            (0xF0F0F0F0, "Alternating nibbles inverse"),
            (0x00FF00FF, "Alternating bytes"),
            (0xFF00FF00, "Alternating bytes inverse"),
            (0xDEADBEEF, "Mixed pattern"),
            (0x5A5A5A5A, "Test pattern"),
        ]

        try:
            with self.device:
                gpu_array = cp.zeros(self.array_size, dtype=cp.uint32)

                # Run patterns repeatedly for ~5 minutes
                iteration = 0
                while (time.time() - start_time) < target_duration:
                    for pattern_value, pattern_name in patterns:
                        gpu_array.fill(pattern_value)
                        cp.cuda.Stream.null.synchronize()

                        mismatches = gpu_array != pattern_value
                        error_count = cp.sum(mismatches).get()

                        if error_count > 0:
                            errors += error_count

                        # Check if we've reached target duration
                        if (time.time() - start_time) >= target_duration:
                            break
                    iteration += 1

            elapsed = time.time() - start_time
            passed = errors == 0
            message = f"All patterns passed ({iteration} iterations)" if passed else f"{errors} pattern errors detected ({iteration} iterations)"

            return TestResult("memory_patterns", passed, errors, elapsed, message)

        except Exception as e:
            elapsed = time.time() - start_time
            return TestResult("memory_patterns", False, -1, elapsed, f"Test crashed: {str(e)}")

    def test_arithmetic_operations(self) -> TestResult:
        start_time = time.time()
        errors = 0
        target_duration = self.MAX_DURATION

        try:
            with self.device:
                size = self.array_size

                operations = [
                    ("Addition", lambda x, y: x + y),
                    ("Subtraction", lambda x, y: x - y),
                    ("Multiplication", lambda x, y: x * y),
                    ("Division", lambda x, y: x / (y + 0.001)),
                    ("Sin", lambda x, y: cp.sin(x)),
                    ("Cos", lambda x, y: cp.cos(x)),
                    ("Sqrt", lambda x, y: cp.sqrt(cp.abs(x))),
                    ("Exp", lambda x, y: cp.exp(-cp.abs(x) / 1000)),
                ]

                iteration = 0
                while (time.time() - start_time) < target_duration:
                    # Create new data each iteration
                    a = cp.arange(size, dtype=cp.float32) * 0.001 + iteration * 0.0001
                    b = cp.ones(size, dtype=cp.float32) * 3.14159

                    for op_name, op_func in operations:
                        result1 = op_func(a, b)
                        result2 = op_func(a, b)

                        diff = cp.abs(result1 - result2)
                        tolerance = cp.max(cp.abs(result1)) * 1e-6
                        inconsistent = diff > tolerance
                        error_count = cp.sum(inconsistent).get()

                        if error_count > 0:
                            errors += error_count

                        # Check if we've reached target duration
                        if (time.time() - start_time) >= target_duration:
                            break

                    if (time.time() - start_time) >= target_duration:
                        break
                    iteration += 1

            elapsed = time.time() - start_time
            passed = errors == 0
            message = f"All arithmetic operations passed ({iteration} iterations)" if passed else f"{errors} arithmetic errors detected ({iteration} iterations)"

            return TestResult("arithmetic_operations", passed, errors, elapsed, message)

        except Exception as e:
            elapsed = time.time() - start_time
            return TestResult("arithmetic_operations", False, -1, elapsed, f"Test crashed: {str(e)}")

    def test_memory_integrity(self) -> TestResult:
        start_time = time.time()
        errors = 0
        target_duration = self.MAX_DURATION

        try:
            with self.device:
                iteration = 0
                while (time.time() - start_time) < target_duration:
                    rng = cp.random.RandomState(seed=42 + iteration)
                    original = rng.randint(0, 2**30, size=self.array_size, dtype=cp.int32)
                    original_sum = cp.sum(original, dtype=cp.int64).get()

                    data = cp.copy(original)
                    for cycle in range(20):
                        temp = cp.copy(data)
                        data = temp

                        if cycle % 5 == 4:
                            current_sum = cp.sum(data, dtype=cp.int64).get()
                            if current_sum != original_sum:
                                errors += 1

                            differences = data != original
                            diff_count = cp.sum(differences).get()
                            if diff_count > 0:
                                errors += diff_count

                    iteration += 1

                    # Check if we've reached target duration
                    if (time.time() - start_time) >= target_duration:
                        break

            elapsed = time.time() - start_time
            passed = errors == 0
            message = f"Memory integrity maintained ({iteration} iterations)" if passed else f"{errors} memory corruption events ({iteration} iterations)"

            return TestResult("memory_integrity", passed, errors, elapsed, message)

        except Exception as e:
            elapsed = time.time() - start_time
            return TestResult("memory_integrity", False, -1, elapsed, f"Test crashed: {str(e)}")

    def test_data_transfer(self) -> TestResult:
        start_time = time.time()
        errors = 0
        target_duration = self.MAX_DURATION
        transfer_size = min(self.array_size, 10 * 1024 * 1024)

        try:
            iteration = 0
            while (time.time() - start_time) < target_duration:
                host_data = np.random.randint(0, 2**31, size=transfer_size, dtype=np.int32)

                for cycle in range(10):
                    device_data = cp.asarray(host_data)
                    result = cp.asnumpy(device_data)

                    if not np.array_equal(host_data, result):
                        differences = host_data != result
                        diff_count = np.sum(differences)
                        errors += diff_count

                iteration += 1

                # Check if we've reached target duration
                if (time.time() - start_time) >= target_duration:
                    break

            elapsed = time.time() - start_time
            passed = errors == 0
            message = f"All transfers successful ({iteration} iterations)" if passed else f"{errors} transfer errors detected ({iteration} iterations)"

            return TestResult("data_transfer", passed, errors, elapsed, message)

        except Exception as e:
            elapsed = time.time() - start_time
            return TestResult("data_transfer", False, -1, elapsed, f"Test crashed: {str(e)}")

    def test_concurrent_operations(self) -> TestResult:
        """
        Test concurrent kernel execution and stream operations.
        Runs for ~5 minutes. Detects synchronization issues and race conditions.

        Returns:
            TestResult object with test outcome
        """
        start_time = time.time()
        errors = 0
        target_duration = self.MAX_DURATION

        try:
            with self.device:
                num_streams = 4
                iteration = 0

                while (time.time() - start_time) < target_duration:
                    streams = [cp.cuda.Stream() for _ in range(num_streams)]
                    arrays = []

                    for i, stream in enumerate(streams):
                        with stream:
                            arr = cp.full(self.array_size // num_streams, i + iteration, dtype=cp.int32)
                            arrays.append(arr)
                            arr *= 2
                            arr += 10

                    for stream in streams:
                        stream.synchronize()

                    for i, arr in enumerate(arrays):
                        expected_value = (i + iteration) * 2 + 10
                        if not cp.all(arr == expected_value):
                            error_count = cp.sum(arr != expected_value).get()
                            errors += error_count

                    iteration += 1

                    # Check if we've reached target duration
                    if (time.time() - start_time) >= target_duration:
                        break

            elapsed = time.time() - start_time
            passed = errors == 0
            message = f"Concurrent operations stable ({iteration} iterations)" if passed else f"{errors} concurrency errors detected ({iteration} iterations)"

            return TestResult("concurrent_operations", passed, errors, elapsed, message)

        except Exception as e:
            elapsed = time.time() - start_time
            return TestResult("concurrent_operations", False, -1, elapsed, f"Test crashed: {str(e)}")

    def test_random_stress(self) -> TestResult:
        start_time = time.time()
        errors = 0
        target_duration = self.MAX_DURATION

        try:
            with self.device:
                iteration = 0
                while (time.time() - start_time) < target_duration:
                    for sub_iter in range(5):
                        size = self.array_size // 4
                        data = cp.random.random(size, dtype=cp.float32)

                        result = data
                        result = cp.sin(result * cp.pi)
                        result = cp.sqrt(cp.abs(result))
                        result = result * 1000
                        result = cp.floor(result)

                        data2 = cp.copy(data)
                        result2 = data2
                        result2 = cp.sin(result2 * cp.pi)
                        result2 = cp.sqrt(cp.abs(result2))
                        result2 = result2 * 1000
                        result2 = cp.floor(result2)

                        if not cp.allclose(result, result2, rtol=1e-5):
                            diff_count = cp.sum(cp.abs(result - result2) > 1e-3).get()
                            errors += diff_count

                        # Check if we've reached target duration
                        if (time.time() - start_time) >= target_duration:
                            break

                    if (time.time() - start_time) >= target_duration:
                        break
                    iteration += 1

            elapsed = time.time() - start_time
            passed = errors == 0
            message = f"Stress test passed ({iteration * 5} iterations)" if passed else f"{errors} stress test errors detected ({iteration * 5} iterations)"

            return TestResult("random_stress", passed, errors, elapsed, message)

        except Exception as e:
            elapsed = time.time() - start_time
            return TestResult("random_stress", False, -1, elapsed, f"Test crashed: {str(e)}")

    def run_all_tests(self) -> Dict[str, TestResult]:
        results = {}
        for test_name in self.AVAILABLE_TESTS.keys():
            test_method = getattr(self, f"test_{test_name}")
            results[test_name] = test_method()
        return results


class MultiGPUSDCChecker:
    def __init__(self, gpu_ids: Optional[List[int]] = None):

        if not DEPENDENCIES_AVAILABLE:
            raise RuntimeWarning(f"Required dependencies not available: {_import_error}")        

        # Detect available GPUs
        try:
            self.num_gpus = cp.cuda.runtime.getDeviceCount()
        except Exception as e:
            raise RuntimeError(f"Failed to detect GPUs: {e}")

        # Set GPU IDs to test
        if gpu_ids is None:
            self.gpu_ids = list(range(self.num_gpus))
        else:
            # Validate GPU IDs
            invalid_ids = [gid for gid in gpu_ids if gid >= self.num_gpus or gid < 0]
            if invalid_ids:
                raise ValueError(f"Invalid GPU IDs: {invalid_ids}. Available GPUs: 0-{self.num_gpus-1}")
            self.gpu_ids = gpu_ids

        # Create checkers for each GPU
        self.checkers = {}
        for gpu_id in self.gpu_ids:
            try:
                self.checkers[gpu_id] = GPUSDCChecker(gpu_id=gpu_id)
            except Exception as e:
                print(f"Warning: Failed to initialize checker for GPU {gpu_id}: {e}")

        if not self.checkers:
            raise RuntimeError("No GPU checkers could be initialized")

    def _run_gpu_tests(self, gpu_id: int) -> Tuple[int, Dict[str, TestResult]]:
        if gpu_id not in self.checkers:
            return gpu_id, {}

        checker = self.checkers[gpu_id]
        return gpu_id, checker.run_all_tests()

    def run_all_tests(self) -> Dict[int, Dict[str, TestResult]]:
        all_results = {}

        # Parallel execution using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(self.checkers)) as executor:
            futures = {
                executor.submit(self._run_gpu_tests, gpu_id): gpu_id
                for gpu_id in self.checkers.keys()
            }

            for future in as_completed(futures):
                gpu_id, results = future.result()
                all_results[gpu_id] = results

        return all_results

    def get_summary(self, results: Dict[int, Dict[str, TestResult]]) -> Dict:
        summary = {
            "hostname": socket.gethostname(),
            "num_gpus_tested": len(self.checkers),
            "gpu_ids": list(self.checkers.keys()),
            "gpu_info": {gpu_id: checker.get_gpu_info() for gpu_id, checker in self.checkers.items()},
            "per_gpu_results": {},
            "aggregate_stats": {
                "total_errors": 0,
                "failed_gpus": [],
                "healthy_gpus": []
            }
        }

        for gpu_id, test_results in results.items():
            gpu_errors = sum(r.error_count for r in test_results.values() if r.error_count > 0)
            gpu_passed = all(r.passed for r in test_results.values())

            summary["per_gpu_results"][gpu_id] = {
                "status": "PASS" if gpu_passed else "FAIL",
                "total_errors": gpu_errors,
                "test_results": {name: result.to_dict() for name, result in test_results.items()}
            }

            summary["aggregate_stats"]["total_errors"] += gpu_errors

            if gpu_errors > 0:
                summary["aggregate_stats"]["failed_gpus"].append(gpu_id)
            else:
                summary["aggregate_stats"]["healthy_gpus"].append(gpu_id)

        summary["aggregate_stats"]["status"] = "PASS" if summary["aggregate_stats"]["total_errors"] == 0 else "FAIL"
        summary["timestamp"] = datetime.now().isoformat()

        return summary

    def print_summary(self, results: Dict[int, Dict[str, TestResult]]):
        summary = self.get_summary(results)

        print("\n" + "=" * 70)
        print(" GPU Silent Data Corruption Test Results")
        print("=" * 70)
        print(f" Host: {summary['hostname']}")
        print(f" GPUs Tested: {summary['num_gpus_tested']} (IDs: {summary['gpu_ids']})")
        print(f" Total Errors: {summary['aggregate_stats']['total_errors']}")
        print(f" Healthy GPUs: {len(summary['aggregate_stats']['healthy_gpus'])} - {summary['aggregate_stats']['healthy_gpus']}")
        print(f" Failed GPUs: {len(summary['aggregate_stats']['failed_gpus'])} - {summary['aggregate_stats']['failed_gpus']}")

        print("\n Per-GPU Results:")
        for gpu_id in sorted(summary['per_gpu_results'].keys()):
            gpu_result = summary['per_gpu_results'][gpu_id]
            info = summary['gpu_info'][gpu_id]
            status = "✓ PASS" if gpu_result['status'] == "PASS" else "✗ FAIL"
            print(f"  GPU {gpu_id} ({info['name']}): {status}")
            if gpu_result['total_errors'] > 0:
                print(f"    Errors: {gpu_result['total_errors']}")
                for test_name, test_result in gpu_result['test_results'].items():
                    if not test_result['passed']:
                        print(f"      - {test_name}: {test_result['error_count']} errors")

        print("=" * 70)

        if summary['aggregate_stats']['total_errors'] == 0:
            print("\n ✓ SUCCESS: No errors detected - All GPUs appear healthy")
        else:
            print("\n ✗ FAILURE: Silent data corruption detected on one or more GPUs!")
            print(f" ✗ Failed GPUs: {summary['aggregate_stats']['failed_gpus']}")
            print(" ✗ These GPUs may have hardware issues and should not be used in production")

    def save_results(self, results: Dict[int, Dict[str, TestResult]], filename: Optional[str] = None) -> str:
        summary = self.get_summary(results)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            hostname = socket.gethostname()
            filename = f"gpu_sdc_results_{hostname}_{timestamp}.json"

        with open(filename, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"\n Results saved to: {filename}")

        return filename


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='GPU Silent Data Corruption (SDC) Checker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Test all available GPUs
  %(prog)s --gpus 0 1           # Test specific GPUs (0 and 1)
  %(prog)s --output results.json # Save results to specific file

Note: Each test runs for approximately 5 minutes. Total runtime will be ~30 minutes
      for all 6 tests running in parallel across all GPUs.
        """
    )

    parser.add_argument('--gpus', nargs='+', type=int, metavar='ID',
                        help='List of specific GPU IDs to test (e.g., --gpus 0 1 2). Default: all GPUs')
    parser.add_argument('--output', '-o', type=str, metavar='FILE',
                        help='Output JSON file (auto-generated if not specified)')

    args = parser.parse_args()

    try:
        print("\n" + "=" * 70)
        print(" GPU Silent Data Corruption Checker")
        print("=" * 70)
        print(f" Host: {socket.gethostname()}")
        print("=" * 70 + "\n")

        # Initialize checker
        checker = MultiGPUSDCChecker(gpu_ids=args.gpus)

        print(f"Testing {len(checker.checkers)} GPU(s): {list(checker.checkers.keys())}")
        print("Running all tests on all GPUs in parallel...\n")

        # Run all tests
        results = checker.run_all_tests()

        # Print summary
        checker.print_summary(results)

        # Save results
        checker.save_results(results, filename=args.output)

        # Exit with appropriate code
        summary = checker.get_summary(results)
        sys.exit(0 if summary['aggregate_stats']['total_errors'] == 0 else 1)

    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
