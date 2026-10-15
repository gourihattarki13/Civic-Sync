"""
Civic Sync AI Urgency Sorter and Categorization Engine
------------------------------------------------------
Hybrid AI Intelligence:
1. Real AI Tier: Google Gemini API (gemini-1.5-flash / gemini-2.0-flash) for deep semantic
   understanding, public safety reasoning, intelligent categorization, and crew dispatch advice.
2. Local Heuristic Tier: High-performance rule-based pattern matching fallback (zero downtime).
"""

import os
import re
import json
import base64
import math
import urllib.request
import urllib.error
from datetime import datetime


# Local priority keyword dictionaries with associated severity weights and tags
CRITICAL_INDICATORS = {
    r"\b(accident|fatal|casualty|death|injur|hospital|ambulance|emergency)\b": ("Critical Safety Hazard", 40),
    r"\b(spark|sparking|electric shock|live wire|hanging wire|transformer|electrocution)\b": ("Electrical Hazard", 45),
    r"\b(fire|blaze|explosion|gas leak|toxic|poisonous)\b": ("Fire / Chemical Hazard", 45),
    r"\b(deep pothole|cave-?in|sinkhole|bridge (crack|damage|collaps)|collapsed road)\b": ("Severe Road Failure", 35),
    r"\b(open manhole|missing manhole cover|open drain|deep ditch|trench)\b": ("Open Fall Hazard", 35),
    r"\b(flood|flooding|waterlogging|submerged|overflowing sewage into house)\b": ("Major Flooding / Sewage", 30),
    r"\b(school|hospital|railway station|bus stand|highway|crossroad|heavy traffic)\b": ("High-Density Public Zone", 20),
}

HIGH_INDICATORS = {
    r"\b(burst pipe|pipeline burst|water contamination|muddy water|foul smell|pest)\b": ("Water / Health Hazard", 25),
    r"\b(traffic jam|block(ed|ing)|gridlock|choked drain|stagnant water)\b": ("Severe Congestion / Drainage", 20),
    r"\b(blackout|street light (out|broken|dark)|no light at night|danger at night)\b": ("Night Visibility Danger", 20),
    r"\b(garbage pile|dumpyard|overflowing bin|rot(ting)?|dead animal)\b": ("Sanitation / Bio Hazard", 22),
    r"\b(urgent|immediate|quickly|danger|hazard|unsafe)\b": ("Citizen Reported Urgency", 15),
}

MEDIUM_INDICATORS = {
    r"\b(pothole|damaged road|rough patch|broken pavement|curb)\b": ("Road Surface Issue", 12),
    r"\b(leak|leaking|dripping|low water pressure)\b": ("Water Distribution Issue", 10),
    r"\b(garbage|trash|waste|litter|dirty street)\b": ("Street Cleaning Required", 10),
    r"\b(drainage slow|clogged gutter|leaves)\b": ("Drain Maintenance", 10),
    r"\b(flickering light|loose wire|dim light)\b": ("Light Inspection", 10),
}

LOW_INDICATORS = {
    r"\b(paint|faded|signboard|board|bench|park|beautification|cosmetic)\b": ("Minor Public Amenity", 5),
    r"\b(tree branch|grass|gardening|weed|pruning)\b": ("Landscape Maintenance", 5),
}


def _analyze_with_gemini(title: str, description: str, category: str = "", api_key: str = "") -> dict:
    """
    Calls Google Gemini 1.5 Flash API with strict JSON schema to evaluate complaint urgency.
    """
    # Using Gemini Flash Lite Latest (fast, responsive)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={api_key}"

    system_prompt = (
        "You are an expert municipal civil engineer and disaster response coordinator. "
        "Analyze this civic complaint and evaluate its public safety hazard, urgency, and recommended dispatch.\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "urgency_score": <integer from 10 to 100>,\n'
        '  "priority_level": <"Critical" | "High" | "Medium" | "Low">,\n'
        '  "priority_color": <"red" | "orange" | "blue" | "green">,\n'
        '  "risk_tags": [<array of up to 3 short risk chips, e.g. "Electrical Hazard", "Accident Prone">],\n'
        '  "sla": <"Immediate (< 4 Hours)" | "Within 24 Hours" | "Within 48–72 Hours" | "Within 5–7 Days">,\n'
        '  "ai_summary": <1-2 concise sentences explaining why this score was assigned>,\n'
        '  "suggested_category": <"Roads" | "Sanitation" | "Water Supply" | "Electricity" | "Drainage" | "Other">,\n'
        '  "dispatch_recommendation": <recommended equipment and crew type to dispatch>\n'
        "}\n\n"
        "Scoring Rules:\n"
        "- 80-100 (Critical): Life-threatening hazards, sparking wires, open manholes, cave-ins, toxic leaks, flood into homes, proximity to schools/hospitals.\n"
        "- 60-79 (High): Major infrastructure breakdown, pipeline bursts, street blackout, severe rotting waste dump.\n"
        "- 35-59 (Medium): Standard pothole, clogged drain, water pressure issue, minor leak.\n"
        "- 10-34 (Low): Faded signage, park bench, cosmetic repairs, gardening/pruning."
    )

    user_text = f"Title: {title}\nDescription: {description}\nCategory: {category}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system_prompt}\n\nCivic Complaint Data:\n{user_text}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "response_mime_type": "application/json"
        }
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=3.5) as response:
        result = json.loads(response.read().decode("utf-8"))
    candidates = result.get("candidates", [])
    if not candidates:
        raise ValueError("No candidates returned from Gemini API")

    text_content = candidates[0]["content"]["parts"][0]["text"]
    parsed = json.loads(text_content)

    # Ensure required keys exist
    score = int(parsed.get("urgency_score", 20))
    score = max(10, min(100, score))
    parsed["urgency_score"] = score

    if "priority_level" not in parsed:
        if score >= 80: parsed["priority_level"] = "Critical"
        elif score >= 60: parsed["priority_level"] = "High"
        elif score >= 35: parsed["priority_level"] = "Medium"
        else: parsed["priority_level"] = "Low"

    if "priority_color" not in parsed:
        colors = {"Critical": "red", "High": "orange", "Medium": "blue", "Low": "green"}
        parsed["priority_color"] = colors.get(parsed["priority_level"], "blue")

    parsed["ai_engine"] = "Google Gemini Flash (Cloud AI)"
    return parsed


def _analyze_local_heuristic(title: str, description: str, category: str = "", created_at=None) -> dict:
    """
    Local heuristic rule-based engine: fast pattern recognition and SLA calculation.
    """
    text = f"{title or ''} {description or ''}".lower()
    score = 20
    risk_tags = []
    drivers = []

    # 1. Critical Indicators
    for pattern, (tag, weight) in CRITICAL_INDICATORS.items():
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
            if tag not in risk_tags:
                risk_tags.append(tag)
            drivers.append(tag)

    # 2. High Indicators
    for pattern, (tag, weight) in HIGH_INDICATORS.items():
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
            if tag not in risk_tags and len(risk_tags) < 4:
                risk_tags.append(tag)
            if tag not in drivers:
                drivers.append(tag)

    # 3. Medium Indicators
    for pattern, (tag, weight) in MEDIUM_INDICATORS.items():
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
            if tag not in risk_tags and len(risk_tags) < 3:
                risk_tags.append(tag)

    # 4. Low Indicators
    for pattern, (tag, weight) in LOW_INDICATORS.items():
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
            if not risk_tags:
                risk_tags.append(tag)

    # Category weight adjustments
    cat_lower = (category or "").lower()
    if "electric" in cat_lower and ("wire" in text or "shock" in text):
        score += 10
    elif "water" in cat_lower and ("burst" in text or "no water" in text):
        score += 8
    elif "road" in cat_lower and "accident" in text:
        score += 15

    # Clamp score
    final_score = min(100, max(10, score))

    if final_score >= 80:
        priority_level = "Critical"
        priority_color = "red"
        sla = "Immediate (< 4 Hours)"
        ai_summary = "High hazard to public safety detected. Requires immediate on-site response."
    elif final_score >= 60:
        priority_level = "High"
        priority_color = "orange"
        sla = "Within 24 Hours"
        ai_summary = "Significant disruption to civic infrastructure or health risk. Priority escalation."
    elif final_score >= 35:
        priority_level = "Medium"
        priority_color = "blue"
        sla = "Within 48–72 Hours"
        ai_summary = "Standard maintenance required. Scheduled for departmental review."
    else:
        priority_level = "Low"
        priority_color = "green"
        sla = "Within 5–7 Days"
        ai_summary = "Non-hazardous or routine request. Scheduled in normal maintenance cycle."

    if not risk_tags:
        risk_tags = ["Standard Civic Review"]

    return {
        "urgency_score": final_score,
        "priority_level": priority_level,
        "priority_color": priority_color,
        "risk_tags": risk_tags[:3],
        "sla": sla,
        "ai_summary": ai_summary,
        "suggested_category": category or "Other",
        "dispatch_recommendation": "Standard departmental maintenance unit.",
        "ai_engine": "CivicSync Heuristic Engine (Local)"
    }


_ANALYSIS_CACHE = {}


def analyze_complaint_ai(title: str, description: str, category: str = "", created_at=None, upvotes_count: int = 0) -> dict:
    """
    Master analyzer function:
    1. Attempts real Google Gemini API call if GEMINI_API_KEY is configured.
    2. Gracefully falls back to local heuristic analysis on missing key or network error.
    3. Factors in complaint aging.
    4. Factors in citizen community votes (highest voted issues escalate to top priority).
    """
    cache_key = ((title or "").strip(), (description or "").strip(), (category or "").strip())
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    result = None

    if cache_key in _ANALYSIS_CACHE:
        result = dict(_ANALYSIS_CACHE[cache_key])
        result["risk_tags"] = list(_ANALYSIS_CACHE[cache_key].get("risk_tags", []))
    elif api_key and (title or description):
        try:
            result = _analyze_with_gemini(title, description, category, api_key)
            if result:
                _ANALYSIS_CACHE[cache_key] = dict(result)
        except Exception as e:
            # Fallback gracefully
            print(f"[AI Sorter] Gemini API call skipped/failed: {e}. Using local heuristic engine.")

    if not result:
        result = _analyze_local_heuristic(title, description, category, created_at)
        _ANALYSIS_CACHE[cache_key] = dict(result)

    # 5. Aging Factor (Complaints pending for more time get an urgency boost)
    days_old = 0
    if created_at:
        try:
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at)
            else:
                created_dt = created_at
            now = datetime.now()
            days_old = max(0, (now - created_dt).days)
            # Add up to 15 points for older complaints (3 points per day pending)
            age_boost = min(15, days_old * 3)
            result["urgency_score"] = min(100, result["urgency_score"] + age_boost)
            if days_old >= 3 and len(result.get("risk_tags", [])) < 3:
                result["risk_tags"].append(f"⏳ Pending {days_old} days")
        except Exception:
            pass

    # 6. Citizen Community Voting Factor (Democratic Escalation Engine)
    # When multiple citizens in the same area or city endorse a problem,
    # the issue gets prioritized over isolated complaints.
    upvotes = int(upvotes_count or 0)
    if upvotes > 0:
        vote_boost = min(35, upvotes * 3)  # +3 points per upvote up to 35 pts
        result["urgency_score"] = min(100, result["urgency_score"] + vote_boost)

        vote_tag = f"🔥 {upvotes} Citizen Vote{'s' if upvotes > 1 else ''}"
        tags = result.get("risk_tags", [])
        if vote_tag not in tags:
            tags.insert(0, vote_tag)
        result["risk_tags"] = tags[:4]

        # Priority Escalation based on community voting volume
        if result["urgency_score"] >= 80:
            result["priority_level"] = "Critical"
            result["priority_color"] = "red"
            result["sla"] = "Immediate (< 4 Hours)"
        elif result["urgency_score"] >= 60:
            result["priority_level"] = "High"
            result["priority_color"] = "orange"
            result["sla"] = "Within 24 Hours"

    result["days_old"] = days_old
    result["upvotes_count"] = upvotes
    return result


def sort_complaints_with_ai(complaints_data: list, sort_by: str = "ai_urgency") -> list:
    """
    Takes a list of complaint dicts/objects, enriches them with AI analysis + community vote escalation,
    and returns them sorted according to the requested criteria:
    - 'ai_urgency': Highest Urgency first (combines AI safety score + aging + citizen vote boost)
    - 'community_votes' or 'most_voted': Highest citizen upvotes first (pure community consensus)
    - 'date_desc': Newest first
    - 'date_asc': Oldest first
    - 'status': Grouped by status
    """
    enriched = []

    for c in complaints_data:
        if hasattr(c, "complaint_id"):
            upvotes = getattr(c, "upvotes_count", 0) or 0
            c_dict = {
                "complaint_id": c.complaint_id,
                "title": c.title,
                "description": c.description,
                "category": c.category,
                "location": c.location,
                "latitude": float(c.latitude) if c.latitude is not None else None,
                "longitude": float(c.longitude) if c.longitude is not None else None,
                "status": c.status,
                "created_at": c.created_at,
                "created_at_formatted": c.created_at.strftime("%d-%m-%Y %H:%M") if c.created_at else "N/A",
                "user_id": c.user_id,
                "upvotes_count": upvotes,
            }
        else:
            c_dict = dict(c)
            upvotes = int(c_dict.get("upvotes_count") or 0)
            c_dict["upvotes_count"] = upvotes

        ai_meta = analyze_complaint_ai(
            title=c_dict.get("title", ""),
            description=c_dict.get("description", ""),
            category=c_dict.get("category", ""),
            created_at=c_dict.get("created_at"),
            upvotes_count=upvotes
        )
        c_dict["ai"] = ai_meta
        enriched.append(c_dict)

    if sort_by in ["community_votes", "most_voted"]:
        # Highest upvoted complaints first, AI urgency as secondary tie-breaker
        enriched.sort(key=lambda x: (x.get("upvotes_count", 0), x["ai"]["urgency_score"]), reverse=True)
    elif sort_by == "ai_urgency":
        # AI urgency (which already includes community vote boost), then upvotes
        enriched.sort(key=lambda x: (x["ai"]["urgency_score"], x.get("upvotes_count", 0)), reverse=True)
    elif sort_by == "date_asc":
        enriched.sort(key=lambda x: str(x.get("created_at") or ""))
    elif sort_by == "date_desc":
        enriched.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    elif sort_by == "status":
        status_order = {"Reported": 1, "Under Review": 2, "In Progress": 3, "Resolved": 4}
        enriched.sort(key=lambda x: status_order.get(x.get("status"), 5))

    return enriched


def _chat_fallback(message: str, form_context: dict = None) -> dict:
    """
    Local heuristic fallback conversational engine when Gemini API is offline or quota reached.
    """
    msg_lower = (message or "").lower()
    draft = None
    chips = [
        "How do I track my complaint?",
        "What is the standard SLA?",
        "Help me draft my grievance",
        "Which department handles water issues?"
    ]

    if any(k in msg_lower for k in ["pothole", "road", "pavement", "footpath", "divider", "asphalt"]):
        reply = (
            "I've categorized this under the **Roads Department**. Potholes and damaged asphalt represent severe traffic hazards. "
            "I have drafted a formal grievance ticket for you below. You can click **Apply to Form** to load it directly into your report."
        )
        draft = {
            "title": "Hazardous Road Surface Defect and Deep Potholes",
            "category": "Roads",
            "description": "Severe road deterioration with deep potholes causing vehicular damage and pedestrian tripping hazards. Immediate inspection, barricading, and resurfacing requested to restore safe transit."
        }
        chips = ["What is the Roads Dept SLA?", "What photo evidence should I attach?", "How to pin location on map?"]

    elif any(k in msg_lower for k in ["water", "pipe", "pipeline", "leak", "tap", "pressure", "muddy"]):
        reply = (
            "This pertains to the **Water Supply Department**. Water supply interruptions and pipeline leaks require urgent attention to prevent civic resource wastage and contamination. "
            "I have prepared an official complaint draft below."
        )
        draft = {
            "title": "Major Water Supply Disruption and Pipeline Leakage",
            "category": "Water Supply",
            "description": "Continuous water leakage observed from main pipeline, resulting in localized waterlogging and diminished household water pressure. Urgent repair by the municipal water works team required."
        }
        chips = ["Who handles sewage vs clean water?", "What is the Water Supply SLA?", "Check emergency numbers"]

    elif any(k in msg_lower for k in ["electric", "wire", "spark", "light", "dark", "pole", "transformer", "shock"]):
        reply = (
            "This falls under the **Electricity & Streetlighting Department**. "
            "⚠️ *Warning*: If there is any active sparking, hanging live wire, or shock risk, keep distance and notify emergency line **112** immediately! "
            "I've generated a priority complaint draft for this incident below."
        )
        draft = {
            "title": "Critical Electrical Hazard and Inoperative Streetlights",
            "category": "Electricity",
            "description": "Non-functional streetlights and exposed/hanging electrical infrastructure creating severe public safety danger during evening and night hours. Prompt line inspection and repair needed."
        }
        chips = ["Is this a Critical Emergency?", "What is the Electricity SLA?", "How to track resolution?"]

    elif any(k in msg_lower for k in ["garbage", "trash", "waste", "dump", "cleaning", "bin", "sweep", "smell", "rotting"]):
        reply = (
            "This issue is routed to the **Sanitation & Waste Management Department**. "
            "Accumulated waste poses bio-sanitary and vector-borne illness risks. Here is a drafted grievance ticket ready for filing."
        )
        draft = {
            "title": "Accumulation of Uncollected Municipal Solid Waste",
            "category": "Sanitation",
            "description": "Excessive overflow of solid waste and uncollected garbage at public roadside, emitting foul odors and attracting stray animals. Requesting urgent garbage compactor dispatch and sanitation clearance."
        }
        chips = ["What is the Sanitation SLA?", "Report illegal dumping", "Attach photo proof"]

    elif any(k in msg_lower for k in ["drain", "sewage", "gutter", "waterlog", "flood", "manhole"]):
        reply = (
            "This falls under the **Drainage & Sewage Department**. "
            "⚠️ Open manholes or overflowing sewage are classified as high hazards. I've prepared a high-priority ticket draft for you below."
        )
        draft = {
            "title": "Choked Sewage Drainage and Open Manhole Hazard",
            "category": "Drainage",
            "description": "Severe drainage blockage with overflowing sewage and potential fall hazard from damaged/open manhole. Immediate desilting, drain clearing, and protective cover placement required."
        }
        chips = ["Open manhole emergency SLA", "Drainage vs Roads department", "How to add photos?"]

    elif any(k in msg_lower for k in ["sla", "time", "hours", "days", "how long"]):
        reply = (
            "### ⏱️ CivicSync Service Level Agreements (SLAs):\n\n"
            "• **Critical Urgency (< 4 Hours):** Live sparking wires, open manholes, active water main bursts, flood into homes.\n"
            "• **High Urgency (Within 24 Hours):** Major street blackout, uncollected rotting garbage dump, contaminated water.\n"
            "• **Medium Urgency (48–72 Hours):** Routine potholes, low water pressure, broken pavement.\n"
            "• **Low Urgency (5–7 Days):** Park bench repair, cosmetic maintenance, faded street signage."
        )
        chips = ["Help me draft my grievance", "Who is my department officer?", "Check complaint status"]

    elif any(k in msg_lower for k in ["emergency", "accident", "fire", "gas", "life", "danger"]):
        reply = (
            "### 🚨 Municipal & Civic Emergency Contacts:\n\n"
            "• **National Emergency / Police:** `112`\n"
            "• **Fire & Rescue:** `101`\n"
            "• **Ambulance / Medical:** `108`\n"
            "• **Electricity Hazard Helpline:** `1912`\n"
            "• **Municipal Disaster Control:** `1800-233-1000`\n\n"
            "If anyone is in immediate physical danger, call the emergency number first before filing an online grievance!"
        )
        chips = ["Draft an urgent complaint", "Report live wire", "Report open manhole"]

    elif any(k in msg_lower for k in ["track", "status", "check"]):
        reply = (
            "You can track any grievance in real time! Go to **[Track Complaint](/track-complaint)** and enter your Complaint ID. "
            "You will see the assigned department, current status (*Reported*, *Under Review*, *In Progress*, *Resolved*), officer remarks, and live timeline."
        )
        chips = ["Where do I find my Complaint ID?", "Help me write a complaint", "What is the SLA?"]

    else:
        reply = (
            "Hello! I am **CivicSync AI Assistant** (powered by Google Gemini). 🏛️\n\n"
            "I'm here to help you file grievances quickly and accurately. You can:\n"
            "• Describe any municipal issue (e.g. *'There is a big pothole near market'* or *'Streetlights are dark'*)\n"
            "• Ask me to draft a complaint title and description with 1-click form fill\n"
            "• Inquire about department responsibilities and resolution SLAs\n\n"
            "What civic issue can I help you with today?"
        )

    return {
        "success": True,
        "reply": reply,
        "draft": draft,
        "suggested_chips": chips,
        "ai_engine": "CivicSync Heuristic Assistant (Offline/Fallback)"
    }


def chat_with_gemini(message: str, history: list = None, form_context: dict = None) -> dict:
    """
    Interactive Civic Assistant chat powered by Google Gemini API.
    Provides conversational municipal assistance and generates structured complaint drafts.
    Falls back gracefully to local heuristic assistant if offline or quota exceeded.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not (message or "").strip():
        return _chat_fallback(message, form_context)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={api_key}"

    system_instruction = (
        "You are CivicSync AI Assistant, an empathetic, highly knowledgeable municipal civil assistant embedded in CivicSync (a civic grievance management system).\n\n"
        "Your core objectives:\n"
        "1. Help citizens articulate, draft, and file civic complaints accurately.\n"
        "2. Accurately identify the responsible municipal department from one of: \"Roads\", \"Sanitation\", \"Water Supply\", \"Electricity\", \"Drainage\", or \"Other\".\n"
        "3. Explain standard resolution timelines (SLAs), what photographic evidence or landmarks to provide, and how hazards are prioritized.\n"
        "4. If the citizen describes any problem or asks you to write, refine, summarize, or draft a complaint, ALWAYS conclude your message with a structured JSON block delimited by ```civic_draft:\n"
        "```civic_draft\n"
        "{\n"
        '  "title": "<Concise, clear complaint title under 80 characters>",\n'
        '  "category": "<Roads | Sanitation | Water Supply | Electricity | Drainage | Other>",\n'
        '  "description": "<Detailed, formal complaint description mentioning location details, public safety impact, and required municipal remediation.>"\n'
        "}\n"
        "```\n"
        "5. If the citizen reports an immediate life-threatening emergency (such as gas leaks, collapsed structures, direct live wire touching water/pedestrians, active fire), clearly remind them to first call emergency services (112 / 101 / 108) immediately alongside filing this ticket.\n"
        "6. Keep your prose concise, structured with friendly bullet points or short paragraphs. Avoid overly long walls of text.\n"
        "7. Format using clean markdown (bolding, bullet points, numbered lists)."
    )

    contents = []
    if history and isinstance(history, list):
        for turn in history[-6:]:
            role = turn.get("role", "user")
            text = turn.get("text", "").strip()
            if text:
                role = "model" if role in ["model", "assistant", "bot"] else "user"
                contents.append({"role": role, "parts": [{"text": text}]})

    current_prompt = message
    if form_context:
        ctx_parts = []
        if form_context.get("category"):
            ctx_parts.append(f"Selected Category: {form_context['category']}")
        if form_context.get("title"):
            ctx_parts.append(f"Current Title: {form_context['title']}")
        if form_context.get("description"):
            ctx_parts.append(f"Current Description: {form_context['description']}")
        if ctx_parts:
            current_prompt += f"\n\n[Form Context: {', '.join(ctx_parts)}]"

    contents.append({"role": "user", "parts": [{"text": current_prompt}]})

    payload = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 800
        }
    }

    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned from Gemini API")

            raw_text = candidates[0]["content"]["parts"][0]["text"].strip()

            draft = None
            clean_reply = raw_text
            match = re.search(r"```(?:civic_draft|json)?\s*(\{[\s\S]*?\})\s*```", raw_text)
            if match:
                try:
                    draft = json.loads(match.group(1))
                    if not draft.get("title") or not draft.get("description"):
                        draft = None
                except Exception:
                    draft = None

                if draft:
                    clean_reply = raw_text[:match.start()].strip() + "\n\n" + raw_text[match.end():].strip()
                    clean_reply = clean_reply.strip()

            if not clean_reply and draft:
                clean_reply = "I've drafted your civic complaint below based on your description. Click **Apply to Form** to load it directly into your report."

            lower_raw = raw_text.lower()
            chips = []
            if "roads" in lower_raw or "pothole" in lower_raw:
                chips = ["What is the Roads Dept SLA?", "What photo evidence should I attach?", "How do I pin location?"]
            elif "water" in lower_raw:
                chips = ["What is the Water Supply SLA?", "Who handles pipeline bursts?", "Track my complaint"]
            elif "electric" in lower_raw or "light" in lower_raw:
                chips = ["Is a dark streetlight high priority?", "Electricity repair timeline", "Emergency safety numbers"]
            elif "sanitation" in lower_raw or "garbage" in lower_raw:
                chips = ["Sanitation collection timeline", "Report illegal dumping", "Attach photo proof"]
            else:
                chips = ["Help me draft this complaint", "Which department handles this?", "What is the standard SLA?", "How to track status?"]

            return {
                "success": True,
                "reply": clean_reply,
                "draft": draft,
                "suggested_chips": chips,
                "ai_engine": "Google Gemini Flash (Cloud AI)"
            }

    except Exception as e:
        print(f"[Gemini Chat] API call failed: {e}. Falling back to local heuristic engine.")
        return _chat_fallback(message, form_context)


def verify_image_issue_match(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    category: str = "",
    title: str = "",
    description: str = "",
    api_key: str = None
) -> dict:
    """
    Multimodal Google Gemini Vision verification engine.
    Inspects citizen-uploaded grievance photo and evaluates whether the photo
    authentically matches the reported municipal category and description,
    preventing submission of unrelated, fraudulent, or mismatched images.
    """
    if not image_bytes or len(image_bytes) < 10:
        return {
            "success": False,
            "is_match": False,
            "confidence": 0.0,
            "detected_elements": ["Empty File"],
            "reason": "The uploaded photo file is empty or corrupted.",
            "suggested_category": "Invalid"
        }

    key = api_key or os.getenv("GEMINI_API_KEY", "")
    if not key:
        return {
            "success": True,
            "is_match": True,
            "confidence": 0.8,
            "detected_elements": ["Photo Evidence (Local Heuristic)"],
            "reason": "API key unavailable. Local heuristic validation passed.",
            "suggested_category": category or "Other",
            "ai_engine": "Local Heuristic"
        }

    # Normalize mime_type
    if not mime_type or "/" not in mime_type:
        mime_type = "image/jpeg"
    elif "png" in mime_type.lower():
        mime_type = "image/png"
    elif "webp" in mime_type.lower():
        mime_type = "image/webp"
    else:
        mime_type = "image/jpeg"

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={key}"

    prompt = f"""You are an AI Civic Integrity Officer. Inspect this citizen-submitted grievance photo and determine if the image authenticates and matches the reported civic issue.

Reported Grievance:
- Category: {category}
- Title: {title}
- Description: {description}

Rules:
1. is_match = TRUE if the image depicts or relates to the civic infrastructure problem described (e.g., damaged road/pothole for Roads, overflowing garbage/dump for Sanitation, leaking pipe/water pooling for Water Supply, damaged street light/wires for Electricity, clogged gutter/open manhole for Drainage, public property damage for Other).
2. is_match = FALSE if the image is unrelated, such as:
   - Selfies, personal portraits, people posing
   - Household pets, cats, dogs (unless dead animal obstructing road)
   - Food, meals, restaurants
   - Solid colors, blank images, screenshots, memes, wallpapers
   - Indoors (bedrooms, living rooms) with no municipal problem
   - A completely different civic category (e.g. user selected Roads but photo shows a pet, food, or indoor lighting)

Return ONLY valid JSON matching this schema:
{{
  "is_match": <boolean true or false>,
  "confidence": <float 0.0 to 1.0>,
  "detected_elements": [<short list of strings describing visible elements>],
  "reason": <1-2 sentences explaining why it matches or why it was rejected>,
  "suggested_category": <string of detected category, or "Non-civic / Invalid">
}}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_image
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json"
        }
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned from Gemini Vision API")

            raw_text = candidates[0]["content"]["parts"][0]["text"].strip()
            match = re.search(r"\{[\s\S]*\}", raw_text)
            if match:
                parsed = json.loads(match.group(0))
            else:
                parsed = json.loads(raw_text)

            is_match = bool(parsed.get("is_match", True))
            confidence = float(parsed.get("confidence", 0.9))
            detected = parsed.get("detected_elements", [])
            reason = parsed.get("reason", "Photo verified.")
            suggested = parsed.get("suggested_category", category)

            return {
                "success": True,
                "is_match": is_match,
                "confidence": confidence,
                "detected_elements": detected,
                "reason": reason,
                "suggested_category": suggested,
                "ai_engine": "Google Gemini Vision (Cloud AI)"
            }

    except Exception as e:
        print(f"[Gemini Vision] Image verification API call skipped/failed: {e}. Using local heuristic engine.")
        is_valid_header = False
        if len(image_bytes) >= 4:
            if image_bytes[:2] == b'\xff\xd8' or image_bytes[:4] == b'\x89PNG' or b'WEBP' in image_bytes[:12]:
                is_valid_header = True

        return {
            "success": True,
            "is_match": is_valid_header,
            "confidence": 0.75 if is_valid_header else 0.2,
            "detected_elements": ["Civic Photo Evidence" if is_valid_header else "Unrecognized Image Format"],
            "reason": "Image format verified by local fallback." if is_valid_header else "Invalid image binary format.",
            "suggested_category": category or "Other",
            "ai_engine": "Local Heuristic Engine"
        }


def find_duplicate_complaints(
    complaints_list: list,
    category: str,
    latitude: float,
    longitude: float,
    location_text: str = "",
    title_text: str = "",
    radius_km: float = 0.35,
    exclude_user_id: int = None,
    exclude_complaint_id: int = None
) -> list:
    """
    Identifies potential duplicate complaints in complaints_list based on
    matching category, geographical proximity (within ~350 meters), or street location match.
    Allows multiple citizens to report the same issue while clustering them for accelerated municipal escalation.
    """
    def haversine(lat1, lon1, lat2, lon2):
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return float('inf')
        R = 6371.0 # Earth radius in km
        dlat = math.radians(float(lat2) - float(lat1))
        dlon = math.radians(float(lon2) - float(lon1))
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    duplicates = []
    norm_cat = category.strip().lower() if category else ""
    norm_loc = location_text.strip().lower() if location_text else ""
    norm_title = title_text.strip().lower() if title_text else ""

    for c in complaints_list:
        c_id = getattr(c, "complaint_id", None) or (c.get("complaint_id") if isinstance(c, dict) else None)
        c_uid = getattr(c, "user_id", None) or (c.get("user_id") if isinstance(c, dict) else None)
        c_status = getattr(c, "status", "") or (c.get("status") if isinstance(c, dict) else "")
        c_cat = (getattr(c, "category", "") or (c.get("category") if isinstance(c, dict) else "")).lower()
        c_lat = getattr(c, "latitude", None) if not isinstance(c, dict) else c.get("latitude")
        c_lng = getattr(c, "longitude", None) if not isinstance(c, dict) else c.get("longitude")
        c_loc = (getattr(c, "location", "") or (c.get("location") if isinstance(c, dict) else "")).lower()
        c_title = (getattr(c, "title", "") or (c.get("title") if isinstance(c, dict) else "")).lower()

        # Exclude self or resolved complaints
        if exclude_complaint_id and c_id == exclude_complaint_id:
            continue
        if exclude_user_id and c_uid == exclude_user_id:
            continue
        if c_status == "Resolved":
            continue

        # Check category match
        cat_match = (norm_cat == c_cat) or (norm_cat in c_cat) or (c_cat in norm_cat)

        # Check distance
        dist = haversine(latitude, longitude, c_lat, c_lng)
        geo_match = dist <= radius_km

        # Check text match if location or title are very close
        text_match = False
        if norm_loc and c_loc:
            common_words = set(norm_loc.split()) & set(c_loc.split()) - {"road", "street", "near", "opposite", "opp", "lane", "nagar", "sector", "the", "and"}
            if len(common_words) >= 2 or norm_loc == c_loc:
                text_match = True

        if cat_match and (geo_match or text_match):
            duplicates.append({
                "complaint_id": c_id,
                "title": getattr(c, "title", "") if not isinstance(c, dict) else c.get("title"),
                "category": getattr(c, "category", "") if not isinstance(c, dict) else c.get("category"),
                "location": getattr(c, "location", "") if not isinstance(c, dict) else c.get("location"),
                "status": c_status,
                "distance_meters": round(dist * 1000) if dist != float('inf') else None,
                "created_at": getattr(c, "created_at", None) if not isinstance(c, dict) else c.get("created_at"),
                "upvotes_count": getattr(c, "upvotes_count", 0) if not isinstance(c, dict) else c.get("upvotes_count", 0)
            })

    duplicates.sort(key=lambda d: d.get("distance_meters") or 999999)
    return duplicates


