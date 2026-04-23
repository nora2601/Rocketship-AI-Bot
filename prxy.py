# sales_engine.py

import json
import os
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

class SalesConsultant:
    def __init__(self, tenant_id, product_catalog, inventory, seller_settings):
        self.tenant_id = tenant_id
        self.product_catalog = product_catalog
        self.inventory = inventory  # dict: {product_id: {'stock': int, ...}}
        self.seller_settings = seller_settings
        self.brand_voice = seller_settings.get('brand_voice', 'Professional')
        self.custom_emojis = seller_settings.get('custom_emojis', {})

    def get_smart_response(self, user_message, product_id):
        requested_product_id = product_id
        if requested_product_id not in self.product_catalog:
            normalized_message = str(user_message).lower()
            matched_ids = [
                pid
                for pid, prod in self.product_catalog.items()
                if str(prod.get('name', '')).lower() in normalized_message
            ]
            if len(matched_ids) == 1:
                requested_product_id = matched_ids[0]

        stock = self.inventory.get(requested_product_id, {}).get('stock', 0)
        product = self.product_catalog.get(requested_product_id)
        final_resp = ""
        brand_voice_normalized = str(self.brand_voice).lower()
        shipping = self.seller_settings.get('shipping_info', '')
        pay = self.seller_settings.get('platforms', {}).get('payment_method', '')

        if not product:
            final_resp = self._reply("Sorry, I couldn't find that product.", fallback=True)
        elif stock > 0:
            base_resp = (
                f"Yes, we have {product['name']} in stock! {self._emoji('in_stock')}"
            )
            if brand_voice_normalized == "luxury":
                final_resp = self._reply(base_resp)
            else:
                final_resp = base_resp

        else:
            # 1) Bridge selection (Luxury case-insensitive, otherwise friendly bridge)
            product_name = product['name']
            if brand_voice_normalized == "luxury":
                bridge = f"Our {product_name} is currently being restocked for our most discerning clients."
            else:
                bridge = (
                    f"Whoops! {product_name} flew off the shelves. "
                    f"But wait, fabulous backup options just for you! {self._emoji('bridge')}"
                )

            # 2) Collect alternatives
            alternatives = self._suggest_alternatives(requested_product_id, product)
            qualify = self._qualifying_question() or "Can I help you choose the best option for your needs?"
            suggestions = "\n".join(
                [f"- {alt['name']}: {alt.get('description', '')} {self._emoji('alt')}" for alt in alternatives]
            )

            # 3) Final assembly
            final_resp = (
                f"{bridge}\n"
                f"Here are some handpicked alternatives for you:\n"
                f"{suggestions}\n"
                f"{qualify}"
            )
        if product:
            final_resp = f"{final_resp}\n\n{shipping}\n{pay}"
        return final_resp

    def _suggest_alternatives(self, product_id, product):
        tag_set = set(product.get('tags', []))
        category = product.get('category')

        candidates = []
        for pid, prod in self.product_catalog.items():
            if pid == product_id or self.inventory.get(pid, {}).get('stock', 0) <= 0:
                continue
            score = 0
            if prod.get('category') == category:
                score += 2
            score += len(tag_set.intersection(set(prod.get('tags', []))))
            candidates.append((score, prod))
        candidates = sorted(candidates, key=lambda x: -x[0])
        top = [prod for score, prod in candidates if score > 0]
        if len(top) >= 2:
            return top[:2]
        # fallback: fill up with anything in stock if not enough relevant
        others = [
            prod
            for pid, prod in self.product_catalog.items()
            if pid != product_id and self.inventory.get(pid, {}).get('stock', 0) > 0 and prod not in top
        ]
        random.shuffle(others)
        return (top + others)[:2]

    def _qualifying_question(self):
        questions = [
            "Is this for daily use or a special gift?",
            "Are you shopping for yourself or someone else?",
            "Can I help you find something unique?",
        ]
        # Customization per brand
        brand_voice_normalized = str(self.brand_voice).lower()
        if brand_voice_normalized == "luxury":
            return "May I ask, is this discerning choice intended as a refined daily delight or as a thoughtful gift? " + self._emoji('qualify')
        elif brand_voice_normalized == "sassy":
            return "Spill the tea – daily must-have or is this a shiny gift? " + self._emoji('qualify')
        elif brand_voice_normalized == "professional":
            return "Is this for everyday use or might it be a gift?" + self._emoji('qualify')
        return random.choice(questions) + " " + self._emoji('qualify')

    def _out_of_stock_bridge(self, product_name):
        brand_voice_normalized = str(self.brand_voice).lower()
        if brand_voice_normalized == "luxury":
            return (
                f"While our exclusive {product_name} is currently spoken for, "
                f"may I tempt you with equally exquisite alternatives? {self._emoji('bridge')}"
            )
        elif brand_voice_normalized == "sassy":
            return (
                f"Whoops! {product_name} flew off the shelves. But wait, fabulous backup options just for you! {self._emoji('bridge')}"
            )
        elif brand_voice_normalized == "professional":
            return (
                f"Unfortunately, {product_name} is not available at the moment. However, I can suggest some great alternatives. {self._emoji('bridge')}"
            )
        return f"{product_name} is out of stock, but I have other awesome picks! {self._emoji('bridge')}"

    def _emoji(self, context):
        # Allow per-seller emoji selection
        return self.custom_emojis.get(context, "")

    def _reply(self, text, fallback=False):
        # Could be used for more advanced formatting per brand
        if self.brand_voice == "Luxury":
            return "💎 " + text
        elif self.brand_voice == "Sassy":
            return "✨ " + text
        elif self.brand_voice == "Professional":
            return text
        return text


def load_sellers_data(file_path=None):
    path = Path(file_path) if file_path else Path(__file__).with_name("sellers.json")
    with path.open("r", encoding="utf-8") as sellers_file:
        return json.load(sellers_file)


SELLER_DATA = load_sellers_data()
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "my_rocketship_2026")


def create_consultant_from_seller_id(seller_id, sellers_data):
    seller_data = sellers_data.get(seller_id)
    if not seller_data:
        raise ValueError(f"Unknown seller_id: {seller_id}")
    return SalesConsultant(
        seller_id,
        seller_data.get("product_catalog", {}),
        seller_data.get("inventory", {}),
        seller_data.get("seller_settings", {}),
    )


def run_demo_for_seller(seller_id, user_message, product_id):
    consultant = create_consultant_from_seller_id(seller_id, SELLER_DATA)
    print(f"You: {user_message}")
    resp = consultant.get_smart_response(user_message, product_id)
    print("SalesConsultant:", resp)
    print()


def run_mart_demo():
    run_demo_for_seller("high_end_luxury", "Do you have any Gourmet Cake Mix?", "p1")


def run_localmart_demo():
    run_demo_for_seller("friendly_mart", "Do you have Cheaps Biscuits?", "p1")

def extract_message_fields(payload):
    """
    Supports two payload styles:
    1) Simple internal payload:
       {"sender_id": "...", "message_text": "...", "product_id": "..."}
    2) Meta/Instagram webhook payload:
       {"entry": [{"messaging": [{"sender": {"id": "..."}, "message": {"text": "..."}}]}]}
    """
    sender_id = payload.get("sender_id")
    message_text = payload.get("message_text")
    product_id = payload.get("product_id")

    if sender_id and message_text:
        return sender_id, message_text, product_id

    entries = payload.get("entry", [])
    for entry in entries:
        messaging_events = entry.get("messaging", [])
        for event in messaging_events:
            sender = event.get("sender", {}) or {}
            message = event.get("message", {}) or {}
            sender_id = sender.get("id")
            message_text = message.get("text")
            if sender_id and message_text:
                product_id = (
                    (event.get("postback") or {}).get("payload")
                    or payload.get("product_id")
                    or "p1"
                )
                return sender_id, message_text, product_id

    return None, None, None


app = FastAPI(title="AI Sales Rocketship Webhook API")


@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    return JSONResponse(
        status_code=403,
        content={"error": "Verification token mismatch or invalid mode."},
    )


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    sender_id, message_text, product_id = extract_message_fields(payload)

    if not sender_id or not message_text:
        raise HTTPException(
            status_code=400,
            detail="Could not extract sender_id and message_text from payload.",
        )

    try:
        consultant = create_consultant_from_seller_id(sender_id, SELLER_DATA)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    response_text = consultant.get_smart_response(message_text, product_id or "p1")
    return {
        "recipient_id": sender_id,
        "response_text": response_text,
    }