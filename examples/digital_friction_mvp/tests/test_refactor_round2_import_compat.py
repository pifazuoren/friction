from __future__ import annotations

from proto.family_helper_agent import FamilyHelperAgent as OldFamilyHelperAgent
from proto.outcome_model import (
    derive_effective_support_features as old_derive_effective_support_features,
)
from proto.outcome_model import infer_avoid_reason as old_infer_avoid_reason
from proto.outcome_model import infer_support_mode as old_infer_support_mode
from proto.outcome_model import resolve_attempt_outcome as old_resolve_attempt_outcome
from proto.outcome_model import support_quality_from_env as old_support_quality_from_env
from proto.psychology.helplessness import (
    apply_helplessness_update as new_apply_helplessness_update,
)
from proto.psychology.helplessness import (
    apply_helplessness_update_rule_v1 as new_apply_helplessness_update_rule_v1,
)
from proto.psychology.helplessness import (
    apply_helplessness_update_v2 as new_apply_helplessness_update_v2,
)
from proto.state_update import (
    apply_helplessness_update as old_apply_helplessness_update,
)
from proto.state_update import (
    apply_helplessness_update_rule_v1 as old_apply_helplessness_update_rule_v1,
)
from proto.state_update import (
    apply_helplessness_update_v2 as old_apply_helplessness_update_v2,
)
from proto.support.family_helper import FamilyHelperAgent as NewFamilyHelperAgent
from proto.support.protocol import SupportRequest as NewSupportRequest
from proto.support.protocol import SupportResponse as NewSupportResponse
from proto.support.protocol import (
    support_style_to_support_mode as new_support_style_to_support_mode,
)
from proto.support.support_response import (
    SupportResponseBlock as NewSupportResponseBlock,
)
from proto.support.support_response import (
    SupportResponseBlockOutput as NewSupportResponseBlockOutput,
)
from proto.support_protocol import SupportRequest as OldSupportRequest
from proto.support_protocol import SupportResponse as OldSupportResponse
from proto.support_protocol import (
    support_style_to_support_mode as old_support_style_to_support_mode,
)
from proto.support_response_block import (
    SupportResponseBlock as OldSupportResponseBlock,
)
from proto.support_response_block import (
    SupportResponseBlockOutput as OldSupportResponseBlockOutput,
)
from proto.task_flow.outcome import (
    derive_effective_support_features as new_derive_effective_support_features,
)
from proto.task_flow.outcome import infer_avoid_reason as new_infer_avoid_reason
from proto.task_flow.outcome import infer_support_mode as new_infer_support_mode
from proto.task_flow.outcome import resolve_attempt_outcome as new_resolve_attempt_outcome
from proto.task_flow.outcome import support_quality_from_env as new_support_quality_from_env


def test_round2_outcome_wrapper_exports_old_objects() -> None:
    assert new_resolve_attempt_outcome is old_resolve_attempt_outcome
    assert new_infer_avoid_reason is old_infer_avoid_reason
    assert new_infer_support_mode is old_infer_support_mode
    assert new_support_quality_from_env is old_support_quality_from_env
    assert (
        new_derive_effective_support_features
        is old_derive_effective_support_features
    )


def test_round2_helplessness_wrapper_exports_old_objects() -> None:
    assert new_apply_helplessness_update is old_apply_helplessness_update
    assert new_apply_helplessness_update_v2 is old_apply_helplessness_update_v2
    assert (
        new_apply_helplessness_update_rule_v1
        is old_apply_helplessness_update_rule_v1
    )


def test_round2_support_wrapper_exports_old_objects() -> None:
    assert NewSupportRequest is OldSupportRequest
    assert NewSupportResponse is OldSupportResponse
    assert new_support_style_to_support_mode is old_support_style_to_support_mode
    assert NewFamilyHelperAgent is OldFamilyHelperAgent
    assert NewSupportResponseBlock is OldSupportResponseBlock
    assert NewSupportResponseBlockOutput is OldSupportResponseBlockOutput
