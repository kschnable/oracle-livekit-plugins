from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Demo")


@mcp.tool()
async def fetch_weather(location: str) -> str:
    print("MCP fetch_weather() called.    location: " + location)
    return f"The weather in {location} is a perfect sunny 70°F today."


@mcp.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> float:
    print("MCP calculate_bmi() called.    weight_kg: " + str(weight_kg) + "    height_m: " + str(height_m))
    return weight_kg / (height_m ** 2)


@mcp.tool()
async def convert_pounds_to_kilograms(pounds: float) -> float:
    print("MCP convert_pounds_to_kilograms() called.    pounds: " + str(pounds))
    return pounds * 0.4535924


@mcp.tool()
async def convert_inches_to_meters(inches: float) -> float:
    print("MCP convert_inches_to_meters() called.    inches: " + str(inches))
    return inches * 0.0254


@mcp.tool()
async def convert_feet_to_meters(feet: float) -> float:
    print("MCP convert_feet_to_meters() called.    feet: " + str(feet))
    return feet * 0.3048


if __name__ == "__main__":
    mcp.run(transport="sse")
