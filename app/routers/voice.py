from fastapi import APIRouter, Depends, HTTPException, status, WebSocket
import os
import urllib.request
import urllib.error
import json
import re

from app.database import SessionLocal
from app import models

router = APIRouter(prefix="/api/voice", tags=["Voice Agent"])

@router.post("/session")
def create_voice_session():
    api_key = os.environ.get("RETELL_API_KEY")
    agent_id = os.environ.get("RETELL_AGENT_ID")
    
    if not api_key or not agent_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Retell API credentials are not configured on the server."
        )
        
    url = "https://api.retellai.com/v2/create-web-call"
    req_body = {"agent_id": agent_id}
    data = json.dumps(req_body).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return {"access_token": res_data.get("access_token")}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", "Unknown Retell API error")
        except Exception:
            error_msg = error_body or str(e)
        raise HTTPException(
            status_code=e.code,
            detail=f"Retell AI session error: {error_msg}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect to voice service: {str(e)}"
        )

@router.websocket("/llm-websocket/{call_id}")
async def websocket_endpoint(websocket: WebSocket, call_id: str):
    await websocket.accept()
    
    # Send initial greeting
    welcome_text = "Hello! I am Aura, your streetwear store voice assistant. How can I help you style your techwear today?"
    await websocket.send_text(json.dumps({
        "response": {"content": welcome_text}
    }))
    
    db = SessionLocal()
    try:
        while True:
            data = await websocket.receive_text()
            event = json.loads(data)
            
            if event.get("interaction_type") == "response_required":
                user_msg = ""
                for msg in reversed(event.get("transcript", [])):
                    if msg.get("role") == "user":
                        user_msg = msg.get("content", "")
                        break
                
                if not user_msg:
                    continue
                
                openai_key = os.environ.get("OPENAI_API_KEY")
                gemini_key = os.environ.get("GEMINI_API_KEY")
                
                # Fetch catalog
                products_db = db.query(models.Product).all()
                catalog_text = ""
                for p in products_db:
                    catalog_text += f"- Product ID: {p.id}\n  Name: {p.name}\n  Price: ${p.price:.2f}\n  Stock: {p.stock} units\n  Colors: {p.colors}\n  Sizes: {p.sizes}\n  Description: {p.description}\n\n"
                
                # Fetch FAQs
                faqs_db = db.query(models.FAQ).all()
                faqs_text = ""
                for faq in faqs_db:
                    faqs_text += f"Question: {faq.question}\nAnswer: {faq.answer}\n\n"
                
                system_instruction = (
                    "You are Aura, the expert, helpful, and sleek digital fashion AI voice assistant for Aura Streetwear Store. "
                    "Your tone is modern, friendly, and highly knowledgeable in techwear and streetwear fashion.\n\n"
                    "RULES FOR VOICE ASSISTANT RESPONSES:\n"
                    "1. Responses MUST be extremely short, conversational, and easy to speak aloud. Avoid lists, HTML tags, or markdown stars (e.g. no bold **, no bullet points -). Output pure, natural sentences.\n"
                    "2. Keep replies under 3 sentences (maximum 40 words) unless specifically asked for details. "
                    "Recommend outfit coordinates (matching sets) and explain how items layer together.\n"
                    "3. When referring to products, speak their names clearly. Do NOT output HTML links (e.g. do not output <a href...>, just say the product name).\n"
                    "4. Answer catalog, pricing, sizing, and shipping policy questions using this store information:\n"
                    f"{catalog_text}\n"
                    f"{faqs_text}"
                )
                
                reply = None
                try:
                    from app.routers.chatbot import call_chatgpt_api, call_gemini_api
                    
                    gemini_contents = []
                    for h in event.get("transcript", []):
                        role = "user" if h.get("role") == "user" else "model"
                        gemini_contents.append({
                            "role": role,
                            "parts": [{"text": h.get("content", "")}]
                        })
                    
                    if openai_key:
                        reply = call_chatgpt_api(openai_key, system_instruction, gemini_contents)
                    elif gemini_key:
                        reply = call_gemini_api(gemini_key, system_instruction, gemini_contents)
                except Exception as llm_err:
                    print(f"Error calling LLM in voice websocket: {llm_err}")
                
                if not reply:
                    user_msg_lower = user_msg.lower()
                    if any(kw in user_msg_lower for kw in ["recommend", "suggest", "preference"]):
                        reply = "I recommend checking out our Luna Windbreaker Jacket. It is waterproof, oversized, and styles perfectly with ripstop cargo pants. What size do you wear?"
                    elif any(kw in user_msg_lower for kw in ["shipping", "delivery", "cost"]):
                        reply = "We offer free shipping on all orders over one hundred dollars. Orders are processed within two business days. Is there a specific item you want to ship?"
                    elif any(kw in user_msg_lower for kw in ["return", "exchange", "refund"]):
                        reply = "We offer a thirty day return policy on all garments in original condition. Returns are processed within five business days. Do you need help with a purchase?"
                    else:
                        reply = "I'm sorry, I couldn't reach my brain. But we sell premium techwear and streetwear. You can ask me about our jackets, hoodies, or pants!"
                
                # Strip out HTML elements, links, and formatting
                clean_reply = reply.replace("<br>", " ").replace("<strong>", "").replace("</strong>", "")
                clean_reply = re.sub(r'<a\s+[^>]*>', '', clean_reply)
                clean_reply = clean_reply.replace("</a>", "")
                clean_reply = re.sub(r'\s+', ' ', clean_reply).strip()
                
                await websocket.send_text(json.dumps({
                    "response": {
                        "content": clean_reply
                    }
                }))
                
    except Exception as e:
        print(f"WebSocket voice connection closed for {call_id}: {e}")
    finally:
        db.close()
