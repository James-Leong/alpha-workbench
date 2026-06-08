"""Optional Agno workflow runtime helpers.

The project can run without Agno installed, but when Agno is available this
module builds real Agno Workflow/Step objects around our stable Python
interfaces.
"""

from __future__ import annotations

from typing import Any, Callable


AGNO_IMPORT_ERROR: str | None = None

try:  # Agno current package layout.
    from agno.workflow.step import Step, StepOutput
    from agno.workflow.workflow import Workflow

    AGNO_AVAILABLE = True
except Exception as exc:
    try:  # Older/shorter import style shown in some examples.
        from agno.workflow import Step, StepOutput, Workflow

        AGNO_AVAILABLE = True
    except Exception:
        Step = None  # type: ignore[assignment]
        StepOutput = None  # type: ignore[assignment]
        Workflow = None  # type: ignore[assignment]
        AGNO_AVAILABLE = False
        AGNO_IMPORT_ERROR = str(exc)


StepExecutor = Callable[[Any], Any]


def workflow_runtime_metadata() -> dict[str, Any]:
    return {
        "workflow_framework": "agno" if AGNO_AVAILABLE else "python_fallback",
        "agno_available": AGNO_AVAILABLE,
        "agno_import_error": AGNO_IMPORT_ERROR,
    }


def make_step_output(content: Any) -> Any:
    if StepOutput is None:
        return content
    return StepOutput(content=content)


def step_input_payload(step_input: Any) -> Any:
    previous = getattr(step_input, "previous_step_content", None)
    if previous is not None:
        return previous
    return getattr(step_input, "input", step_input)


def workflow_response_content(response: Any) -> Any:
    if isinstance(response, dict):
        return response
    for attr in ("content", "output", "result"):
        value = getattr(response, attr, None)
        if value is not None:
            return value
    return response


def build_agno_workflow(
    *,
    name: str,
    description: str,
    steps: list[tuple[str, str, StepExecutor]],
) -> Any | None:
    if not AGNO_AVAILABLE or Step is None or Workflow is None:
        return None

    agno_steps = [
        Step(name=step_name, description=step_description, executor=executor)
        for step_name, step_description, executor in steps
    ]
    try:
        return Workflow(
            name=name,
            description=description,
            steps=agno_steps,
            store_events=True,
            telemetry=False,
        )
    except TypeError:
        return Workflow(name=name, description=description, steps=agno_steps)
