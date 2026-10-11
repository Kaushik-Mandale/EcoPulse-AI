# 🏙️ CITY_SWAP / EcoPulse AI

> **A Next-Generation Municipal Sanitation Intelligence & Intercity Resource Exchange Platform**  
> *Engineered for Shirpur Municipal Council (Maharashtra) & Scalable Globally*

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev)
[![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![PostgreSQL](https://img.shields.io/badge/Neon_PostgreSQL-16-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://neon.tech)
[![Pytest](https://img.shields.io/badge/Pytest-21_Passed-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

---

## 📖 Table of Contents
1. [Project Overview](#-project-overview)
2. [Key Features](#-key-features)
3. [Architecture & Folder Structure](#-architecture--folder-structure)
4. [Tech Stack & Justifications](#-tech-stack--justifications)
5. [Prerequisites](#-prerequisites)
6. [Developer Quickstart & Setup Guide](#-developer-quickstart--setup-guide)
7. [Environment Variables (`.env`)](#-environment-variables-env)
8. [Run Commands Reference](#-run-commands-reference)
9. [Pre-Seeded Demo Credentials](#-pre-seeded-demo-credentials)
10. [API Documentation & Endpoints](#-api-documentation--endpoints)
11. [WhatsApp Conversational Engine Setup](#-whatsapp-conversational-engine-setup)
12. [Testing & Quality Verification](#-testing--quality-verification)
13. [Deployment Guide (Render Blueprint)](#-deployment-guide-render-blueprint)
14. [Security Best Practices](#-security-best-practices)
15. [Future Scope](#-future-scope)

---

## 📌 Project Overview

**CITY_SWAP / EcoPulse AI** is a dual-core civic and circular economy platform designed to solve urban waste management bottlenecks and facilitate peer-to-peer item exchanges across cities.

Originally conceptualized as an intercity resource exchange network (**City Swap**), the platform has been significantly expanded with **EcoPulse AI**, a smart sanitation and waste management dispatch operating system piloted for the **Shirpur Municipal Council** (*Shirpur-Warwade, Dhule District, Maharashtra*), serving over **90,000 citizens across 27 municipal wards**.

### What It Does:
1. **For Citizens**:
   - Report overflowing garbage bins or uncollected waste via Web portal or directly through **WhatsApp** using photos and GPS pins.
   - Earn **EcoCoins** for verified reports, redeemable for municipal property tax rebates, public library memberships, and free saplings.
   - Track garbage trucks (*Ghanta Gadi*) in real-time on an interactive OpenStreetMap GIS layer.
   - Exchange unused goods, travel gear, and short-term accommodations with residents of other cities.
2. **For Sanitation Drivers**:
   - Access real-time assigned route polylines and optimized collection stops.
   - Mark collection tasks as "In Progress" or "Resolved" with geotagged photo proof.
   - Track fuel consumption and vehicle telematics directly from their mobile portal.
3. **For Municipal Administrators & Ward Officers**:
   - Monitor real-time IoT bin fill sensors, SLA compliance, and fleet dispatch across all 27 wards.
   - Auto-triage incoming citizen complaints using AI vision and assign them to active drivers.
   - Broadcast emergency municipal sanitation advisories to citizens.

---

## 🚀 Key Features

- **🏛️ Multi-Portal Role Architecture**: Dedicated, secure portals for **Citizens**, **Drivers**, and **Municipal Administrators** with role-based JWT authentication.
- **📱 Original WhatsApp Citizen Bot**: Complete conversational reporting flow requiring zero app installation—citizens simply scan a municipal bin QR code, send a picture and GPS pin, and receive automated updates in Marathi or English.
- **🗺️ Real-Time GIS & Driver Telematics**: Live interactive OpenStreetMap powered by Leaflet, displaying live driver GPS coordinates, route polylines, and geotagged waste incident markers.
- **🪙 Municipal Eco-Wallet & Gamification**: Citizen coin ledger incentivizing civic cleanliness with tangible local government rebates.
- **🔄 Intercity Swap Marketplace (`/swaps`)**: Dedicated peer-to-peer listing portal where users can list and exchange items across different cities.
- **⚡ 1-Click Instant Evaluation Sandbox (`/demo`)**: Instant evaluator sandbox allowing developers and reviewers to test Citizen, Driver, and Admin portals with zero typing.
- **🛡️ DPDP Act 2023 Compliant**: Built strictly adhering to the Indian Digital Personal Data Protection Act with masked contact info and 256-bit encryption.

---

## 📁 Architecture & Folder Structure

The project strictly follows an enterprise-grade full-stack architecture separating the client-side presentation layer from the modular backend API service:

```
CITY_SWAP/
├── client/                              # All React 19 Frontend Code (Vite SPA)
│   ├── public/                          # Static assets, sitemap.xml, robots.txt
│   │   ├── api/                         # Static JSON failover endpoints (health, status)
│   │   └── favicon.svg                  # Application branding
│   ├── src/
│   │   ├── assets/                      # SVG icons and stylesheets
│   │   ├── components/                  # Reusable UI & Atomic Components
│   │   │   ├── auth/                    # LoginForm, AuthModal, Portal Logins, ProtectedRoute
│   │   │   ├── ecopulse/                # Navbar, HeroSection, FooterSection, ImpactSection
│   │   │   ├── CreateItemModal.jsx      # Swap item creation dialog
│   │   │   ├── InteractiveMap.jsx       # Leaflet OpenStreetMap live GIS component
│   │   │   ├── ItemCard.jsx             # City Swap listing card
│   │   │   └── ProfileModal.jsx         # User profile and settings modal
│   │   ├── hooks/                       # Custom React hooks (useSwapItems.js)
│   │   ├── pages/                       # 25+ Standalone Full-Page Route Views
│   │   │   ├── AdminDashboardPage.jsx   # Municipal administrative control center
│   │   │   ├── AuthPage.jsx             # Multi-portal login & registration
│   │   │   ├── ContactPage.jsx          # Municipal consultation and council contacts
│   │   │   ├── DashboardPage.jsx        # Citizen dashboard & complaint status
│   │   │   ├── DemoPage.jsx             # 1-Click instant role evaluation sandbox
│   │   │   ├── DriverDashboardPage.jsx  # Sanitation driver route & duty portal
│   │   │   ├── EcoWalletPage.jsx        # Citizen EcoCoin wallet & rebate redemption
│   │   │   ├── ForgotPasswordPage.jsx   # Role-based password recovery
│   │   │   ├── HelpFaqPage.jsx          # Bilingual (English/Marathi) FAQ & knowledgebase
│   │   │   ├── HomePage.jsx             # Civic landing page & pilot overview
│   │   │   ├── InteractiveMapPage.jsx   # Fullscreen live GIS map view
│   │   │   ├── LegalPage.jsx            # DPDP Act 2023 privacy policy & terms
│   │   │   ├── NotFoundPage.jsx         # Custom 404 error page
│   │   │   ├── NotificationsPage.jsx    # Municipal civic announcements feed
│   │   │   ├── OtpVerifyPage.jsx        # 4-digit OTP verification screen
│   │   │   ├── ReportWastePage.jsx      # Standalone public waste incident reporting portal
│   │   │   ├── SignupPage.jsx           # Citizen & Driver self-registration
│   │   │   ├── SwapMarketplacePage.jsx  # Intercity goods exchange marketplace
│   │   │   └── TrackComplaintPage.jsx   # Public 4-step ticket status tracker
│   │   ├── services/                    # API Integration Layer
│   │   │   ├── adminService.js          # Municipal metrics, bins, drivers, broadcasts
│   │   │   ├── api.js                   # Base Axios instance with JWT interceptors
│   │   │   ├── authService.js           # Authentication, OTP, and session storage
│   │   │   ├── complaintService.js      # Waste complaints submission and tracking
│   │   │   └── driverService.js         # Driver task updates, fuel logs, and dispatch
│   │   ├── App.jsx                      # Root router configuration & Agentation wrapper
│   │   ├── index.css                    # Tailwind CSS v4 & custom glassmorphism design tokens
│   │   └── main.jsx                     # Vite DOM mount point
│   ├── index.html                       # HTML5 template entry
│   ├── package.json                     # NPM dependencies & build scripts
│   └── vite.config.js                   # Vite configuration with Tailwind CSS v4 plugin
│
├── server/                              # All FastAPI Backend Code (Python 3.10+)
│   ├── database/                        # Database Connection & Engine
│   │   └── db.py                        # SQLAlchemy engine & session factory (Neon PostgreSQL)
│   ├── models/                          # SQLAlchemy ORM Database Models
│   │   ├── __init__.py                  # Model exports
│   │   ├── admin.py                     # BinSensor, BroadcastNotification, WardMetric models
│   │   ├── complaint.py                 # Citizen Complaint & Photo records
│   │   ├── driver.py                    # DriverDuty, FuelLog, DriverMessage models
│   │   ├── item.py                      # Intercity City Swap item exchange models
│   │   ├── task.py                      # Sanitation task dispatch records
│   │   ├── user.py                      # User accounts, credentials, and roles
│   │   └── whatsapp_session.py          # WhatsApp conversational state machine records
│   ├── routes/                          # Modular FastAPI Endpoint Routers
│   │   ├── admin.py                     # `/api/admin/*` (KPI metrics, drivers, bins, broadcasts)
│   │   ├── auth.py                      # `/api/auth/*` (Login, Signup, OTP, Password Reset)
│   │   ├── complaint.py                 # `/api/complaints/*` (Report waste, track tickets)
│   │   ├── driver.py                    # `/api/driver/*` (Tasks, duty toggle, fuel logging)
│   │   ├── health.py                    # `/api/health`, `/api/notifications`
│   │   ├── item.py                      # `/api/items/*` (City Swap listings & search)
│   │   └── whatsapp.py                  # `/api/whatsapp/*` (Meta Cloud API Webhook)
│   ├── schemas/                         # Pydantic v2 Type & Validation Schemas
│   │   ├── admin.py                     # Metric, Bin, Broadcast DTOs
│   │   ├── auth.py                      # Login, Signup, OTP, Token DTOs
│   │   ├── complaint.py                 # Complaint create/response schemas
│   │   ├── driver.py                    # Duty & Fuel log validation
│   │   ├── item.py                      # Swap item request/response DTOs
│   │   └── task.py                      # Driver task dispatch schemas
│   ├── services/                        # Business Logic Layer (Clean Architecture)
│   │   ├── admin_service.py             # Analytics calculations & fleet aggregation
│   │   ├── auth_service.py              # Password hashing, JWT creation, OTP logic
│   │   ├── complaint_service.py         # AI triage simulator, ticket generator
│   │   ├── driver_service.py            # Task assignment & route telematics
│   │   ├── item_service.py              # Item marketplace persistence
│   │   └── whatsapp_service.py          # Bilingual conversational state machine
│   ├── tests/                           # Automated Backend Pytest Suite
│   │   ├── conftest.py                  # Shared pytest fixtures & FastAPI TestClient
│   │   ├── test_admin_api.py            # Admin telemetry, driver, and bin tests
│   │   ├── test_api.py                  # Auth, OTP, complaints, items, notifications tests
│   │   └── test_whatsapp_api.py         # WhatsApp webhook & conversation tests
│   ├── utils/                           # Shared Utilities & Helpers
│   │   ├── config.py                    # Pydantic BaseSettings loading from `.env`
│   │   └── security.py                  # Bcrypt hashing & JWT token encoding/decoding
│   ├── .env                             # Backend environment variables (git-ignored)
│   └── main.py                          # FastAPI application initialization & lifespan
│
├── myenv/                               # Python Virtual Environment (git-ignored)
├── .gitignore                           # Git exclusion rules (node_modules, myenv, .env)
├── pytest.ini                           # Pytest configuration settings
├── README.md                            # Complete developer documentation
├── render.yaml                          # Render Blueprint infrastructure specification
├── requirements.txt                     # Pinned Python package dependencies
└── WHATSAPP_SETUP_GUIDE.txt             # Production Meta WhatsApp Cloud API instructions
```

---

## 🛠️ Tech Stack & Justifications

### Backend Python Packages (`server/requirements.txt`)
All backend packages **must be installed inside `myenv`** (never globally):

| Package | Purpose & Technical Justification |
| :--- | :--- |
| **`fastapi`** | Modern, asynchronous, high-performance web framework providing auto-generated OpenAPI / Swagger docs and native async routing. |
| **`uvicorn[standard]`** | High-throughput ASGI production server utilizing uvloop and httptools. |
| **`pydantic` (v2)** | High-speed data validation and serialization utilizing Rust core for strict request/response DTO contracts. |
| **`sqlalchemy`** | Enterprise Object-Relational Mapper (ORM) for robust database transactions and schema migrations. |
| **`psycopg2-binary`** | PostgreSQL database adapter for production connectivity to Neon PostgreSQL. |
| **`bcrypt` & `passlib[bcrypt]`** | Industry-standard password hashing algorithm with salt generation protecting user credentials. |
| **`python-jose[cryptography]`** | Cryptographic implementation of JSON Web Tokens (JWT) for stateless user authentication. |
| **`python-multipart`** | Streaming parser for handling file uploads (photo evidence and reports) via HTTP multipart form data. |
| **`python-dotenv`** | Secure runtime loading of environment variables from `.env` files into system environment. |
| **`httpx`** | Asynchronous HTTP client used for automated API testing and outbound webhooks. |
| **`pytest`** | Automated testing framework used to execute our comprehensive 21-test API validation suite. |

### Frontend NPM Packages (`client/package.json`)
Every installed frontend package is documented and justified below:

| Package | Purpose & Technical Justification |
| :--- | :--- |
| **`react` & `react-dom` (v19)** | Declarative component UI library for building reactive, component-based user interfaces. |
| **`vite` (v8)** | Next-generation frontend build tool providing sub-second HMR and optimized production bundling. |
| **`tailwindcss` & `@tailwindcss/vite` (v4)** | Modern utility-first CSS engine delivering low-latency styles and customizable glassmorphism design tokens. |
| **`axios`** | Promise-based HTTP client with global request/response interceptors for JWT token injection and automatic 401 handling. |
| **`react-router-dom` (v7)** | Declarative client-side routing enabling SPA navigation across 25+ standalone page views. |
| **`leaflet` & `react-leaflet`** | Open-source mobile-friendly interactive mapping library for real-time driver GPS tracking and bin markers. |
| **`framer-motion`** | Production-ready motion library for spring animations, portal card sliders, and modal transitions. |
| **`lucide-react`** | High-clarity, lightweight SVG icon system providing modern visual cues across all dashboards. |
| **`react-hook-form`** | Performant, un-opinionated form state management minimizing unnecessary component re-renders. |
| **`zod` & `@hookform/resolvers`** | TypeScript-first schema declaration and runtime validation library linking form inputs to strict validation schemas. |
| **`agentation`** | In-browser visual annotation toolbar enabling developer feedback and MCP server synchronization with AI agents. |
| **`oxlint`** | High-speed JavaScript/JSX static analysis tool ensuring strict code quality and catching undefined JSX symbols. |

---

## 💻 Prerequisites

Ensure you have the following installed on your development machine:
- **Node.js**: `v18.0.0` or higher ([Download Node.js](https://nodejs.org))
- **Python**: `3.10.x` to `3.14.x` ([Download Python](https://python.org))
- **Git**: Installed and configured ([Download Git](https://git-scm.com))

---

## ⚡ Developer Quickstart & Setup Guide

Follow these exact steps to set up the project locally:

### Step 1: Clone the Repository
```bash
git clone https://github.com/bhaveshburad729/CITY_SWAP.git
cd CITY_SWAP
```

### Step 2: Backend Setup (`server/`)
Strictly activate the **`myenv`** virtual environment before installing packages or running the server:

#### On Windows (PowerShell):
```powershell
# 1. Create the virtual environment (if not already present)
python -m venv myenv

# 2. Activate the virtual environment
.\myenv\Scripts\activate

# 3. Install all dependencies from requirements.txt
pip install -r requirements.txt
```

#### On Linux / macOS:
```bash
# 1. Create the virtual environment (if not already present)
python3 -m venv myenv

# 2. Activate the virtual environment
source myenv/bin/activate

# 3. Install all dependencies from requirements.txt
pip install -r requirements.txt
```

> [!NOTE]
> Always verify that your terminal prompt displays `(myenv)` before running backend commands. Never install packages globally.

### Step 3: Frontend Setup (`client/`)
In a separate terminal window:
```bash
cd client

# Install all npm packages
npm install
```

---

## 🔐 Environment Variables (`.env`)

Create or review the `server/.env` configuration file. A template is provided below:

```env
# Application Metadata
PROJECT_NAME="CITY_SWAP / EcoPulse AI API"
VERSION="1.0.0"
ENV="development"
PORT=8000

# Authentication & Security (generate with: openssl rand -hex 32)
SECRET_KEY="generate_a_secure_random_64_character_hex_key_for_production"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Database Connection (Neon PostgreSQL / Local PostgreSQL)
DATABASE_URL="postgresql://your_db_user:your_db_password@ep-your-database-id.region.neon.tech/neondb?sslmode=require"

# WhatsApp Cloud API (Optional - For Live Meta Webhook)
WHATSAPP_PROVIDER="meta"
WHATSAPP_TOKEN="your_meta_system_user_token"
WHATSAPP_PHONE_NUMBER_ID="your_meta_phone_number_id"
WHATSAPP_VERIFY_TOKEN="ecopulse_whatsapp_token_2026"
WHATSAPP_BUSINESS_PHONE="+919876543210"
```

> [!CAUTION]
> **Security Notice**: Never commit `server/.env` to public version control. It is explicitly listed in `.gitignore` to prevent credential exposure.

---

## 🏃 Run Commands Reference

### Start Backend Development Server
```powershell
# Ensure myenv is activated:
.\myenv\Scripts\activate

# Launch Uvicorn with hot reloading:
uvicorn server.main:app --reload --port 8000

# OR run directly via module entry point:
python -m server.main
```
- **Backend API**: `http://127.0.0.1:8000`
- **Swagger Interactive API Docs**: `http://127.0.0.1:8000/docs`
- **ReDoc Alternative Docs**: `http://127.0.0.1:8000/redoc`

### Start Frontend Development Server
```bash
cd client
npm run dev
```
- **Frontend SPA**: `http://localhost:5173`

### Run Backend Automated Tests (Pytest)
```powershell
.\myenv\Scripts\activate
python -m pytest server/tests
```
*(Runs 21 automated test cases against live endpoints with 100% pass rate).*

### Build & Lint Frontend
```bash
cd client

# Run high-speed static linter:
npm run lint

# Compile production build:
npm run build
```

---

## 🔑 Pre-Seeded Demo Credentials

You can test any role immediately using these pre-configured municipal accounts, or simply visit the **`/demo`** sandbox page for **1-click instant login**:

| Role | Identifier / Email | Password | Primary Dashboard |
| :--- | :--- | :--- | :--- |
| **Citizen (नागरिक)** | `priya@cityswap.io` | `Password123!` | [`/citizen`](http://localhost:5173/citizen) |
| **Driver (चालक)** | `EMP-DRIVER-01` | `Password123!` | [`/driver`](http://localhost:5173/driver) |
| **Driver 2 (चालक २)** | `EMP-DRIVER-02` | `Password123!` | [`/driver`](http://localhost:5173/driver) |
| **Municipal Admin (प्रशासक)** | `admin@cityswap.io` | `Password123!` | [`/admin`](http://localhost:5173/admin) |

---

## 📡 API Documentation & Endpoints

FastAPI automatically generates interactive Swagger documentation accessible at **`http://127.0.0.1:8000/docs`**. Below is a summary of all available REST endpoints:

### 1. Authentication & Identity (`/api/auth`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/login` | Authenticate user credentials and return JWT bearer token. |
| `POST` | `/api/auth/signup` | Register new Citizen or Driver account with ward assignment. |
| `POST` | `/api/auth/forgot-password` | Generate password reset recovery token / instructions. |
| `POST` | `/api/auth/send-otp` | Dispatch SMS/WhatsApp 4-digit verification code. |
| `POST` | `/api/auth/verify-otp` | Validate OTP code and return authenticated user session. |

### 2. Complaints & Waste Reporting (`/api/complaints`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/complaints` *(or `/report`)* | Submit citizen waste incident with photo evidence, GPS coordinates, and ward. |
| `GET` | `/api/complaints/track/{tracking_id}` | Fetch public status, assigned driver, and 4-step audit timeline for a ticket. |
| `GET` | `/api/complaints/{complaint_id}` | Fetch comprehensive details for a specific municipal complaint. |

### 3. Municipal Administration (`/api/admin`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/admin/metrics` | Retrieve aggregated municipal KPIs (tonnage, active bins, response SLAs). |
| `GET` | `/api/admin/drivers` | List all municipal collection drivers, active duty states, and locations. |
| `GET` | `/api/admin/bins` | Retrieve real-time IoT bin telemetry, sensor levels, and battery percentages. |
| `POST` | `/api/admin/notifications/broadcast` | Publish civic emergency alert to citizens across targeted wards. |

### 4. Sanitation Driver Duty (`/api/driver`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/driver/tasks` | Fetch assigned waste collection stops and route order for on-duty driver. |
| `PATCH` | `/api/driver/tasks/{task_id}` | Update status of a collection task (`in_progress`, `completed`). |
| `POST` | `/api/driver/fuel-log` | Submit odometer reading, fuel volume (Liters), and cost for vehicle. |

### 5. City Swap Marketplace (`/api/items`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/items` | List active intercity exchange items with category and city filtering. |
| `GET` | `/api/items/{id}` | Retrieve full details and contact options for an item listing. |
| `POST` | `/api/items` | Create new peer-to-peer item swap offering. |

### 6. WhatsApp Cloud API Webhook (`/api/whatsapp`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/whatsapp/webhook` | Meta verification challenge handshake endpoint (`hub.challenge`). |
| `POST` | `/api/whatsapp/webhook` | Inbound message processing engine for citizen conversational bot. |

---

## 📱 WhatsApp Conversational Engine Setup

To connect the platform to Meta's live **WhatsApp Cloud API**:

1. Log into the [Meta for Developers Portal](https://developers.facebook.com/).
2. Create an App of type **Business** and add the **WhatsApp** product.
3. Configure the Webhook under **WhatsApp ➔ Configuration**:
   - **Callback URL**: `https://<your-deployed-domain>/api/whatsapp/webhook`
   - **Verify Token**: `ecopulse_whatsapp_token_2026` *(or your custom token in `.env`)*
4. Under **Webhook Fields**, subscribe to `messages`.
5. Add your **System User Access Token** and **Phone Number ID** to `server/.env`.
6. For detailed troubleshooting, refer to [`WHATSAPP_SETUP_GUIDE.txt`](file:///c:/Users/Hi/Desktop/CITY_SWAP/WHATSAPP_SETUP_GUIDE.txt).

For the optional Twilio provider, set `WHATSAPP_PROVIDER=twilio`, configure
`TWILIO_AUTH_TOKEN`, and set `TWILIO_WEBHOOK_URL` to the exact public HTTPS
callback URL configured in Twilio, including its path and query string if used.
For Render, configure `TWILIO_WEBHOOK_URL` in the backend service environment.
Do not derive it from forwarded request headers; requests fail closed if the URL
is missing or invalid. Use a value such as
`https://<your-public-domain>/api/whatsapp/twilio-webhook` only after confirming
that it exactly matches the callback URL configured in Twilio. The repository's
`.env.example` contains only a placeholder.

---

## 🧪 Testing & Quality Verification

This codebase includes full test coverage for core business logic, authentication flows, and API contracts.

### Running Pytest
```powershell
.\myenv\Scripts\activate
python -m pytest server/tests -v
```

### Verified Test Results:
```text
server/tests/test_admin_api.py::test_admin_metrics PASSED
server/tests/test_admin_api.py::test_admin_drivers_list PASSED
server/tests/test_admin_api.py::test_admin_bins_list PASSED
server/tests/test_admin_api.py::test_admin_broadcast_notification PASSED
server/tests/test_admin_api.py::test_admin_analytics_summary PASSED
server/tests/test_api.py::test_health_check PASSED
server/tests/test_api.py::test_get_items_empty_or_seeded PASSED
server/tests/test_api.py::test_create_and_fetch_item PASSED
server/tests/test_api.py::test_auth_flow PASSED
server/tests/test_api.py::test_create_complaint PASSED
server/tests/test_api.py::test_track_complaint PASSED
server/tests/test_api.py::test_forgot_password PASSED
server/tests/test_api.py::test_otp_flow PASSED
server/tests/test_api.py::test_public_notifications PASSED
server/tests/test_whatsapp_api.py::test_webhook_verification PASSED
server/tests/test_whatsapp_api.py::test_webhook_unauthorized PASSED
server/tests/test_whatsapp_api.py::test_incoming_text_message PASSED
server/tests/test_whatsapp_api.py::test_menu_command PASSED
server/tests/test_whatsapp_api.py::test_location_handling PASSED
server/tests/test_whatsapp_api.py::test_photo_handling PASSED
server/tests/test_whatsapp_api.py::test_language_switch PASSED

================== 21 passed, 1 warning in 121.09s ==================
```

---

## 🌐 Deployment Guide (Render Blueprint)

The repository includes a production-ready **Render Blueprint** ([`render.yaml`](file:///c:/Users/Hi/Desktop/CITY_SWAP/render.yaml)) configured for high availability:

1. **Push your code to GitHub / GitLab**.
2. Go to your [Render Dashboard](https://dashboard.render.com/) and click **New + ➔ Blueprint**.
3. Connect your repository. Render automatically provisions:
   - **`city-swap-backend`**: FastAPI web service running with `uvicorn server.main:app --host 0.0.0.0 --port 10000`.
   - **`city-swap-frontend`**: React Static Site with automatic SPA fallback to `/index.html` and `/api/*` reverse-proxy routing.
4. Set the `DATABASE_URL` and `SECRET_KEY` environment variables in the Render dashboard and deploy!

---

## 🛡️ Security Best Practices

- **Zero Hardcoded Secrets**: All tokens, database URIs, and credentials reside in `.env` and are excluded from git history.
- **Argon2 / Bcrypt Password Hashing**: Passwords are never stored in plaintext and use strong salt hashing via Passlib.
- **Stateless JWT Authorization**: Bearer tokens are validated on every protected endpoint with standard expiration checks.
- **SQL Injection Prevention**: SQLAlchemy parameterized queries protect all database interactions.
- **CORS Protection**: CORS middleware is explicitly restricted to verified client origins.
- **DPDP Act 2023**: Citizen personal data (mobile numbers, home locations) are masked in public endpoints.

---

## 🔮 Future Scope

- **Edge Computer Vision (YOLOv8)**: Deploy an edge machine learning model to classify municipal waste (dry, wet, hazardous, recyclable) in real-time from citizen WhatsApp uploads.
- **Automated Vehicle Routing Problem (VRP)**: Implement Dijkstra / Genetic TSP algorithms to calculate optimal garbage truck routes dynamically based on live IoT bin fill levels.
- **Direct Municipal Property Tax Gateway**: Link the EcoCoin wallet directly with the Shirpur Municipal Council property tax API to automatically deduct verified EcoCoin credits from household tax bills.

---

## 👨‍💻 Author & Acknowledgements

- **Developer**: Bhavesh Burad ([GitHub](https://github.com/bhaveshburad729))
- **Pilot Municipality**: Shirpur Municipal Council (*Shirpur-Warwade, Maharashtra, India*)
- **License**: MIT License - Free to use and adapt for academic, municipal, and commercial applications.