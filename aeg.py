import httpx
import requests
from fastmcp import FastMCP
from fastmcp.server.openapi import RouteMap, MCPType

# Function to get JWT token
def get_jwt_token(username="admin", password="password"):
    response = requests.post(
        f"http://localhost:8000/token",
        params={"username": username, "password": password}
    )
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"Error getting token: {response.status_code}")
        print(response.text)
        return None

# Get a JWT token
token = get_jwt_token()
if not token:
    print("Failed to get JWT token. Exiting.")
    exit(1)

print(f"Successfully obtained JWT token: {token[:20]}...")

# Define which routes should be exposed as tools in the MCP
custom_route_mappings = [ 
    RouteMap(
        methods=["GET", "POST", "PUT", "DELETE"], 
        pattern=r"^/teas$", 
        mcp_type=MCPType.TOOL,
    ),
]

# Sync client to fetch OpenAPI spec
with httpx.Client(base_url="http://localhost:8000") as client:
    response = client.get("/openapi.json")
    openapi_spec = response.json()

    # Create MCP from OpenAPI spec with JWT authentication
    mcp = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=httpx.AsyncClient(
            base_url="http://localhost:8000",
            headers={"Authorization": f"Bearer {token}"}
        ),
        name="Tea Shop API MCP",
        route_maps=custom_route_mappings,
    )

    if __name__ == "__main__":
        # Start the MCP server with SSE transport
        mcp.run(transport="sse", host="localhost", port=8080)
