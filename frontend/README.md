# Flathunter Frontend

A web-based frontend for viewing apartment listings from the Flathunter crawler.

## Features

- **Interactive Map**: View all apartments with coordinates on an OpenStreetMap-based map
- **List View**: Browse all apartments in a detailed card layout
- **High Rent Indicators**: Apartments with rent > 13 EUR/m² are highlighted in red
- **Filtering**: Filter apartments by high rent or presence of coordinates
- **Responsive Design**: Works on desktop and mobile devices

## Technology Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla JavaScript with Leaflet.js for maps
- **Database**: MongoDB
- **Deployment**: Docker

## Running with Docker Compose

The frontend is included in the main docker-compose.yaml file. To start all services:

```bash
# From the project root directory
docker-compose up -d
```

This will start:
- MongoDB on port 27017
- Flathunter crawler (app service)
- Frontend on port 8000

Access the frontend at: http://localhost:8000

## Running Locally (Development)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set MongoDB connection (optional, defaults to mongodb://mongodb:27017/):
```bash
export MONGO_URI="mongodb://localhost:27017/"
```

3. Run the application:
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

4. Open browser to: http://localhost:8000

## API Endpoints

- `GET /` - Serves the main HTML page
- `GET /api/apartments` - Returns JSON with all apartment listings
- `GET /static/*` - Serves static files (CSS, JS)

## High Rent Threshold

Apartments are marked as "high rent" if their price per square meter exceeds **13 EUR/m²**.

This threshold is defined in:
- Backend: `frontend/app.py` (line ~124)
- Frontend: `frontend/static/app.js` (map marker colors and badges)

## Data Structure

The frontend expects apartments with the following fields from MongoDB:
- `id`: Unique identifier
- `title`: Apartment title
- `url`: Link to original listing
- `address`: Street address
- `price`: Rent price (string)
- `size`: Size in m² (string)
- `rooms`: Number of rooms
- `latitude`, `longitude`: GPS coordinates
- `image`: Image URL (optional)
- `crawler`: Source crawler name

## Customization

### Change High Rent Threshold

Edit `frontend/app.py` line ~124:
```python
apt['high_rent'] = apt['price_per_sqm'] > 13  # Change 13 to your threshold
```

### Map Center/Zoom

Edit `frontend/static/app.js` line ~12:
```javascript
map = L.map('map').setView([52.520008, 13.404954], 11);  // [lat, lng], zoom
```

## Troubleshooting

### No apartments showing
- Ensure the Flathunter crawler has run and populated MongoDB
- Check MongoDB connection: `docker logs flathunter-frontend`
- Verify MongoDB is running: `docker ps`

### Map not loading
- Check browser console for JavaScript errors
- Verify Leaflet.js CDN is accessible

### Connection errors
- Ensure MongoDB service name is `mongodb` in docker-compose
- Check that services are on the same Docker network

