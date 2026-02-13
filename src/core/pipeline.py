from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from src.core.contracts import ContractValidator
from src.core.intent_lock import IntentLock
from src.core.intent_router import IntentRouter
from src.core.postprocess import Postprocessor

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    """Normalized incoming message (common format across all channels)."""

    channel_type: str
    channel_conversation_id: str
    channel_message_id: str
    text: str
    sender_name: str | None = None
    sender_phone: str | None = None
    timestamp: datetime | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class OutgoingMessage:
    """Agent response ready to be sent through a channel adapter."""

    text: str
    conversation_id: str
    channel_conversation_id: str
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineContext:
    """Pipeline context that gets enriched at each step."""

    incoming: IncomingMessage
    agent_config: object
    knowledge: dict
    dialogue_policy: object

    history: list[dict] = field(default_factory=list)
    detected_intent: str | None = None
    calendar_context: str = ""
    ai_response: str | None = None
    outgoing: OutgoingMessage | None = None
    actions_to_run: list[str] = field(default_factory=list)
    error: str | None = None


class MessagePipeline:
    """
    Message processing pipeline.

    Steps:
    1. enrich       - load history/state
    2. detect       - detect intent
    3. pre_action   - actions before LLM (e.g., calendar lookup)
    4. think        - request to LLM
    5. validate     - contract validation
    6. postprocess  - normalize output
    7. post_action  - actions after LLM (booking/logging/etc.)
    """

    def __init__(self, brain, db_session=None):
        self.brain = brain
        self.db = db_session
        # These are initialized per-request from agent config in process().
        self._router: IntentRouter | None = None
        self._validator: ContractValidator | None = None
        self._postprocessor: Postprocessor | None = None
        self._intent_lock: IntentLock | None = None

    async def process(self, ctx: PipelineContext) -> PipelineContext:
        """Run the message through the whole pipeline."""
        # Initialize dialogue modules from config.
        self._router = IntentRouter(ctx.dialogue_policy.intents)
        self._validator = ContractValidator(ctx.agent_config.style)
        self._postprocessor = Postprocessor(ctx.agent_config.style)
        self._intent_lock = IntentLock()

        steps = [
            ("enrich", self._enrich),
            ("detect", self._detect_intent),
            ("pre_action", self._pre_action),
            ("think", self._think),
            ("validate", self._validate),
            ("postprocess", self._postprocess),
            ("post_action", self._post_action),
        ]

        for step_name, step_fn in steps:
            try:
                ctx = await step_fn(ctx)
                if ctx.error:
                    logger.error("Pipeline error at %s: %s", step_name, ctx.error)
                    break
            except Exception as e:
                logger.exception("Pipeline exception at %s", step_name)
                ctx.error = f"{step_name}: {str(e)}"
                break

        return ctx

    async def _enrich(self, ctx: PipelineContext) -> PipelineContext:
        """Load conversation history and state from DB."""
        if not self.db:
            return ctx

        from uuid import UUID

        from src.core.crud import get_conversation_history, get_or_create_conversation

        agent_id = ctx.incoming.metadata.get("agent_id")
        if not agent_id:
            return ctx

        if isinstance(agent_id, str):
            try:
                agent_id = UUID(agent_id)
            except ValueError:
                return ctx

        if not ctx.incoming.channel_conversation_id:
            return ctx

        conv, is_new = await get_or_create_conversation(
            self.db,
            agent_id=agent_id,
            channel_type=ctx.incoming.channel_type,
            channel_conversation_id=ctx.incoming.channel_conversation_id,
        )

        # Load history for existing conversations.
        if not is_new:
            ctx.history = await get_conversation_history(
                self.db,
                conv.id,
                limit=ctx.agent_config.llm.max_history,
            )

        # Load conversation state (for intent lock, pending bookings, etc.).
        ctx.incoming.metadata["conversation_state"] = conv.state or {}
        ctx.incoming.metadata["conversation_id"] = str(conv.id)

        # Update lead info from incoming message.
        if ctx.incoming.sender_name and not conv.lead_name:
            conv.lead_name = ctx.incoming.sender_name
        if ctx.incoming.sender_phone and not conv.lead_phone:
            conv.lead_phone = ctx.incoming.sender_phone

        return ctx

    async def _detect_intent(self, ctx: PipelineContext) -> PipelineContext:
        """Detect intent using IntentRouter + IntentLock."""
        if not self._router or not self._intent_lock:
            raise RuntimeError("Dialogue modules are not initialized")

        raw_intent = self._router.detect(ctx.incoming.text)

        # Apply intent lock using conversation state.
        conv_state = ctx.incoming.metadata.get("conversation_state", {})
        effective_intent = self._intent_lock.apply(
            state=conv_state,
            raw_intent=raw_intent,
            intents=ctx.dialogue_policy.intents,
        )

        ctx.detected_intent = effective_intent
        # Store updated state back.
        ctx.incoming.metadata["conversation_state"] = conv_state

        return ctx

    async def _pre_action(self, ctx: PipelineContext) -> PipelineContext:
        """Run actions before LLM (stub; implemented in Phase 2)."""
        # TODO: Check calendar if the user mentions a date/time.
        return ctx

    async def _think(self, ctx: PipelineContext) -> PipelineContext:
        """Call the AI Brain."""
        from src.core.prompt_builder import PromptBuilder

        system_prompt = PromptBuilder.build(
            agent_config=ctx.agent_config,
            knowledge=ctx.knowledge,
            extra_context=ctx.calendar_context,
        )

        messages = ctx.history + [{"role": "user", "content": ctx.incoming.text}]

        max_hist = ctx.agent_config.llm.max_history
        if len(messages) > max_hist:
            messages = messages[-max_hist:]

        response = await self.brain.think(system_prompt, messages)

        # Parse action tags from AI response.
        from src.core.action_parser import parse_action_tags

        parsed = parse_action_tags(response.content)

        ctx.ai_response = parsed.clean_text
        ctx.actions_to_run = parsed.actions
        ctx.outgoing = OutgoingMessage(
            text=parsed.clean_text,
            conversation_id=ctx.incoming.metadata.get("conversation_id", ""),
            channel_conversation_id=ctx.incoming.channel_conversation_id,
            metadata={"intent": ctx.detected_intent, "model": response.model, "usage": response.usage},
        )

        return ctx

    async def _validate(self, ctx: PipelineContext) -> PipelineContext:
        """Validate response against intent contract + style limits."""
        if not ctx.ai_response:
            return ctx

        if not self._router or not self._validator:
            raise RuntimeError("Dialogue modules are not initialized")

        intent_config = self._router.get_intent_config(ctx.detected_intent or "")
        contract = intent_config.contract if intent_config else None

        result = self._validator.validate(ctx.ai_response, contract)

        if not result.ok:
            logger.warning("Contract violation for intent %s: %s", ctx.detected_intent, result.violations)
            # Store violations in metadata for debugging.
            if ctx.outgoing:
                ctx.outgoing.metadata["contract_violations"] = result.violations

        return ctx

    async def _postprocess(self, ctx: PipelineContext) -> PipelineContext:
        """Post-process LLM output: markdown, fillers, limits, forbidden content."""
        if not ctx.outgoing:
            return ctx

        if not self._router or not self._postprocessor:
            raise RuntimeError("Dialogue modules are not initialized")

        intent_config = self._router.get_intent_config(ctx.detected_intent or "")
        contract = intent_config.contract if intent_config else None

        # Allow prepayment only if the response triggers booking creation.
        allow_prepayment = "CREATE_BOOKING" in (ctx.actions_to_run or [])

        cleaned = self._postprocessor.process(
            text=ctx.outgoing.text,
            intent_id=ctx.detected_intent,
            contract=contract,
            allow_prepayment=allow_prepayment,
        )

        ctx.outgoing.text = cleaned
        ctx.ai_response = cleaned

        return ctx

    async def _post_action(self, ctx: PipelineContext) -> PipelineContext:
        """Run actions after LLM (stubs; actions are implemented in Phase 3)."""
        for action_name in ctx.actions_to_run:
            if action_name == "CREATE_BOOKING":
                logger.info("TODO: Create booking (Phase 3)")
                # TODO: call google_calendar.create_booking()
            elif action_name == "RESET":
                logger.info("Resetting conversation state")
                ctx.incoming.metadata["conversation_state"] = {}
            elif action_name == "ESCALATE":
                logger.info("TODO: Escalate to human (Phase 3)")
                # TODO: send notification to manager
            else:
                logger.warning("Unknown action: %s", action_name)

        return ctx
