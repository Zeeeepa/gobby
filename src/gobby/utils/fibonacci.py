"""Recursive fibonacci function implementation."""


def fibonacci(n: int) -> int:
    """
    Compute the nth Fibonacci number using recursion.

    Args:
        n: The position in the Fibonacci sequence (0-indexed)

    Returns:
        The nth Fibonacci number
    """
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def test_fibonacci() -> None:
    """Test fibonacci function with values n=0..12."""
    expected = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]
    for n in range(13):
        result = fibonacci(n)
        assert result == expected[n], f"fibonacci({n}) = {result}, expected {expected[n]}"
    print("All tests passed!")


if __name__ == "__main__":
    test_fibonacci()
