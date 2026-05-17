# krashi_mitra
An Agriculture based website ...



# PROJECT RULES — KrashiMitra

## IMPORTANT

This is an EXISTING agriculture AI project.

DO NOT:

* rebuild project from scratch
* restructure folders unnecessarily
* rename APIs
* rewrite unrelated working code
* install unnecessary frameworks
* modify unrelated modules

---

# PROJECT STRUCTURE

backend/
routes/
services/
database/
utils/
data/

frontend/
js/
css/

---

# CODING RULES

* Use FastAPI APIRouter
* Use snake_case naming
* Keep code modular
* Keep functions small
* Keep Hindi as primary language support
* Mobile-first mindset

---

# API RESPONSE FORMAT

Always use:

```json
{
  "success": true,
  "message": "",
  "data": {}
}
```

Error format:

```json
{
  "success": false,
  "message": "Error message",
  "data": {}
}
```

---

# DATABASE RULES

* PostgreSQL is primary DB
* Do not rename tables unnecessarily
* Do not redesign schema without need

---

# ENV VARIABLES

Use ONLY:

```env
DATABASE_URL=
OPENAI_API_KEY=
OPENWEATHER_API_KEY=
JWT_SECRET=
SMTP_EMAIL=
SMTP_PASSWORD=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
RESEND_API_KEY=
RESEND_FROM_EMAIL=
```

---

# DEVELOPMENT RULES

* Work in SMALL chunks
* Return COMPLETE UPDATED FILES
* Mention changed files
* Preserve existing functionality
* Keep project runnable after every update

---

# GOAL

Build a modular, scalable agriculture AI assistant for Indian farmers with Hindi-first support.

# DATABASE SCHEMA — KrashiMitra

# USERS TABLE

## users

id
name
email
hashed_password
is_verified
otp
otp_expiry
preferred_language
created_at

---

# WEATHER DATA TABLE

## weather_data

id
district
state
temperature
humidity
rainfall
wind_speed
weather_condition
updated_at

---

# CHAT HISTORY TABLE

## chat_history

id
user_id
user_message
bot_response
created_at

---

# FUTURE TABLES

mandi_prices
fertilizer
crop_disease_reports

---

# IMPORTANT RULES

DO NOT:

* rename existing columns unnecessarily
* redesign schema completely
* create duplicate user tables

Keep schema simple and scalable.



# API CONTRACTS — KrashiMitra

# AUTH APIs

## Signup

POST /signup

Request:

```json
{
  "name": "Kunal",
  "email": "user@gmail.com",
  "password": "123456"
}
```

Response:

```json
{
  "success": true,
  "message": "OTP sent",
  "data": {}
}
```

---

## Verify OTP

POST /verify-otp

Request:

```json
{
  "email": "user@gmail.com",
  "otp": "123456"
}
```

---

## Login

POST /login

Request:

```json
{
  "email": "user@gmail.com",
  "password": "123456"
}
```

Response:

```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "token": ""
  }
}
```

---

# WEATHER API

GET /weather?district=Meerut

Response:

```json
{
  "success": true,
  "message": "",
  "data": {
    "district": "Meerut",
    "temperature": 32
  }
}
```

---

# CHATBOT API

POST /chat

Request:

```json
{
  "message": "गेहूं में कौन सा खाद डालें?"
}
```

Response:

```json
{
  "success": true,
  "message": "",
  "data": {
    "response": ""
  }
}
```

---

# IMPORTANT RULES

* Do not rename endpoints
* Keep response structure consistent
* Preserve compatibility across modules
