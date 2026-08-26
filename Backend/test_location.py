from location import get_coordinates


location = get_coordinates("Bengaluru")

print("\nLocation found:")
print("Name:", location["name"])
print("Latitude:", location["latitude"])
print("Longitude:", location["longitude"])

print("\nGeometry:")
print("Type:", location["geometry"]["type"])

print("\nBoundary successfully identified!")