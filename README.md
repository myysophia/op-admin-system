# OP Admin System

A comprehensive operation platform for managing app users, reviewing memes, and providing customer support.

## Overview

This system provides a centralized platform for operations team to:
- Review and moderate user-created memes
- Handle customer support conversations in real-time
- Adjust content weights and priorities
- Track all administrative actions with audit logs

## Architecture

```
┌─────────────────┐
│  React Frontend │  ← Ant Design UI
│   (Admin UI)    │
└────────┬────────┘
         │ HTTP/WebSocket
         ↓
┌─────────────────┐
│   FastAPI       │  ← Business Logic
│   Backend       │
└────┬────────┬───┘
     │        │
     ↓        ↓
┌─────────┐ ┌────────┐
│PostgreSQL│ │OpenIM  │  ← Messaging
│ Database │ │ SDK    │
└──────────┘ └────────┘
```

## Tech Stack

### Backend
- **Framework**: FastAPI 0.104+
- **Database**: PostgreSQL 15
- **Cache**: Redis 7
- **ORM**: SQLAlchemy 2.0 (async)
- **Migration**: Alembic
- **WebSocket**: Native FastAPI support
- **Messaging**: OpenIM integration

## Features

### 1. User Management 
- **User List**: Search and filter across multiple fields (UID, username, email, wallet address, etc.)
- **User Details**: View comprehensive user information including:
  - Profile data (username, display name, email, wallet, etc.)
  - Device information
  - Registration details
  - Ban history
- **Ban/Unban Operations**:
  - Account-level or device-level banning
  - Permanent or custom duration bans
  - Optional notifications via OpenIM
  - Detailed reason logging
- **Audit Trail**: Complete history of all ban/unban operations

### 2. Operations 

#### Meme Review 
- Review user-created memes
- Approve or reject with comments
- Automatic status updates (pending → approved/rejected)
- User notifications via OpenIM
- Complete review history

#### Post Weight Management 
- View all posts with current weights
- Create new posts with URL validation
- Adjust post weights to control visibility
- Track weight adjustment history
- Reason logging for each adjustment

### 3. Support 
- **Real-time Chat**: WebSocket-based instant messaging
- **Conversation Management**:
  - Pending: New user messages awaiting response
  - Processing: Currently being handled by an operator
  - Processed: Closed conversations
- **Conversation Locking**: Prevents multiple operators from handling the same conversation
- **Quick Replies**: Pre-defined message templates for common responses
- **Message History**: Complete conversation history
- **Notifications**: Alert operators of new messages

## Quick Start

### Prerequisites
- Docker & Docker Compose (recommended)
- OR: Python 3.11+, PostgreSQL 14, Redis 7

### Option 1: Docker (Recommended)

```bash
# Clone the repository
cd op-admin-system

# Start all services
./start.sh
# Choose option 1 for Docker

# Access the application
# - Backend API: http://localhost:8000
# - API Docs: http://localhost:8000/api/docs
```

### Option 2: Local Development

```bash
# Start the services
./start.sh
# Choose option 2 for local development

# Or manually:

# 1. Start backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your configuration
alembic upgrade head
uvicorn app.main:app --reload

# 2. Start frontend (in another terminal)
cd frontend
npm install
npm start
```

## Project Structure

```
op-admin-system/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/v1/         # API endpoints
│   │   ├── models/         # Database models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Business logic
│   │   ├── utils/          # Utilities
│   │   ├── config.py       # Configuration
│   │   ├── database.py     # DB setup
│   │   └── main.py         # App entry point
│   ├── alembic/            # DB migrations
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── frontend/                # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── pages/          # Page components
│   │   ├── services/       # API services
│   │   ├── hooks/          # Custom hooks
│   │   └── store/          # Redux store
│   ├── package.json
│   └── README.md
├── docker-compose.yml       # Docker orchestration
├── start.sh                 # Quick start script
├── TECHNICAL_DESIGN.md      # Detailed design doc
└── README.md                # This file
```

## API Documentation

Once the backend is running, visit:
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

### Main API Endpoints

#### Users
- `GET /api/v1/users` - List users with search/filter
- `GET /api/v1/users/{uid}` - Get user details
- `PUT /api/v1/users/{uid}` - Update user info
- `POST /api/v1/users/{uid}/ban` - Ban user
- `POST /api/v1/users/{uid}/unban` - Unban user

#### Operations - Meme Review
- `GET /api/v1/operations/memes/review` - List memes for review
- `POST /api/v1/operations/memes/{id}/review` - Approve/reject meme

#### Operations - Posts
- `GET /api/v1/operations/posts` - List posts
- `POST /api/v1/operations/posts` - Create post
- `PUT /api/v1/operations/posts/{id}/weight` - Update weight

#### Support
- `GET /api/v1/support/conversations` - List conversations
- `GET /api/v1/support/conversations/{id}` - Get conversation details
- `POST /api/v1/support/conversations/{id}/assign` - Assign to operator
- `POST /api/v1/support/conversations/{id}/close` - Close conversation
- `POST /api/v1/support/conversations/{id}/messages` - Send message
- `WS /api/v1/support/ws` - WebSocket for real-time chat

## Database Schema

The system uses PostgreSQL with the following main tables:

- **users**: User accounts and profiles
- **user_ban_records**: Ban/unban history
- **device_ban_records**: Device-level bans
- **memes**: User-created memes
- **meme_review_records**: Meme review history
- **posts**: Content posts
- **post_weight_records**: Weight adjustment history
- **support_conversations**: Customer support conversations
- **support_messages**: Chat messages
- **quick_replies**: Quick reply templates
- **operator_audit_logs**: All operator actions


## Configuration

### Backend (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/op_admin

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# OpenIM
OPENIM_API_URL=http://localhost:10002
OPENIM_SECRET=your-openim-secret

# CORS
CORS_ORIGINS=["http://localhost:3000"]
```

### Frontend (.env)

```bash
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000
```

## Development

### Backend Development

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Create migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Start server with auto-reload
uvicorn app.main:app --reload
```

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm start

# Run tests
npm test

# Build for production
npm run build
```

## Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend

# Stop all services
docker-compose down

# Rebuild services
docker-compose up -d --build

# Remove volumes (⚠️ deletes all data)
docker-compose down -v
```

## Security Considerations

- [ ] Implement JWT authentication
- [ ] Add role-based access control (RBAC)
- [ ] Enable HTTPS in production
- [ ] Use strong secrets for JWT and database
- [ ] Implement rate limiting
- [ ] Add CSRF protection
- [ ] Sanitize user inputs
- [ ] Enable SQL injection protection (handled by SQLAlchemy)
- [ ] Set up proper CORS policies
- [ ] Implement audit logging (✓ implemented)

## Production Deployment

1. **Environment Setup**
   - Use production-grade PostgreSQL server
   - Set up Redis cluster for high availability
   - Configure OpenIM server

2. **Security**
   - Generate strong SECRET_KEY and JWT_SECRET_KEY
   - Set up SSL/TLS certificates
   - Configure firewall rules
   - Set proper CORS origins

3. **Performance**
   - Enable database connection pooling
   - Set up Redis caching
   - Configure CDN for frontend assets
   - Enable gzip compression

4. **Monitoring**
   - Set up application monitoring
   - Configure error tracking (e.g., Sentry)
   - Enable performance monitoring
   - Set up database monitoring

5. **Backup**
   - Configure automated database backups
   - Set up backup retention policy
   - Test backup restoration regularly

## Troubleshooting

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# View PostgreSQL logs
docker-compose logs postgres

# Connect to database manually
docker-compose exec postgres psql -U postgres -d op_admin
```

### Redis Connection Issues

```bash
# Check if Redis is running
docker-compose ps redis

# Test Redis connection
docker-compose exec redis redis-cli ping
```

### Backend Issues

```bash
# View backend logs
docker-compose logs -f backend

# Restart backend
docker-compose restart backend

# Access backend shell
docker-compose exec backend /bin/bash
```

## Support

For technical questions and design details, see:
- [backend/README.md](backend/README.md) - Backend documentation

## References


## License

Proprietary
