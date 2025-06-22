from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
from sqlmodel import SQLModel, Field, Session, create_engine, select
from pydantic import BaseModel
import uvicorn
import os
import jwt
from datetime import datetime, timedelta

# Create FastAPI app
app = FastAPI(
    title="Tea Shop API",
    description="A friendly API for managing your tea inventory.",
    version="1.0.0"
)

# JWT Security setup
security = HTTPBearer()

# JWT Secret key - in production, this should be a secure environment variable
JWT_SECRET_KEY = "your-secret-key"  # Keep this consistent!
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 30

# Function to generate JWT token
def generate_jwt_token(data: dict):
    """Generate a JWT token with the given data."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    to_encode.update({"exp": expire})
    try:
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        # If encoded_jwt is bytes, convert to string
        if isinstance(encoded_jwt, bytes):
            return encoded_jwt.decode('utf-8')
        return encoded_jwt
    except Exception as e:
        print(f"Error generating token: {e}")
        raise

# Database config
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, echo=True)

# Models
class User(SQLModel, table=True):
    """Represents a user in the database"""
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password: str

class Tea(SQLModel, table=True):
    """Represents a tea in the database"""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(description="The name of the tea")
    origin: str = Field(description="The country or region where the tea is grown")

# Pydantic models for request/response
class TeaCreate(BaseModel):
    """Schema for creating a new tea"""
    name: str
    origin: str

class TokenResponse(BaseModel):
    """Schema for token response"""
    access_token: str
    token_type: str

# Create tables on startup
@app.on_event("startup")
def on_startup() -> None:
    # Create all tables
    SQLModel.metadata.create_all(engine)
    
    # Create a default user if none exists
    with Session(engine) as session:
        user = session.exec(select(User)).first()
        if not user:
            default_user = User(username="admin", password="password")
            session.add(default_user)
            session.commit()
            print("Created default user: admin/password")

# Authentication function with detailed error handling
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        # Print the token for debugging
        print(f"Received token: {credentials.credentials[:20]}...")
        
        # Decode the JWT token
        payload = jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        print(f"Decoded payload: {payload}")
        
        username = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no username found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify the user exists in the database
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == username)).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            print(f"Found user: {user.username}")
            return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        # Catch any other exceptions for debugging
        print(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Token endpoint
@app.post("/token", 
    response_model=TokenResponse,
    summary="Get access token",
    description="Authenticate and receive a JWT token for API access"
)
def login_for_access_token(username: str, password: str):
    """Get a JWT token for API access by providing valid credentials."""
    try:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == username)).first()
            if not user or user.password != password:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect username or password",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Generate token
            token_data = {"sub": user.username}
            access_token = generate_jwt_token(token_data)
            
            # Print token for debugging
            print(f"Generated token: {access_token[:20]}...")
            
            return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        print(f"Error in login_for_access_token: {e}")
        raise

# Routes
@app.get("/", 
    response_model=dict,
    summary="Welcome",
    description="Welcome to the Tea Shop API"
)
def root() -> dict:
    """The home page of our Tea Shop API."""
    return {"message": "WELCOME TO THE TEA SHOP!"}

@app.get("/teas", 
    response_model=List[Tea],
    summary="Get all teas",
    description="Get a list of all teas in the collection"
)
def get_teas() -> List[Tea]:
    """See all the teas in your collection at once."""
    with Session(engine) as session:
        teas = session.exec(select(Tea)).all()
        return teas

@app.post("/teas", 
    response_model=Tea,
    summary="Create a new tea",
    description="Add a new tea to the collection"
)
def create_tea(tea: TeaCreate, current_user: User = Depends(get_current_user)) -> Tea:
    """Add a new tea to your collection. Requires authentication."""
    db_tea = Tea(name=tea.name, origin=tea.origin)
    with Session(engine) as session:
        session.add(db_tea)
        session.commit()
        session.refresh(db_tea)
        return db_tea

@app.put("/teas/{tea_id}", 
    response_model=Tea,
    summary="Update a tea",
    description="Update an existing tea in the collection"
)
def update_tea(tea_id: int, tea_update: TeaCreate, current_user: User = Depends(get_current_user)) -> Tea:
    """Modify information about a tea that's already in your collection. Requires authentication."""
    with Session(engine) as session:
        tea = session.get(Tea, tea_id)
        if tea is None:
            raise HTTPException(status_code=404, detail="Tea not found")
        tea.name = tea_update.name
        tea.origin = tea_update.origin
        session.add(tea)
        session.commit()
        session.refresh(tea)
        return tea

@app.delete("/teas/{tea_id}", 
    response_model=dict,
    summary="Delete a tea",
    description="Remove a tea from the collection"
)
def delete_tea(tea_id: int, current_user: User = Depends(get_current_user)) -> dict:
    """Remove a tea completely from your collection. Requires authentication."""
    with Session(engine) as session:
        tea = session.get(Tea, tea_id)
        if tea is None:
            raise HTTPException(status_code=404, detail="Tea not found")
        session.delete(tea)
        session.commit()
        return {"message": f"Tea with id {tea_id} deleted"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
