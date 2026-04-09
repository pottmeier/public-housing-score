# Housing Convenience Score - Streamlit Frontend

A modern, user-friendly Streamlit web application for the Housing Convenience Score API.

## Features

- **🔍 Address Lookup** - Enter any address to get a convenience score
- **📊 Detailed Analysis** - View breakdowns by category (supermarkets, doctors, public transport, parks)
- **🗺️ Interactive Maps** - Visualize locations with Folium maps
- **📥 Export Results** - Download results in CSV or JSON format
- **⚡ Fast & Responsive** - Built with Streamlit for instant interactions
- **🎨 Beautiful UI** - Clean, modern design with color-coded scores

## Installation

### Prerequisites
- Python 3.9+
- pip

### Local Setup

```bash
# Navigate to the streamlit-frontend directory
cd frontend

# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run app.py
```

The app will be available at `http://localhost:8501`

### Configuration

Create a `.streamlit/secrets.toml` file in the streamlit-frontend directory:

```toml
API_BASE_URL = "http://localhost:8000"
```

## Docker Setup

### Build the Docker image

```bash
docker build -t housing-score-streamlit .
```

### Run the container

```bash
docker run -p 8501:8501 \
  -e API_BASE_URL="http://backend:8000" \
  housing-score-streamlit
```

### Docker Compose

The application is integrated into the main docker-compose.yml. To run everything together:

```bash
docker-compose up --build
```

Then access:
- Streamlit Frontend: http://localhost:8501
- React Frontend: http://localhost:3000
- API: http://localhost:8000/docs

## API Integration

The Streamlit frontend communicates with the Housing Convenience Score API:

- **Endpoint**: `POST /api/score`
- **Request**: 
  ```json
  {
    "address": "10 Downing Street, London"
  }
  ```
- **Response**:
  ```json
  {
    "total_score": 75.5,
    "address_display": "10 Downing Street, London",
    "lat": 51.5033,
    "lon": -0.1276,
    "details": [
      {
        "category": "supermarket",
        "score": 85.0,
        "nearest_po_dist": 250.0,
        "count_nearby": 12
      },
      ...
    ]
  }
  ```

## Features Explained

### Score Calculation
- **Overall Score**: Weighted average of all categories (0-100)
- **Category Scores**: Based on proximity to nearest facility
  - Supermarkets: 30% weight, ideal distance 300m
  - Doctors: 20% weight
  - Public Transport: 30% weight
  - Parks: 20% weight

### Color-Coded Results
- 🟢 **Score 70+**: Excellent convenience
- 🟡 **Score 40-70**: Good convenience  
- 🔴 **Score <40**: Limited convenience

### Data Export
- **CSV Format**: Tabular results for spreadsheet analysis
- **JSON Format**: Complete data structure with timestamp

## Project Structure

```
streamlit-frontend/
├── app.py                    # Main Streamlit application
├── requirements.txt          # Python dependencies
├── Dockerfile               # Docker container configuration
├── .streamlit/
│   └── config.toml         # Streamlit configuration
└── README.md               # This file
```

## Dependencies

- **streamlit**: Web framework for data apps
- **requests**: HTTP client for API calls
- **folium**: Interactive map creation
- **streamlit-folium**: Streamlit wrapper for Folium
- **pandas**: Data manipulation and export

## Troubleshooting

### "Cannot connect to API"
- Ensure the backend API is running on the configured URL
- Check `API_BASE_URL` setting in sidebar
- Verify network connectivity between frontend and backend

### "Address not found"
- Try a more specific address format
- Include city/country information
- Use the exact address notation for your region

### Map not displaying
- Clear browser cache
- Check browser console for JavaScript errors
- Ensure Folium is properly installed

## Development

### Environment Variables

When running with Docker, set:
```bash
API_BASE_URL=http://backend:8000  # For inter-container communication
```

When running locally:
```bash
API_BASE_URL=http://localhost:8000
```

### Code Style

The application follows Python best practices:
- Clean separation of concerns
- Modular function design
- Comprehensive error handling
- Type hints where applicable

## Future Enhancements

- [ ] Search history and favorites
- [ ] Comparison tool for multiple addresses
- [ ] Custom weighting preferences
- [ ] Advanced filtering options
- [ ] User authentication and saved searches
- [ ] Mobile-optimized layout
- [ ] Dark mode theme

## License

Part of the Housing Score project
