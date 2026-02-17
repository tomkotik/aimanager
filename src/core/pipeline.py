from __future__ import annotations

import logging
import time
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
    intent_confidence: float = 0.0
    calendar_context: str = ""
    ai_response: str | None = None
    raw_response: str | None = None
    outgoing: OutgoingMessage | None = None
    actions_to_run: list[str] = field(default_factory=list)
    booking_data: dict | None = None
    error: str | None = None
    
    # Debug fields
    debug: dict = field(default_factory=dict)


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
        state = conv.state or {}
        ctx.incoming.metadata["conversation_state"] = state
        ctx.incoming.metadata["conversation_id"] = str(conv.id)
        
        # Initialize conversation flow tracking if not present
        if "flow" not in state:
            state["flow"] = {
                "stage": "qualify",  # qualify → offer → close → finalize
                "booking_data": {},  # Collected booking data
            }

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

        raw_intent, confidence = self._router.detect_with_confidence(ctx.incoming.text)

        # Apply intent lock using conversation state.
        conv_state = ctx.incoming.metadata.get("conversation_state", {})
        effective_intent = self._intent_lock.apply(
            state=conv_state,
            raw_intent=raw_intent,
            intents=ctx.dialogue_policy.intents,
        )

        ctx.detected_intent = effective_intent
        ctx.intent_confidence = confidence
        
        # Store updated state back.
        ctx.incoming.metadata["conversation_state"] = conv_state

        return ctx

    async def _pre_action(self, ctx: PipelineContext) -> PipelineContext:
        """Run actions before LLM: check calendar availability if date/time mentioned."""
        # Check if message mentions date/time patterns
        text_lower = ctx.incoming.text.lower()
        date_keywords = ["завтра", "сегодня", "суббот", "воскресен", "понедельник", 
                        "вторник", "среду", "четверг", "пятниц", "числ"]
        time_keywords = ["час", "утр", "вечер", "дн", "ночь", "00", ":"]
        
        has_date = any(kw in text_lower for kw in date_keywords)
        has_time = any(kw in text_lower for kw in time_keywords)
        
        if has_date or has_time:
            try:
                from pathlib import Path
                from src.integrations.google_calendar import GoogleCalendarAdapter
                
                # Load calendar config from secrets (graceful degradation)
                secrets_dir = Path("/app/secrets/j-one-studio")
                calendar_id_file = secrets_dir / "google_calendar_id"
                sa_path_file = secrets_dir / "google_sa_path"
                
                if calendar_id_file.exists() and sa_path_file.exists():
                    calendar_id = calendar_id_file.read_text().strip()
                    sa_path = sa_path_file.read_text().strip()
                    
                    if calendar_id != "CHANGE_ME":
                        adapter = GoogleCalendarAdapter({
                            "calendar_id": calendar_id,
                            "service_account_path": sa_path,
                            "ics_url": "",  # Optional: add ICS URL if available
                        })
                        
                        # Note: actual availability check would need parsed datetime
                        # For now, we just signal that calendar is configured
                        ctx.calendar_context = "Календарь настроен, проверяется доступность."
                        logger.info("Calendar pre-check triggered for message with date/time")
                else:
                    logger.debug("Calendar secrets not found, skipping availability check")
                    
            except Exception as e:
                logger.error("Calendar pre-action failed: %s", e)
                # Non-fatal: continue pipeline
        
        return ctx

    async def _think(self, ctx: PipelineContext) -> PipelineContext:
        """Call the AI Brain."""
        # Fast path: deterministic greeting from config.
        if (
            (ctx.detected_intent or "").upper() == "GREETING"
            and getattr(ctx.agent_config.style, "greeting", "").strip()
        ):
            greeting_text = ctx.agent_config.style.greeting.strip()
            ctx.ai_response = greeting_text
            ctx.raw_response = greeting_text
            ctx.debug = {
                "prompt_sent": "",
                "documents_used": [],
                "latency_ms": 0,
                "raw_response": greeting_text,
            }
            ctx.outgoing = OutgoingMessage(
                text=greeting_text,
                conversation_id=ctx.incoming.metadata.get("conversation_id", ""),
                channel_conversation_id=ctx.incoming.channel_conversation_id,
                metadata={
                    "intent": ctx.detected_intent,
                    "intent_confidence": ctx.intent_confidence,
                    "model": "greeting_template",
                    "usage": {},
                    "latency_ms": 0,
                    "documents_used": [],
                    "prompt_sent": "",
                    "raw_response": greeting_text,
                    "config_version": ctx.incoming.metadata.get("config_version", ""),
                },
            )
            return ctx

        # Fast path: deterministic answer for photo-of-rooms requests.
        text_lower = (ctx.incoming.text or "").lower()
        photo_markers = ["фото зал", "фотографии зал", "есть фото", "покажите фото", "посмотреть фото"]
        if any(m in text_lower for m in photo_markers):
            photo_reply = (
                "Да, конечно! Фото залов:\n"
                "- Агат (22м²): https://j-one.studio/agat\n"
                "- Карелия (29м²): https://j-one.studio/karelia\n"
                "- Уют (29м²): https://j-one.studio/cozy\n"
                "- Грань (34м²): https://j-one.studio/edge\n"
                "- Лофт (45м²): https://j-one.studio/loft\n\n"
                "Подскажите формат съёмки и количество участников — помогу выбрать зал."
            )
            ctx.ai_response = photo_reply
            ctx.raw_response = photo_reply
            ctx.outgoing = OutgoingMessage(
                text=photo_reply,
                conversation_id=ctx.incoming.metadata.get("conversation_id", ""),
                channel_conversation_id=ctx.incoming.channel_conversation_id,
                metadata={
                    "intent": ctx.detected_intent,
                    "intent_confidence": ctx.intent_confidence,
                    "model": "photo_rooms_template",
                    "usage": {},
                    "latency_ms": 0,
                    "documents_used": ["rooms", "faq"],
                    "prompt_sent": "",
                    "raw_response": photo_reply,
                },
            )
            return ctx

        from src.core.prompt_builder import PromptBuilder

        # Get conversation flow state for prompt
        conv_state = ctx.incoming.metadata.get("conversation_state", {})
        flow_state = conv_state.get("flow", {})

        system_prompt = PromptBuilder.build(
            agent_config=ctx.agent_config,
            knowledge=ctx.knowledge,
            extra_context=ctx.calendar_context,
            flow_stage=flow_state.get("stage"),
            booking_data=flow_state.get("booking_data"),
        )

        messages = ctx.history + [{"role": "user", "content": ctx.incoming.text}]

        max_hist = ctx.agent_config.llm.max_history
        if len(messages) > max_hist:
            messages = messages[-max_hist:]

        # Track latency
        start_time = time.time()
        response = await self.brain.think(system_prompt, messages)
        latency_ms = int((time.time() - start_time) * 1000)

        # Track which knowledge documents were used
        documents_used = list(ctx.knowledge.keys()) if ctx.knowledge else []

        # Parse action tags from AI response.
        from src.core.action_parser import parse_action_tags

        parsed = parse_action_tags(response.content)

        ctx.ai_response = parsed.clean_text
        ctx.raw_response = response.content  # Save raw response before postprocessing
        ctx.actions_to_run = parsed.actions
        ctx.booking_data = parsed.booking_data
        
        # Store debug information
        ctx.debug = {
            "prompt_sent": system_prompt,
            "documents_used": documents_used,
            "latency_ms": latency_ms,
            "raw_response": response.content,
        }
        
        ctx.outgoing = OutgoingMessage(
            text=parsed.clean_text,
            conversation_id=ctx.incoming.metadata.get("conversation_id", ""),
            channel_conversation_id=ctx.incoming.channel_conversation_id,
            metadata={
                "intent": ctx.detected_intent,
                "intent_confidence": ctx.intent_confidence,
                "model": response.model,
                "usage": response.usage,
                "latency_ms": latency_ms,
                "documents_used": documents_used,
                "prompt_sent": system_prompt,
                "raw_response": response.content,
                "config_version": ctx.incoming.metadata.get("config_version", ""),
            },
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
        """Run actions after LLM: booking, escalation, state updates."""
        conv_state = ctx.incoming.metadata.get("conversation_state", {})
        flow_state = conv_state.get("flow", {})
        booking_finalized_now = False

        # Runtime trace for debugging rule decisions in production.
        if ctx.outgoing is not None:
            ctx.outgoing.metadata.setdefault("automation_trace", [])

        # Always refresh flow data from the latest user message first.
        # This prevents missing fields when intent confidence fluctuates.
        self._update_flow_stage(ctx, flow_state)

        for action_name in ctx.actions_to_run:
            if action_name == "CREATE_BOOKING":
                booking_result = await self._handle_create_booking(ctx)
                if booking_result.get("success") and booking_result.get("event_id"):
                    event_id = booking_result.get("event_id")
                    if ctx.outgoing:
                        ctx.outgoing.metadata["booking_event_id"] = event_id
                    flow_state["booking_event_id"] = event_id
                    flow_state["booking_status"] = "created"
                    flow_state["stage"] = "finalize"
                    booking_finalized_now = True
                elif booking_result.get("reason") == "slot_busy":
                    flow_state["booking_status"] = "busy"
                    if ctx.outgoing:
                        busy_rooms = booking_result.get("conflicting_rooms") or []
                        rooms_hint = f" Сейчас заняты: {', '.join(busy_rooms)}." if busy_rooms else ""
                        ctx.outgoing.text = (
                            "К сожалению, выбранный слот занят. "
                            "Предложите другой зал или другое время, и я сразу проверю доступность."
                            f"{rooms_hint}"
                        ).strip()
                else:
                    flow_state.setdefault("booking_status", "pending_manager")
            elif action_name == "RESET":
                logger.info("Resetting conversation state")
                ctx.incoming.metadata["conversation_state"] = {}
            elif action_name == "ESCALATE":
                await self._handle_escalation(ctx)
            else:
                logger.warning("Unknown action: %s", action_name)

        # Fallback escalation by intent (if LLM forgot [ACTION:ESCALATE]).
        if (
            (ctx.detected_intent or "").upper() == "ESCALATE"
            and "ESCALATE" not in (ctx.actions_to_run or [])
        ):
            await self._handle_escalation(ctx)

        # Re-apply flow update after actions: this merges parsed [BOOKING:...] fields
        # (name/phone) into state and keeps stage consistent.
        self._update_flow_stage(ctx, flow_state)

        # Fallback booking creation when all required fields are already present
        # but LLM forgot to emit [BOOKING:...].
        booking_data = (flow_state or {}).get("booking_data", {})
        required = ["date", "time", "duration", "room", "name", "phone"]
        has_all_booking_fields = all(booking_data.get(k) for k in required)
        if has_all_booking_fields and "CREATE_BOOKING" not in (ctx.actions_to_run or []):
            ctx.booking_data = booking_data
            booking_result = await self._handle_create_booking(ctx)
            if booking_result.get("success") and booking_result.get("event_id"):
                event_id = booking_result.get("event_id")
                if ctx.outgoing:
                    ctx.outgoing.metadata["booking_event_id"] = event_id
                flow_state["booking_event_id"] = event_id
                flow_state["booking_status"] = "created"
                booking_finalized_now = True
            elif booking_result.get("reason") == "slot_busy":
                flow_state["booking_status"] = "busy"
                if ctx.outgoing:
                    busy_rooms = booking_result.get("conflicting_rooms") or []
                    rooms_hint = f" Сейчас заняты: {', '.join(busy_rooms)}." if busy_rooms else ""
                    ctx.outgoing.text = (
                        "К сожалению, выбранный слот занят. "
                        "Предложите другой зал или другое время, и я сразу проверю доступность."
                        f"{rooms_hint}"
                    ).strip()
            else:
                flow_state.setdefault("booking_status", "pending_manager")

        # If booking was finalized in this turn, keep an explicit durable marker.
        if booking_finalized_now:
            flow_state["stage"] = "finalize"
            flow_state["booking_finalized"] = True
            flow_state.setdefault("booking_status", "created")

        automations_cfg = getattr(ctx.agent_config, "automations", None)
        automations_enabled = bool(getattr(automations_cfg, "enabled", False))

        # Legacy default automation: keep behavior only when configurable automations are disabled.
        if not automations_enabled:
            if (booking_finalized_now or (flow_state.get("stage") == "finalize" and has_all_booking_fields)) and not flow_state.get("manager_notified"):
                await self._handle_escalation(ctx)
                flow_state["manager_notified"] = True
                if flow_state.get("booking_status") == "busy":
                    flow_state["booking_status"] = "busy_escalated"

        # Configurable automations from agent.config.automations
        await self._run_config_automations(ctx, flow_state)

        if self.db and ctx.incoming.metadata.get("conversation_id"):
            await self._save_conversation_state(ctx)

        return ctx

    async def _handle_create_booking(self, ctx: PipelineContext) -> dict:
        """Create booking in Google Calendar."""
        try:
            from pathlib import Path
            from datetime import datetime, timedelta
            from src.integrations.google_calendar import GoogleCalendarAdapter

            secrets_dir = Path("/app/secrets/j-one-studio")
            calendar_id_file = secrets_dir / "google_calendar_id"
            sa_path_file = secrets_dir / "google_sa_path"

            if not calendar_id_file.exists() or not sa_path_file.exists():
                logger.warning("Calendar not configured, skipping booking creation")
                return {"success": False, "reason": "calendar_not_configured"}

            calendar_id = calendar_id_file.read_text().strip()
            sa_path = sa_path_file.read_text().strip()

            if calendar_id == "CHANGE_ME":
                logger.warning("Calendar ID not set, skipping booking creation")
                return {"success": False, "reason": "calendar_id_missing"}

            adapter = GoogleCalendarAdapter(
                {
                    "calendar_id": calendar_id,
                    "service_account_path": sa_path,
                }
            )

            flow_state = ctx.incoming.metadata.get("conversation_state", {}).get("flow", {})
            flow_booking = flow_state.get("booking_data", {}) or {}
            existing_event_id = flow_state.get("booking_event_id")

            # Idempotency: if booking already exists for this conversation, do not re-create.
            if existing_event_id:
                logger.info("Booking already exists for conversation, reuse event_id=%s", existing_event_id)
                return {"success": True, "event_id": existing_event_id, "idempotent": True}

            # Merge booking data from flow-state and parsed [BOOKING] tag.
            # [BOOKING] currently has 5 fields and may omit duration.
            booking_info = {}
            if isinstance(flow_booking, dict):
                booking_info.update(flow_booking)
            if isinstance(ctx.booking_data, dict):
                booking_info.update({k: v for k, v in ctx.booking_data.items() if v is not None})

            if not booking_info:
                logger.warning("No booking data available")
                return {"success": False, "reason": "booking_data_missing"}

            date_str = (booking_info.get("date") or "").strip()
            time_str = (booking_info.get("time") or "").strip()
            room = (booking_info.get("room") or "").strip() or "Не указан"
            client_name = (booking_info.get("name") or "Клиент").strip()
            phone = (booking_info.get("phone") or "").strip()
            duration_hours = int(booking_info.get("duration") or 2)

            # Fallback parse from the current message if some booking fields were not captured.
            text_now = ctx.incoming.text or ""
            import re
            if not booking_info.get("duration"):
                text_now_lower = text_now.lower()
                dmatch = re.search(r"(?:на\s*)?(\d{1,2})\s*час", text_now_lower)
                if dmatch:
                    duration_hours = int(dmatch.group(1))
                    booking_info["duration"] = duration_hours
                else:
                    word_to_num = {
                        "один": 1, "одна": 1,
                        "два": 2, "две": 2,
                        "три": 3,
                        "четыре": 4,
                        "пять": 5,
                        "шесть": 6,
                        "семь": 7,
                        "восемь": 8,
                        "девять": 9,
                        "десять": 10,
                        "одиннадцать": 11,
                        "двенадцать": 12,
                    }
                    for word, num in word_to_num.items():
                        if re.search(rf"\b{word}\b\s*час", text_now_lower):
                            duration_hours = num
                            booking_info["duration"] = duration_hours
                            break
            if not booking_info.get("phone"):
                pmatch = re.search(r"\+?\d[\d\s\-\(\)]{7,}", text_now)
                if pmatch:
                    booking_info["phone"] = pmatch.group().strip()
                    phone = booking_info["phone"]
            if not booking_info.get("name") and ctx.incoming.sender_name:
                booking_info["name"] = ctx.incoming.sender_name
                client_name = booking_info["name"]

            if not date_str or not time_str:
                logger.warning("Booking missing date/time: %s", booking_info)
                return {"success": False, "reason": "booking_datetime_missing"}

            start = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            end = start + timedelta(hours=duration_hours)

            availability = await adapter.check_availability(
                {
                    "start": start,
                    "duration_hours": duration_hours,
                    "room": room,
                }
            )
            if availability.get("success") and availability.get("available") is False:
                logger.info("Requested slot busy, skipping calendar create: %s", booking_info)
                return {
                    "success": False,
                    "reason": "slot_busy",
                    "conflicting_rooms": availability.get("conflicting_rooms", []),
                }

            result = await adapter.create_booking(
                {
                    "start": start,
                    "end": end,
                    "summary": f"Бронь J-One: {client_name} / {room}",
                    "description": f"Клиент: {client_name}; Телефон: {phone}; Канал: {ctx.incoming.channel_type}",
                }
            )

            if result.get("success"):
                event_id = result.get("event_id")
                logger.info("Booking created in Google Calendar: %s", event_id)
                return {"success": True, "event_id": event_id}
            else:
                logger.error("Calendar booking failed: %s", result.get("error"))
                return {"success": False, "reason": "calendar_create_failed", "error": result.get("error")}

        except Exception as e:
            logger.error("Failed to create booking: %s", e)
            return {"success": False, "reason": "exception", "error": str(e)}

    async def _handle_escalation(self, ctx: PipelineContext) -> dict:
        """Send escalation notification to manager via Telegram."""
        try:
            from src.integrations.telegram_notify import TelegramNotifier

            notifier = TelegramNotifier.from_secrets()
            if not notifier:
                logger.warning("Telegram notifier not configured, skipping escalation")
                return {"success": False, "reason": "notifier_not_configured"}

            client_name = ctx.incoming.sender_name
            channel = ctx.incoming.channel_type
            last_message = ctx.incoming.text

            # Build conversation link if available
            conversation_id = ctx.incoming.metadata.get("conversation_id", "")
            conversation_link = f"/conversations/{conversation_id}" if conversation_id else ""

            result = await notifier.send_escalation(
                client_name=client_name,
                channel=channel,
                last_message=last_message,
                conversation_link=conversation_link,
            )

            if result.get("success"):
                logger.info("Escalation notification sent successfully")
                return {"success": True}
            else:
                logger.error("Escalation notification failed: %s", result.get("error"))
                return {"success": False, "reason": "escalation_send_failed", "error": result.get("error")}

        except Exception as e:
            logger.error("Failed to handle escalation: %s", e)
            return {"success": False, "reason": "exception", "error": str(e)}

    def _update_flow_stage(self, ctx: PipelineContext, flow_state: dict) -> None:
        """Update conversation flow stage based on collected data and intent."""
        booking_data = flow_state.get("booking_data", {})

        # Merge data extracted from [BOOKING:...] tag when present.
        if ctx.booking_data:
            booking_data.update({k: v for k, v in ctx.booking_data.items() if v})

        text = ctx.incoming.text or ""
        text_lower = text.lower()

        import re

        phone_match = re.search(r"\+?\d[\d\s\-\(\)]{7,}", text)
        if phone_match and not booking_data.get("phone"):
            booking_data["phone"] = phone_match.group().strip()

        # Name parsing from user text ("имя Иван", "меня зовут Иван").
        name_match = re.search(r"(?:имя\s*[:\-]?\s*|меня\s+зовут\s+)([A-Za-zА-Яа-яЁё\-]{2,})", text, flags=re.IGNORECASE)
        if name_match:
            candidate = name_match.group(1).strip().title()
            if candidate.lower() not in {"здравствуйте", "привет", "добрый", "день", "вечер"}:
                booking_data["name"] = candidate

        if ctx.incoming.sender_name and not booking_data.get("name"):
            booking_data["name"] = ctx.incoming.sender_name

        for room in ["агат", "карелия", "уют", "грань", "лофт"]:
            if room in text_lower:
                # Explicit user correction should override stale room.
                booking_data["room"] = room.capitalize()
                break

        # Absolute date: DD.MM[.YYYY]
        date_match = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?\b", text)
        if date_match and not booking_data.get("date"):
            dd = int(date_match.group(1))
            mm = int(date_match.group(2))
            yyyy = int(date_match.group(3)) if date_match.group(3) else datetime.now().year
            booking_data["date"] = f"{dd:02d}.{mm:02d}.{yyyy}"

        # Relative date keywords.
        if not booking_data.get("date"):
            now = datetime.now()
            weekday_map = {
                "понедельник": 0,
                "вторник": 1,
                "сред": 2,
                "четверг": 3,
                "пятниц": 4,
                "суббот": 5,
                "воскресен": 6,
            }
            resolved = None
            low = text_lower
            if "сегодня" in low:
                resolved = now
            elif "завтра" in low:
                from datetime import timedelta as _td
                resolved = now + _td(days=1)
            elif "послезавтра" in low:
                from datetime import timedelta as _td
                resolved = now + _td(days=2)
            else:
                for token, target_wd in weekday_map.items():
                    if token in low:
                        from datetime import timedelta as _td
                        delta = (target_wd - now.weekday()) % 7
                        if delta == 0:
                            delta = 7
                        resolved = now + _td(days=delta)
                        break

            if resolved is not None:
                booking_data["date"] = resolved.strftime("%d.%m.%Y")

        time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
        if time_match and not booking_data.get("time"):
            hh = int(time_match.group(1))
            mi = int(time_match.group(2))
            booking_data["time"] = f"{hh:02d}:{mi:02d}"

        dur_match = re.search(r"(?:на\s*)?(\d{1,2})\s*час", text_lower)
        if dur_match and not booking_data.get("duration"):
            booking_data["duration"] = int(dur_match.group(1))

        # Also support durations written with words: "два часа", "пять часов".
        if not booking_data.get("duration"):
            word_to_num = {
                "один": 1, "одна": 1,
                "два": 2, "две": 2,
                "три": 3,
                "четыре": 4,
                "пять": 5,
                "шесть": 6,
                "семь": 7,
                "восемь": 8,
                "девять": 9,
                "десять": 10,
                "одиннадцать": 11,
                "двенадцать": 12,
            }
            for word, num in word_to_num.items():
                if re.search(rf"\b{word}\b\s*час", text_lower):
                    booking_data["duration"] = num
                    break

        part_match = re.search(r"(\d{1,2})\s*(чел|человек|участ)", text_lower)
        if part_match and not booking_data.get("participants"):
            booking_data["participants"] = int(part_match.group(1))

        required_fields = ["date", "time", "duration", "room", "name", "phone"]
        collected_fields = sum(1 for field in required_fields if booking_data.get(field))

        if collected_fields == 0:
            flow_state["stage"] = "qualify"
        elif collected_fields < 3:
            flow_state["stage"] = "offer"
        elif collected_fields < len(required_fields):
            flow_state["stage"] = "close"
        else:
            flow_state["stage"] = "finalize"

        flow_state["booking_data"] = booking_data
        logger.debug(
            "Flow stage: %s, collected: %d/%d fields",
            flow_state["stage"],
            collected_fields,
            len(required_fields),
        )

    async def _run_config_automations(self, ctx: PipelineContext, flow_state: dict) -> None:
        """Run configurable automations from agent.config.automations."""
        automations = getattr(ctx.agent_config, "automations", None)
        if not automations or not getattr(automations, "enabled", False):
            return

        rules = getattr(automations, "rules", []) or []
        auto_state = flow_state.setdefault("automations", {})
        trace = (ctx.outgoing.metadata.setdefault("automation_trace", []) if ctx.outgoing else None)

        for rule in rules:
            if not getattr(rule, "enabled", True):
                if trace is not None:
                    trace.append({"rule_id": getattr(rule, "id", ""), "matched": False, "reason": "disabled"})
                continue

            rule_id = getattr(rule, "id", "") or ""
            once_per_conversation = bool(getattr(rule, "once_per_conversation", True))
            if once_per_conversation and auto_state.get(rule_id):
                if trace is not None:
                    trace.append({"rule_id": rule_id, "matched": False, "reason": "already_executed"})
                continue

            when = getattr(rule, "when", {}) or {}
            matched, reason = self._automation_matches(ctx, flow_state, when)
            if not matched:
                if trace is not None:
                    trace.append({"rule_id": rule_id, "matched": False, "reason": reason})
                continue

            actions = getattr(rule, "do", []) or []
            action_results = []
            for action in actions:
                result = await self._run_automation_action(ctx, flow_state, action)
                action_results.append({"action": action, "result": result})

            if once_per_conversation and rule_id:
                auto_state[rule_id] = True

            if trace is not None:
                trace.append({
                    "rule_id": rule_id,
                    "matched": True,
                    "reason": "executed",
                    "actions": action_results,
                })

    def _automation_matches(self, ctx: PipelineContext, flow_state: dict, when: dict) -> tuple[bool, str]:
        """Evaluate simple automation conditions."""
        if not isinstance(when, dict):
            return False, "invalid_when"

        intent_is = when.get("intent_is")
        if intent_is and (ctx.detected_intent or "").upper() != str(intent_is).upper():
            return False, "intent_mismatch"

        stage_is = when.get("stage_is")
        if stage_is and str(flow_state.get("stage", "")) != str(stage_is):
            return False, "stage_mismatch"

        booking_finalized = when.get("booking_finalized")
        if booking_finalized is not None and bool(flow_state.get("booking_finalized", False)) != bool(booking_finalized):
            return False, "booking_not_finalized"

        fields_present = when.get("fields_present")
        if isinstance(fields_present, list):
            booking_data = flow_state.get("booking_data", {}) or {}
            missing = [str(field) for field in fields_present if not booking_data.get(str(field))]
            if missing:
                return False, f"missing_fields:{','.join(missing)}"

        text_matches = when.get("text_matches")
        if text_matches:
            import re
            try:
                if not re.search(str(text_matches), ctx.incoming.text or "", flags=re.IGNORECASE):
                    return False, "text_no_match"
            except re.error:
                return False, "invalid_regex"

        return True, "matched"

    async def _run_automation_action(self, ctx: PipelineContext, flow_state: dict, action: str) -> dict:
        """Execute one automation action."""
        action_name = str(action).strip().lower()

        if action_name == "notify_manager":
            return await self._handle_escalation(ctx)

        if action_name == "create_calendar_event":
            booking_data = flow_state.get("booking_data", {}) or {}
            if booking_data:
                ctx.booking_data = booking_data
            result = await self._handle_create_booking(ctx)
            if result.get("success") and result.get("event_id") and ctx.outgoing:
                ctx.outgoing.metadata["booking_event_id"] = result.get("event_id")
            return result

        if action_name.startswith("set_state:"):
            # Format: set_state:key=value
            payload = action_name[len("set_state:"):]
            if "=" in payload:
                key, value = payload.split("=", 1)
                flow_state[str(key).strip()] = value.strip()
                return {"success": True, "state_key": str(key).strip(), "state_value": value.strip()}
            return {"success": False, "reason": "invalid_set_state_payload"}

        logger.warning("Unknown automation action: %s", action)
        return {"success": False, "reason": "unknown_action"}

    async def _save_conversation_state(self, ctx: PipelineContext) -> None:
        """Save updated conversation state to database."""
        try:
            from uuid import UUID
            from src.core.crud import update_conversation_state
            
            conversation_id = ctx.incoming.metadata.get("conversation_id")
            if not conversation_id:
                return
            
            import json
            conv_state = ctx.incoming.metadata.get("conversation_state", {})
            # Force a detached plain-dict copy so SQLAlchemy JSON update is persisted.
            conv_state = json.loads(json.dumps(conv_state, ensure_ascii=False))

            await update_conversation_state(
                self.db,
                conversation_id=UUID(conversation_id),
                state=conv_state,
            )
            
        except Exception as e:
            logger.error("Failed to save conversation state: %s", e)
