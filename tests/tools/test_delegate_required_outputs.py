from tools.delegation_required_outputs import (
    append_required_outputs_contract,
    build_required_outputs_retry_message,
    coerce_required_outputs,
    validate_required_outputs,
)
from tools.delegate_tool import _run_single_child


def test_coerce_required_outputs_rejects_invalid_and_duplicate_names():
    assert coerce_required_outputs(None) == (None, None)
    assert coerce_required_outputs([])[1]
    assert coerce_required_outputs(["range formulas", "Range Formulas"])[1]


def test_contract_names_every_required_heading():
    context = append_required_outputs_contract(
        "Read only.", ["Interval formulas", "Manifest facts"]
    )
    assert "Read only." in context
    assert "- Interval formulas" in context
    assert "- Manifest facts" in context


def test_report_with_every_named_nonempty_section_passes():
    valid, errors = validate_required_outputs(
        "# Interval formulas\nUse start minus warmup.\n\n"
        "## Manifest facts\nInclude the latest source revision.",
        ["Interval formulas", "Manifest facts"],
    )
    assert valid is True
    assert errors == []


def test_generic_prior_summary_does_not_pass_named_output_validation():
    valid, errors = validate_required_outputs(
        "The earlier audit found that workers use PostgreSQL and ClickHouse.",
        ["Interval formulas", "Manifest facts"],
    )
    assert valid is False
    assert errors == [
        "Missing Markdown heading: Interval formulas",
        "Missing Markdown heading: Manifest facts",
    ]


def test_empty_named_section_does_not_pass():
    valid, errors = validate_required_outputs(
        "# Interval formulas\n# Manifest facts\nA concrete fact.",
        ["Interval formulas", "Manifest facts"],
    )
    assert valid is False
    assert errors == ["Markdown section is empty: Interval formulas"]


def test_retry_message_names_exact_validation_errors():
    message = build_required_outputs_retry_message(
        ["Missing Markdown heading: Manifest facts"]
    )
    assert "Missing Markdown heading: Manifest facts" in message
    assert "SCOUT OUTPUT CONTRACT" in message


class _StubScout:
    tool_progress_callback = None
    _delegate_saved_tool_names: list = []
    _credential_pool = None
    _subagent_id = None
    _delegate_depth = 1
    _parent_subagent_id = None
    _delegate_output_schema = None
    model = "test-model"
    session_prompt_tokens = 0
    session_completion_tokens = 0
    session_estimated_cost_usd = 0.0
    session_reasoning_tokens = 0

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self._delegate_required_outputs = ["Interval formulas", "Manifest facts"]

    def get_activity_summary(self):
        return {"api_call_count": 1, "max_iterations": 5, "current_tool": None}

    def run_conversation(self, user_message, task_id=None, **_kwargs):
        self.calls.append(user_message)
        return {
            "final_response": self.responses.pop(0),
            "completed": True,
            "api_calls": 1,
            "messages": [],
        }

    def close(self):
        return None


class _StubParent:
    _current_task_id = None
    _delegate_depth = 0

    def _touch_activity(self, _description):
        return None


def _run_scout(child):
    return _run_single_child(0, "inspect inputs", child, _StubParent())


def test_named_scout_report_passes_without_retry():
    child = _StubScout(
        [
            "# Interval formulas\nstart minus warmup\n"
            "# Manifest facts\nsource revision"
        ]
    )
    entry = _run_scout(child)
    assert entry["status"] == "completed"
    assert entry["required_outputs_valid"] is True
    assert len(child.calls) == 1


def test_generic_summary_retries_once_and_still_fails():
    generic = "Workers use PostgreSQL and ClickHouse."
    child = _StubScout([generic, generic])
    entry = _run_scout(child)
    assert entry["status"] == "failed"
    assert entry["required_outputs_valid"] is False
    assert entry["required_outputs_retries"] == 1
    assert entry["required_outputs_errors"] == [
        "Missing Markdown heading: Interval formulas",
        "Missing Markdown heading: Manifest facts",
    ]
    assert len(child.calls) == 2


def test_generic_summary_can_be_corrected_on_bounded_retry():
    child = _StubScout(
        [
            "Workers use PostgreSQL and ClickHouse.",
            "# Interval formulas\nstart minus warmup\n"
            "# Manifest facts\nsource revision",
        ]
    )
    entry = _run_scout(child)
    assert entry["status"] == "completed"
    assert entry["required_outputs_valid"] is True
    assert entry["required_outputs_retries"] == 1
    assert len(child.calls) == 2
