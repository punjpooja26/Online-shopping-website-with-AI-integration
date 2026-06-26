// ==========================================================================
// Aura Fashion — Global Frontend Client JavaScript Orchestrator
// ==========================================================================

const API_BASE = ""; // Empty string calls relative local paths on same port

// Helper to check authentication
function getToken() {
    return localStorage.getItem("aura_token");
}

function saveToken(token) {
    localStorage.setItem("aura_token", token);
}

function removeToken() {
    localStorage.removeItem("aura_token");
    localStorage.removeItem("aura_user");
}

function getHeaders() {
    const headers = {
        "Content-Type": "application/json"
    };
    const token = getToken();
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
}

// Check if current user details are synced
async function syncUserSession() {
    const token = getToken();
    if (!token) return null;
    
    try {
        const res = await fetch(`${API_BASE}/api/auth/me`, {
            headers: getHeaders()
        });
        if (res.ok) {
            const user = await res.json();
            localStorage.setItem("aura_user", JSON.stringify(user));
            return user;
        } else {
            // Session expired
            removeToken();
            return null;
        }
    } catch (e) {
        console.error("Session sync failed:", e);
        return null;
    }
}

function getStoredUser() {
    const userStr = localStorage.getItem("aura_user");
    return userStr ? JSON.parse(userStr) : null;
}

// Generate or retrieve Session ID for visitor tracking
function getOrCreateSessionId() {
    let sessionId = sessionStorage.getItem("aura_session_id");
    if (!sessionId) {
        sessionId = "session-" + Math.random().toString(36).substring(2, 15) + "-" + Date.now();
        sessionStorage.setItem("aura_session_id", sessionId);
    }
    return sessionId;
}

// Log page view and visitor activity
async function logVisitorActivity(activity = null) {
    const sessionId = getOrCreateSessionId();
    const pageUrl = window.location.pathname;
    
    // Attempt to extract product ID if we are on details page
    const urlParams = new URLSearchParams(window.location.search);
    const productId = urlParams.get("id") ? parseInt(urlParams.get("id")) : null;
    
    try {
        await fetch(`${API_BASE}/api/analytics/log`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify({
                session_id: sessionId,
                page_url: pageUrl,
                product_id: productId,
                cart_activity: activity,
                duration: 0.0
            })
        });
    } catch (e) {
        console.warn("Analytics tracking failure: ", e);
    }
}

// Setup Page Duration Heartbeat (every 10 seconds)
function startAnalyticsHeartbeat() {
    const sessionId = getOrCreateSessionId();
    const pageUrl = window.location.pathname;
    let secondsSpent = 0;
    
    setInterval(async () => {
        secondsSpent += 10;
        try {
            await fetch(`${API_BASE}/api/analytics/heartbeat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: sessionId,
                    page_url: pageUrl,
                    duration: parseFloat(secondsSpent)
                })
            });
        } catch (e) {
            // Fail silently
        }
    }, 10000);
}

// Fetch search suggestions
async function getSearchSuggestions(query) {
    if (!query || query.length < 2) return [];
    try {
        const res = await fetch(`${API_BASE}/api/products/?search=${encodeURIComponent(query)}&limit=5`);
        if (res.ok) {
            const data = await res.json();
            return data.products;
        }
    } catch (e) {
        console.error("Suggestions fetch error:", e);
    }
    return [];
}

// Injects Common Layout Elements (Navbar, Footer, Chatbot)
async function injectCommonLayout() {
    const user = getStoredUser();
    const isLoggedIn = !!user;
    const isAdmin = user ? user.is_admin : false;
    
    // 1. INJECT NAVBAR
    const navbarHTML = `
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark sticky-top shadow-sm py-3 border-bottom border-secondary">
        <div class="container">
            <a class="navbar-brand d-flex align-items-center gap-2" href="index.html">
                <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2.5" class="text-info" style="filter: drop-shadow(0 0 5px rgba(0, 242, 254, 0.5))">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                </svg>
                <span class="fw-bold tracking-wider fs-4 text-white">AURA</span>
            </a>
            <button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#navContent">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navContent">
                <ul class="navbar-nav mx-auto mb-2 mb-lg-0 gap-1 gap-lg-3">
                    <li class="nav-item"><a class="nav-link text-uppercase fw-semibold" style="font-size: 0.88rem;" href="index.html">Home</a></li>
                    <li class="nav-item"><a class="nav-link text-uppercase fw-semibold" style="font-size: 0.88rem;" href="products.html?category_id=1">Men</a></li>
                    <li class="nav-item"><a class="nav-link text-uppercase fw-semibold" style="font-size: 0.88rem;" href="products.html?category_id=2">Women</a></li>
                    <li class="nav-item"><a class="nav-link text-uppercase fw-semibold" style="font-size: 0.88rem;" href="products.html?category_id=3">Kids</a></li>
                    <li class="nav-item"><a class="nav-link text-uppercase fw-semibold" style="font-size: 0.88rem;" href="products.html?category_id=4">Shoes</a></li>
                    <li class="nav-item"><a class="nav-link text-uppercase fw-semibold" style="font-size: 0.88rem;" href="products.html?category_id=5">Accessories</a></li>
                    <li class="nav-item"><a class="nav-link text-uppercase fw-semibold" style="font-size: 0.88rem;" href="contact.html">Contact</a></li>
                </ul>
                
                <div class="d-flex align-items-center gap-3 mt-3 mt-lg-0">
                    <form class="d-flex position-relative" action="products.html" method="GET" style="width: 220px;">
                        <input class="form-control rounded-pill bg-secondary text-white border-0 ps-3 pe-4" type="search" id="navbarSearch" name="search" autocomplete="off" placeholder="Search grid...">
                        <button class="btn btn-link position-absolute end-0 top-50 translate-middle-y text-white-50 p-0 me-2" type="submit">
                            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        </button>
                        <div id="searchSuggestionsBox" class="search-suggestions-dropdown d-none"></div>
                    </form>

                    <a href="wishlist.html" class="text-white position-relative hover-white p-1" title="Wishlist">
                        <svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger border border-dark d-none" id="wishlistBadge" style="font-size: 0.65rem;">0</span>
                    </a>
                    <a href="cart.html" class="text-white position-relative hover-white p-1 me-2" title="Shopping Cart">
                        <svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-info border border-dark text-dark fw-bold d-none" id="cartBadge" style="font-size: 0.65rem;">0</span>
                    </a>
                    
                    ${isLoggedIn ? `
                        <div class="dropdown">
                            <button class="btn btn-outline-info rounded-pill dropdown-toggle d-flex align-items-center gap-2 py-1 px-3" type="button" id="userMenu" data-bs-toggle="dropdown" aria-expanded="false" style="font-size: 0.9rem;">
                                <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                                <span>${user.name.split(' ')[0]}</span>
                            </button>
                            <ul class="dropdown-menu dropdown-menu-end dropdown-menu-dark shadow border-secondary mt-2" aria-labelledby="userMenu">
                                <li class="dropdown-header text-info fw-bold border-bottom border-secondary mb-1 pb-2">ID: AUR-${String(user.id).padStart(4, '0')}</li>
                                <li><a class="dropdown-item" href="profile.html">My Profile</a></li>
                                <li><a class="dropdown-item" href="order-history.html">Order History</a></li>
                                ${isAdmin ? `<li><hr class="dropdown-divider border-secondary"></li><li><a class="dropdown-item text-warning fw-bold" href="admin.html">Admin Dashboard</a></li>` : ""}
                                <li><hr class="dropdown-divider border-secondary"></li>
                                <li><button class="dropdown-item text-danger" id="logoutBtn">Logout</button></li>
                            </ul>
                        </div>
                    ` : `
                        <a href="login.html" class="btn btn-sm btn-outline-light rounded-pill px-3 py-1" style="font-size: 0.85rem;">Login</a>
                        <a href="register.html" class="btn btn-sm btn-info rounded-pill px-3 py-1 text-dark fw-semibold" style="font-size: 0.85rem;">Register</a>
                    `}
                </div>
            </div>
        </div>
    </nav>
    `;
    document.body.insertAdjacentHTML("afterbegin", navbarHTML);
    
    // Attach logout event
    if (isLoggedIn) {
        document.getElementById("logoutBtn").addEventListener("click", () => {
            removeToken();
            window.location.href = "index.html";
        });
    }

    // Attach Search Suggestions logic
    const searchInput = document.getElementById("navbarSearch");
    const suggestionsBox = document.getElementById("searchSuggestionsBox");
    
    if (searchInput && suggestionsBox) {
        searchInput.addEventListener("input", async () => {
            const query = searchInput.value.trim();
            if (query.length < 2) {
                suggestionsBox.classList.add("d-none");
                return;
            }
            const items = await getSearchSuggestions(query);
            if (items.length === 0) {
                suggestionsBox.classList.add("d-none");
                return;
            }
            suggestionsBox.innerHTML = "";
            items.forEach(item => {
                suggestionsBox.innerHTML += `
                <a href="product-details.html?id=${item.id}" class="suggestion-item d-flex align-items-center gap-2 p-2 text-decoration-none">
                    <img src="${item.image_url}" class="rounded bg-dark border border-secondary" style="width: 32px; height: 32px; object-fit: contain;">
                    <div class="flex-grow-1 text-truncate text-white" style="font-size: 0.85rem;">${item.name}</div>
                    <div class="text-info fw-bold" style="font-size: 0.85rem;">$${item.price.toFixed(2)}</div>
                </a>
                `;
            });
            suggestionsBox.classList.remove("d-none");
        });
        
        // Close dropdown when clicking outside
        document.addEventListener("click", (e) => {
            if (!searchInput.contains(e.target) && !suggestionsBox.contains(e.target)) {
                suggestionsBox.classList.add("d-none");
            }
        });
    }
    
    // 2. INJECT FOOTER
    const footerHTML = `
    <footer class="bg-dark text-white pt-5 pb-4 mt-auto border-top border-secondary">
        <div class="container text-center text-md-start">
            <div class="row text-center text-md-start">
                <div class="col-md-3 col-lg-3 col-xl-3 mx-auto mt-3">
                    <h5 class="text-uppercase mb-4 font-weight-bold text-info">AURA FASHION</h5>
                    <p class="text-white-50">High-end, modern streetwear garments mapping innovative utility cybernetics to physical coordinates.</p>
                </div>
                <div class="col-md-2 col-lg-2 col-xl-2 mx-auto mt-3">
                    <h6 class="text-uppercase mb-4 font-weight-bold text-white">Collections</h6>
                    <p><a href="products.html?category_id=1" class="text-white-50 text-decoration-none hover-white">Men's Apparel</a></p>
                    <p><a href="products.html?category_id=2" class="text-white-50 text-decoration-none hover-white">Women's Wear</a></p>
                    <p><a href="products.html?category_id=4" class="text-white-50 text-decoration-none hover-white">Shoes Collection</a></p>
                    <p><a href="products.html?category_id=5" class="text-white-50 text-decoration-none hover-white">Accessories</a></p>
                </div>
                <div class="col-md-3 col-lg-2 col-xl-2 mx-auto mt-3">
                    <h6 class="text-uppercase mb-4 font-weight-bold text-white">Useful links</h6>
                    <p><a href="profile.html" class="text-white-50 text-decoration-none hover-white">Your Account</a></p>
                    <p><a href="order-history.html" class="text-white-50 text-decoration-none hover-white">Track Orders</a></p>
                    <p><a href="cart.html" class="text-white-50 text-decoration-none hover-white">Shopping Cart</a></p>
                    <p><a href="wishlist.html" class="text-white-50 text-decoration-none hover-white">Wishlist</a></p>
                </div>
                <div class="col-md-4 col-lg-3 col-xl-3 mx-auto mt-3">
                    <h6 class="text-uppercase mb-4 font-weight-bold text-white">Contact</h6>
                    <p class="text-white-50"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" class="me-2" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg> New Delhi, DL, India</p>
                    <p class="text-white-50"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" class="me-2" viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg> contact@aurafashion.com</p>
                </div>
            </div>
            <hr class="mb-4 border-secondary">
            <div class="row align-items-center">
                <div class="col-md-7 col-lg-8 text-md-start text-center">
                    <p class="text-white-50">&copy; 2026 AURA Inc. Cybernetics & Design Storefront.</p>
                </div>
                <div class="col-md-5 col-lg-4 text-md-end text-center">
                    <a href="#" class="btn btn-outline-light btn-sm rounded-circle me-2"><svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg></a>
                    <a href="#" class="btn btn-outline-light btn-sm rounded-circle me-2"><svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z"/></svg></a>
                    <a href="#" class="btn btn-outline-light btn-sm rounded-circle me-2"><svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204 0.013-3.583 0.07-4.849 0.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.051.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg></a>
                </div>
            </div>
        </div>
    </footer>
    `;
    document.body.insertAdjacentHTML("beforeend", footerHTML);
    // 3. INJECT CUSTOM CHATBOT INTEGRATION
    const chatbotHTML = `
    <!-- Floating Chatbot Toggle Bubble -->
    <div id="chatBubble" class="chat-bubble shadow" title="Chat with Aura Assistant">
        <svg width="28" height="28" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
    </div>

    <!-- Chat Window Card -->
    <div id="chatWindow" class="card chat-window shadow-lg border-0 d-none">
        <div class="card-header bg-dark text-white d-flex align-items-center justify-content-between py-3">
            <div class="d-flex align-items-center gap-2">
                <div class="spinner-grow spinner-grow-sm text-info" role="status"></div>
                <strong class="text-info tracking-wide" style="font-size: 0.95rem;">AURA ASSISTANT</strong>
            </div>
            <button type="button" class="btn-close btn-close-white" id="closeChatBtn" aria-label="Close"></button>
        </div>
        <div class="card-body chat-body" id="chatMessages">
            <div class="message bot-message" id="chatbotInitialGreeting">
                <span>Hello! I am Aura, your AI digital assistant. I can guide you through our collections and help with orders/shipping FAQs.</span>
            </div>
        </div>
        <div class="card-footer bg-secondary p-2 border-0 d-none" id="chatInputArea">
            <div class="input-group">
                <input type="text" id="chatInput" class="form-control bg-dark text-white border-0" placeholder="Type a message...">
                <button class="btn btn-info text-dark fw-bold px-3" id="sendChatBtn">
                    <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                </button>
            </div>
        </div>
    </div>

    <!-- Floating Voice Agent Widget -->
    <div class="voice-widget-container" id="voiceWidget" style="position: fixed; bottom: 24px; right: 96px; display: flex; align-items: center; gap: 12px; z-index: 1050;">
        <!-- Audio Wave Animation and Status -->
        <div class="voice-status-panel d-none" id="voiceStatus" style="background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 6px 12px; display: flex; align-items: center; gap: 8px; color: #f8fafc; font-size: 0.8rem; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3); backdrop-filter: blur(12px);">
            <span class="status-dot" id="voiceStatusDot" style="width: 8px; height: 8px; border-radius: 50%; background-color: #00f2fe; box-shadow: 0 0 8px #00f2fe;"></span>
            <span class="status-text" id="voiceStatusText" style="font-weight: 500; font-family: 'Outfit', sans-serif;">Initializing...</span>
            <div class="voice-waves d-none" id="voiceWaves" style="display: flex; align-items: center; gap: 2px; height: 12px;">
                <span class="wave-bar bar-1"></span>
                <span class="wave-bar bar-2"></span>
                <span class="wave-bar bar-3"></span>
                <span class="wave-bar bar-4"></span>
            </div>
        </div>
        <button class="voice-widget-btn" id="voiceToggleBtn" title="Talk to Voice Agent" style="width: 60px; height: 60px; border-radius: 50%; background: #0f172a; border: 1.5px solid rgba(255, 255, 255, 0.15); color: #00f2fe; cursor: pointer; display: flex; justify-content: center; align-items: center; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.37); backdrop-filter: blur(12px); transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);">
            <div class="widget-icon-wrapper d-flex align-items-center justify-content-center" id="voiceIconWrapper">
                <!-- Mic Icon -->
                <svg class="icon-mic" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
                <!-- Phone Hangup Icon -->
                <svg class="icon-hangup d-none" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 2.59 3.4z"/></svg>
            </div>
        </button>
    </div>
    `;
    document.body.insertAdjacentHTML("beforeend", chatbotHTML);

    const chatBubble = document.getElementById("chatBubble");
    const chatWindow = document.getElementById("chatWindow");
    const closeChatBtn = document.getElementById("closeChatBtn");
    const chatInput = document.getElementById("chatInput");
    const sendChatBtn = document.getElementById("sendChatBtn");
    const chatMessages = document.getElementById("chatMessages");
    const chatInputArea = document.getElementById("chatInputArea");

    let hasContact = false;
    let leadData = null;

    // Check backend lead status
    async function checkLeadStatus() {
        try {
            const res = await fetch(`${API_BASE}/api/chatbot/lead-status?session_id=${getOrCreateSessionId()}`, {
                headers: getHeaders()
            });
            if (res.ok) {
                const data = await res.json();
                hasContact = data.has_contact;
                leadData = data;
                if (hasContact) {
                    chatInputArea.classList.remove("d-none");
                } else {
                    injectLeadForm();
                }
            }
        } catch (e) {
            console.warn("Could not retrieve lead status: ", e);
            injectLeadForm();
        }
    }

    function injectLeadForm() {
        const loggedInUser = getStoredUser();
        const prefilledName = leadData && leadData.name ? leadData.name : (loggedInUser ? loggedInUser.name : "");
        const prefilledEmail = leadData && leadData.email ? leadData.email : (loggedInUser ? loggedInUser.email : "");
        
        const formHTML = `
        <div class="lead-form-container p-3 rounded-4 border border-secondary text-center mt-2" id="leadCaptureForm" style="background: rgba(15, 23, 42, 0.8);">
            <h6 class="text-info fw-bold mb-2">Styling Registration</h6>
            <p class="text-white-50 small mb-3">Submit your coordinates to connect with our design team and unlock the AI fashion assistant.</p>
            <form id="chatbotLeadForm">
                <div class="mb-2">
                    <input type="text" id="leadName" class="form-control form-control-sm bg-dark text-white border-secondary rounded-pill ps-3" placeholder="Full Name" value="${prefilledName}" ${prefilledName ? 'readonly style="background-color: rgba(255,255,255,0.05); color: #888;"' : ''} required>
                </div>
                <div class="mb-2">
                    <input type="email" id="leadEmail" class="form-control form-control-sm bg-dark text-white border-secondary rounded-pill ps-3" placeholder="Email Address" value="${prefilledEmail}" ${prefilledEmail ? 'readonly style="background-color: rgba(255,255,255,0.05); color: #888;"' : ''} required>
                </div>
                <div class="mb-3">
                    <input type="tel" id="leadPhone" class="form-control form-control-sm bg-dark text-white border-secondary rounded-pill ps-3" placeholder="Phone Number" required>
                </div>
                <button type="submit" class="btn btn-info btn-sm w-100 rounded-pill text-dark fw-bold py-2">Begin Chat</button>
            </form>
        </div>
        `;
        chatMessages.insertAdjacentHTML("beforeend", formHTML);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        const leadForm = document.getElementById("chatbotLeadForm");
        leadForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const name = document.getElementById("leadName").value.trim();
            const email = document.getElementById("leadEmail").value.trim();
            const phone = document.getElementById("leadPhone").value.trim();

            const submitBtn = leadForm.querySelector("button[type='submit']");
            submitBtn.disabled = true;
            submitBtn.textContent = "Syncing with CRM...";

            const registerMessage = `My name is ${name}, my email is ${email}, and my phone number is ${phone}`;
            
            try {
                const res = await fetch(`${API_BASE}/api/chatbot/query`, {
                    method: "POST",
                    headers: getHeaders(),
                    body: JSON.stringify({
                        message: registerMessage,
                        session_id: getOrCreateSessionId()
                    })
                });
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById("leadCaptureForm").remove();
                    document.getElementById("chatbotInitialGreeting").remove();
                    
                    hasContact = true;
                    chatInputArea.classList.remove("d-none");
                    
                    appendMessage(registerMessage, "user-message");
                    appendMessage(data.reply, "bot-message");
                    chatInput.focus();
                } else {
                    throw new Error("Failed to register lead");
                }
            } catch (err) {
                console.error(err);
                submitBtn.disabled = false;
                submitBtn.textContent = "Begin Chat";
                alert("Failed to submit details. Please verify inputs and try again.");
            }
        });
    }

    checkLeadStatus();

    chatBubble.addEventListener("click", () => {
        chatWindow.classList.toggle("d-none");
        chatBubble.classList.toggle("d-none");
        if (hasContact) {
            chatInput.focus();
        } else {
            const leadName = document.getElementById("leadName");
            if (leadName && !leadName.readOnly) {
                leadName.focus();
            } else {
                const leadPhone = document.getElementById("leadPhone");
                if (leadPhone) leadPhone.focus();
            }
        }
    });

    closeChatBtn.addEventListener("click", () => {
        chatWindow.classList.add("d-none");
        chatBubble.classList.remove("d-none");
    });

    async function sendChatMessage() {
        const text = chatInput.value.trim();
        if (!text) return;
        
        appendMessage(text, "user-message");
        chatInput.value = "";
        
        const loaderId = appendMessage("Thinking...", "bot-message typing");
        
        try {
            const res = await fetch(`${API_BASE}/api/chatbot/query`, {
                method: "POST",
                headers: getHeaders(),
                body: JSON.stringify({
                    message: text,
                    session_id: getOrCreateSessionId()
                })
            });
            if (res.ok) {
                const data = await res.json();
                document.getElementById(loaderId).remove();
                appendMessage(data.reply, "bot-message");
            } else {
                throw new Error("Chatbot API response failure");
            }
        } catch (err) {
            document.getElementById(loaderId).remove();
            appendMessage("I'm sorry, I'm having trouble connecting to my servers. Please try again.", "bot-message text-danger");
        }
    }

    function appendMessage(html, className) {
        const msgId = "chat-msg-" + Date.now() + Math.random().toString(36).substring(2, 5);
        const bubble = document.createElement("div");
        bubble.className = `message ${className}`;
        bubble.id = msgId;
        bubble.innerHTML = `<span>${html}</span>`;
        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return msgId;
    }

    // Attach chatbot interaction event listeners
    if (sendChatBtn) {
        sendChatBtn.addEventListener("click", sendChatMessage);
    }
    if (chatInput) {
        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                sendChatMessage();
            }
        });
    }

    // ==========================================================================
    // Retell AI Voice Call Widget Logic
    // ==========================================================================
    let retellClient = null;
    let isCallActive = false;

    const voiceToggleBtn = document.getElementById("voiceToggleBtn");
    const voiceStatus = document.getElementById("voiceStatus");
    const voiceStatusText = document.getElementById("voiceStatusText");
    const voiceStatusDot = document.getElementById("voiceStatusDot");
    const voiceWaves = document.getElementById("voiceWaves");

    async function initRetellClient() {
        if (retellClient) return retellClient;
        
        updateVoiceUIState("connecting", "Loading voice agent...");
        
        try {
            const { RetellWebClient } = await import("https://cdn.jsdelivr.net/npm/retell-client-js-sdk@2.0.8/+esm");
            retellClient = new RetellWebClient();
            
            retellClient.on("call_started", () => {
                isCallActive = true;
                updateVoiceUIState("active", "Live Call");
            });

            retellClient.on("call_ended", () => {
                isCallActive = false;
                updateVoiceUIState("idle");
            });

            retellClient.on("agent_start_talking", () => {
                voiceWaves.classList.remove("d-none");
            });

            retellClient.on("agent_stop_talking", () => {
                voiceWaves.classList.add("d-none");
            });

            retellClient.on("error", (error) => {
                console.error("Retell Client Error:", error);
                isCallActive = false;
                updateVoiceUIState("error", "Call Error");
                setTimeout(() => updateVoiceUIState("idle"), 3000);
            });

            return retellClient;
        } catch (err) {
            console.error("Failed to load Retell SDK:", err);
            updateVoiceUIState("error", "SDK Error");
            setTimeout(() => updateVoiceUIState("idle"), 3000);
            return null;
        }
    }

    function updateVoiceUIState(state, text = "") {
        if (state === "idle") {
            voiceStatus.classList.add("d-none");
            voiceWaves.classList.add("d-none");
            voiceToggleBtn.style.background = "#0f172a";
            voiceToggleBtn.style.color = "#00f2fe";
            voiceToggleBtn.style.borderColor = "rgba(255, 255, 255, 0.15)";
            voiceToggleBtn.querySelector(".icon-mic").classList.remove("d-none");
            voiceToggleBtn.querySelector(".icon-hangup").classList.add("d-none");
        } else if (state === "connecting") {
            voiceStatus.classList.remove("d-none");
            voiceStatusText.textContent = text;
            voiceStatusDot.style.backgroundColor = "#ffb703";
            voiceStatusDot.style.boxShadow = "0 0 8px #ffb703";
            voiceWaves.classList.add("d-none");
        } else if (state === "active") {
            voiceStatus.classList.remove("d-none");
            voiceStatusText.textContent = text;
            voiceStatusDot.style.backgroundColor = "#00f2fe";
            voiceStatusDot.style.boxShadow = "0 0 8px #00f2fe";
            voiceToggleBtn.style.background = "linear-gradient(135deg, #dc2626 0%, #991b1b 100%)";
            voiceToggleBtn.style.color = "#ffffff";
            voiceToggleBtn.style.borderColor = "#dc2626";
            voiceToggleBtn.querySelector(".icon-mic").classList.add("d-none");
            voiceToggleBtn.querySelector(".icon-hangup").classList.remove("d-none");
        } else if (state === "error") {
            voiceStatus.classList.remove("d-none");
            voiceStatusText.textContent = text;
            voiceStatusDot.style.backgroundColor = "#ef4444";
            voiceStatusDot.style.boxShadow = "0 0 8px #ef4444";
            voiceWaves.classList.add("d-none");
        }
    }

    let isLocalCallActive = false;
    let localRecognition = null;

    async function toggleVoiceCall() {
        if (isCallActive || isLocalCallActive) {
            if (isCallActive && retellClient) {
                try { retellClient.stopCall(); } catch (e) {}
            }
            if (isLocalCallActive) {
                stopLocalVoiceCall();
            }
            isCallActive = false;
            isLocalCallActive = false;
            updateVoiceUIState("idle");
        } else {
            updateVoiceUIState("connecting", "Initializing...");

            try {
                const res = await fetch(`${API_BASE}/api/voice/session`, {
                    method: "POST",
                    headers: getHeaders()
                });
                if (!res.ok) {
                    throw new Error("Credentials unconfigured");
                }
                const data = await res.json();
                
                const client = await initRetellClient();
                if (!client) throw new Error("Could not initialize SDK");

                updateVoiceUIState("connecting", "Starting WebRTC...");

                await client.startCall({
                    accessToken: data.access_token
                });
            } catch (err) {
                console.warn("Retell AI unconfigured or failed. Falling back to browser voice agent...", err);
                startLocalVoiceCall();
            }
        }
    }

    function startLocalVoiceCall() {
        isLocalCallActive = true;
        updateVoiceUIState("active", "Aura Voice Active");
        
        const greeting = "Hello! I am Aura, your streetwear store voice assistant. How can I help you style your techwear today?";
        speakLocalText(greeting, () => {
            listenLocalUser();
        });
    }

    function stopLocalVoiceCall() {
        isLocalCallActive = false;
        if (typeof window !== "undefined" && window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
        if (localRecognition) {
            try { localRecognition.abort(); } catch (e) {}
            localRecognition = null;
        }
        updateVoiceUIState("idle");
    }

    function speakLocalText(text, onEndCallback) {
        if (typeof window === "undefined" || !window.speechSynthesis) {
            if (onEndCallback) onEndCallback();
            return;
        }
        window.speechSynthesis.cancel();
        
        const cleanText = text.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
        const utterance = new SpeechSynthesisUtterance(cleanText);
        utterance.lang = "en-US";
        
        const voices = window.speechSynthesis.getVoices();
        const preferredVoice = voices.find(v => v.lang.startsWith("en") && (v.name.includes("Google") || v.name.includes("Natural")));
        if (preferredVoice) utterance.voice = preferredVoice;

        utterance.onstart = () => {
            voiceWaves.classList.remove("d-none");
        };

        utterance.onend = () => {
            voiceWaves.classList.add("d-none");
            if (onEndCallback && isLocalCallActive) onEndCallback();
        };

        utterance.onerror = (e) => {
            console.error("Speech Synthesis error:", e);
            voiceWaves.classList.add("d-none");
            if (onEndCallback && isLocalCallActive) onEndCallback();
        };

        window.speechSynthesis.speak(utterance);
    }

    function listenLocalUser() {
        if (!isLocalCallActive) return;

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            updateVoiceUIState("error", "Mic API Unsupported");
            setTimeout(() => stopLocalVoiceCall(), 3000);
            return;
        }

        localRecognition = new SpeechRecognition();
        localRecognition.continuous = false;
        localRecognition.interimResults = false;
        localRecognition.lang = "en-US";

        localRecognition.onstart = () => {
            if (isLocalCallActive) {
                updateVoiceUIState("active", "Listening...");
            }
        };

        localRecognition.onresult = async (event) => {
            const transcript = event.results[0][0].transcript;
            if (isLocalCallActive) {
                updateVoiceUIState("active", "Thinking...");
                await processLocalQuery(transcript);
            }
        };

        localRecognition.onerror = (event) => {
            console.warn("Speech Recognition error:", event.error);
            if (isLocalCallActive && event.error !== "no-speech") {
                setTimeout(() => listenLocalUser(), 1000);
            } else if (isLocalCallActive && event.error === "no-speech") {
                listenLocalUser();
            }
        };

        localRecognition.onend = () => {
            localRecognition = null;
        };

        localRecognition.start();
    }

    async function processLocalQuery(text) {
        try {
            const res = await fetch(`${API_BASE}/api/chatbot/query`, {
                method: "POST",
                headers: getHeaders(),
                body: JSON.stringify({
                    message: text,
                    session_id: getOrCreateSessionId()
                })
            });
            if (res.ok) {
                const data = await res.json();
                
                appendMessage(text, "user-message");
                appendMessage(data.reply, "bot-message");

                if (isLocalCallActive) {
                    updateVoiceUIState("active", "Speaking...");
                    speakLocalText(data.reply, () => {
                        listenLocalUser();
                    });
                }
            } else {
                throw new Error("Chatbot query failed");
            }
        } catch (err) {
            console.error("Local query processing error:", err);
            if (isLocalCallActive) {
                speakLocalText("I had trouble reaching the styling backend. Please try again.", () => {
                    listenLocalUser();
                });
            }
        }
    }

    if (voiceToggleBtn) {
        voiceToggleBtn.addEventListener("click", toggleVoiceCall);
    }

    // 4. SYNC BAG BADGES
    updateBadges();
}

async function updateBadges() {
    const token = getToken();
    if (!token) return;
    
    try {
        // Fetch cart badge
        const cartRes = await fetch(`${API_BASE}/api/cart/`, { headers: getHeaders() });
        if (cartRes.ok) {
            const cartItems = await cartRes.json();
            const totalCount = cartItems.reduce((acc, item) => acc + item.quantity, 0);
            const cartBadge = document.getElementById("cartBadge");
            if (totalCount > 0) {
                cartBadge.textContent = totalCount;
                cartBadge.classList.remove("d-none");
            } else {
                cartBadge.classList.add("d-none");
            }
        }
        
        // Fetch wishlist badge
        const wishRes = await fetch(`${API_BASE}/api/wishlist/`, { headers: getHeaders() });
        if (wishRes.ok) {
            const wishItems = await wishRes.json();
            const wishBadge = document.getElementById("wishlistBadge");
            if (wishItems.length > 0) {
                wishBadge.textContent = wishItems.length;
                wishBadge.classList.remove("d-none");
            } else {
                wishBadge.classList.add("d-none");
            }
        }
    } catch (e) {
        console.error("Badge sync error:", e);
    }
}

// Global UI Initialization
window.addEventListener("DOMContentLoaded", async () => {
    // 1. Sync User Session details
    await syncUserSession();
    // 2. Inject Navbar/Footer/Chatbot
    await injectCommonLayout();
    // 3. Log Initial Page View Analytics
    await logVisitorActivity();
    // 4. Start session duration tracker
    startAnalyticsHeartbeat();
});
