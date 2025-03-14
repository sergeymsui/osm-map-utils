run:
    go run cmd/server/main.go

test:
    go test ./...

build:
    go build -o osm-server ./cmd/server

docker:
    docker build -t osm-map-utils .