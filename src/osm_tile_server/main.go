package main

import (
	"context"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-resty/resty/v2"
	"github.com/redis/go-redis/v9"
)

var ctx = context.Background()

func main() {
	rdb := redis.NewClient(&redis.Options{
		Addr: os.Getenv("REDIS_SERVER"),
		DB:   0,
	})

	r := chi.NewRouter()
	r.Use(middleware.Logger)

	r.Get("/{z}/{x}/{y}.png", func(w http.ResponseWriter, r *http.Request) {

		z := chi.URLParam(r, "z")
		x := chi.URLParam(r, "x")
		y := chi.URLParam(r, "y")

		tileName := fmt.Sprintf("tile_%s_%s_%s", x, y, z)
		tile, err := rdb.Get(ctx, tileName).Result()
		if err != redis.Nil {
			if err == nil {

				// Tile loading
				w.Write([]byte(tile))
				return
			} else {
				log.Printf("Redis Get для %s завершился ошибкой: %v\n", tileName, err)
			}
		}

		// Load tile via openstreetmap.org

		randomOSMURL := func(x, y, z string) string {
			osm_url := []string{
				fmt.Sprintf("https://tile.openstreetmap.org/%s/%s/%s.png", z, x, y),
				fmt.Sprintf("https://a.tile.openstreetmap.org/%s/%s/%s.png", z, x, y),
				fmt.Sprintf("https://b.tile.openstreetmap.org/%s/%s/%s.png", z, x, y),
				fmt.Sprintf("https://c.tile.openstreetmap.org/%s/%s/%s.png", z, x, y),
			}
			return osm_url[rand.Intn(len(osm_url))]
		}

		client := resty.New()

		client.SetHeaders(map[string]string{
			"User-Agent": "OSM-Viewer/1.0 (contact@example.com)",
		})

		url := randomOSMURL(x, y, z)
		resp, err := client.R().Get(url)

		if err != nil {
			w.WriteHeader(http.StatusNotFound)
			w.Write([]byte(err.Error()))
		}

		pipeline := rdb.Pipeline()
		pipeline.Set(ctx, tileName, resp.Body(), 0)

		if _, err := pipeline.Exec(ctx); err != nil {
			log.Printf("Ошибка pipeline: %v", err)
		}

		w.Write([]byte(resp.Body()))
	})

	log.Print("Serve on :8080")
	log.Fatal(http.ListenAndServe(":8080", r))
}
