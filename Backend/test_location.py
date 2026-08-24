from location import get_coordinates


location = input(
    "Enter a city, state or country: "
)

result = get_coordinates(location)

print("\nLocation found:")
print("Name:", result["name"])
print("Latitude:", result["latitude"])
print("Longitude:", result["longitude"])