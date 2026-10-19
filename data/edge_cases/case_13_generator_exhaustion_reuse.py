"""Edge Case 13: Generator exhaustion on multiple passes.

Category: Iterator Semantics & Pipeline State
Vulnerability: Generators and iterators can only be consumed once; second pass yields empty.
SteerLM / Fuzzer relevance: Fuzzer tests generator objects and streams across multi-pass metrics.
"""

from typing import Iterable, Tuple, Optional
import itertools

EDGE_CASE_METADATA = {
    "case_id": "EC-013",
    "name": "generator_exhaustion",
    "category": "iterator_semantics",
    "vulnerability_type": "ZeroDivisionError / Empty Iterator Silent Failure",
    "trigger_input": "Passing a generator expression (x for x in data) to a two-pass algorithm",
    "expected_exception": "ZeroDivisionError",
    "description": "Iterating over an Iterable twice: if input is a generator, pass 2 sees empty elements.",
    "remediation": "Convert to a list if bounded, or use itertools.tee() to clone the iterator."
}


def buggy_mean_and_variance(numbers: Iterable[float]) -> Tuple[float, float]:
    """Buggy two-pass calculation: if numbers is a generator, second pass finds zero elements."""
    # Pass 1: compute mean
    total = 0.0
    count = 0
    for n in numbers:
        total += n
        count += 1
    if count == 0:
        return 0.0, 0.0
    mean = total / count

    # Pass 2: compute variance (numbers is now EXHAUSTED if it was a generator!)
    var_sum = 0.0
    pass2_count = 0
    for n in numbers:  # Yields NOTHING!
        var_sum += (n - mean) ** 2
        pass2_count += 1

    variance = var_sum / count  # Returns 0.0 variance even when variance > 0!
    return mean, variance


def safe_mean_and_variance(numbers: Optional[Iterable[float]]) -> Tuple[float, float]:
    """Defensive calculation: uses Welford's single-pass algorithm or materializes safely."""
    if numbers is None:
        return 0.0, 0.0

    # Welford's single-pass algorithm for numerical mean and variance
    count = 0
    mean = 0.0
    M2 = 0.0

    for x in numbers:
        if not isinstance(x, (int, float)):
            continue
        count += 1
        delta = x - mean
        mean += delta / count
        delta2 = x - mean
        M2 += delta * delta2

    if count < 1:
        return 0.0, 0.0
    variance = M2 / count
    return round(mean, 4), round(variance, 4)


def test_edge_case():
    # Pass generator
    gen_buggy = (x for x in [10.0, 20.0, 30.0])
    mean_b, var_b = buggy_mean_and_variance(gen_buggy)
    # Buggy computed 0.0 variance because second pass was empty!
    assert var_b == 0.0  # Incorrect!

    # Safe single-pass correctly calculates mean and variance in one pass
    gen_safe = (x for x in [10.0, 20.0, 30.0])
    mean_s, var_s = safe_mean_and_variance(gen_safe)
    assert mean_s == 20.0
    assert var_s == 66.6667
    assert safe_mean_and_variance(None) == (0.0, 0.0)
    assert safe_mean_and_variance([]) == (0.0, 0.0)
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-013 passed verification.")
