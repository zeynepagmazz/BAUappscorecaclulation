from typing import Optional


def perform_calculation(input_value: Optional[float]) -> float:
	"""Placeholder calculation logic. Replace with the real logic.

	Currently doubles the numeric input.
	"""
	if input_value is None:
		raise ValueError("Input is required")

	return float(input_value) * 2.0
