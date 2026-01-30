---
title: CBT Companion API
emoji: 💙
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# CBT Companion API

Backend API for the CBT Companion mental health support app.

## Features

- 🔐 User authentication (register/login)
- 🧠 Cognitive distortion classification (TinyBERT)
- 💬 Therapeutic conversations (Groq LLaMA 3.3)
- 🚨 Crisis detection and flagging
- 📊 User statistics tracking
- 🗄️ Turso database integration

## Environment Variables Required

- `GROQ_API_KEY`: Your Groq API key
- `TURSO_DATABASE_URL`: Your Turso database URL
- `TURSO_AUTH_TOKEN`: Your Turso auth token
- `JWT_SECRET`: Secret key for JWT tokens (optional, has default)

## API Endpoints

### Auth
- `POST /api/register` - Register new user
- `POST /api/login` - Login user
- `GET /api/me` - Get current user info

### Sessions
- `POST /api/session/new` - Start new chat session
- `GET /api/session/status` - Get session status
- `GET /api/sessions` - Get user's past sessions

### Chat
- `POST /api/chat` - Send message and get response

### Exercises
- `GET /api/exercise` - Get exercise for session
- `POST /api/exercise/complete` - Mark exercise done

### Stats
- `GET /api/stats` - Get user statistics
- `GET /api/resources` - Get crisis resources (public)

## Crisis Detection

The API automatically detects crisis-related messages and:
1. Flags them in the database for admin review
2. Returns immediate crisis resources to the user
3. Stores user name/email for follow-up
