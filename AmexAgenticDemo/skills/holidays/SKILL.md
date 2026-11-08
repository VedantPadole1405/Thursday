# Holidays Skill


---
name: holiday-planner
description: Recommend holiday destinations using budget, travel dates, weather forecasts, and traveler preferences.
---

# Holiday Planning Skill

## Objective

Recommend suitable holiday destinations based on:
- User budget
- Travel dates
- Preferred activities
- Destination weather
- Safety and weather alerts

## Instructions

1. Retrieve available holiday packages using the Holidays MCP Server.
2. Filter packages based on the user's budget and duration.
3. Obtain weather forecasts for the requested travel dates.
4. Evaluate whether the forecast affects the planned activities.
5. Rank suitable destinations.
6. Explain the reasons for each recommendation.

## Weather Rules

### Heavy Rain
- Avoid recommending outdoor-focused holidays when heavy rain is forecast.
- Consider indoor activities as alternatives.
- Do not automatically reject destinations because of light rain.

### Thunderstorms
- Warn about lightning and outdoor activity risks.
- Avoid recommending exposed beaches or outdoor adventures during thunderstorms.

### Extreme Heat
- Warn about high temperatures.
- Recommend indoor or early-morning activities when appropriate.

### Clear Weather
- Prefer destinations with favorable weather for the user's activities.

### Missing Forecasts
- Never invent weather information.
- Explain when forecasts are unavailable.
- Do not treat missing forecasts as clear weather.

## Recommendation Output

For every recommended destination, include:
- Destination
- Duration
- Package price
- Weather assessment
- Weather-related risks
- Recommendation reason

## Safety

Never claim that a destination is safe based only on weather.
Never invent forecasts or travel advisories.
Do not book travel or initiate payments without user authorization.

## User Interaction

- Always confirm user preferences and constraints before finalizing recommendations.
- Provide clear explanations for why certain destinations are recommended or not recommended.
- Allow users to modify their preferences and re-evaluate recommendations accordingly.

## Nearby Holidays MCP App

- For nearby holiday requests, prefer any place explicitly named in the chat.
  Call `get_nearby_holidays` with `location` containing just that place, e.g.
  "holidays near mubai" becomes `location: "mubai"` (Mumbai is also accepted).
  The gateway exposes the tool as `holidays_get_nearby_holidays`.
- A named place takes priority over device location and requires no device consent.
  Never substitute device location if the named place is unknown or ambiguous;
  ask for corrected spelling or a country/region instead.
- If no place is named, call without location or coordinates to open the device
  location app. Do not guess coordinates from the user's chat or request history.
- The app asks for explicit consent, then the browser asks for location permission.
  Never infer the user's current coordinates or set `location_consent` for them.
- The radius is in kilometers, defaults to 500, and must be greater than zero and
  at most 20050. Results use the simulated catalog, ordered by distance.
- If location is denied or unavailable, offer a destination-based search instead.
