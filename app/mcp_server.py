import logging
import sys

from fastmcp import FastMCP

# Configure logging to stderr
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("event_mcp_server")

mcp = FastMCP("Event Coordinator MCP Server")


@mcp.tool()
def get_catering_options(
    cuisine: str, guest_count: int, budget_per_person: float
) -> str:
    """Get catering options, menus, and estimated pricing for a specific cuisine, guest count, and budget.

    Args:
        cuisine: The type of cuisine (e.g. Italian, Mexican, Vegan, BBQ).
        guest_count: Number of guests attending.
        budget_per_person: Budget per guest in USD.
    """
    logger.info(
        f"Retrieving catering options for cuisine: {cuisine}, guests: {guest_count}, budget: {budget_per_person}"
    )

    if budget_per_person < 15:
        return "Budget per person is too low. Minimum standard catering starts at $15/person."

    options = {
        "italian": f"**Luigi's Bistro**\n- Menu: Pasta Station (Penne Marinara, Fettuccine Alfredo), Garlic Bread, House Salad.\n- Price: ${12 * guest_count} (Estimated ${12}/person + service)\n- Suitability: Vegan & Gluten-free options available.",
        "mexican": f"**El Taco Express**\n- Menu: Taco Bar (Beef, Chicken, Vegetarian beans, salsa, guacamole, tortillas).\n- Price: ${10 * guest_count} (Estimated ${10}/person)\n- Suitability: Gluten-free friendly.",
        "vegan": f"**Green Garden Catering**\n- Menu: Buddha Bowls, Quinoa Salad, Falafel Wraps, Hummus platter.\n- Price: ${18 * guest_count} (Estimated ${18}/person)\n- Suitability: 100% Plant-based.",
        "bbq": f"**Smokehouse BBQ**\n- Menu: Pulled pork, Smoked chicken, Mac and cheese, Coleslaw.\n- Price: ${20 * guest_count} (Estimated ${20}/person)\n- Suitability: Hearty portions, contains gluten.",
    }

    selected = options.get(cuisine.lower())
    if not selected:
        # Default fallback
        return f"**Generic Catering Co.**\n- Menu: Standard party platters, finger sandwiches, vegetable crudite.\n- Price: ${15 * guest_count} (Estimated ${15}/person)\n- Suitability: General audience."

    return selected


@mcp.tool()
def get_venue_details(venue_name: str, guest_count: int) -> str:
    """Look up details, capacity, and rental pricing for a venue.

    Args:
        venue_name: Name or type of venue (e.g. Backyard, Community Center, Banquet Hall, Rooftop Lounge).
        guest_count: Number of guests expected.
    """
    logger.info(f"Looking up venue: {venue_name} for guest count: {guest_count}")

    venues = {
        "backyard": {
            "capacity": 50,
            "cost": 0,
            "description": "A cozy outdoor setting. Best for casual gatherings. Weather-dependent.",
        },
        "community center": {
            "capacity": 150,
            "cost": 250,
            "description": "Spacious indoor hall. Includes tables, chairs, and kitchen access. Budget-friendly.",
        },
        "banquet hall": {
            "capacity": 300,
            "cost": 1500,
            "description": "Elegant formal hall with built-in sound system, lighting, and stage. Ideal for weddings and galas.",
        },
        "rooftop lounge": {
            "capacity": 80,
            "cost": 2000,
            "description": "High-end lounge with city views, bar service, and ambient seating. Premium experience.",
        },
    }

    normalized_name = venue_name.lower().strip()
    match = None
    for name, details in venues.items():
        if name in normalized_name or normalized_name in name:
            match = (name, details)
            break

    if not match:
        return f"Venue '{venue_name}' not recognized. Try 'Backyard', 'Community Center', 'Banquet Hall', or 'Rooftop Lounge'."

    name, details = match
    if guest_count > int(details["capacity"]):
        return f"⚠️ **Capacity Warning:** Venue '{name}' capacity is {details['capacity']} guests, which is less than the requested {guest_count} guests."

    return f"**Venue:** {name.title()}\n- **Description:** {details['description']}\n- **Capacity:** {details['capacity']} guests\n- **Rental Cost:** ${details['cost']} USD"


@mcp.tool()
def generate_invitation_email(
    event_name: str, date: str, time: str, location: str, rsvp_deadline: str
) -> str:
    """Draft a professional invitation email body for the event.

    Args:
        event_name: The name of the event (e.g. Graduation Party, Summer BBQ).
        date: The date of the event.
        time: The time of the event.
        location: The location of the event.
        rsvp_deadline: The deadline date for RSVP responses.
    """
    logger.info(f"Generating invitation email for: {event_name}")

    email_body = (
        f"Subject: You're Invited to {event_name}!\n\n"
        f"Hi everyone,\n\n"
        f"We are excited to invite you to '{event_name}'!\n\n"
        f"📅 **Date:** {date}\n"
        f"⏰ **Time:** {time}\n"
        f"📍 **Location:** {location}\n\n"
        f"Please let us know if you can make it by replying to this email or clicking our RSVP portal.\n"
        f"🕒 **RSVP Deadline:** {rsvp_deadline}\n\n"
        f"Hope to see you there!\n\n"
        f"Best regards,\n"
        f"Event Coordinator Team"
    )
    return email_body


if __name__ == "__main__":
    mcp.run()
