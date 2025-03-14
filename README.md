# OSM Map Utils

OSM Map Utils is a project that provides utilities for working with OpenStreetMap (OSM) data. It includes tools for loading and caching OSM tiles, as well as a graphical interface for viewing and interacting with OSM maps.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Requirements

- Python 3.x
- Go 1.24 or later
- Redis server
- PySide6
- Requests library

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/osm-map-utils.git
    cd osm-map-utils
    ```

2. Create envirinment (optional):
   ```sh
   python -m venv venv
   source ./venv/bin/activate
   ```
   
3. Install Python dependencies:
    ```sh
    pip install -r requirements.txt
    ```

4. Install Go dependencies:
    ```sh
    go mod tidy
    ```

## Usage

### Running the OSM Tile Server

1. Start the Redis server:
    ```sh
    redis-server
    ```

2. Run the OSM Tile Server:
    ```sh
    cd cmd/server
    go run main.go
    ```

### Loading and Caching OSM Tiles

1. Run the tile loader:
    ```sh
    cd example/load_cache
    go run main.go
    ```

### Running the OSM Map Viewer

1. Run the OSM Map Viewer:
    ```sh
    cd py-src
    python main.py
    ```

## Project Components

### Tile Loader

The tile loader is implemented in Go and is located in `example/load_cache/main.go`. It loads OSM tiles for a specified bounding box and zoom levels, and caches them in Redis.

### OSM Tile Server

The OSM Tile Server is implemented in Go and is located in `cmd/server/main.go`. It serves OSM tiles from Redis or fetches them from the OSM servers if they are not cached.

### OSM Map Viewer

The OSM Map Viewer is implemented in Python using PySide6 and is located in `py-src/osm_graphics_view.py` and `py-src/mainwindow.py`. It provides a graphical interface for viewing and interacting with OSM maps.

### Search Widget

The search widget is implemented in Python and is located in `py-src/searchwidget.py`. It allows users to search for locations using the Nominatim API and displays suggestions in a list.
