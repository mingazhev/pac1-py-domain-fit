"""Typed routing surface for the clean PAC1 runtime."""

from .extractor import (
    RoutedTaskInputs,
    extract_task_inputs,
    extract_task_inputs_for_decision,
    extract_typed_request_for_decision,
)
from .gateway import StructuredExtractionGateway
from .gateway_factory import build_structured_extraction_gateway
from .finance_lookup import (
    FinanceLookupAction,
    FinanceLookupIntent,
    format_finance_record_date_output,
    resolve_finance_lookup_intent,
)
from .model import (
    AccountLookupRequest,
    CaptureLookupRequest,
    ContactLookupRequest,
    EntityQueryRequest,
    FinanceLineItemDraft,
    FinanceLookupRequest,
    FinanceMutationRequest,
    FollowUpRescheduleRequest,
    FollowUpSendRequest,
    InboxEmailLookupRequest,
    InboxProcessNextRequest,
    MessageQueryRequest,
    OutboundEmailLookupRequest,
    OutboxDraftRequest,
    ProjectMutationRequest,
    ProjectQueryRequest,
    QueueMutationRequest,
    QueueStateLookupRequest,
    TaskIntent,
    TaskRouteDecision,
    TypedTaskRequest,
)
from .openai_gateway import OpenAICompatibleStructuredExtractionGateway
from .openai_gateway import OpenAIStructuredExtractionGateway
from .provider import (
    JsonSchemaPromptProfile,
    NativePromptProfile,
    ProviderCapabilities,
    default_prompt_profile_name,
    provider_config_for_model,
    resolve_transport_name,
)
from .resolvers import (
    CastResolverSet,
    ProjectResolverSet,
    resolve_entity_candidate,
    resolve_message_entity_candidate,
    resolve_project_candidate,
    resolve_project_subject_candidate,
)
from .step_contract import (
    StepContract,
    StepPolicyClass,
    StepResultShape,
    StepSideEffectClass,
)
from .step_registry import (
    UnregisteredStepError,
    contract_for_command,
    registered_step_types,
)

AccountLookupCommand = AccountLookupRequest
CaptureLookupCommand = CaptureLookupRequest
ContactLookupCommand = ContactLookupRequest
EntityQueryCommand = EntityQueryRequest
FinanceLineItem = FinanceLineItemDraft
FinanceLookupCommand = FinanceLookupRequest
FinanceMutationCommand = FinanceMutationRequest
FollowUpRescheduleCommand = FollowUpRescheduleRequest
FollowUpSendCommand = FollowUpSendRequest
InboxEmailLookupCommand = InboxEmailLookupRequest
InboxProcessNextCommand = InboxProcessNextRequest
MessageQueryCommand = MessageQueryRequest
OutboundEmailLookupCommand = OutboundEmailLookupRequest
OutboxDraftCommand = OutboxDraftRequest
ProjectMutationCommand = ProjectMutationRequest
ProjectQueryCommand = ProjectQueryRequest
QueueMutationCommand = QueueMutationRequest
QueueStateLookupCommand = QueueStateLookupRequest
TypedStep = TypedTaskRequest

__all__ = [
    "AccountLookupCommand",
    "CastResolverSet",
    "CaptureLookupCommand",
    "ContactLookupCommand",
    "EntityQueryCommand",
    "FinanceLineItem",
    "FinanceLookupAction",
    "FinanceLookupCommand",
    "FinanceLookupIntent",
    "FinanceMutationCommand",
    "FollowUpRescheduleCommand",
    "FollowUpSendCommand",
    "InboxEmailLookupCommand",
    "InboxProcessNextCommand",
    "JsonSchemaPromptProfile",
    "MessageQueryCommand",
    "NativePromptProfile",
    "OpenAICompatibleStructuredExtractionGateway",
    "OpenAIStructuredExtractionGateway",
    "OutboundEmailLookupCommand",
    "OutboxDraftCommand",
    "ProjectMutationCommand",
    "ProjectQueryCommand",
    "ProjectResolverSet",
    "ProviderCapabilities",
    "QueueStateLookupCommand",
    "QueueMutationCommand",
    "RoutedTaskInputs",
    "StepContract",
    "StepPolicyClass",
    "StepResultShape",
    "StepSideEffectClass",
    "StructuredExtractionGateway",
    "TaskIntent",
    "TaskRouteDecision",
    "TypedStep",
    "UnregisteredStepError",
    "build_structured_extraction_gateway",
    "contract_for_command",
    "default_prompt_profile_name",
    "extract_task_inputs",
    "extract_task_inputs_for_decision",
    "extract_typed_request_for_decision",
    "format_finance_record_date_output",
    "provider_config_for_model",
    "registered_step_types",
    "resolve_transport_name",
    "resolve_entity_candidate",
    "resolve_finance_lookup_intent",
    "resolve_message_entity_candidate",
    "resolve_project_candidate",
    "resolve_project_subject_candidate",
]
