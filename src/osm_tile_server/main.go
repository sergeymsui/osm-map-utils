package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
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
			fmt.Println("Not found ", tileName)

			if err == nil {
				w.Write([]byte(tile))
				return
			} else {
				log.Printf("Redis Get для %s завершился ошибкой: %v\n", tileName, err)
			}

			w.WriteHeader(http.StatusNotFound)
		}
	})

	log.Print("Serve on :8080")
	log.Fatal(http.ListenAndServe(":8080", r))
}
