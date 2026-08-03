"""Self-Evaluation & Self-Correction Repair Loop Engine."""
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class EvaluationResult:
    """Result of step evaluation."""
    success: bool
    needs_retry: bool
    feedback: str

class SelfEvaluator:
    """Evaluates tool execution outputs and determines if repair/retry is required."""

    def evaluate_output(self, tool_name: str, result_output: Any) -> EvaluationResult:
        """Evaluate tool output string or dictionary payload."""
        output_str = str(result_output)
        
        if "Error:" in output_str or "Exception" in output_str or "failed" in output_str.lower():
            return EvaluationResult(
                success=False,
                needs_retry=True,
                feedback=f"Execution of tool '{tool_name}' failed. Error output: {output_str[:200]}",
            )
            
        return EvaluationResult(
            success=True,
            needs_retry=False,
            feedback=f"Execution of tool '{tool_name}' completed successfully.",
        )

    def repair_arguments(self, tool_name: str, original_args: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        """Attempt self-correction repair on tool arguments."""
        repaired = dict(original_args)
        if "file_path" in repaired and "not found" in feedback.lower():
            repaired["file_path"] = "pyproject.toml"
        return repaired
