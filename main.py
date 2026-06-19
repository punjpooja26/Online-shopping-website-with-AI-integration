from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import os
import datetime
import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
load_dotenv()

from app.database import Base, engine, SessionLocal
from app import models, auth
from app.routers import (
    auth as r_auth,
    products,
    categories,
    cart,
    wishlist,
    orders,
    reviews,
    admin,
    chatbot,
    analytics
)

# ==========================================================================
# AUTOMATED EMAIL REMINDERS ENGINE & BACKGROUND WORKERS
# ==========================================================================
def send_automated_email(email: str, name: str, subject: str, body_html: str):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_user = os.environ.get("SMTP_USERNAME")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    sender_email = os.environ.get("SENDER_EMAIL", "noreply@aurafashion.com")
    
    # Write to local mock log file (for testing and manual verification)
    log_dir = "C:/Users/HP VICTUS/.gemini/antigravity/scratch/ecommerce"
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "emails_sent.log")
    
    timestamp = datetime.datetime.utcnow().isoformat()
    log_entry = f"[{timestamp}] TO: {name} <{email}>\nSUBJECT: {subject}\nCONTENT:\n{body_html}\n" + "="*50 + "\n"
    try:
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(log_entry)
        print(f"INFO: Mock email logged to {log_file_path}")
    except Exception as log_err:
        print(f"ERROR: Failed to write to mock email log: {log_err}")

    # If real SMTP is configured, send it
    if smtp_host and smtp_port and smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender_email
            msg["To"] = email
            
            part = MIMEText(body_html, "html")
            msg.attach(part)
            
            with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(sender_email, email, msg.as_string())
            print(f"INFO: Real email successfully sent to {email}")
        except Exception as smtp_err:
            print(f"ERROR: Failed to send real SMTP email to {email}: {smtp_err}")
    else:
        print("INFO: SMTP not configured. Fallback to mock log complete.")

def check_and_send_email_reminders():
    print("Background worker thread started for email reminders...")
    while True:
        # Sleep for 60 seconds
        time.sleep(60)
        
        db: Session = SessionLocal()
        try:
            # 1. CHECK INCOMPLETE REGISTRATIONS (leads with email but no phone number)
            incomplete_leads = db.query(models.Lead).filter(
                models.Lead.email.isnot(None),
                models.Lead.email != "",
                (models.Lead.phone.is_(None)) | (models.Lead.phone == "")
            ).all()
            
            for lead in incomplete_leads:
                already_sent = db.query(models.SentEmail).filter(
                    models.SentEmail.email == lead.email,
                    models.SentEmail.reason == "incomplete_registration"
                ).first()
                
                if not already_sent:
                    subject = "Complete Your Styling Profile - Aura Streetwear"
                    body = f"""
                    <html>
                    <body>
                        <h3>Hello {lead.name or "Stylist Visitor"},</h3>
                        <p>Thank you for initiating your priority styling registration with Aura!</p>
                        <p>We noticed that you haven't completed your profile yet. Please share your <strong>Phone Number</strong> in our chatbot to finalize your registration and connect with a dedicated personal stylist.</p>
                        <br>
                        <p>Best regards,</p>
                        <p><strong>Aura Streetwear Team</strong></p>
                    </body>
                    </html>
                    """
                    send_automated_email(lead.email, lead.name or "Visitor", subject, body)
                    
                    sent_record = models.SentEmail(
                        email=lead.email,
                        subject=subject,
                        reason="incomplete_registration"
                    )
                    db.add(sent_record)
                    db.commit()
                    
                    try:
                        from app.routers.chatbot import log_activity_to_hubspot
                        log_activity_to_hubspot(
                            lead.email,
                            f"<strong>System Action:</strong> Sent incomplete registration reminder email: '{subject}'"
                        )
                    except Exception as hs_err:
                        print(f"HubSpot CRM logging error for SentEmail: {hs_err}")
            
            # 2. CHECK ABANDONED CARTS
            time_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            time_cooloff = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
            
            checkout_sessions = db.query(models.VisitorLog.session_id).filter(
                models.VisitorLog.cart_activity == "checkout_complete",
                models.VisitorLog.visited_at >= time_threshold
            ).subquery()
            
            abandoned_logs = db.query(models.VisitorLog).filter(
                models.VisitorLog.cart_activity == "add_to_cart",
                models.VisitorLog.visited_at >= time_threshold,
                models.VisitorLog.visited_at <= time_cooloff,
                ~models.VisitorLog.session_id.in_(checkout_sessions)
            ).all()
            
            processed_sessions = set()
            for log in abandoned_logs:
                if log.session_id in processed_sessions:
                    continue
                processed_sessions.add(log.session_id)
                
                from app.routers.analytics import get_lead_email
                email = get_lead_email(db, log.session_id, log.user_id)
                if not email:
                    continue
                    
                already_sent = db.query(models.SentEmail).filter(
                    models.SentEmail.email == email,
                    models.SentEmail.reason == "abandoned_cart"
                ).first()
                
                if not already_sent:
                    lead_name = "Aura Customer"
                    lead = db.query(models.Lead).filter(models.Lead.email.ilike(email)).first()
                    if lead:
                        lead_name = lead.name
                    elif log.user_id:
                        user = db.query(models.User).filter(models.User.id == log.user_id).first()
                        if user:
                            lead_name = user.name
                            
                    subject = "Complete Your Purchase - Aura Streetwear"
                    body = f"""
                    <html>
                    <body>
                        <h3>Hello {lead_name},</h3>
                        <p>We noticed you left some premium techwear items in your wardrobe registry cart!</p>
                        <p>These items are in high demand and stocks are limited. Complete your purchase now to secure your coordinates and sync them with your physical delivery node.</p>
                        <p><a href="http://127.0.0.1:8000/cart.html" style="background-color: #00f2fe; color: #020617; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Return to Cart Drawer</a></p>
                        <br>
                        <p>Best regards,</p>
                        <p><strong>Aura Streetwear Team</strong></p>
                    </body>
                    </html>
                    """
                    send_automated_email(email, lead_name, subject, body)
                    
                    sent_record = models.SentEmail(
                        email=email,
                        subject=subject,
                        reason="abandoned_cart"
                    )
                    db.add(sent_record)
                    db.commit()
                    
                    try:
                        from app.routers.chatbot import log_activity_to_hubspot
                        log_activity_to_hubspot(
                            email,
                            f"<strong>System Action:</strong> Sent abandoned cart email reminder: '{subject}'"
                        )
                    except Exception as hs_err:
                        print(f"HubSpot CRM logging error for SentEmail: {hs_err}")
                        
        except Exception as worker_err:
            print(f"ERROR: Email background worker run encountered error: {worker_err}")
        finally:
            db.close()


# Create all database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Aura E-Commerce API",
    description="Backend REST endpoints for the full-stack e-commerce marketplace.",
    version="1.0.0"
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(r_auth.router)
app.include_router(products.router)
app.include_router(categories.router)
app.include_router(cart.router)
app.include_router(wishlist.router)
app.include_router(orders.router)
app.include_router(reviews.router)
app.include_router(admin.router)
app.include_router(chatbot.router)
app.include_router(analytics.router)

# ==========================================================================
# MOCK DATABASE SEEDING ON STARTUP
# ==========================================================================
@app.on_event("startup")
def seed_database():
    # Start the automated email reminders background worker thread
    threading.Thread(target=check_and_send_email_reminders, daemon=True).start()
    
    db: Session = SessionLocal()
    try:
        # Check if users already exist
        admin_exists = db.query(models.User).filter(models.User.email == "admin@aura.com").first()
        if not admin_exists:
            # Seed Admin User
            admin_user = models.User(
                name="Aura Admin",
                email="admin@aura.com",
                password_hash=auth.get_password_hash("admin123"),
                is_admin=True
            )
            db.add(admin_user)
            
            # Seed Standard Customer
            regular_user = models.User(
                name="Aura Customer",
                email="user@aura.com",
                password_hash=auth.get_password_hash("user123"),
                is_admin=False
            )
            db.add(regular_user)
            db.commit()

        # Check if categories exist
        category_count = db.query(models.Category).count()
        if category_count == 0:
            # Seed Categories
            men = models.Category(name="Men's Collection", description="Premium jackets, shirts, jeans, and ethnic wear.")
            women = models.Category(name="Women's Collection", description="Elegant tops, kurtis, sarees, and dresses.")
            kids = models.Category(name="Kids Collection", description="Comfortable and stylish clothes for children.")
            shoes = models.Category(name="Shoes Collection", description="Sneakers, running shoes, formal wear, heels, and sandals.")
            acc = models.Category(name="Accessories", description="Luxury watches, bags, wallets, and sunglasses.")
            
            db.add_all([men, women, kids, shoes, acc])
            db.commit()

            # Seed Products with detailed specifications, sizes, colors, and original prices
            p1 = models.Product(
                name="Luna Windbreaker Jacket",
                description="A premium weatherproof trench windbreaker featuring geometric seam structuring, double-lined storm collar, and water-repellent shell canvas.",
                price=189.99,
                original_price=249.99,
                stock=25,
                category_id=men.id,
                image_url="assets/luna_jacket.png",
                gallery_images="assets/luna_jacket.png,https://images.unsplash.com/photo-1551028719-00167b16eac5?w=500",
                sizes="S,M,L,XL",
                colors="Violet,Black,Slate",
                specifications="Fit:Oversized;Material:Gore-Tex;Weatherproofing:Waterproof;Pockets:4 Zippered",
                rating=4.8
            )
            p2 = models.Product(
                name="Retro Cyber Denim Jeans",
                description="High-mobility techwear cargo jeans. Equipped with modular magnetic straps and deep side utility storage.",
                price=129.99,
                original_price=159.99,
                stock=40,
                category_id=men.id,
                image_url="assets/aero_pants.png",
                gallery_images="assets/aero_pants.png,https://images.unsplash.com/photo-1542272604-787c3835535d?w=500",
                sizes="30,32,34,36",
                colors="Indigo,Dark Grey",
                specifications="Fit:Regular Utility;Material:100% Rigid Cotton Denim;Hardware:Magnetic Buckles",
                rating=4.5
            )
            p3 = models.Product(
                name="Classic Oxford Cotton Shirt",
                description="A high-quality 100% organic cotton long-sleeve oxford shirt. Styled in a clean white profile, suitable for smart casual coordinates.",
                price=49.99,
                original_price=69.99,
                stock=35,
                category_id=men.id,
                image_url="https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500",
                gallery_images="https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500",
                sizes="S,M,L,XL",
                colors="White,Light Blue,Black",
                specifications="Fit:Regular;Material:100% Cotton;Sleeve:Long Sleeve",
                rating=4.6
            )
            p4 = models.Product(
                name="Slim-Fit Leather Biker Jacket",
                description="Premium vintage biker jacket in soft black faux leather. Featuring silver-tone asymmetric zip hardware and zippered pockets.",
                price=119.99,
                original_price=159.99,
                stock=15,
                category_id=men.id,
                image_url="https://images.unsplash.com/photo-1551028719-00167b16eac5?w=500",
                gallery_images="https://images.unsplash.com/photo-1551028719-00167b16eac5?w=500",
                sizes="M,L,XL",
                colors="Pitch Black,Dark Brown",
                specifications="Material:Faux Leather;Fit:Slim Fit Biker;Lining:Polyester",
                rating=4.8
            )
            p5 = models.Product(
                name="Premium Summer Linen Blazer",
                description="A lightweight, breathable structured linen blazer in sandy beige. Perfect for casual summer evenings or destination coordinates.",
                price=149.99,
                original_price=199.99,
                stock=12,
                category_id=men.id,
                image_url="https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=500",
                gallery_images="https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=500",
                sizes="S,M,L,XL",
                colors="Beige,Navy Blue",
                specifications="Material:Linen Blend;Fit:Unstructured Slim;Vent:Double Vent",
                rating=4.7
            )
            p6 = models.Product(
                name="Cyber Mesh Fitted Top",
                description="A beautiful breathable knit crop top featuring mesh shoulder panels and geometric digital prints.",
                price=59.99,
                original_price=79.99,
                stock=30,
                category_id=women.id,
                image_url="https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=500",
                gallery_images="https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=500,https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=500",
                sizes="XS,S,M,L",
                colors="Neon Pink,Pitch Black",
                specifications="Fit:Slim Crop;Material:Polyester Blend;Knit Type:Ribbed Mesh",
                rating=4.3
            )
            p7 = models.Product(
                name="Designer Geometric Saree",
                description="A high-quality traditional digital print Georgette saree matching innovation to standard coordinates.",
                price=149.99,
                original_price=199.99,
                stock=15,
                category_id=women.id,
                image_url="https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=500",
                gallery_images="https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=500,https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=500",
                sizes="Free Size",
                colors="Emerald Teal,Gold Highlight",
                specifications="Length:5.5 Meters;Fabric:Premium Georgette;Occasion:Festive Wear",
                rating=4.9
            )
            p8 = models.Product(
                name="Iridescent Violet Trench Coat",
                description="A breathtaking high-performance women's trench coat. Waterproof shell with custom iridescent violet seam highlights.",
                price=199.99,
                original_price=249.99,
                stock=20,
                category_id=women.id,
                image_url="assets/luna_jacket.png",
                gallery_images="assets/luna_jacket.png,https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=500",
                sizes="XS,S,M,L",
                colors="Violet,Onyx",
                specifications="Fit:Oversized;Material:Iridescent Gore-Tex;Weatherproofing:Waterproof",
                rating=4.9
            )
            p9 = models.Product(
                name="Elegant Georgette Anarkali Dress",
                description="A classic flowy traditional Anarkali suit in premium georgette fabric. Embellished with detailed embroidery highlights.",
                price=129.99,
                original_price=179.99,
                stock=15,
                category_id=women.id,
                image_url="https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=500",
                gallery_images="https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=500",
                sizes="S,M,L",
                colors="Midnight Blue,Emerald Green",
                specifications="Length:Ankle Length;Fabric:Premium Georgette;Dupatta:Included",
                rating=4.8
            )
            p10 = models.Product(
                name="Off-Shoulder Satin Gown",
                description="An elegant floor-length evening dress in rich emerald green satin. Features a supportive boned bodice and side leg slit.",
                price=179.99,
                original_price=229.99,
                stock=10,
                category_id=women.id,
                image_url="https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500",
                gallery_images="https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500",
                sizes="XS,S,M,L",
                colors="Emerald Green,Royal Red",
                specifications="Fabric:Satin;Length:Floor Length;Occasion:Formal Gown",
                rating=4.9
            )
            p11 = models.Product(
                name="Casual Pleated Trousers",
                description="Comfortable high-waisted linen trousers featuring front pleat detailing, wide leg cuffs, and functional side slash pockets.",
                price=54.99,
                original_price=69.99,
                stock=24,
                category_id=women.id,
                image_url="https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?w=500",
                gallery_images="https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?w=500",
                sizes="XS,S,M,L",
                colors="Tan,Sand,Olive",
                specifications="Rise:High Waisted;Material:Linen Cotton;Fit:Wide Leg",
                rating=4.5
            )
            p12 = models.Product(
                name="Floral Print Summer Dress",
                description="Breezy summer slip dress styled in organic yellow cotton with detailed floral prints and adjustable shoulder straps.",
                price=44.99,
                original_price=59.99,
                stock=25,
                category_id=women.id,
                image_url="https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=500",
                gallery_images="https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=500",
                sizes="XS,S,M,L,XL",
                colors="Bright Yellow,Soft Rose",
                specifications="Pattern:Floral Print;Material:100% Organic Cotton;Neckline:Sweetheart",
                rating=4.4
            )
            p13 = models.Product(
                name="Kids Neon Tech Sneakers",
                description="Ultra-lightweight youth streetwear shoes featuring secure elastic toggles and reactive light-up soles.",
                price=79.99,
                original_price=99.99,
                stock=18,
                category_id=kids.id,
                image_url="https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?w=500",
                gallery_images="https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?w=500",
                sizes="Kids 10,Kids 11,Kids 12,Kids 1",
                colors="Glow Lime,Electric Blue",
                specifications="Fastener:Elastic Drawstring;Sole:Non-marking Rubber;Insole:Cushioned Memory Foam",
                rating=4.6
            )
            p14 = models.Product(
                name="Kids Cyber Fleece Hoodie",
                description="A super soft cotton-blend fleece hoodie with neon stitching highlights and a comfortable relaxed street fit.",
                price=49.99,
                original_price=69.99,
                stock=25,
                category_id=kids.id,
                image_url="assets/solar_hoodie.png",
                gallery_images="assets/solar_hoodie.png,https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=500",
                sizes="S (6-7),M (8-9),L (10-11)",
                colors="Desert Amber,Acid Yellow",
                specifications="Fabric:80% Organic Cotton, 20% Polyester;Weight:320 GSM;Hood:Unlined Relaxed",
                rating=4.2
            )
            p15 = models.Product(
                name="Kids Cartoon Printed Tee",
                description="Playful graphic t-shirt in super soft organic cotton, featuring a cute digital robot print and flatlock seams for comfort.",
                price=19.99,
                original_price=24.99,
                stock=40,
                category_id=kids.id,
                image_url="https://images.unsplash.com/photo-1519457431-44ccd64a579b?w=500",
                gallery_images="https://images.unsplash.com/photo-1519457431-44ccd64a579b?w=500",
                sizes="3-4Y,5-6Y,7-8Y",
                colors="Acid Lime,Crimson,Midnight",
                specifications="Material:100% Organic Cotton;Sleeve:Short Sleeve;Neck:Crew Neck",
                rating=4.6
            )
            p16 = models.Product(
                name="Aura Knit Running Shoes",
                description="Advanced sports sneakers designed with a glow-in-the-dark woven knit mesh and reactive foam cushioning.",
                price=179.99,
                original_price=219.99,
                stock=35,
                category_id=shoes.id,
                image_url="assets/aura_sneaker.png",
                gallery_images="assets/aura_sneaker.png,https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500",
                sizes="8,9,10,11,12",
                colors="Teal Blue,Grey Glow,Midnight",
                specifications="Style:Running/Athletic;Cushioning:Reactive Foam;Upper:3D Knit Mesh;Weight:220g",
                rating=4.7
            )
            p17 = models.Product(
                name="Retro White Leather Sneakers",
                description="Classic retro style minimal low-top sneakers in clean white calf leather. Extremely comfortable padded collar and ortholite insoles.",
                price=89.99,
                original_price=119.99,
                stock=25,
                category_id=shoes.id,
                image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?w=500",
                gallery_images="https://images.unsplash.com/photo-1549298916-b41d501d3772?w=500",
                sizes="7,8,9,10,11",
                colors="Full White,Off-White/Gum",
                specifications="Material:Calf Leather;Insole:Ortholite;Sole:Vulcanized Rubber",
                rating=4.7
            )
            p18 = models.Product(
                name="Titan Chrono Steel Watch",
                description="A luxury stainless steel chronograph watch. Water-resistant and features an illuminated dashboard and smart stopwatch indicators.",
                price=249.99,
                original_price=299.99,
                stock=12,
                category_id=acc.id,
                image_url="https://images.unsplash.com/photo-1522312346375-d1a52e2b99b3?w=500",
                gallery_images="https://images.unsplash.com/photo-1522312346375-d1a52e2b99b3?w=500,https://images.unsplash.com/photo-1547996160-81dfa63595aa?w=500",
                sizes="42mm Band",
                colors="Gunmetal Grey,Metallic Silver",
                specifications="Movement:Quartz Chronograph;Water Resistance:50 Meters;Glass:Scratch Resistant Sapphire",
                rating=4.8
            )
            p19 = models.Product(
                name="Modular Utility Sling Bag",
                description="A cross-body tactical chest bag equipped with MOLLE webbing and multiple quick-release magnetic dividers.",
                price=89.99,
                original_price=109.99,
                stock=22,
                category_id=acc.id,
                image_url="https://images.unsplash.com/photo-1622560480605-d83c853bc5c3?w=500",
                gallery_images="https://images.unsplash.com/photo-1622560480605-d83c853bc5c3?w=500",
                sizes="One Size",
                colors="Matte Black,Olive Drab",
                specifications="Volume:8 Liters;Material:1000D Cordura Nylon;Hardware:Fidlock Buckles",
                rating=4.4
            )
            p20 = models.Product(
                name="Polarized Aviator Sunglasses",
                description="Classic steel-frame pilot sunglasses equipped with dark green polarized lenses offering 100% UV protection.",
                price=59.99,
                original_price=79.99,
                stock=30,
                category_id=acc.id,
                image_url="https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=500",
                gallery_images="https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=500",
                sizes="One Size",
                colors="Gunmetal Frame,Gold Frame",
                specifications="Lenses:Polarized UV400;Frame:Stainless Steel;Case:Leatherette Included",
                rating=4.8
            )
            p21 = models.Product(
                name="Sleek Leather Bi-Fold Wallet",
                description="Minimalist full-grain leather bi-fold wallet featuring RFID-blocking mesh, 6 card slots, and an integrated cash clip.",
                price=39.99,
                original_price=49.99,
                stock=35,
                category_id=acc.id,
                image_url="https://images.unsplash.com/photo-1627123424574-724758594e93?w=500",
                gallery_images="https://images.unsplash.com/photo-1627123424574-724758594e93?w=500",
                sizes="Standard",
                colors="Tan Leather,Onyx Black",
                specifications="Material:Full-Grain Leather;RFID Protection:Yes;Capacity:6 Cards + Cash",
                rating=4.5
            )
            
            db.add_all([p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21])
            db.commit()

        # Seed FAQs if table is empty
        faq_count = db.query(models.FAQ).count()
        if faq_count == 0:
            faq1 = models.FAQ(
                question="What is your shipping policy?",
                answer="We offer free standard shipping on all coordinates. Standard delivery takes 3-5 business days. We also support secure credit card, PayPal, UPI, and Cash on Delivery (COD) options.",
                keywords="shipping,delivery,cod,payment,how long,time"
            )
            faq2 = models.FAQ(
                question="What is your return and refund policy?",
                answer="Coordinates can be returned within 14 days of delivery. Items must be unworn, unwashed, and in their original packaging with security tags intact to qualify for a full refund.",
                keywords="return,refund,exchange,policy,14 days"
            )
            faq3 = models.FAQ(
                question="Do you have a sizing guide?",
                answer="Yes! For garments: S (Chest 36-38\"), M (Chest 38-40\"), L (Chest 40-42\"), XL (Chest 42-44\"). For footwear: we offer standard US sizes 7 to 12. If you are in between sizes, we recommend sizing up for outerwear and sizing down for knit sneakers.",
                keywords="size,sizing,fit,guide,small,medium,large,measure"
            )
            faq4 = models.FAQ(
                question="Are there any active discount codes or promotions?",
                answer="Use code <strong>AURATECH10</strong> at checkout to get 10% off your first order! We also offer seasonal styling discounts that sync directly to your registered phone number.",
                keywords="discount,promo,coupon,code,sale,offer"
            )
            faq5 = models.FAQ(
                question="How do I style techwear outfits?",
                answer="Aura fashion coordinates are designed for utility layering. We recommend combining our <a href='product-details.html?id=1' class='text-info'>Luna Windbreaker Jacket</a> with <a href='product-details.html?id=3' class='text-info'>High-Mobility Ripstop Cargo Pants</a> and a breathable cotton inner layer. Finish with dynamic accessories like a tactical sling bag.",
                keywords="style,layering,match,wear,outfit,coordinate"
            )
            faq6 = models.FAQ(
                question="What is the Aura Loyalty Membership program?",
                answer="Our Priority Styling membership is free! By registering your name, email, and phone number, you get priority access to new release cycles, exclusive styling discounts, and direct telemetry connection to our design team.",
                keywords="loyalty,member,membership,priority,stylist,register"
            )
            db.add_all([faq1, faq2, faq3, faq4, faq5, faq6])
            db.commit()
            
    finally:
        db.close()

# Mount Frontend static directory serving HTML/CSS/JS client
os.makedirs("frontend", exist_ok=True)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
