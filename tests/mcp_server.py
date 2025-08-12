"""
This module starts up a test MCP server to test tool calls originating from the LiveKit LLM plug-in.

Author: Keith Schnable (at Oracle Corporation)
Date: 2025-08-12
"""

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Demo")


@mcp.tool()
async def fetch_weather(location: str) -> str:
    """
    Fetch the weather for the specified location.

    Parameters:
    location (str): The location.

    Returns:
    str: The description of the weather.
    """

    print("MCP fetch_weather() called.    location: " + location)
    return f"The weather in {location} is a perfect sunny 70°F today."


@mcp.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """
    Calculate a person's body-mass index (BMI) for the specified weight in kilograms and height in meters.

    Parameters:
    weight_kg (float): The weight in kilograms.
    height_m (float): The height in meters.

    Returns:
    float: The BMI.
    """

    print("MCP calculate_bmi() called.    weight_kg: " + str(weight_kg) + "    height_m: " + str(height_m))
    return weight_kg / (height_m ** 2)


@mcp.tool()
async def convert_pounds_to_kilograms(pounds: float) -> float:
    """
    Convert pounds to kilograms for the specified number of pounds.

    Parameters:
    pounds (float): Pounds.

    Returns:
    float: Kilograms.
    """

    print("MCP convert_pounds_to_kilograms() called.    pounds: " + str(pounds))
    return pounds * 0.4535924


@mcp.tool()
async def convert_inches_to_meters(inches: float) -> float:
    """
    Convert inches to meters for the specified number of inches.

    Parameters:
    inches (float): Inches.

    Returns:
    float: Meters.
    """

    print("MCP convert_inches_to_meters() called.    inches: " + str(inches))
    return inches * 0.0254


@mcp.tool()
async def convert_feet_to_meters(feet: float) -> float:
    """
    Convert feet to meters for the specified number of feet.

    Parameters:
    feet (float): Feet.

    Returns:
    float: Meters.
    """

    print("MCP convert_feet_to_meters() called.    feet: " + str(feet))
    return feet * 0.3048


if __name__ == "__main__":
    mcp.run(transport="sse")
