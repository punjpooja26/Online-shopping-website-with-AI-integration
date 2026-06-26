from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
import re
import os
import urllib.request
import json
import datetime
from typing import Optional
from jose import jwt, JWTError
from app.auth import SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/api/chatbot", tags=["AI Chatbot"])

def get_optional_user(request: Request, db: Session) -> Optional[models.User]:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id:
            return db.query(models.User).filter(models.User.id == user_id).first()
    except JWTError:
        pass
    return None

def get_or_create_hubspot_contact(email: str, name: str, phone: str = None) -> Optional[str]:
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
    if not token:
        return None

    # Split name into first and last
    name_parts = name.split(" ", 1)
    firstname = name_parts[0]
    lastname = name_parts[1] if len(name_parts) > 1 else ""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # 1. Try to fetch existing contact
    get_url = f"https://api.hubapi.com/crm/v3/objects/contacts/{email}?idProperty=email"
    try:
        req = urllib.request.Request(get_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            contact_id = res_data.get("id")
            
            # If found, update it with name and phone
            patch_url = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}"
            properties = {}
            if firstname:
                properties["firstname"] = firstname
            if lastname:
                properties["lastname"] = lastname
            if phone:
                properties["phone"] = phone
                
            if properties:
                update_payload = {"properties": properties}
                update_req = urllib.request.Request(
                    patch_url,
                    data=json.dumps(update_payload).encode("utf-8"),
                    headers=headers,
                    method="PATCH"
                )
                with urllib.request.urlopen(update_req, timeout=5):
                    pass
            return str(contact_id)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 2. Contact not found, create new one
            create_url = "https://api.hubapi.com/crm/v3/objects/contacts"
            payload_data = {
                "properties": {
                    "email": email,
                    "firstname": firstname,
                    "lastname": lastname,
                    "phone": phone or ""
                }
            }
            try:
                req = urllib.request.Request(
                    create_url,
                    data=json.dumps(payload_data).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    return str(res_data.get("id"))
            except Exception as ex:
                print(f"ERROR: HubSpot CRM contact creation failed: {ex}")
                return None
        else:
            print(f"ERROR: HubSpot CRM contact lookup failed: {e}")
            return None
    except Exception as e:
        print(f"ERROR: HubSpot CRM contact lookup failed: {e}")
        return None

def sync_lead_to_hubspot(lead: models.Lead) -> tuple[str, str]:
    """
    Syncs or updates a lead in HubSpot CRM API v3.
    Returns (status, hubspot_contact_id)
    """
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
    if not token:
        print("WARNING: HUBSPOT_ACCESS_TOKEN is not configured in environment. Lead sync marked as Local.")
        return "Local Only", None
        
    contact_id = get_or_create_hubspot_contact(lead.email, lead.name, lead.phone)
    if contact_id:
        return "Synced", contact_id
    else:
        return "Failed", None

def log_activity_to_hubspot(email: str, note_body: str) -> bool:
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
    if not token:
        return False
        
    contact_id = get_or_create_hubspot_contact(email, "Aura Lead")
    if not contact_id:
        return False
        
    url = "https://api.hubapi.com/crm/v3/objects/notes"
    payload = {
        "properties": {
            "hs_note_body": note_body,
            "hs_timestamp": datetime.datetime.utcnow().isoformat() + "Z"
        },
        "associations": [
            {
                "to": {
                    "id": contact_id
                },
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 202
                    }
                ]
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return True
    except Exception as e:
        print(f"ERROR: HubSpot CRM note creation failed: {e}")
        return False

@router.get("/lead-status")
def check_lead_status(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    current_user = get_optional_user(request, db)
    user_id = current_user.id if current_user else None
    
    # 1. If user is logged in, check lead by email
    lead = None
    if user_id:
        lead = db.query(models.Lead).filter(models.Lead.email == current_user.email).first()
        if not lead:
            # Create a skeleton lead for logged in user
            lead = models.Lead(
                name=current_user.name,
                email=current_user.email,
                phone=None,
                hubspot_sync_status="Pending"
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            
    # 2. If not logged in, check by session chat history
    if not lead and session_id:
        chats = db.query(models.ChatHistory).filter(
            models.ChatHistory.session_id == session_id,
            models.ChatHistory.sender == "user"
        ).all()
        for chat in chats:
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', chat.message)
            if email_match:
                email = email_match.group(0).strip().lower()
                lead = db.query(models.Lead).filter(models.Lead.email.ilike(email)).first()
                if lead:
                    break

    has_contact = lead is not None and lead.phone is not None
    return {
        "has_contact": has_contact,
        "name": lead.name if lead else None,
        "email": lead.email if lead else None,
        "phone": lead.phone if lead else None
    }

def call_gemini_api(api_key: str, system_instruction: str, history: list) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": history
    }
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        return res_data["candidates"][0]["content"]["parts"][0]["text"]

def call_chatgpt_api(api_key: str, system_instruction: str, history: list) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    messages = [{"role": "system", "content": system_instruction}]
    for msg in history:
        role = "assistant" if msg.get("role") in ["model", "assistant", "bot"] else "user"
        content_text = ""
        if "parts" in msg:
            content_text = msg.get("parts", [{"text": ""}])[0].get("text", "")
        else:
            content_text = msg.get("content", "") or msg.get("message", "")
        messages.append({
            "role": role,
            "content": content_text
        })
    payload = {
        "model": "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.7
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        return res_data["choices"][0]["message"]["content"]


@router.post("/query", response_model=schemas.ChatResponse)
def query_chatbot(
    message_in: schemas.ChatMessage,
    request: Request,
    db: Session = Depends(get_db)
):
    msg = message_in.message.strip()
    msg_lower = msg.lower()
    session_id = message_in.session_id or "default_session"
    
    current_user = get_optional_user(request, db)
    user_id = current_user.id if current_user else None
    
    # 1. Save User message to ChatHistory database
    user_chat = models.ChatHistory(
        session_id=session_id,
        user_id=user_id,
        sender="user",
        message=msg
    )
    db.add(user_chat)
    db.commit()
    
    # 2. Check current lead status
    lead = None
    if user_id:
        lead = db.query(models.Lead).filter(models.Lead.email == current_user.email).first()
        if not lead:
            lead = models.Lead(
                name=current_user.name,
                email=current_user.email,
                phone=None,
                hubspot_sync_status="Pending"
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            
    if not lead and session_id:
        chats = db.query(models.ChatHistory).filter(
            models.ChatHistory.session_id == session_id,
            models.ChatHistory.sender == "user"
        ).all()
        for chat in chats:
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', chat.message)
            if email_match:
                email = email_match.group(0).strip().lower()
                lead = db.query(models.Lead).filter(models.Lead.email.ilike(email)).first()
                if lead:
                    break

    has_contact_info = lead is not None and lead.phone is not None
    reply = ""
    
    # Extract possible contact coordinates from current message
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', msg)
    phone_match = re.search(r'\+?\b\d{10,15}\b', msg)
    
    # 3. Process immediate registration/update if matching coordinates are sent in this message
    is_submitting_details = False
    if email_match and phone_match:
        is_submitting_details = True
        email = email_match.group(0).strip().lower()
        phone = phone_match.group(0)
        
        # Extract name
        name_match = re.search(r'(?:my name is|i am|call me|name is|name:|name)\s+([a-zA-Z]{2,15}(?:\s+[a-zA-Z]{2,15}){0,2})', msg_lower)
        name = "Aura Lead"
        if name_match:
            name = name_match.group(1).title().strip()
        else:
            temp_msg = msg.replace(email_match.group(0), "").replace(phone_match.group(0), "")
            temp_msg = re.sub(r'[^a-zA-Z\s]', ' ', temp_msg)
            noise_words = {
                "email", "phone", "number", "mobile", "is", "and", "my", "name", 
                "contact", "details", "here", "are", "to", "with", "call", "me", 
                "i", "am", "lead", "hi", "hello", "hey", "please", "connect", 
                "stylist", "representative", "agent", "get", "in", "touch"
            }
            words = [w for w in temp_msg.split() if w.lower() not in noise_words and len(w) >= 2]
            if words:
                name = " ".join(words[:2]).title().strip()
                
        existing_lead = db.query(models.Lead).filter(models.Lead.email == email).first()
        if existing_lead:
            existing_lead.phone = phone
            existing_lead.name = name
            sync_status, hs_id = sync_lead_to_hubspot(existing_lead)
            existing_lead.hubspot_sync_status = sync_status
            if hs_id:
                existing_lead.hubspot_contact_id = hs_id
            db.commit()
            lead = existing_lead # Ensure lead variable is set to this lead for subsequent context
            has_contact_info = True # Re-evaluate state
            reply = f"Awesome! I've updated your lead profile. Name: <strong>{name}</strong>, Email: <strong>{email}</strong>, Phone: <strong>{phone}</strong>. Sync status with HubSpot CRM: <strong>{sync_status}</strong>. How can I assist you with our catalog today?"
        else:
            new_lead = models.Lead(
                name=name,
                email=email,
                phone=phone,
                hubspot_sync_status="Pending"
            )
            db.add(new_lead)
            db.commit()
            db.refresh(new_lead)
            
            sync_status, hs_id = sync_lead_to_hubspot(new_lead)
            new_lead.hubspot_sync_status = sync_status
            if hs_id:
                new_lead.hubspot_contact_id = hs_id
            db.commit()
            lead = new_lead # Ensure lead variable is set to this lead for subsequent context
            has_contact_info = True # Re-evaluate state
            reply = f"Thank you, <strong>{name}</strong>! I have captured your details and synchronized them with HubSpot CRM.<br>HubSpot CRM Sync: <strong>{sync_status}</strong>.<br>How can I help you today?"
            
    elif lead and lead.phone is None and phone_match:
        is_submitting_details = True
        phone = phone_match.group(0)
        lead.phone = phone
        sync_status, hs_id = sync_lead_to_hubspot(lead)
        lead.hubspot_sync_status = sync_status
        if hs_id:
            lead.hubspot_contact_id = hs_id
        db.commit()
        has_contact_info = True # Re-evaluate state
        reply = f"Thank you, <strong>{lead.name}</strong>! I've updated your phone number to <strong>{phone}</strong>. Your styling profile is now complete. We have synchronized this with HubSpot CRM.<br>How can I help you today?"

    # 4. State check for Q&A or other actions
    if not is_submitting_details:
        if not has_contact_info:
            if lead and lead.phone is None:
                reply = f"Welcome back, <strong>{lead.name}</strong>! Before we begin, please share your <strong>Phone number</strong> to complete your priority styling registration."
            elif email_match:
                reply = "Thank you! I see your email is <strong>" + email_match.group(0) + "</strong>, but I still need your <strong>Phone number and Name</strong> to connect you with our styling team. Please provide them."
            elif phone_match:
                reply = "Thank you! I see your phone number is <strong>" + phone_match.group(0) + "</strong>, but I still need your <strong>Email and Name</strong> to connect you with our styling team. Please provide them."
            else:
                reply = "Hello! I am Aura, your e-commerce AI assistant. To help you with your fashion queries, please share your <strong>Name, Email, and Phone number</strong> first so we can register you in our system."
        else:
            # Check if ChatGPT or Gemini API keys are available
            openai_key = os.environ.get("OPENAI_API_KEY")
            gemini_key = os.environ.get("GEMINI_API_KEY")
            
            # Prepare instructions, catalog, and dynamic FAQs
            products_db = db.query(models.Product).all()
            catalog_text = ""
            for p in products_db:
                orig = f" (Original Price: ${p.original_price:.2f})" if p.original_price else ""
                catalog_text += f"- Product ID: {p.id}\n  Name: {p.name}\n  Category: {p.category.name if p.category else 'Apparel'}\n  Price: ${p.price:.2f}{orig}\n  Stock: {p.stock} units\n  Sizes: {p.sizes}\n  Colors: {p.colors}\n  Rating: {p.rating} ★\n  Specs: {p.specifications}\n  Description: {p.description}\n\n"
        
            faqs_db = db.query(models.FAQ).all()
            faqs_text = ""
            for faq in faqs_db:
                faqs_text += f"Question: {faq.question}\nAnswer: {faq.answer}\n\n"

            system_instruction = (
                "You are Aura, the premier AI fashion stylist and customer support assistant for Aura Streetwear Store. "
                "Your tone is sleek, confident, and expert in techwear/streetwear.\n\n"
                "YOUR CORE MISSIONS:\n"
                "1. Respond directly, strongly, and accurately to any customer questions about products, sizing, coordinates, shipping, cart, checkout, returns, and loyalty membership.\n"
                "2. Sizing advice: Techwear fits are often oversized. Standard fit is true-to-size, and utility items are tailored for layering.\n"
                "3. Layering & styling: Suggest sets of matching coordinates (e.g., matching a jacket with ripstop cargo pants or tactical bags).\n\n"
                "REAL-TIME CATALOG INVENTORY:\n"
                f"{catalog_text}\n"
                "DYNAMIC STORE POLICIES & FAQS:\n"
                f"{faqs_text}\n"
                "CUSTOMER PROFILE:\n"
                f"- Name: {lead.name}\n"
                f"- Email: {lead.email}\n"
                f"- Phone: {lead.phone}\n\n"
                "IMPORTANT FORMATTING RULES:\n"
                "1. Product Links: You MUST format any product recommendation as a clickable HTML link. "
                "Format: <a href=\"product-details.html?id=PRODUCT_ID\" class=\"text-info\">PRODUCT_NAME</a>. Do not forget this!\n"
                "2. Structure: Use HTML line breaks (<br>) and bold tag (<strong>) for spacing and formatting. Do not use markdown bullet lists (-), use HTML list tags or bullet characters (•).\n"
                "3. Cart/Checkout: If asked to add to cart or buy, instruct them to click on the product link and use the 'Add to Cart' button on the detail page.\n"
                "4. Conversation: Always end with a styling follow-up question."
            )
        
            # Fetch chat history (limit to last 12 messages for token efficiency)
            history_msgs = db.query(models.ChatHistory).filter(
                models.ChatHistory.session_id == session_id
            ).order_by(models.ChatHistory.created_at.asc()).limit(12).all()
        
            gemini_contents = []
            for msg_hist in history_msgs:
                role = "user" if msg_hist.sender == "user" else "model"
                gemini_contents.append({
                    "role": role,
                    "parts": [{"text": msg_hist.message}]
                })
        
            if gemini_contents and gemini_contents[-1]["role"] != "user":
                gemini_contents.append({
                    "role": "user",
                    "parts": [{"text": msg}]
                })
            elif not gemini_contents:
                gemini_contents.append({
                    "role": "user",
                    "parts": [{"text": msg}]
                })
        
            reply = None
            if openai_key:
                try:
                    reply = call_chatgpt_api(openai_key, system_instruction, gemini_contents)
                except Exception as e:
                    print(f"ChatGPT API Error: {e}")
            
            if not reply and gemini_key:
                try:
                    reply = call_gemini_api(gemini_key, system_instruction, gemini_contents)
                except Exception as e:
                    print(f"Gemini API Error: {e}")
            
            # Fallback to Rule-Based Engine
            if not reply:
                # 1. Intercept Greetings and Acknowledgments first
                greetings = ["hi", "hello", "hey", "hola", "yo", "greetings", "good morning", "good afternoon", "good evening", "howdy"]
                acknowledgments = ["ok", "okay", "thanks", "thank you", "sure", "cool", "fine", "awesome", "perfect", "great"]
                clean_msg = re.sub(r'[^\w\s]', '', msg_lower).strip()
                
                # Check if it's just a greeting or acknowledgment
                is_greeting = clean_msg in greetings
                is_acknowledgment = clean_msg in acknowledgments
                
                if is_greeting:
                    reply = f"Hello <strong>{lead.name}</strong>! Welcome to Aura Streetwear Store. I am your personal AI fashion stylist.<br><br>How can I help you style your outfit today? You can ask me to <strong>recommend garments</strong>, check <strong>sizing</strong>, or answer questions about <strong>shipping</strong> and <strong>returns</strong>."
                elif is_acknowledgment:
                    reply = "Awesome! Let me know if you need styling coordination, sizing advice, or help with checkouts. I'm here to help!"
                elif any(keyword in msg_lower for keyword in ["recommend", "suggest", "preferences", "what should i buy", "recommendation", "outfit", "style", "layer"]):
                    cat_filter = None
                    category_name = ""
                    if "men" in msg_lower:
                        cat_filter = "Men"
                        category_name = "Men's Collection"
                    elif "women" in msg_lower:
                        cat_filter = "Women"
                        category_name = "Women's Collection"
                    elif "kid" in msg_lower:
                        cat_filter = "Kids"
                        category_name = "Kids Collection"
                    elif "shoe" in msg_lower or "footwear" in msg_lower:
                        cat_filter = "Shoes"
                        category_name = "Shoes Collection"
                    elif "access" in msg_lower or "bag" in msg_lower or "watch" in msg_lower:
                        cat_filter = "Accessories"
                        category_name = "Accessories"
                    
                    if cat_filter:
                        db_products = db.query(models.Product).join(models.Category)\
                            .filter(models.Category.name.ilike(f"%{cat_filter}%")).limit(3).all()
                    else:
                        db_products = db.query(models.Product).order_by(models.Product.rating.desc()).limit(3).all()
                        category_name = "Best Rated Items"
                    
                    if db_products:
                        reply = f"Based on your styling request, here are our top recommendations in <strong>{category_name}</strong>:<br>"
                        for p in db_products:
                            orig_price_str = f" <del class='text-muted'>${p.original_price:.2f}</del>" if p.original_price else ""
                            discount_badge = " <span class='badge bg-danger'>Sale</span>" if p.original_price and p.original_price > p.price else ""
                            reply += f"• <strong><a href='product-details.html?id={p.id}' class='text-info'>{p.name}</a></strong> - ${p.price:.2f}{orig_price_str}{discount_badge} ({p.rating} ★)<br>"
                        reply += "<br>We recommend layering utility jackets with high-mobility ripstop cargos for the ultimate techwear aesthetic. Would you like styling details for any of these fits?"
                    else:
                        reply = "We currently don't have matched products, but you can browse all items in our Shop catalog. What specific size or color are you looking for?"
                elif any(re.search(rf"\b{kw}\b", msg_lower) for kw in ["size", "sizes", "sizing", "fit", "fits", "measurement", "measurements", "guide"]):
                    reply = "Aura garments are engineered for utility streetwear layering. Jackets generally feature a modern, slightly oversized fit, while cargo pants run true-to-size with adjustable drawcords. We recommend checking the sizing charts on each individual product page. What size do you normally wear?"
                elif any(re.search(rf"\b{kw}\b", msg_lower) for kw in ["shipping", "delivery", "cost", "costs", "ship", "ships", "deliver", "delivers", "arrive", "arrives"]):
                    reply = "We offer free shipping on all orders over $100! Standard domestic delivery typically takes 3-5 business days. You can track your shipment node directly from your user dashboard. Do you need shipping details for a specific order?"
                elif any(re.search(rf"\b{kw}\b", msg_lower) for kw in ["return", "returns", "refund", "refunds", "exchange", "exchanges", "policy"]):
                    reply = "We offer a 30-day return policy on all unworn garments in original condition. Return shipping coordinates and labels can be requested from your profile page, and refunds are processed back to your original payment node within 5 business days. Do you need help returning a purchase?"
                elif any(re.search(rf"\b{kw}\b", msg_lower) for kw in ["cart", "checkout", "purchase", "buy", "order", "add"]):
                    reply = "To purchase items or manage your cart, simply click on any product link (such as the <a href='product-details.html?id=1' class='text-info'>Luna Windbreaker Jacket</a>), select your preferred size and color on the details page, and click the <strong>Add to Cart</strong> button. Once ready, you can click on the shopping bag icon in the navbar to proceed to checkout. Can I recommend some coordinates to add?"
                elif any(re.search(rf"\b{kw}\b", msg_lower) for kw in ["contact", "email", "phone", "support", "help", "address", "membership", "loyalty"]):
                    reply = "You can contact the Aura design team directly at <strong>support@aurastreetwear.com</strong> or call us at <strong>+1 (555) AURA-FIT</strong>. As a Priority Styling member, your registered phone number connects you directly to our personal fashion consultants. How can I help you regarding support today?"
                elif any(keyword in msg_lower for keyword in ["what products", "list products", "show products", "all products", "available products", "what do you sell"]):
                    products = db.query(models.Product).limit(5).all()
                    if not products:
                        reply = "We currently do not have any catalog listings registered. Please check back later!"
                    else:
                        reply = "Here are some of our premium items:<br>"
                        for p in products:
                            reply += f"• <strong><a href='product-details.html?id={p.id}' class='text-info'>{p.name}</a></strong> - ${p.price:.2f} ({p.stock} in stock)<br>"
                        reply += "<br>You can ask 'details about [Product Name]' to learn more specifications! What kind of streetwear style are you looking for?"
                elif any(kw in msg_lower for kw in ["details about", "tell me about", "info on", "show me", "look for"]):
                    prod_name = None
                    for kw in ["details about", "tell me about", "info on", "show me", "look for"]:
                        if kw in msg_lower:
                            parts = msg_lower.split(kw, 1)
                            if len(parts) > 1:
                                prod_name = parts[1].strip()
                                break
                    if prod_name:
                        product = db.query(models.Product).filter(models.Product.name.ilike(f"%{prod_name}%")).first()
                        if product:
                            sizes_str = f"<br>• <strong>Available Sizes</strong>: {product.sizes}" if product.sizes else ""
                            colors_str = f"<br>• <strong>Available Colors</strong>: {product.colors}" if product.colors else ""
                            reply = f"Here is the specification card for <strong>{product.name}</strong>:<br>" \
                                    f"• <strong>Category</strong>: {product.category.name if product.category else 'Apparel'}<br>" \
                                    f"• <strong>Price</strong>: ${product.price:.2f} " \
                                    f"{f'(Original: <del>${product.original_price:.2f}</del>)' if product.original_price else ''}<br>" \
                                    f"• <strong>Rating</strong>: {product.rating} ★{sizes_str}{colors_str}<br>" \
                                    f"• <strong>Inventory Stock</strong>: {product.stock} units remaining<br>" \
                                    f"• <strong>Description</strong>: {product.description}<br>" \
                                    f"<br><a href='product-details.html?id={product.id}' class='btn btn-sm btn-info text-dark rounded-pill mt-2 fw-bold px-3'>View Coordinates Page</a>" \
                                    f"<br><br>Would you like to know about matching items to style this product?"
                        else:
                            reply = f"I couldn't find any product matching '<strong>{prod_name}</strong>' in our inventory. Are there other garments or fits you want to explore?"
                    else:
                        reply = "What product would you like details for?"
                else:
                    # Match query against database FAQ questions/keywords
                    matched_faq = None
                    for faq in faqs_db:
                        faq_q_lower = faq.question.lower()
                        clean_faq_q = re.sub(r'[^\w\s]', '', faq_q_lower).strip()
                        clean_user_msg = re.sub(r'[^\w\s]', '', msg_lower).strip()
                        
                        if clean_faq_q in clean_user_msg or clean_user_msg in clean_faq_q:
                            if len(clean_user_msg) >= 4 or clean_user_msg == clean_faq_q:
                                matched_faq = faq
                                break
                        
                        if faq.keywords:
                            kw_list = [k.strip().lower() for k in faq.keywords.split(",") if len(k.strip()) >= 3]
                            for kw in kw_list:
                                if re.search(rf"\b{re.escape(kw)}\b", msg_lower):
                                    matched_faq = faq
                                    break
                            if matched_faq:
                                break
                    
                    if matched_faq:
                        reply = matched_faq.answer + "<br><br>Does this help with your question? Let me know if you need sizing or styling styling coordination!"
                    else:
                        # Strip punctuation for cleaner NLP database search
                        clean_query = re.sub(r'[^\w\s]', ' ', msg_lower).strip()
                        clean_query = re.sub(r'\s+', ' ', clean_query)
                        
                        # Generate normalized words list without punctuation
                        words = [w.strip() for w in re.split(r'[^\w]', msg_lower) if len(w.strip()) > 2]
                        product = None
                        if clean_query:
                            product = db.query(models.Product).filter(models.Product.name.ilike(f"%{clean_query}%")).first()
                        if not product and words:
                            for word in words:
                                if word in ["the", "for", "with", "and", "you", "that", "this", "some", "show", "find"]:
                                    continue
                                product = db.query(models.Product).filter(models.Product.name.ilike(f"%{word}%")).first()
                                if product:
                                    break
                        if product:
                            sizes_str = f"<br>• <strong>Available Sizes</strong>: {product.sizes}" if product.sizes else ""
                            colors_str = f"<br>• <strong>Available Colors</strong>: {product.colors}" if product.colors else ""
                            reply = f"I found a matching product! Here is the details card for <strong>{product.name}</strong>:<br>" \
                                    f"• <strong>Category</strong>: {product.category.name if product.category else 'Apparel'}<br>" \
                                    f"• <strong>Price</strong>: ${product.price:.2f} " \
                                    f"{f'(Original: <del>${product.original_price:.2f}</del>)' if product.original_price else ''}<br>" \
                                    f"• <strong>Rating</strong>: {product.rating} ★{sizes_str}{colors_str}<br>" \
                                    f"• <strong>Inventory Stock</strong>: {product.stock} units remaining<br>" \
                                    f"• <strong>Description</strong>: {product.description}<br>" \
                                    f"<br><a href='product-details.html?id={product.id}' class='btn btn-sm btn-info text-dark rounded-pill mt-2 fw-bold px-3'>View Coordinates Page</a>" \
                                    f"<br><br>Would you like to see coordinates styling recommendations for this product?"
                        else:
                            category = db.query(models.Category).filter(models.Category.name.ilike(f"%{clean_query}%")).first()
                            if not category and words:
                                for word in words:
                                    if word in ["the", "for", "with", "and", "you", "that", "this", "some", "show", "find"]:
                                        continue
                                    category = db.query(models.Category).filter(models.Category.name.ilike(f"%{word}%")).first()
                                    if category:
                                        break
                            if category:
                                cat_products = db.query(models.Product).filter(models.Product.category_id == category.id).limit(3).all()
                                if cat_products:
                                    reply = f"I found some products in the <strong>{category.name}</strong> category:<br>"
                                    for p in cat_products:
                                        reply += f"• <strong><a href='product-details.html?id={p.id}' class='text-info'>{p.name}</a></strong> - ${p.price:.2f}<br>"
                                    reply += f"<br><a href='products.html?category_id={category.id}' class='btn btn-sm btn-info text-dark rounded-pill mt-2 fw-bold px-3'>Browse {category.name} Category</a>" \
                                             f"<br><br>Which style in this category fits your current wardrobe?"
                                else:
                                    reply = f"I found the <strong>{category.name}</strong> category, but we don't have any products in it right now. What other kinds of techwear coordinates are you planning?"
                            else:
                                reply = "I'm sorry, I didn't quite catch that. You can ask me to <strong>recommend products</strong>, list our active <strong>categories</strong>, " \
                                        "or ask about <strong>shipping</strong>, <strong>returns</strong>, <strong>sizing</strong>, <strong>contacting support</strong>, or <strong>cart checkout</strong>! What styling coordinates can I help you find?"

    # 5. Save Bot message to ChatHistory database
    bot_chat = models.ChatHistory(
        session_id=session_id,
        user_id=user_id,
        sender="bot",
        message=reply
    )
    db.add(bot_chat)
    db.commit()

    # 6. Log conversation inquiry to HubSpot CRM
    if reply and lead and lead.email:
        try:
            note_body = f"<strong>Chatbot Inquiry:</strong><br>User: {msg}<br>Aura: {reply}"
            log_activity_to_hubspot(lead.email, note_body)
        except Exception as hs_err:
            print(f"Failed to log chatbot inquiry to HubSpot: {hs_err}")
    
    return {"reply": reply}

