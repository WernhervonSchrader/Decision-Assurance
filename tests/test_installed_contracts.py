from decision_assurance.benchmark import _transition_fixture
from decision_assurance.validation import ContractValidator


def test_packaged_benchmark_transition_fixture_is_contract_valid() -> None:
    ContractValidator().validate("decision-file", _transition_fixture())
