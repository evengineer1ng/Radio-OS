"""
Radio Station Meta Plugin

Wraps the existing sophisticated curator/navigator/character manager/producer/embedder
LLM logic from bookmark.py. This is the gold standard meta plugin for radio stations.

This meta plugin preserves:
- Navigator -> Curator -> Producer -> Character Manager -> Embedder pipeline
- Multi-character coordination
- Existing prompt templates
- Music breaks special handling
- Live config reload patterns
"""

from typing import Any, Dict, List, Optional, Tuple
import json
import random
import time
import os

# Import MetaPluginBase from bookmark
try:
    from bookmark import MetaPluginBase
except ImportError:
    import sys
    # If bookmark not in sys.modules, it means we're running standalone
    # Define a minimal stub for development/testing
    from abc import ABC, abstractmethod
    class MetaPluginBase(ABC):
        @abstractmethod
        def initialize(self, runtime_context, cfg, mem): pass
        @abstractmethod
        def curate_candidates(self, candidates, state): pass
        @abstractmethod
        def generate_script(self, segment, state): pass
        @abstractmethod
        def generate_narration(self, events, context): pass
        @abstractmethod
        def delegate_decision(self, available_actions, state, identity, focus): pass
        @abstractmethod
        def shutdown(self): pass

try:
    from context_engine import format_context_for_prompt
except ImportError:
    format_context_for_prompt = lambda d, t: str(d)


class RadioStationMetaPlugin(MetaPluginBase):
    """
    Meta plugin for traditional radio station operation.
    """
    
    def __init__(self):
        self.context = {}
        self.cfg = {}
        self.mem = {}
        self.log_func = print

    def initialize(self, runtime_context: Dict[str, Any], cfg: Dict[str, Any], mem: Dict[str, Any]) -> None:
        """Initialize with runtime context."""
        self.context = runtime_context
        self.cfg = cfg
        self.mem = mem
        self.log_func = runtime_context.get("log", print)
        self.log("meta", "RadioStationMetaPlugin initialized")

    def log(self, channel: str, msg: str):
        if self.log_func:
            self.log_func(channel, msg)

    def _llm(self, *args, **kwargs):
        return self.context["llm_generate"](*args, **kwargs)

    def _parse_json(self, *args, **kwargs):
        return self.context["parse_json_lenient"](*args, **kwargs)

    def _get_prompt(self, key: str) -> str:
        """Get prompt template using stored mem reference."""
        return self.context["get_prompt"](self.mem, key)

    def _cfg_get(self, key: str, default: Any = None) -> Any:
        return self.context["cfg_get"](key, default)

    # =========================================================================
    # Step 1: Intelligence (Curator)
    # =========================================================================

    def curate_candidates(self, candidates: List[Dict[str, Any]], mem: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Takes raw candidates (RSS, social, etc), runs Curator + Navigator logic,
        and returns the prioritized queue of segments to be created.
        """
        # 1. Curator
        producer_model = self._cfg_get("models.producer", "") or "gpt-3.5-turbo"
        max_tokens = int(self._cfg_get("producer.max_tokens", 800))
        temperature = float(self._cfg_get("producer.temperature", 0.7))
        
        discoveries: List[Dict[str, Any]] = []
        if producer_model:
            try:
                sys_prompt = self._curator_system_context(mem)
                user_prompt = self._curator_candidates_prompt(mem, candidates)

                raw = self._llm(
                    user_prompt,
                    sys_prompt,
                    model=producer_model,
                    num_predict=max_tokens,
                    temperature=temperature,
                    timeout=int(self._cfg_get("producer.timeout_sec", 60)),
                    force_json=True
                )
                plan = self._parse_json(raw) if raw else {}
                if isinstance(plan, dict):
                    discoveries = plan.get("discoveries", []) if isinstance(plan.get("discoveries"), list) else []
            except Exception as e:
                self.log("meta", f"curator error: {type(e).__name__}: {e}")
                discoveries = []

        # Fallback if AI fails or no discoveries
        if not discoveries:
            discoveries = [self._discovery_from_candidate(c) for c in candidates[:3]]

        # Sanitize
        discoveries = [d for d in discoveries if isinstance(d, dict) and (d.get("post_id") or d.get("id"))]
        
        # 2. Navigator
        # Only run navigator if we have valid discoveries
        if not discoveries:
            return []

        nav_queue: List[Dict[str, Any]] = []
        navigator_model = (self._cfg_get("models.navigator", "") or producer_model).strip()
        
        if navigator_model:
            try:
                nav_sys, nav_user = self._navigator_prompt(mem, discoveries)
                raw = self._llm(
                    nav_user,
                    nav_sys,
                    model=navigator_model,
                    num_predict=int(self._cfg_get("navigator.max_tokens", 160)),
                    temperature=float(self._cfg_get("navigator.temperature", 0.55)),
                    timeout=int(self._cfg_get("navigator.timeout_sec", 45)),
                    force_json=True
                )
                nav = self._parse_json(raw) if raw else {}
                if isinstance(nav, dict):
                    nav_queue = nav.get("queue", []) if isinstance(nav.get("queue"), list) else []
            except Exception as e:
                self.log("meta", f"navigator error: {type(e).__name__}: {e}")
                nav_queue = []

        # Fallback navigator
        if not nav_queue:
            nav_queue = []
            for d in discoveries[:3]:
                tags = d.get("tags", []) if isinstance(d.get("tags"), list) else []
                nav_queue.append({
                    "target_id": d.get("post_id") or d.get("id"),
                    "move": "explore",
                    "focus": (tags[0] if tags else ""),
                    "energy": "medium",
                    "open_loop": "",
                    "lead_voice": ""
                })

        # Merge Logic (simulating the join performed in producer loop)
        # We need to map `nav_queue` decisions back to `discoveries` and `candidates`
        # and return the FINAL property-rich objects that the runtime DB expects.
        
        # Index data
        by_id_cand = {}
        for c in candidates:
            pid = str(c.get("post_id") or c.get("id"))
            if pid: by_id_cand[pid] = c
            
        by_id_disc = {}
        for d in discoveries:
            pid = str(d.get("post_id") or d.get("id"))
            if pid: by_id_disc[pid] = d

        final_items = []
        seen_pids = set()

        for decision in nav_queue:
            target_id = str(decision.get("target_id") or decision.get("post_id") or decision.get("id"))
            if not target_id or target_id in seen_pids:
                continue

            discovery = by_id_disc.get(target_id)
            base = by_id_cand.get(target_id)
            
            if not discovery or not base:
                continue
            
            # Here we construct the "merged" object that the runtime's producer loop uses 
            # to build `seg_obj`.
            # We must return a dict that has all keys needed by the runtime loop 
            # (move, focus, lead_voice, angle, why, key_points, etc.)
            
            merged = base.copy()
            merged.update(discovery) # Discovery overrides base
            merged.update(decision)  # Decision overrides discovery (move, focus, energy)
            
            # Ensure critical keys exist
            merged["post_id"] = target_id
            
            # The runtime loop expects these specific keys to form seg_obj:
            # angle, why, key_points, host_hint, priority
            # move, focus, open_loop, energy, lead_voice
            
            final_items.append(merged)
            seen_pids.add(target_id)
            
        return final_items

    # =========================================================================
    # Step 2: Production (Script Generation)
    # =========================================================================

    def generate_script(self, segment: Dict[str, Any], mem: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes a segment (topic/story), generates a radio script packet.
        Returns a dict with keys: host_intro, summary, panel, host_takeaway
        """
        
        # 0. Resolve Lead Voice / Characters
        lead_voice, other_voices = self._resolve_lead_voice(segment)
        
        # Update segment metadata with chosen lead
        segment["lead_voice"] = lead_voice
        
        # 1. Generate Script (Host Packet)
        start_t = time.time()
        host_pkt = self._generate_host_packet(segment, mem, lead_voice, other_voices)
        
        if not host_pkt or not isinstance(host_pkt, dict):
            self.log("meta", "Host packet generation failed, using extractive fallback")
            return self._extractive_fallback(segment)

        # 2. Convert Host Packet to Radio Station Packet format
        # Expected format from LLM (based on prompts):
        # {
        #     "lead_line": "...",
        #     "followup_line": "...",
        #     "supporting_lines": [{"voice": "...", "line": "..."}],
        #     "takeaway": "...",
        #     "callback": "..."
        # }
        #
        # Required output format for bookmark.py:
        # {
        #     "host_intro": "...",
        #     "summary": "...",
        #     "panel": [{"voice": "...", "line": "..."}],
        #     "host_takeaway": "..."
        # }
        
        lead_line = host_pkt.get("lead_line", "").strip()
        followup = host_pkt.get("followup_line", "").strip()
        supporting = host_pkt.get("supporting_lines", [])
        takeaway = host_pkt.get("takeaway", "").strip()
        
        # Build the packet
        packet = {
            "host_intro": lead_line,
            "summary": followup,
            "panel": supporting if isinstance(supporting, list) else [],
            "host_takeaway": takeaway
        }
        
        # Fallback if critical fields are empty
        if not packet["host_intro"] and not packet["summary"]:
            self.log("meta", "Empty packet from LLM, using extractive fallback")
            return self._extractive_fallback(segment)
                
        return packet

    # =========================================================================
    # Internal Helpers (Logic extracted from bookmark.py)
    # =========================================================================
    
    def _curator_system_context(self, mem: Dict[str, Any]) -> str:
        base = self._get_prompt("producer_system_context")
        if not base:
            # Fallback
            return "You are the Executive Producer of a radio station. Evaluate content and decide what airs."
        
        # Enrich with context
        ctx_str = format_context_for_prompt(mem.get("context_state", {}), "producer")
        return base.replace("{{CONTEXT}}", ctx_str)

    def _curator_candidates_prompt(self, mem: Dict[str, Any], candidates: List[Dict[str, Any]]) -> str:
        prompt = self._get_prompt("producer_candidates_prompt")
        if not prompt:
            return "Select the best stories from: " + json.dumps(candidates)
            
        c_str = json.dumps([{
            "id": c.get("post_id") or c.get("id") or str(i),
            "title": c.get("title", "No Title"),
            "source": c.get("source", "feed"),
            "body": (c.get("body") or "")[:200]
        } for i, c in enumerate(candidates)], indent=2)
        
        return prompt.replace("{{CANDIDATES}}", c_str)

    def _navigator_prompt(self, mem: Dict[str, Any], discoveries: List[Dict[str, Any]]) -> Tuple[str, str]:
        sys_p = self._get_prompt("navigator_system_prompt")
        user_p = self._get_prompt("navigator_user_prompt")
        
        # Minimal context
        ctx = mem.get("context_state", {})
        curr_show = ctx.get("current_show", "General Rotation")
        
        sys_p = sys_p.replace("{{SHOW_CONTEXT}}", f"Current Show: {curr_show}")
        
        disc_lite = [{
            "id": d.get("post_id") or d.get("id"),
            "title": d.get("title"),
            "angle": d.get("angle"),
            "priority": d.get("priority")
        } for d in discoveries]
        
        user_p = user_p.replace("{{DISCOVERIES}}", json.dumps(disc_lite, indent=2))
        return sys_p, user_p

    def _generate_host_packet(self, segment: Dict[str, Any], mem: Dict[str, Any], lead_voice: str, other_voices: List[str]) -> Dict[str, Any]:
        """
        Generates the script using 'host_packet_system' and 'host_packet_user' prompts.
        Returns dict with: lead_line, followup_line, supporting_lines, takeaway, callback
        """
        # Load Prompt Templates
        sys_template = self._get_prompt("host_packet_system")
        user_template = self._get_prompt("host_packet_user")

        if not sys_template:
            sys_template = """You are the LEAD VOICE for a radio station.
Lead voice identity: {lead_voice}

You interpret content into natural spoken audio for radio.

Panel voices available: {roster}

Rules:
- Spoken words only, natural conversational tone
- NO bullet points, NO stage directions, NO announcements
- Transform content into insights and commentary, NOT just reading data
- Do not invent facts not in the source material
- Keep it relevant and engaging

Output STRICT JSON only:
{{
    "lead_line": "opening hook or intro",
    "followup_line": "main commentary or analysis",  
    "supporting_lines": [
        {{ "voice": "voice_name", "line": "supporting insight" }}
    ],
    "takeaway": "closing thought or perspective",
    "callback": "optional follow-up hook"
}}"""

        if not user_template:
            user_template = """LEAD VOICE: {lead_voice}

CONTENT TO COVER:
TITLE: {title}
ANGLE: {angle}
WHY IT MATTERS: {why}
KEY POINTS: {key_points}

SOURCE MATERIAL:
{material}

IMPORTANT: Do NOT just read out data or JSON. Give INSIGHTS, COMMENTARY, and PERSPECTIVE on this content.
Make it conversational and radio-ready."""

        # Prepare Vars
        title = segment.get("title", "").strip()
        body = segment.get("body", "").strip()
        angle = segment.get("angle", "").strip()
        why = segment.get("why", "").strip()
        
        # Parse key_points - handle both list and JSON string
        key_points_raw = segment.get("key_points", [])
        key_points_list = []
        
        if isinstance(key_points_raw, list):
            key_points_list = key_points_raw
        elif isinstance(key_points_raw, str) and key_points_raw:
            try:
                import json
                parsed = json.loads(key_points_raw)
                if isinstance(parsed, list):
                    key_points_list = parsed
            except:
                pass
        
        keypts = "\n".join([f"- {k}" for k in key_points_list if k and isinstance(k, str)])
        
        # Extract comments - handle both 'comments' list and 'comments_json' string
        comments_list = []
        
        # Try comments_json first (database field)
        comments_raw = segment.get("comments_json", "")
        if comments_raw:
            try:
                import json
                if isinstance(comments_raw, str):
                    parsed = json.loads(comments_raw)
                    if isinstance(parsed, list):
                        comments_list = parsed
                elif isinstance(comments_raw, list):
                    comments_list = comments_raw
            except:
                pass
        
        # Fallback to 'comments' if present
        if not comments_list:
            comments_field = segment.get("comments", [])
            if isinstance(comments_field, list):
                comments_list = comments_field
        
        # Build a clean material string (NOT raw JSON)
        material_parts = []
        if body:
            material_parts.append(f"Content: {body[:600]}")
        
        # Extract meaningful comments
        if comments_list:
            comment_insights = []
            for c in comments_list[:5]:  # Top 5 comments max
                if isinstance(c, dict):
                    author = c.get("author", "user")
                    text = c.get("body", "").strip()
                    if text and isinstance(text, str):
                        comment_insights.append(f"{author}: {text[:150]}")
            
            if comment_insights:
                material_parts.append("\nTop Reactions:\n" + "\n".join(comment_insights))
        
        material = "\n\n".join(material_parts) if material_parts else body[:800]
        
        # Context
        ctx_data = mem.get("context_state", {})
        themes = ctx_data.get("active_themes", [])
        callbacks = ctx_data.get("callbacks", [])
        show_name = self._cfg_get("station.name", "this station")
        
        # Get roster of voices (handle both list and dict formats)
        live_roles = self.context.get("LIVE_ROLES", [])
        if isinstance(live_roles, dict):
            live_roles_list = list(live_roles.keys())
        elif isinstance(live_roles, list):
            live_roles_list = live_roles
        else:
            live_roles_list = []
        
        roster = ", ".join(live_roles_list) if live_roles_list else "Host"
        allowed_p_str = " or ".join(live_roles_list) if live_roles_list else "Host"
        
        # Calculate min/max panel requirements
        min_n = max(2, len(live_roles_list) // 2) if len(live_roles_list) > 1 else 0
        max_n = max(3, len(live_roles_list)) if len(live_roles_list) > 0 else 3
        
        # Format system prompt
        sys_final = sys_template.format(
            show_name=show_name,
            lead_voice=lead_voice,
            roster=roster,
            allowed_p_str=allowed_p_str,
            min_n=min_n,
            max_n=max_n,
            themes=", ".join(themes[:3]) if themes else "general topics",
            callbacks=", ".join(callbacks[:2]) if callbacks else "none"
        )
        
        # Format user prompt with procedural context
        move = segment.get("move", "explore")
        focus = segment.get("focus", "")
        energy = segment.get("energy", "medium")
        open_loop = segment.get("open_loop", "")
        tags = segment.get("tags", [])
        tags_str = ", ".join(tags) if isinstance(tags, list) else ""
        
        user_final = user_template.format(
            lead_voice=lead_voice,
            move=move,
            focus=focus,
            energy=energy,
            open_loop=open_loop,
            title=title,
            angle=angle,
            why=why,
            key_points=keypts,
            tags=tags_str,
            material=material,
            comments="" # Already integrated into material
        )
        
        # Call LLM
        host_model = self._cfg_get("models.host_model", "") or self._cfg_get("models.producer", "") or "gpt-3.5-turbo"
        
        try:
            raw = self._llm(
                user_final,
                sys_final,
                model=host_model,
                num_predict=int(self._cfg_get("host.max_tokens", 800)),
                temperature=float(self._cfg_get("host.temperature", 0.7)),
                timeout=int(self._cfg_get("host.timeout_sec", 60)),
                force_json=True
            )
            data = self._parse_json(raw)
            
            if not isinstance(data, dict):
                self.log("meta", f"LLM returned non-dict: {type(data)}")
                return {}
            
            # Validate required fields
            if not data.get("lead_line") and not data.get("followup_line"):
                self.log("meta", "LLM returned empty lead_line and followup_line")
                return {}
            
            return data
            
        except Exception as e:
            self.log("meta", f"Host packet generation failed: {e}")
            return {}

    def _resolve_lead_voice(self, segment: Dict[str, Any]) -> Tuple[str, List[str]]:
        """
        Decide who speaks based on segment hints or defaults.
        """
        # Check segment overrides
        hint = segment.get("lead_voice", "").strip()
        
        # Get Available Roles from Runtime (handle both list and dict formats)
        live_roles = self.context.get("LIVE_ROLES", [])
        if isinstance(live_roles, dict):
            all_speakers = list(live_roles.keys())
        elif isinstance(live_roles, list):
            all_speakers = live_roles
        else:
            all_speakers = []
        
        if hint and hint in all_speakers:
            lead = hint
        else:
            # Default to random for equal distribution
            lead = random.choice(all_speakers) if all_speakers else "Host"

        others = [s for s in all_speakers if s != lead]
        return lead, others

    def _discovery_from_candidate(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback discovery object"""
        return {
            "post_id": c.get("post_id") or c.get("id"),
            "title": c.get("title", ""),
            "angle": "Report",
            "why": "Interesting story",
            "priority": 50,
            "type": "story",
            "tags": []
        }

    def _extractive_fallback(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback packet using only extractive content (no generation).
        Returns dict with: host_intro, summary, panel, host_takeaway
        """
        def clean(s):
            return str(s).strip() if s else ""
        
        title = clean(segment.get("title", ""))[:500]
        angle = clean(segment.get("angle", ""))[:700]
        why = clean(segment.get("why", ""))[:700]
        body = clean(segment.get("body", "") or "")[:1200]

        pkt = {"panel": []}

        if title:
            pkt["host_intro"] = title
        if body:
            pkt["summary"] = body
        elif angle:
            pkt["summary"] = angle
        elif why:
            pkt["summary"] = why

        if why:
            pkt["host_takeaway"] = why
        elif angle:
            pkt["host_takeaway"] = angle

        return pkt

    # =========================================================================
    # Abstract Methods (Radio Station Context)
    # =========================================================================

    def generate_narration(self, events: List[Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate narration segments from events.
        For radio stations, this is handled by the host packet generation system.
        """
        # Radio stations use generate_script() instead of direct narration
        # This method exists to satisfy the abstract base class
        return []

    def delegate_decision(self, available_actions: List[Any], state: Any, identity: List[str], focus: Optional[str]) -> Any:
        """
        Make AI decisions when player delegates control.
        Not applicable to radio stations - only used in game contexts.
        """
        return None

    def shutdown(self) -> None:
        """Cleanup resources."""
        self.log("meta", "RadioStationMetaPlugin shutting down")
